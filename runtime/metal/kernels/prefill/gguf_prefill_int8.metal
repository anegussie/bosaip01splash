// Int8-activation prefill GEMMs for MLX affine 4- and 5-bit weights in groups of 64 (af4g64, af5g64) and for Q8_0
// (ops::LinearTile::GgufPrefillInt8). Each 64-input group g of a chunk row is quantized to int8 codes qa with its own
// scale sa_g, and with w = s * q + z per affine weight group:
//
//   y[m][n] = sum_g ( (sa_g[m] s_g[n]) sum_{k in g} qa[m][k] q[n][k]  +  z_g[n] (sa_g[m] sum_{k in g} qa[m][k]) )
//
// and with w = d * q per Q8_0 32-group h of g (its codes int8 already):
//
//   y[m][n] = sum_g sa_g[m] sum_{h < 2} d_{g,h}[n] sum_{k in h} qa[m][k] q[n][k]
//
// The weights' codes feed int8 16x32x16 matmul2d fragments straight from the planes; each group's int32 sums (each
// Q8_0 32-group's) fold into fp32 once. The weights are exact; only the activations round, per row and group.
//
// The fragment schedule and the activations' slot order are adapted from oMLX's oQ A8 kernel (Apache-2.0 notice in
// THIRD_PARTY_NOTICES): in fragment step t (0-3) of a group, lane column x (coord.x / 4) supplies inputs
// 16x + 4t .. 16x + 4t + 3, 32-group x >> 1, chunk 2 (x & 1) + (t >> 1) of the planes (each weight column's 16 codes
// of the lane are one uint2 of its 4-bit plane), nibbles (word >> 4 (t & 1)) & 0x0f0f0f0f: chunk slots {0, 4, 1, 5}
// or {2, 6, 3, 7} (metal/abi/QuantFormat.h). The quantizer writes each 32-group in that order. Q8_0's tile reads the
// same codes in another schedule, so that a fused projection of both quantizes its rows once: steps 2h and 2h + 1
// take 32-group h alone, lane column x the inputs at 32h + 8x + 4 (t & 1) .. +3, chunk x of the 32-group's plane
// record (one uint2 of its bytes, chunk slots {0, 4, 1, 5} from it in the even step, {2, 6, 3, 7} in the odd one).
#include "metal/abi/Gguf.h"
#include "metal/abi/QuantTables.h"
#include "metal/kernels/common/gguf_prefill_int8_tile.h"
#include "metal/kernels/common/gguf_tile.h"
#include "metal/kernels/common/int8_activations.h"

#include <MetalPerformancePrimitives/MetalPerformancePrimitives.h>
#include <metal_stdlib>
using namespace metal;

// grid (groups / GGUF_PREFILL_INT8_QUANTIZE_SIMDGROUPS, rows): simdgroup s of threadgroup (b, row) quantizes group
// b * GGUF_PREFILL_INT8_QUANTIZE_SIMDGROUPS + s of the row by the int8-activation rule
// (kernels/common/int8_activations.h), loading 64 bfloats as 32 coalesced bfloat2s, packing the
// prefill_int8_position(quant_slot(e)) permutation in registers with one simd_shuffle_xor(p16, 8), and writing 16
// coalesced uints (64 bytes) to codes.
kernel void gguf_prefill_int8_quantize(device const bfloat *input [[buffer(0)]], device char *codes [[buffer(1)]],
                                       device float2 *scales [[buffer(2)]],
                                       constant GgufPrefillInt8QuantizeParams &p [[buffer(3)]],
                                       uint2 tid [[threadgroup_position_in_grid]],
                                       ushort lane [[thread_index_in_simdgroup]],
                                       ushort simd_group [[simdgroup_index_in_threadgroup]]) {
  const uint g = tid.x * GGUF_PREFILL_INT8_QUANTIZE_SIMDGROUPS + simd_group, row = tid.y;
  if (g >= p.input_size / GGUF_PREFILL_INT8_GROUP || row >= p.rows) return;
  const ulong at = ulong(row) * p.input_size + g * GGUF_PREFILL_INT8_GROUP;
  const bfloat2 bf = reinterpret_cast<device const bfloat2 *>(input + at)[lane];
  const float x0 = float(bf.x), x1 = float(bf.y);
  const Int8Block block = int8_activation_block(simd_max(max(fabs(x0), fabs(x1))));
  const int q0 = int8_activation_code(x0, block.inverse), q1 = int8_activation_code(x1, block.inverse);
  const uint p16 = (uint(uchar(q0)) & 0xFFu) | ((uint(uchar(q1)) & 0xFFu) << 16);
  const uint partner = simd_shuffle_xor(p16, 8);
  const uint h = lane >> 4, sub = lane & 15u;
  if (sub < 8u) {
    reinterpret_cast<device uint *>(codes + at)[h * 8u + sub] = p16 | (partner << 8);
  }
  const int sum = simd_sum(q0 + q1);
  const bool finite = simd_all(!int8_activation_not_finite(bf.x) && !int8_activation_not_finite(bf.y));
  if (lane != 0) return;
  ((device uint2 *)scales)[ulong(g) * p.storage_rows + row] =
      uint2(int8_activation_bits(block.scale, finite), int8_activation_bits(block.scale * float(sum), finite));
}

