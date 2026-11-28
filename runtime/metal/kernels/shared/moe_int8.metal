// The MoE experts' prefill passes on int8 activations (ops/MoE.cpp): the dense prefill's int8 tile
// (kernels/common/gguf_prefill_int8_tile.h) over the grouping's tiles (kernels/shared/moe.metal), each tile's expert
// reached as the staged passes reach it (moe_gguf_segment), in af4g64 or af5g64 (quant_moe_int8_format).
#include "metal/abi/MoE.h"
#include "metal/kernels/common/gguf_prefill_int8_tile.h"
#include "metal/kernels/common/moe_expert_slab.h"

#include <metal_stdlib>
using namespace metal;

// Copies each grouped row's codes and scales from its chunk row's, so every expert tile is a dense matrix of its
// live rows. Threadgroup (tile, part) caches the tile's source row indices once in threadgroup memory, copies the
// part's 256 codes of the tile's rows with 16-byte coalesced vectors, and copies its four 64-input groups' scales
// with one simdgroup per group so grouped_scales writes are fully coalesced across consecutive grouped rows.
kernel void moe_gather_int8(device const char *codes [[buffer(0)]], device const float2 *scales [[buffer(1)]],
                            device const uint *grouped_routes [[buffer(2)]],
                            device const MoeTileDescriptor *tiles [[buffer(3)]],
                            device const uint *tile_count [[buffer(4)]], device char *grouped_codes [[buffer(5)]],
                            device float2 *grouped_scales [[buffer(6)]],
                            constant MoeGatherInt8Params &p [[buffer(7)]],
                            uint2 group [[threadgroup_position_in_grid]],
                            uint thread_index [[thread_index_in_threadgroup]]) {
  const uint t = moe_first_tile(tile_count, p.tiles) + group.x;
  if (t >= moe_end_tile(tile_count, p.tiles)) return;
  const MoeTileDescriptor tile = tiles[t];
  threadgroup uint src_rows[GGUF_PREFILL_INT8_ROWS];
  if (thread_index < tile.rows) {
    src_rows[thread_index] = grouped_routes[tile.first_row + thread_index] / p.routes_per_row;
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  const uint lane = thread_index & 15u, column = group.y * 256u + lane * 16u;
  const uint r0 = thread_index >> 4;
  if (r0 < tile.rows) {
    const uint source = src_rows[r0];
    *reinterpret_cast<device uint4 *>(grouped_codes + ulong(tile.first_row + r0) * p.input_size + column) =
        *reinterpret_cast<device const uint4 *>(codes + ulong(source) * p.input_size + column);
  }
  const uint r1 = r0 + 16u;
  if (r1 < tile.rows) {
    const uint source = src_rows[r1];
    *reinterpret_cast<device uint4 *>(grouped_codes + ulong(tile.first_row + r1) * p.input_size + column) =
        *reinterpret_cast<device const uint4 *>(codes + ulong(source) * p.input_size + column);
  }
  if (thread_index < 128u) {
    const uint r = thread_index & 31u;
    if (r < tile.rows) {
      const uint g = group.y * 4u + (thread_index >> 5);
      grouped_scales[ulong(g) * p.routes + tile.first_row + r] = scales[ulong(g) * p.rows + src_rows[r]];
    }
  }
}

// An expert pass of the grouping's tiles: threadgroup (x, y) computes column tile x of tile moe_first_tile + y with
// its expert's weights, the tile's rows (at most GGUF_PREFILL_INT8_ROWS, the grouping's tile_rows) as the dense tile's
// one row tile, its sums times its expert's scale of the projection (moe_expert_scale). The up pass (EpUpWithGate)
// multiplies by the gate the gate pass wrote to `output`, each element in place: the thread that writes an element
// has read its gate there.
template <int BITS, GgufEpilogue Ep, uint Shared, uint Projection>
kernel void moe_expert_int8(device const char *codes [[buffer(0)]], device const float2 *scales [[buffer(1)]],
                            device const MoeTileDescriptor *tiles [[buffer(2)]],
                            device const uint *tile_count [[buffer(3)]], device uchar *sw0 [[buffer(4)]],
                            device uchar *sw1 [[buffer(5)]], device uchar *smeta [[buffer(6)]],
                            device bfloat *output [[buffer(7)]], device const uint *slots [[buffer(8)]],
                            device const float *expert_scales [[buffer(9)]],
                            constant MoeInt8ExpertParams &p [[buffer(10)]], constant ulong *chunks [[buffer(11)]],
                            uint2 group [[threadgroup_position_in_grid]],
                            ushort lane [[thread_index_in_simdgroup]],
                            ushort simd_group [[simdgroup_index_in_threadgroup]]) {
  const uint t = moe_first_tile(tile_count, p.tiles) + group.y;
  if (t >= moe_end_tile(tile_count, p.tiles)) return;
  const MoeTileDescriptor tile = tiles[t];
  const MoeGgufSegment s =
      moe_gguf_segment<Shared>(tile.expert, p.experts, p.input_size, p.output_size, p.routed_format, p.shared_format,
                               slots, chunks, p.floor_slots, p.chunk_slots, Projection, sw0, sw1, smeta);
  const ulong out = ulong(tile.first_row) * p.output_size;
  prefill_int8_tile<BITS, Ep>(codes + ulong(tile.first_row) * p.input_size, scales + tile.first_row, s.w0, s.w1,
                              s.meta, output + out, output + out,
                              {p.input_size, tile.rows, p.routes, p.output_size, 0, p.input_size},
                              uint2(group.x, 0), lane, simd_group,
                              moe_expert_scale(expert_scales, tile.expert, p.experts, Projection));
}

// Fused gate + up expert pass: simdgroup 0 computes gate (projection 0) and
// simdgroup 1 computes up (projection 1) on the same 32-column tile, sharing
// L1 activation reads and combining silu(gate) * up via 2 KiB of threadgroup
// memory without round-tripping the intermediate buffer to device memory.
template <int BITS, uint Shared>
kernel void moe_expert_int8_gate_up(device const char *codes [[buffer(0)]], device const float2 *scales [[buffer(1)]],
                                    device const MoeTileDescriptor *tiles [[buffer(2)]],
                                    device const uint *tile_count [[buffer(3)]], device uchar *gsw0 [[buffer(4)]],
                                    device uchar *gsw1 [[buffer(5)]], device uchar *gsmeta [[buffer(6)]],
                                    device uchar *usw0 [[buffer(7)]], device uchar *usw1 [[buffer(8)]],
                                    device uchar *usmeta [[buffer(9)]], device bfloat *output [[buffer(10)]],
                                    device const uint *slots [[buffer(11)]],
                                    device const float *expert_scales [[buffer(12)]],
                                    constant MoeInt8GateUpParams &p [[buffer(13)]], constant ulong *chunks [[buffer(14)]],
                                    uint2 group [[threadgroup_position_in_grid]],
                                    ushort lane [[thread_index_in_simdgroup]],
                                    ushort simd_group [[simdgroup_index_in_threadgroup]]) {
  threadgroup bfloat park[kInt8RowFrags * kInt8Elements * 32];
  const uint t = moe_first_tile(tile_count, p.tiles) + group.y;
  if (t >= moe_end_tile(tile_count, p.tiles)) return;
  const MoeTileDescriptor tile = tiles[t];
  const bool up = simd_group == 1;
  const MoeGgufSegment s =
      up ? moe_gguf_segment<Shared>(tile.expert, p.experts, p.input_size, p.output_size, p.up_routed_format,
                                    p.up_shared_format, slots, chunks, p.floor_slots, p.chunk_slots, 1, usw0, usw1,
                                    usmeta)
         : moe_gguf_segment<Shared>(tile.expert, p.experts, p.input_size, p.output_size, p.gate_routed_format,
                                    p.gate_shared_format, slots, chunks, p.floor_slots, p.chunk_slots, 0, gsw0, gsw1,
                                    gsmeta);
  const float scale = moe_expert_scale(expert_scales, tile.expert, p.experts, up ? 1 : 0);
  const ulong out = ulong(tile.first_row) * p.output_size;
  const PrefillInt8Shape shape{p.input_size, tile.rows, p.routes, p.output_size, 0, p.input_size};
  const int col_base = int(group.x) * kInt8FragN;
  float cf[kInt8RowFrags][kInt8Elements];
  prefill_int8_accum<BITS>(codes + ulong(tile.first_row) * p.input_size, scales + tile.first_row, s.w0, s.w1, s.meta,
                           shape, 0, col_base, lane, cf);
  const short2 coord = prefill_int8_coord(lane);
  const int m_base = coord.y;
  const int frags = int(tile.rows) > kInt8FragM ? kInt8RowFrags : 1;
  if (!up) {
    for (int i = 0; i < frags; ++i)
#pragma unroll
      for (int e = 0; e < kInt8Elements; ++e)
        park[(i * kInt8Elements + e) * 32 + lane] = bfloat(cf[i][e] * scale);
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (up) {
    const uint n_run = uint(col_base + coord.x);
    for (int i = 0; i < frags; ++i)
#pragma unroll
      for (int e = 0; e < kInt8Elements; ++e) {
        const int m = m_base + i * kInt8FragM + ((e & 7) >> 2) * 8;
        if (m >= int(tile.rows)) continue;
        const ulong o = out + ulong(m) * p.output_size + n_run + (e & 3) + 16 * (e >> 3);
        const float gate_v = float(park[(i * kInt8Elements + e) * 32 + lane]);
        const float up_v = float(bfloat(cf[i][e] * scale));
        output[o] = bfloat(up_v * splash_silu(gate_v));
      }
  }
}

using MoeExpertInt8Kernel = void(device const char *, device const float2 *, device const MoeTileDescriptor *,
                                 device const uint *, device uchar *, device uchar *, device uchar *, device bfloat *,
                                 device const uint *, device const float *, constant MoeInt8ExpertParams &,
                                 constant ulong *, uint2, ushort, ushort);
using MoeExpertInt8GateUpKernel = void(device const char *, device const float2 *, device const MoeTileDescriptor *,
                                       device const uint *, device uchar *, device uchar *, device uchar *,
                                       device uchar *, device uchar *, device uchar *, device bfloat *,
                                       device const uint *, device const float *, constant MoeInt8GateUpParams &,
                                       constant ulong *, uint2, ushort, ushort);
// moe_expert_int8_<format>_<pass><slices suffix>: the gate (plain), up (times the gate's SiLU), fused gate_up, and down passes.
#define MOE_EXPERT_INT8(B, f, Shared, suffix)                                                                         \
  template [[host_name("moe_expert_int8_" #f "_gate" suffix)]] kernel MoeExpertInt8Kernel                            \
      moe_expert_int8<B, EpNone, Shared, 0>;                                                                         \
  template [[host_name("moe_expert_int8_" #f "_up" suffix)]] kernel MoeExpertInt8Kernel                              \
      moe_expert_int8<B, EpUpWithGate, Shared, 1>;                                                                   \
  template [[host_name("moe_expert_int8_" #f "_gate_up" suffix)]] kernel MoeExpertInt8GateUpKernel                   \
      moe_expert_int8_gate_up<B, Shared>;                                                                            \
  template [[host_name("moe_expert_int8_" #f "_down" suffix)]] kernel MoeExpertInt8Kernel                            \
      moe_expert_int8<B, EpNone, Shared, 2>;
MOE_EXPERT_INT8(2, q20, 1, "")
MOE_EXPERT_INT8(4, af4g64, 1, "")
MOE_EXPERT_INT8(5, af5g64, 1, "")
MOE_EXPERT_INT8(2, q20, 2, "_s2")
MOE_EXPERT_INT8(4, af4g64, 2, "_s2")
MOE_EXPERT_INT8(5, af5g64, 2, "_s2")
#undef MOE_EXPERT_INT8