// The (column tile, row tile) of tile index `at` of grid.x column tiles by grid.y row tiles:
// GGUF_PREFILL_INT8_WALK row tiles take each column tile in turn before the next column tile, the last block of row
// tiles its remainder.
inline uint2 prefill_int8_walk(uint at, uint2 grid) {
  constexpr uint S = GGUF_PREFILL_INT8_WALK;
  const uint block = at / (S * grid.x), height = min(S, grid.y - block * S), i = at - block * S * grid.x;
  return uint2(i / height, block * S + i % height);
}

// grid (GGUF_PREFILL_INT8_WALK, its tiles / GGUF_PREFILL_INT8_WALK rounded up), GGUF_PREFILL_INT8_THREADS threads:
// threadgroup (x, y) takes tile index y GGUF_PREFILL_INT8_WALK + x of the segment's column tiles by the chunk's row
// tiles of GGUF_PREFILL_INT8_ROWS (prefill_int8_walk), and those past the tiles none. A run of 16 threadgroups along
// x is so one column tile's row tiles of a block, whatever the column count; a grid of (column tiles, row tiles)
// kept them together only where the column tiles were a multiple of 16 (M6: 260 column tiles took 29% longer than
// 256 at 2048 rows). aux (buffer 6) is the residual or the gate, the output for the plain epilogue, which reads none.
#define GGUF_PREFILL_INT8_KERNEL(B, f, ep, Ep)                                                                         \
  kernel void gguf_prefill_int8_##f##_##ep(                                                                            \
      device const char *codes [[buffer(0)]], device const float2 *scales [[buffer(1)]],                               \
      device const uchar *w0 [[buffer(2)]], device const uchar *w1 [[buffer(3)]],                                      \
      device const uchar *meta [[buffer(4)]], device bfloat *output [[buffer(5)]],                                     \
      device const bfloat *aux [[buffer(6)]], constant GgufPrefillInt8Params &p [[buffer(7)]],                         \
      uint2 tid [[threadgroup_position_in_grid]], ushort lane [[thread_index_in_simdgroup]],                           \
      ushort simd_group [[simdgroup_index_in_threadgroup]]) {                                                          \
    const uint rows = (p.rows + GGUF_PREFILL_INT8_ROWS - 1) / GGUF_PREFILL_INT8_ROWS,                                  \
               at = tid.y * GGUF_PREFILL_INT8_WALK + tid.x;                                                            \
    if (at >= p.column_tiles * rows) return;                                                                           \
    prefill_int8_tile<B, Ep>(codes, scales, w0, w1, meta, output, aux,                                                 \
                             {p.input_size, p.rows, p.storage_rows, p.out_stride, p.out_offset, p.plane_input_size},    \
                             prefill_int8_walk(at, uint2(p.column_tiles, rows)), lane, simd_group);                    \
  }
// 128-row x 64-column double-buffered threadgroup-staged INT8 prefill for Q3_K: 8 simdgroups (256 threads = 4
// row-slices x 2 col-slices) cooperatively unpack 64x64 Q3_K weights into w_stage[2][16][64] (8 KiB, 1 barrier per
// 64-group, bank-conflict-free across columns), then run hardware int8 matmul2d straight from threadgroup memory.
template <GgufEpilogue Ep>
inline void prefill_int8_q3k_staged128(device const char *codes, device const float2 *scales, device const uchar *w0,
                                       device const uchar *w1, device const uchar *meta, device bfloat *output,
                                       device const bfloat *aux, PrefillInt8Shape p, uint2 tile, ushort lane,
                                       ushort simd_group, threadgroup uint (*w_stage)[16][64],
                                       threadgroup float (*d_stage)[64]) {
  using namespace mpp::tensor_ops;
  constexpr uint T = QUANT_TILE_ROWS;
  const int K = int(p.input_size), M = int(p.rows), groups = K / GGUF_PREFILL_INT8_GROUP;
  const uint plane_groups32 = p.plane_input_size / 32, plane_meta = plane_groups32 / 8;
  const ushort row_sg = simd_group >> 1, col_sg = simd_group & 1;
  const int row_base = int(tile.y) * 128 + int(row_sg) * 32;
  const int tile_col = int(tile.x) * GGUF_TILE_COLUMNS;
  const short2 coord = prefill_int8_coord(lane);
  const int cx = coord.x >> 2;
  const int m_base = row_base + coord.y;

  constexpr auto desc = matmul2d_descriptor(kInt8FragM, kInt8FragN, kInt8FragK, false, true, false,
                                            matmul2d_descriptor::mode::multiply_accumulate);
  constexpr auto desc_set = matmul2d_descriptor(kInt8FragM, kInt8FragN, kInt8FragK, false, true, false,
                                                matmul2d_descriptor::mode::multiply);
  matmul2d<desc, execution_simdgroup> op;
  matmul2d<desc_set, execution_simdgroup> op_set;
  auto ct_a = op.template get_left_input_cooperative_tensor<int8_t, int8_t, int32_t>();
  auto ct_b = op.template get_right_input_cooperative_tensor<int8_t, int8_t, int32_t>();
  auto acc0 = op.template get_destination_cooperative_tensor<decltype(ct_a), decltype(ct_b), int32_t>();
  auto acc1 = op.template get_destination_cooperative_tensor<decltype(ct_a), decltype(ct_b), int32_t>();

  float cf[kInt8RowFrags][kInt8Elements];
#pragma unroll
  for (int i = 0; i < kInt8RowFrags; ++i)
#pragma unroll
    for (int e = 0; e < kInt8Elements; ++e) cf[i][e] = 0.0f;

  // Cooperative unpack mapping: 256 threads = 64 columns x 4 cx slots.
  const uint tid = uint(simd_group) * 32u + uint(lane);
  const uint u_col = tid & 63u;
  const uint u_cx = tid >> 6;
  const uint u_h32 = u_cx >> 1;
  const uint u_n = uint(tile_col) + u_col;
  const ulong u_rec0 = ulong(u_n / T) * plane_groups32 * T + (u_n % T);
  device const uchar *wq3_0 = w0 + u_rec0 * 8 + 4 * (u_cx & 1u);
  device const uchar *wq3_1 = w1 + u_rec0 * 4 + 2 * (u_cx & 1u);
  device const uint4 *mq3 = (device const uint4 *)(meta) + ulong(u_n / T) * plane_meta * T + (u_n % T);
  const int col_base_local = int(col_sg) * kInt8FragN + coord.y;
  const int d_local = int(col_sg) * kInt8FragN + coord.x;

  const int superblocks = groups >> 2;
  for (int sb = 0; sb < superblocks; ++sb) {
    const uint4 mt = mq3[ulong(sb) * T];
    const uint dbuf = uint(sb & 1);
    if (u_cx == 0u) d_stage[dbuf][u_col] = -float(as_type<half>(ushort(mt.x & 0xFFFFu)));
#pragma unroll
    for (int g4 = 0; g4 < 4; ++g4) {
      const int g = sb * 4 + g4;
      const uint buf = uint(g & 1);
      const ulong g32 = ulong(2 * g + int(u_h32)) * T;
      const uint wv0 = *((device const uint *)(wq3_0 + g32 * 8));
      const ushort wv1 = *((device const ushort *)(wq3_1 + g32 * 4));
      const uint t0 = mt.y, t1 = mt.z, t2 = mt.w;
      uint aux_sc;
      if (g4 == 0) aux_sc = (t0 & 0x0f0f0f0fu) | (((t2 >> 0) & 0x03030303u) << 4);
      else if (g4 == 1) aux_sc = (t1 & 0x0f0f0f0fu) | (((t2 >> 2) & 0x03030303u) << 4);
      else if (g4 == 2) aux_sc = ((t0 >> 4) & 0x0f0f0f0fu) | (((t2 >> 4) & 0x03030303u) << 4);
      else aux_sc = ((t1 >> 4) & 0x0f0f0f0fu) | (((t2 >> 6) & 0x03030303u) << 4);
      const uint pair = aux_sc >> (16u * u_h32);
      const short s0 = short(32) - short(pair & 0xFFu);
      const short s1 = short(32) - short((pair >> 8) & 0xFFu);
#pragma unroll
      for (int t = 0; t < 4; ++t) {
        const uint lo = wv0 >> (16u * (t >> 1));
        const ushort hi = wv1 >> (8u * (t >> 1));
        const uint u_lo = 4u * (t & 1), u_hi = 2u * (t & 1);
        const short q0 = short(((lo >> (u_lo + 0)) & 3u) | (((hi >> (u_hi + 0)) & 1u) << 2)) - short(4);
        const short q4 = short(((lo >> (u_lo + 8)) & 3u) | (((hi >> (u_hi + 4)) & 1u) << 2)) - short(4);
        const short q1 = short(((lo >> (u_lo + 2)) & 3u) | (((hi >> (u_hi + 1)) & 1u) << 2)) - short(4);
        const short q5 = short(((lo >> (u_lo + 10)) & 3u) | (((hi >> (u_hi + 5)) & 1u) << 2)) - short(4);
        const char4 quad(int8_t(s0 * q0), int8_t(s1 * q4), int8_t(s0 * q1), int8_t(s1 * q5));
        w_stage[buf][u_cx * 4u + uint(t)][u_col] = as_type<uint>(quad);
      }
      threadgroup_barrier(mem_flags::mem_threadgroup);
#pragma unroll
      for (int t = 0; t < 4; ++t) {
        const uint row_idx = uint(cx * 4 + t);
#pragma unroll
        for (int q = 0; q < 4; ++q) {
          const char4 quad = as_type<char4>(w_stage[buf][row_idx][col_base_local + (q & 1) * 8 + (q >> 1) * 16]);
          const int base = (q >> 1) * 8 + (q & 1) * 4;
          ct_b[base + 0] = quad.x; ct_b[base + 1] = quad.y; ct_b[base + 2] = quad.z; ct_b[base + 3] = quad.w;
        }
#pragma unroll
        for (int hf = 0; hf < kInt8RowFrags; ++hf) {
#pragma unroll
          for (int r = 0; r < 2; ++r) {
            const int m = min(m_base + hf * kInt8FragM + r * 8, M - 1);
            const ulong at = ulong(m) * K + g * GGUF_PREFILL_INT8_GROUP + cx * 16 + t * 4;
            const char4 quad = as_type<char4>(*((device const uint *)(codes + at)));
            ct_a[r * 4 + 0] = quad.x; ct_a[r * 4 + 1] = quad.y; ct_a[r * 4 + 2] = quad.z; ct_a[r * 4 + 3] = quad.w;
          }
          if (t == 0) { if (hf == 0) op_set.run(ct_a, ct_b, acc0); else op_set.run(ct_a, ct_b, acc1); }
          else { if (hf == 0) op.run(ct_a, ct_b, acc0); else op.run(ct_a, ct_b, acc1); }
        }
      }
      float sa[kInt8RowFrags][2];
#pragma unroll
      for (int i = 0; i < kInt8RowFrags; ++i)
#pragma unroll
        for (int r = 0; r < 2; ++r)
          sa[i][r] = scales[ulong(g) * p.storage_rows + min(m_base + i * kInt8FragM + r * 8, M - 1)].x;
#pragma unroll
      for (int e = 0; e < kInt8Elements; ++e) {
        const int r = (e & 7) >> 2;
        const float d = d_stage[dbuf][d_local + (e & 3) + 16 * (e >> 3)];
        cf[0][e] = fma(sa[0][r] * d, float(acc0[e]), cf[0][e]);
        cf[1][e] = fma(sa[1][r] * d, float(acc1[e]), cf[1][e]);
      }
    }
  }
  const uint n_run = uint(tile_col + int(col_sg) * kInt8FragN + coord.x);
#pragma unroll
  for (int i = 0; i < kInt8RowFrags; ++i)
#pragma unroll
    for (int e = 0; e < kInt8Elements; ++e) {
      const int m = m_base + i * kInt8FragM + ((e & 7) >> 2) * 8;
      if (m >= M) continue;
      const ulong o = ulong(m) * p.out_stride + p.out_offset + n_run + (e & 3) + 16 * (e >> 3);
      output[o] = gguf_epilogue<Ep>(cf[i][e], aux, o);
    }
}

#define GGUF_PREFILL_INT8_Q3K_KERNEL(ep, Ep)                                                                           \
  kernel void gguf_prefill_int8_q3k_##ep(                                                                              \
      device const char *codes [[buffer(0)]], device const float2 *scales [[buffer(1)]],                               \
      device const uchar *w0 [[buffer(2)]], device const uchar *w1 [[buffer(3)]],                                      \
      device const uchar *meta [[buffer(4)]], device bfloat *output [[buffer(5)]],                                     \
      device const bfloat *aux [[buffer(6)]], constant GgufPrefillInt8Params &p [[buffer(7)]],                         \
      uint2 tid [[threadgroup_position_in_grid]], ushort lane [[thread_index_in_simdgroup]],                           \
      ushort simd_group [[simdgroup_index_in_threadgroup]]) {                                                          \
    threadgroup uint w_stage[2][16][64];                                                                               \
    threadgroup float d_stage[2][64];                                                                                  \
    const uint rows = (p.rows + 127u) / 128u, at = tid.y * GGUF_PREFILL_INT8_WALK + tid.x;                             \
    if (at >= p.column_tiles * rows) return;                                                                           \
    prefill_int8_q3k_staged128<Ep>(codes, scales, w0, w1, meta, output, aux,                                           \
                                   {p.input_size, p.rows, p.storage_rows, p.out_stride, p.out_offset,                  \
                                    p.plane_input_size},                                                               \
                                   prefill_int8_walk(at, uint2(p.column_tiles, rows)), lane, simd_group, w_stage,      \
                                   d_stage);                                                                           \
  }
GGUF_PREFILL_INT8_Q3K_KERNEL(a, EpNone)
GGUF_PREFILL_INT8_Q3K_KERNEL(r, EpResidual)
GGUF_PREFILL_INT8_Q3K_KERNEL(g, EpUpWithGate)
#undef GGUF_PREFILL_INT8_Q3K_KERNEL

// 128-row x 64-column double-buffered threadgroup-staged INT8 prefill for IQ4_XS: 8 simdgroups (256 threads)
// cooperatively look up kIQ4NLValues (cached in 16-byte threadgroup LUT) into w_stage[2][8][64] (4 KiB, 1 barrier
// per 32-group, Q8_0 schedule), folding d * (ls - 32) once per 32-group.
template <GgufEpilogue Ep>
inline void prefill_int8_iq4xs_staged128(device const char *codes, device const float2 *scales, device const uchar *w0,
                                         device const uchar *meta, device bfloat *output, device const bfloat *aux,
                                         PrefillInt8Shape p, uint2 tile, ushort lane, ushort simd_group,
                                         threadgroup uint (*w_stage)[8][64], threadgroup float (*d_stage)[64],
                                         threadgroup int8_t *iq_lut) {
  using namespace mpp::tensor_ops;
  constexpr uint T = QUANT_TILE_ROWS;
  const int K = int(p.input_size), M = int(p.rows), groups = K / GGUF_PREFILL_INT8_GROUP;
  const uint plane_groups32 = p.plane_input_size / 32, plane_meta = plane_groups32 / 8;
  const ushort row_sg = simd_group >> 1, col_sg = simd_group & 1;
  const int row_base = int(tile.y) * 128 + int(row_sg) * 32;
  const int tile_col = int(tile.x) * GGUF_TILE_COLUMNS;
  const short2 coord = prefill_int8_coord(lane);
  const int cx = coord.x >> 2;
  const int m_base = row_base + coord.y;

  const uint tid = uint(simd_group) * 32u + uint(lane);
  if (tid < 16u) iq_lut[tid] = kIQ4NLValues[tid];
  threadgroup_barrier(mem_flags::mem_threadgroup);

  constexpr auto desc = matmul2d_descriptor(kInt8FragM, kInt8FragN, kInt8FragK, false, true, false,
                                            matmul2d_descriptor::mode::multiply_accumulate);
  constexpr auto desc_set = matmul2d_descriptor(kInt8FragM, kInt8FragN, kInt8FragK, false, true, false,
                                                matmul2d_descriptor::mode::multiply);
  matmul2d<desc, execution_simdgroup> op;
  matmul2d<desc_set, execution_simdgroup> op_set;
  auto ct_a = op.template get_left_input_cooperative_tensor<int8_t, int8_t, int32_t>();
  auto ct_b = op.template get_right_input_cooperative_tensor<int8_t, int8_t, int32_t>();
  auto acc0 = op.template get_destination_cooperative_tensor<decltype(ct_a), decltype(ct_b), int32_t>();
  auto acc1 = op.template get_destination_cooperative_tensor<decltype(ct_a), decltype(ct_b), int32_t>();

  float cf[kInt8RowFrags][kInt8Elements];
#pragma unroll
  for (int i = 0; i < kInt8RowFrags; ++i)
#pragma unroll
    for (int e = 0; e < kInt8Elements; ++e) cf[i][e] = 0.0f;

  const uint u_col = tid & 63u;
  const uint u_cx = tid >> 6;
  const uint u_n = uint(tile_col) + u_col;
  const ulong u_rec0 = ulong(u_n / T) * plane_groups32 * T + (u_n % T);
  device const uchar *wq = w0 + u_rec0 * 16 + 4 * u_cx;
  device const uint2 *miq = (device const uint2 *)(meta) + ulong(u_n / T) * plane_meta * T + (u_n % T);
  const int col_base_local = int(col_sg) * kInt8FragN + coord.y;
  const int d_local = int(col_sg) * kInt8FragN + coord.x;

  const int superblocks = groups >> 2;
  for (int sb = 0; sb < superblocks; ++sb) {
    const uint2 mt = miq[ulong(sb) * T];
    const float d_sb = float(as_type<half>(ushort(mt.x & 0xFFFFu)));
#pragma unroll
    for (int g4 = 0; g4 < 4; ++g4) {
      const int g = sb * 4 + g4;
      float sa[kInt8RowFrags][2];
#pragma unroll
      for (int i = 0; i < kInt8RowFrags; ++i)
#pragma unroll
        for (int r = 0; r < 2; ++r)
          sa[i][r] = scales[ulong(g) * p.storage_rows + min(m_base + i * kInt8FragM + r * 8, M - 1)].x;
#pragma unroll
      for (int h = 0; h < 2; ++h) {
        const uint j = uint((g4 << 1) | h);
        const uint hbuf = uint(h);
        const ulong g32 = ulong(2 * g + h) * T;
        const uint wv = *((device const uint *)(wq + g32 * 16));
#pragma unroll
        for (int t = 0; t < 2; ++t) {
          const uint s = wv >> (8u * t);
          const char4 quad(iq_lut[s & 0xFu], iq_lut[(s >> 16) & 0xFu], iq_lut[(s >> 4) & 0xFu],
                           iq_lut[(s >> 20) & 0xFu]);
          w_stage[hbuf][u_cx * 2u + uint(t)][u_col] = as_type<uint>(quad);
        }
        if (u_cx == 0u) {
          const int ls = int((mt.y >> (4u * j)) & 0xFu) | int((((mt.x >> 16) >> (2u * j)) & 3u) << 4);
          d_stage[hbuf][u_col] = d_sb * float(ls - 32);
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
#pragma unroll
        for (int t = 0; t < 2; ++t) {
          const uint row_idx = uint(cx * 2 + t);
#pragma unroll
          for (int q = 0; q < 4; ++q) {
            const char4 quad = as_type<char4>(w_stage[hbuf][row_idx][col_base_local + (q & 1) * 8 + (q >> 1) * 16]);
            const int base = (q >> 1) * 8 + (q & 1) * 4;
            ct_b[base + 0] = quad.x; ct_b[base + 1] = quad.y; ct_b[base + 2] = quad.z; ct_b[base + 3] = quad.w;
          }
#pragma unroll
          for (int hf = 0; hf < kInt8RowFrags; ++hf) {
#pragma unroll
            for (int r = 0; r < 2; ++r) {
              const int m = min(m_base + hf * kInt8FragM + r * 8, M - 1);
              const ulong at = ulong(m) * K + g * GGUF_PREFILL_INT8_GROUP + 32 * h + cx * 8 + t * 4;
              const char4 quad = as_type<char4>(*((device const uint *)(codes + at)));
              ct_a[r * 4 + 0] = quad.x; ct_a[r * 4 + 1] = quad.y; ct_a[r * 4 + 2] = quad.z; ct_a[r * 4 + 3] = quad.w;
            }
            if (t == 0) { if (hf == 0) op_set.run(ct_a, ct_b, acc0); else op_set.run(ct_a, ct_b, acc1); }
            else { if (hf == 0) op.run(ct_a, ct_b, acc0); else op.run(ct_a, ct_b, acc1); }
          }
        }
#pragma unroll
        for (int e = 0; e < kInt8Elements; ++e) {
          const int r = (e & 7) >> 2;
          const float d = d_stage[hbuf][d_local + (e & 3) + 16 * (e >> 3)];
          cf[0][e] = fma(sa[0][r] * d, float(acc0[e]), cf[0][e]);
          cf[1][e] = fma(sa[1][r] * d, float(acc1[e]), cf[1][e]);
        }
      }
    }
  }
  const uint n_run = uint(tile_col + int(col_sg) * kInt8FragN + coord.x);
#pragma unroll
  for (int i = 0; i < kInt8RowFrags; ++i)
#pragma unroll
    for (int e = 0; e < kInt8Elements; ++e) {
      const int m = m_base + i * kInt8FragM + ((e & 7) >> 2) * 8;
      if (m >= M) continue;
      const ulong o = ulong(m) * p.out_stride + p.out_offset + n_run + (e & 3) + 16 * (e >> 3);
      output[o] = gguf_epilogue<Ep>(cf[i][e], aux, o);
    }
}

#define GGUF_PREFILL_INT8_IQ4XS_KERNEL(ep, Ep)                                                                         \
  kernel void gguf_prefill_int8_iq4xs_##ep(                                                                            \
      device const char *codes [[buffer(0)]], device const float2 *scales [[buffer(1)]],                               \
      device const uchar *w0 [[buffer(2)]], device const uchar *w1 [[buffer(3)]],                                      \
      device const uchar *meta [[buffer(4)]], device bfloat *output [[buffer(5)]],                                     \
      device const bfloat *aux [[buffer(6)]], constant GgufPrefillInt8Params &p [[buffer(7)]],                         \
      uint2 tid [[threadgroup_position_in_grid]], ushort lane [[thread_index_in_simdgroup]],                           \
      ushort simd_group [[simdgroup_index_in_threadgroup]]) {                                                          \
    (void)w1;                                                                                                          \
    threadgroup uint w_stage[2][8][64];                                                                                \
    threadgroup float d_stage[2][64];                                                                                  \
    threadgroup int8_t iq_lut[16];                                                                                     \
    const uint rows = (p.rows + 127u) / 128u, at = tid.y * GGUF_PREFILL_INT8_WALK + tid.x;                             \
    if (at >= p.column_tiles * rows) return;                                                                           \
    prefill_int8_iq4xs_staged128<Ep>(codes, scales, w0, meta, output, aux,                                             \
                                     {p.input_size, p.rows, p.storage_rows, p.out_stride, p.out_offset,                \
                                      p.plane_input_size},                                                             \
                                     prefill_int8_walk(at, uint2(p.column_tiles, rows)), lane, simd_group, w_stage,    \
                                     d_stage, iq_lut);                                                                 \
  }
GGUF_PREFILL_INT8_IQ4XS_KERNEL(a, EpNone)
GGUF_PREFILL_INT8_IQ4XS_KERNEL(r, EpResidual)
GGUF_PREFILL_INT8_IQ4XS_KERNEL(g, EpUpWithGate)
#undef GGUF_PREFILL_INT8_IQ4XS_KERNEL

#define GGUF_PREFILL_INT8_FORMAT(B, f)                                                                                 \
  GGUF_PREFILL_INT8_KERNEL(B, f, a, EpNone) GGUF_PREFILL_INT8_KERNEL(B, f, r, EpResidual)                              \
  GGUF_PREFILL_INT8_KERNEL(B, f, g, EpUpWithGate)
GGUF_PREFILL_INT8_FORMAT(2, q20)
GGUF_PREFILL_INT8_FORMAT(4, af4g64)
GGUF_PREFILL_INT8_FORMAT(5, af5g64)
GGUF_PREFILL_INT8_FORMAT(8, q80)
#undef GGUF_PREFILL_INT8_FORMAT
#undef GGUF_PREFILL_INT8_KERNEL
