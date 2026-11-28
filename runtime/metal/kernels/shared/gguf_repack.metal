#pragma clang fp reassociate(off)
#include "metal/abi/GgufRepack.h"
#include "metal/abi/MoE.h"
#include "metal/kernels/common/moe_expert_chunk.h"
#include <metal_stdlib>

using namespace metal;
constant constexpr uint kPTQ1SourcePow3[5] = {1, 3, 9, 27, 81};

// ---- weight preparation: native GGUF rows -> MDGG0001 planes (metal/abi/QuantFormat.h) ----
// One thread per (row n, 32-wide K group g) of a chunk the host staged in image order.
// Word w of the little-endian string of 32 slot values of `bits` bits each (1, 2, 4 or 8).
static inline uint gguf_bit_word(thread const uchar *slots, uint bits, uint w) {
  const uint per = 32 / bits;
  uint word = 0;
  for (uint i = 0; i < per; ++i) word |= uint(slots[w * per + i]) << (bits * i);
  return word;
}
static inline void gguf_store_bits(thread const uchar *slots, uint bits, device uchar *dst) {
  for (uint w = 0; w < bits; ++w) ((device uint *)dst)[w] = gguf_bit_word(slots, bits, w);
}
// 4-bit linear codes: word c holds slots 8c..8c+7, pair p at bits 4p (e0) and 16 + 4p (e1).
static inline void gguf_store_pairs(thread const uchar *slots, device uchar *dst) {
  for (uint c = 0; c < 4; ++c) {
    uint word = 0;
    for (uint i = 0; i < 8; ++i) word |= uint(slots[8 * c + i]) << ((i & 1) * 16 + 4 * (i >> 1));
    ((device uint *)dst)[c] = word;
  }
}
// A group of a format that keeps its native bytes (metal/abi/QuantFormat.h): group j's plane0 and plane1 bytes of
// the block from `at0` and `at1` on, and once per block the meta unit from `atMeta`.
static inline void gguf_copy_native(device const uchar *blk, uint j, constant QuantFormat &f, uint at0, uint at1,
                                    uint atMeta, device uchar *out0, device uchar *out1, device uchar *meta) {
  for (uint i = 0; i < f.plane0_bytes; ++i) out0[i] = blk[at0 + f.plane0_bytes * j + i];
  for (uint i = 0; i < f.plane1_bytes; ++i) out1[i] = blk[at1 + f.plane1_bytes * j + i];
  if (j == 0) for (uint i = 0; i < f.meta_bytes; ++i) meta[i] = blk[atMeta + i];
}
// Decode one trit from Prism's source PTQ1_0 block. The first 80 and next
// 40 values use 16- and 8-byte stages; qh stores the final eight values.
static inline uint gguf_ptq1_trit(device const uchar *blk, uint e) {
  uint q, n;
  if (e < 80) { n = e / 16; q = blk[e % 16]; }
  else if (e < 120) { const uint x = e - 80; n = x / 8; q = blk[16 + x % 8]; }
  else { const uint x = e - 120; n = x / 2; q = blk[24 + x % 2]; }
  return (((q * kPTQ1SourcePow3[n]) & 255) * 3) >> 8;
}

// Nibbles 0..3 of x at bits 0, 8, 16, 24 to bits 0, 16, 4, 20: four consecutive 4-bit codes as a pair word holds
// them (gguf_store_pairs).
static inline uint gguf_nibble_pairs(uint x) {
  return (x & 0xFu) | ((x >> 12) & 0xF0u) | ((x << 8) & 0xF0000u) | ((x >> 4) & 0xF00000u);
}
// Group j of a Q4_K (qs at byte 16) or Q5_K (qs at 48, with fifth bits) block from its words: a few shifts a word
// instead of a byte load and a pack per element. Pair word c is qs words c and 4 + c; the fifth bits, bit j of
// qh[4k..4k+3] gathered by the multiply, go to slots 8 (k % 4) + 4 (k / 4) on.
static inline void gguf_repack_k_words(device const uchar *blk, uint qs_at, bool fifth, uint j, device uchar *out0,
                                       device uchar *out1, device uchar *meta) {
  device const uint *qs = (device const uint *)(blk + qs_at + (j / 2) * 32);
  uint4 pairs;
  for (uint c = 0; c < 4; ++c)
    pairs[c] = gguf_nibble_pairs((qs[c] >> (4 * (j % 2))) & 0x0F0F0F0Fu) |
               gguf_nibble_pairs((qs[4 + c] >> (4 * (j % 2))) & 0x0F0F0F0Fu) << 8;
  *(device uint4 *)out0 = pairs;
  if (fifth) {
    device const uint *qh = (device const uint *)(blk + 16);
    uint bits = 0;
    for (uint k = 0; k < 8; ++k)
      bits |= ((((qh[k] >> j) & 0x01010101u) * 0x204081u) >> 21 & 0xFu) << (8 * (k % 4) + 4 * (k / 4));
    *(device uint *)out1 = bits;
  }
  device const uint *head = (device const uint *)blk;
  if (j == 0) *(device uint4 *)meta = uint4(head[0], head[1], head[2], head[3]);
}
// Group j of an MLX affine block's codes, from `codes` on, into its planes: element e of group j is code 32 j + e
// of the codes' bit string. The planes keep its low 2 (2, 3 bits) or 4 bits (4, 5, 6) and the rest as Q2_K, Q3_K,
// Q4_K, Q5_K and Q6_K do; 8 bits as Q8_0.
static inline void gguf_repack_affine_codes(device const uchar *codes, uint fmt, uint j, device uchar *out0,
                                            device uchar *out1) {
  const uint bits = quant_affine_bits(fmt), low = bits == 8 ? 8 : bits <= 3 ? 2 : 4;
  uchar lo[32], hi[32];
  for (uint e = 0; e < 32; ++e) {
    const uint at = (32 * j + e) * bits, shift = at % 8;
    const uint word = uint(codes[at / 8]) | (shift + bits > 8 ? uint(codes[at / 8 + 1]) << 8 : 0u);
    const uint code = (word >> shift) & ((1u << bits) - 1);
    lo[quant_slot(e)] = code & ((1u << low) - 1);
    hi[quant_slot(e)] = code >> low;
  }
  if (low == 4) gguf_store_pairs(lo, out0); else gguf_store_bits(lo, low, out0);
  if (bits != low) gguf_store_bits(hi, bits - low, out1);
}
// Group j of 4-bit codes whose element e is in bits 4 (e % 2) of byte e / 2 of the group's 16 bytes from `codes`
// on (NVFP4's, and MXFP4's as MLX packs it).
static inline void gguf_repack_nibbles(device const uchar *codes, uint j, device uchar *out0) {
  uchar lo[32];
  for (uint e = 0; e < 32; ++e) lo[quant_slot(e)] = (codes[16 * j + e / 2] >> (4 * (e % 2))) & 15;
  gguf_store_bits(lo, 4, out0);
}
// Where group g of row n of a tensor of G groups a row in format f writes: its plane0 and plane1 units and its
// block's meta unit, each plane [rows / QUANT_TILE_ROWS][units][QUANT_TILE_ROWS].
struct GgufRepackOutput {
  device uchar *out0, *out1, *meta;
};
static inline GgufRepackOutput gguf_repack_output(constant QuantFormat &f, uint G, uint n, uint g,
                                                  device uchar *plane0, device uchar *plane1, device uchar *meta_plane) {
  const uint b = g / f.meta_groups;
  return {plane0 + quant_tile_index(n, g, G) * f.plane0_bytes, plane1 + quant_tile_index(n, g, G) * f.plane1_bytes,
          meta_plane + quant_tile_index(n, b, G / f.meta_groups) * f.meta_bytes};
}
// Group g (32 wide) of row n of a tensor of G groups a row in format fmt: its native row from `row` on, written
// into its plane0, plane1 and meta planes, each [rows / QUANT_TILE_ROWS][units][QUANT_TILE_ROWS]. Q4_K and Q5_K
// blocks are read as words, Q2_0's, PQ2_0's and the 16-bit formats' as halfwords: their sizes are multiples of
// those, and rows are whole blocks after a tensor start on 8 bytes, in the file (model/GgufFile.cpp) and in the
// staging (pages of buffers bound at offset 0).
static inline void gguf_repack_group(device const uchar *row, uint fmt, uint G, uint n, uint g, device uchar *plane0,
                                     device uchar *plane1, device uchar *meta_plane) {
  constant QuantFormat &f = kQuantFormats[fmt];
  const uint b = g / f.meta_groups, j = g % f.meta_groups;   // native block b holds meta unit b
  device const uchar *blk = row + ulong(b) * f.block_bytes;
  const GgufRepackOutput o = gguf_repack_output(f, G, n, g, plane0, plane1, meta_plane);
  device uchar *out0 = o.out0, *out1 = o.out1, *meta = o.meta;
  uchar lo[32], hi[32];   // per slot: the (low) code and its high bits
  if (quant_affine_format(fmt)) {   // MLX affine {s, z, codes}
    gguf_repack_affine_codes(blk + 4, fmt, j, out0, out1);
    if (j == 0) for (uint i = 0; i < 4; ++i) meta[i] = blk[i];
    return;
  }
  switch (fmt) {
    case GGUF_FMT_Q4K:
      gguf_repack_k_words(blk, 16, false, j, out0, out1, meta);
      break;
    case GGUF_FMT_Q5K:
      gguf_repack_k_words(blk, 48, true, j, out0, out1, meta);
      break;
    case GGUF_FMT_IQ4XS: {
      for (uint l = 0; l < 16; ++l) { const uchar q = blk[8 + 16 * j + l]; lo[quant_slot(l)] = q & 15; lo[quant_slot(16 + l)] = q >> 4; }
      gguf_store_bits(lo, 4, out0);
      if (j == 0) for (uint i = 0; i < 8; ++i) meta[i] = blk[i];
      break;
    }
    case GGUF_FMT_Q6K: {
      const uint hb = j / 4, quarter = j % 4;
      for (uint e = 0; e < 32; ++e) {
        lo[quant_slot(e)] = (blk[64 * hb + 32 * (quarter & 1) + e] >> (4 * (quarter >> 1))) & 15;
        hi[quant_slot(e)] = (blk[128 + 32 * hb + e] >> (2 * quarter)) & 3;
      }
      gguf_store_pairs(lo, out0);
      gguf_store_bits(hi, 2, out1);
      if (j == 0) { for (uint i = 0; i < 16; ++i) meta[i] = blk[192 + i]; meta[16] = blk[208]; meta[17] = blk[209]; meta[18] = 0; meta[19] = 0; }
      break;
    }
    case GGUF_FMT_TQK6: case GGUF_FMT_TQK7: {
      const uint bits = fmt == GGUF_FMT_TQK6 ? 6 : 7;
      for (uint i = 0; i < bits + 2; ++i) out0[i] = blk[2 + ((3 - j) * bits + i) % (4 * bits)];
      if (j == 0) { meta[0] = blk[0]; meta[1] = blk[1]; }
      break;
    }
    case GGUF_FMT_Q3K: {
      const uint hb = j / 4, jj = j % 4;
      for (uint e = 0; e < 32; ++e) {
        lo[quant_slot(e)] = (blk[32 + 32 * hb + e] >> (2 * jj)) & 3;
        hi[quant_slot(e)] = (blk[e] >> j) & 1;
      }
      gguf_store_bits(lo, 2, out0);
      gguf_store_bits(hi, 1, out1);
      if (j == 0) { meta[0] = blk[108]; meta[1] = blk[109]; meta[2] = 0; meta[3] = 0; for (uint i = 0; i < 12; ++i) meta[4 + i] = blk[96 + i]; }
      break;
    }
    case GGUF_FMT_Q80: {
      for (uint e = 0; e < 32; ++e) lo[quant_slot(e)] = blk[2 + e];
      gguf_store_bits(lo, 8, out0);
      meta[0] = blk[0]; meta[1] = blk[1];
      break;
    }
    case GGUF_FMT_Q2K: {   // block_q2_K {scales[16], qs[64], d, dmin}: group j is bits 2 (j % 4) of qs[32 (j / 4)..]
      for (uint e = 0; e < 32; ++e) lo[quant_slot(e)] = (blk[16 + 32 * (j / 4) + e] >> (2 * (j % 4))) & 3;
      gguf_store_bits(lo, 2, out0);
      if (j == 0) { for (uint i = 0; i < 4; ++i) meta[i] = blk[80 + i]; for (uint i = 0; i < 16; ++i) meta[4 + i] = blk[i]; }
      break;
    }
    case GGUF_FMT_PQ20: case GGUF_FMT_Q20: {   // block_pq2_0 {d, qs[32]}, block_q2_0 {d, qs[16]}: element e of group
                                               // j is bits 2 (e % 4) of qs[8 j + e / 4], so qs byte k goes whole to
                                               // word k / 2 % 2 at bit 16 (k % 2) + 8 (k / 4)
      device const ushort *qs = (device const ushort *)(blk + 2 + 8 * j);
      const uint q0 = qs[0], q1 = qs[1], q2 = qs[2], q3 = qs[3];
      *(device uint2 *)out0 = uint2((q0 & 0xFFu) | (q2 & 0xFFu) << 8 | (q0 >> 8) << 16 | (q2 >> 8) << 24,
                                    (q1 & 0xFFu) | (q3 & 0xFFu) << 8 | (q1 >> 8) << 16 | (q3 >> 8) << 24);
      if (j == 0) *(device ushort *)meta = *(device const ushort *)blk;
      break;
    }
    case GGUF_FMT_PTQ10: {
      for (uint k = 0; k < 6; ++k) {
        uint q = 0;
        for (uint n = 0; n < 5; ++n) q = 3 * q + gguf_ptq1_trit(blk, 32 * j + 5 * k + n);
        out0[k] = uchar(q);
      }
      out0[6] = uchar(3 * gguf_ptq1_trit(blk, 32 * j + 30) + gguf_ptq1_trit(blk, 32 * j + 31));
      if (j == 0) { meta[0] = blk[26]; meta[1] = blk[27]; }
      break;
    }
    case GGUF_FMT_IQ4NL: case GGUF_FMT_Q40: case GGUF_FMT_Q41: case GGUF_FMT_MXFP4: {   // the meta unit, then qs[16]
      for (uint l = 0; l < 16; ++l) { const uchar q = blk[f.meta_bytes + l]; lo[quant_slot(l)] = q & 15; lo[quant_slot(16 + l)] = q >> 4; }
      if (fmt == GGUF_FMT_Q40 || fmt == GGUF_FMT_Q41) gguf_store_pairs(lo, out0); else gguf_store_bits(lo, 4, out0);
      for (uint i = 0; i < f.meta_bytes; ++i) meta[i] = blk[i];
      break;
    }
    case GGUF_FMT_Q50: case GGUF_FMT_Q51: {   // the meta unit, qh[4], then qs[16]: element e's fifth bit is bit e of qh
      device const uchar *qh = blk + f.meta_bytes, *qs = qh + 4;
      for (uint l = 0; l < 16; ++l) { lo[quant_slot(l)] = qs[l] & 15; lo[quant_slot(16 + l)] = qs[l] >> 4; }
      for (uint e = 0; e < 32; ++e) hi[quant_slot(e)] = (qh[e / 8] >> (e % 8)) & 1;
      gguf_store_pairs(lo, out0);
      gguf_store_bits(hi, 1, out1);
      for (uint i = 0; i < f.meta_bytes; ++i) meta[i] = blk[i];
      break;
    }
    case GGUF_FMT_NVFP4: case GGUF_FMT_NVFP464: {   // {E4M3 scales[16] or [4], g, codes}: the meta unit, then codes
      gguf_repack_nibbles(blk + f.meta_bytes, j, out0);
      if (j == 0) for (uint i = 0; i < f.meta_bytes; ++i) meta[i] = blk[i];   // the scales and g
      break;
    }
    case GGUF_FMT_FP8: case GGUF_FMT_MXFP8: {   // the meta unit (FP8's g, MXFP8's e), then E4M3 values[256 or 32]
      for (uint e = 0; e < 32; ++e) lo[quant_slot(e)] = blk[f.meta_bytes + 32 * j + e];
      gguf_store_bits(lo, 8, out0);
      if (j == 0) for (uint i = 0; i < f.meta_bytes; ++i) meta[i] = blk[i];
      break;
    }
    case GGUF_FMT_BF16: case GGUF_FMT_F16: {   // 256 values, element e of group j value 32 j + e; no scale: g = 1
      device const ushort *values = (device const ushort *)blk + 32 * j;
      for (uint e = 0; e < 32; ++e) ((device ushort *)out0)[quant_slot(e)] = values[e];
      if (j == 0) *((device float *)meta) = 1.0f;
      break;
    }
    case GGUF_FMT_IQ3XXS: case GGUF_FMT_IQ2XXS: case GGUF_FMT_IQ2XS:   // {d, qs[64 | 32], signs and scales[32] | scales[8]}
      gguf_copy_native(blk, j, f, 2, 66, 0, out0, out1, meta);
      break;
    case GGUF_FMT_IQ1S:   // {d, qs[32], qh[8] (16-bit)}
      gguf_copy_native(blk, j, f, 2, 34, 0, out0, out1, meta);
      break;
    case GGUF_FMT_IQ1M:   // {qs[32], qh[16], scales[8]}
      gguf_copy_native(blk, j, f, 0, 32, 48, out0, out1, meta);
      break;
    case GGUF_FMT_IQ2S: {   // {d, qs[32], signs[32], qh[8], scales[8]}: plane0 the group's qs, then its signs
      for (uint i = 0; i < 4; ++i) { out0[i] = blk[2 + 4 * j + i]; out0[4 + i] = blk[34 + 4 * j + i]; }
      out1[0] = blk[66 + j]; out1[1] = blk[74 + j];
      if (j == 0) { meta[0] = blk[0]; meta[1] = blk[1]; }
      break;
    }
    case GGUF_FMT_IQ3S:
    default: {  // IQ3_S: grid entry t covers elements 4t..4t+3 (qs[t], ninth bit t of qh); sign bit e negates element e
      device const uchar *qs = blk + 2 + 8 * j, *signs = blk + 74 + 4 * j;
      const uint qh = blk[66 + j], scale = (blk[106 + j / 2] >> (4 * (j % 2))) & 15;
      for (uint e = 0; e < 32; ++e) hi[quant_slot(e)] = (signs[e / 8] >> (e % 8)) & 1;
      const uint sign = gguf_bit_word(hi, 1, 0);
      for (uint c = 0; c < 4; ++c)
        ((device uint *)out0)[c] = uint(qs[c]) | uint(qs[4 + c]) << 8 | ((sign >> (8 * c)) & 0xFF) << 16 |
                                   ((qh >> c) & 1) << 24 | ((qh >> (4 + c)) & 1) << 25 | scale << 26;
      if (j == 0) { meta[0] = blk[0]; meta[1] = blk[1]; }
      break;
    }
  }
}

// Group g of row n of an MLX affine, MXFP4 or MXFP8 tensor of G groups a row in format fmt, from its planes as stored
// (model/GgufPreparation.hpp storedPlanes): its codes, scales and biases from `codes`, `scales` and `biases` on,
// `bytes[p]` a row of each, into its planes as gguf_repack_group writes those of the native block that
// readSafetensorsRows (model/GgufPreparation.cpp) builds of them, bit for bit.
static inline void gguf_repack_stored_group(device const uchar *codes, device const uchar *scales,
                                            device const uchar *biases, constant uint *bytes, uint fmt, uint G,
                                            uint n, uint g, device uchar *plane0, device uchar *plane1,
                                            device uchar *meta_plane) {
  constant QuantFormat &f = kQuantFormats[fmt];
  const uint b = g / f.meta_groups, j = g % f.meta_groups, blocks = G / f.meta_groups;
  const uint codesBytes = bytes[0] / blocks, scaleBytes = bytes[1] / blocks;
  codes += ulong(n) * bytes[0] + ulong(b) * codesBytes;
  scales += ulong(n) * bytes[1] + ulong(b) * scaleBytes;
  const GgufRepackOutput o = gguf_repack_output(f, G, n, g, plane0, plane1, meta_plane);
  if (quant_affine_format(fmt)) {
    gguf_repack_affine_codes(codes, fmt, j, o.out0, o.out1);
    biases += ulong(n) * bytes[2] + ulong(b) * scaleBytes;
    if (j == 0) for (uint i = 0; i < 2; ++i) { o.meta[i] = scales[i]; o.meta[2 + i] = biases[i]; }
  } else {   // MXFP4's codes or MXFP8's E4M3 values, and the group's exponent
    if (fmt == GGUF_FMT_MXFP8) {
      uchar values[32];
      for (uint e = 0; e < 32; ++e) values[quant_slot(e)] = codes[e];
      gguf_store_bits(values, 8, o.out0);
    } else {
      gguf_repack_nibbles(codes, 0, o.out0);
    }
    o.meta[0] = scales[0];
  }
}

kernel void gguf_repack(device const uchar *src [[buffer(0)]], device uchar *dst [[buffer(1)]],
                        constant GgufRepackParams &p [[buffer(2)]], uint t [[thread_position_in_grid]]) {
  const uint G = p.input_size / 32;
  if (t >= p.rows * G) return;
  const uint n = t / G, g = t % G;
  gguf_repack_group(src + ulong(n) * p.src_row_bytes, p.fmt, G, n, g, dst, dst + p.dst_plane1, dst + p.dst_meta);
}

// Streamed experts into their slots (model/ExpertStore.cpp): threadgroup (x, y, z) repacks, as gguf_repack does, the
// (row, 32-wide K group) pairs of one QUANT_TILE_ROWS-row tile and MOE_EXPERT_LOAD_SPAN groups of projection z of job
// y, from the rows the host staged for it, its native rows or its stored planes from staging + its sources on
// (metal/abi/MoE.h), into the planes of slot slots[y], in the chunks of the table at the index after the parameters
// (moe_expert_chunk). Thread i takes row i % QUANT_TILE_ROWS of the tile and every
// (MOE_EXPERT_LOAD_THREADS / QUANT_TILE_ROWS)-th group of the span from i / QUANT_TILE_ROWS: a SIMD group's stores
// are consecutive units of the tile's planes, and each row's span of staged bytes is read by one threadgroup. A grid
// of a pair a thread in row order instead stores 32 units a tile row apart and reads a row from many threadgroups;
// past what the caches hold (a prefill's hundreds of experts) that cost about 4x a copy of the bytes, against
// 1.1-1.4x in this order. The grid's jobs are the host's (an indirect grid it writes in the step before).
kernel void moe_expert_load(device const uchar *staging [[buffer(0)]], device const uint *slots [[buffer(1)]],
                            device const ulong *sources [[buffer(2)]], constant MoeExpertLoadParams &p [[buffer(3)]],
                            constant ulong *chunks [[buffer(4)]], uint3 group [[threadgroup_position_in_grid]],
                            uint index [[thread_index_in_threadgroup]]) {
  constant MoeExpertLoadProjection &q = p.projections[group.z];
  const uint G = q.columns / 32, spans = (G + MOE_EXPERT_LOAD_SPAN - 1) / MOE_EXPERT_LOAD_SPAN;
  const uint tile_id = group.x / spans;
  const uint row0 = tile_id * QUANT_TILE_ROWS;
  if (row0 >= q.rows) return;
  const uint first = group.x % spans * MOE_EXPERT_LOAD_SPAN, end = min(G, first + MOE_EXPERT_LOAD_SPAN);
  const MoeExpertChunk c = moe_expert_chunk(chunks, p.floor_slots, p.chunk_slots, slots[group.y], group.z);
  const ulong local = c.local;
  device uchar *w0 = c.w0 + local * q.slot_bytes[0], *w1 = c.w1 + local * q.slot_bytes[1],
               *meta = c.meta + local * q.slot_bytes[2];
  device const ulong *at = sources + (ulong(group.y) * 3 + group.z) * p.source_planes;
  if (q.format == GGUF_FMT_Q20 && !q.stored_bytes[0]) {
    // 32 rows x up to 16 Q2_0 blocks (32 groups = MOE_EXPERT_LOAD_SPAN, 72 uints/row, padded to 73 for 0 bank conflicts).
    // 32 * 73 * 4 = 9,344 bytes (<= 9.2 KiB -> 3 TGs/core in 32 KiB TG memory).
    threadgroup uint tile_buf[32u * 73u];
    const uint rows_in_tile = min(QUANT_TILE_ROWS, q.rows - row0);
    const uint b_first = first >> 1, b_end = end >> 1, n_blocks = b_end - b_first;
    const uint n_ushorts = n_blocks * 9u;
    const uint simd_id = index >> 5, lane = index & 31u;
    device const uchar *src_base = staging + at[0];
    device uint2 *w0_tile = (device uint2 *)w0 + ulong(tile_id) * G * QUANT_TILE_ROWS;
    device ushort *meta_tile = (device ushort *)meta + ulong(tile_id) * (G >> 1) * QUANT_TILE_ROWS;
    const bool aligned4 = (q.row_bytes & 3u) == 0u;
    const bool aligned16 = (q.row_bytes & 15u) == 0u && ((b_first * 18u) & 15u) == 0u && ((n_blocks * 18u) & 15u) == 0u;
    for (uint r_half = 0u; r_half < rows_in_tile; r_half += 32u) {
      const uint nh = min(32u, rows_in_tile - r_half);
      const uint base_row = row0 + r_half;
      const bool flat_v4 = spans == 1u && ((nh * q.row_bytes) & 15u) == 0u && ((base_row * q.row_bytes) & 15u) == 0u;
      if (flat_v4) {
        device const uint4 *src4 = (device const uint4 *)(src_base + ulong(base_row) * q.row_bytes);
        const uint total_v4 = (nh * q.row_bytes) >> 4;
        for (uint i = index; i < total_v4; i += MOE_EXPERT_LOAD_THREADS) {
          const uint4 v = src4[i];
          const uint dst_i = i << 2;
          tile_buf[dst_i] = v.x;
          tile_buf[dst_i + 1u] = v.y;
          tile_buf[dst_i + 2u] = v.z;
          tile_buf[dst_i + 3u] = v.w;
        }
      } else if (aligned16) {
        const uint v4_per_row = (n_blocks * 18u) >> 4;
        const uint total_v4 = nh * v4_per_row;
        device const uchar *chunk_base = src_base + ulong(base_row) * q.row_bytes + ulong(b_first) * 18u;
        for (uint i = index; i < total_v4; i += MOE_EXPERT_LOAD_THREADS) {
          const uint rr = i / v4_per_row, w = i - rr * v4_per_row;
          const uint4 v = ((device const uint4 *)(chunk_base + ulong(rr) * q.row_bytes))[w];
          const uint dst_w = rr * 73u + (w << 2);
          tile_buf[dst_w] = v.x;
          tile_buf[dst_w + 1u] = v.y;
          tile_buf[dst_w + 2u] = v.z;
          tile_buf[dst_w + 3u] = v.w;
        }
      } else if (aligned4 && (n_blocks & 1u) == 0u) {
        const uint n_words = n_ushorts >> 1;
        for (uint rr = simd_id; rr < nh; rr += 8u) {
          device const uint *src =
              (device const uint *)(src_base + ulong(base_row + rr) * q.row_bytes + ulong(b_first) * 18u);
          threadgroup uint *dst = tile_buf + rr * 73u;
          for (uint w = lane; w < n_words; w += 32u) dst[w] = src[w];
        }
      } else {
        for (uint rr = simd_id; rr < nh; rr += 8u) {
          device const ushort *src =
              (device const ushort *)(src_base + ulong(base_row + rr) * q.row_bytes + ulong(b_first) * 18u);
          threadgroup ushort *dst = (threadgroup ushort *)(tile_buf + rr * 73u);
          for (uint w = lane; w < n_ushorts; w += 32u) dst[w] = src[w];
        }
      }
      threadgroup_barrier(mem_flags::mem_threadgroup);
      if (lane < nh) {
        threadgroup const ushort *row_tg =
            flat_v4 ? ((threadgroup const ushort *)tile_buf + lane * n_ushorts)
                    : (threadgroup const ushort *)(tile_buf + lane * 73u);
        device uint2 *w0_row = w0_tile + r_half + lane;
        device ushort *meta_row = meta_tile + r_half + lane;
        for (uint dg = simd_id; dg < n_blocks * 2u; dg += 8u) {
          const uint db = dg >> 1, j = dg & 1u;
          threadgroup const ushort *blk = row_tg + db * 9u;
          threadgroup const ushort *qs = blk + 1u + 4u * j;
          const uint q0 = qs[0], q1 = qs[1], q2 = qs[2], q3 = qs[3];
          w0_row[ulong((b_first << 1) + dg) * QUANT_TILE_ROWS] =
              uint2((q0 & 0xFFu) | (q2 & 0xFFu) << 8 | (q0 >> 8) << 16 | (q2 >> 8) << 24,
                    (q1 & 0xFFu) | (q3 & 0xFFu) << 8 | (q1 >> 8) << 16 | (q3 >> 8) << 24);
          if (j == 0) meta_row[ulong(b_first + db) * QUANT_TILE_ROWS] = blk[0];
        }
      }
      if (r_half + 32u < rows_in_tile) threadgroup_barrier(mem_flags::mem_threadgroup);
    }
    return;
  }
  const uint n = row0 + index % QUANT_TILE_ROWS;
  if (n >= q.rows) return;
  for (uint g = first + index / QUANT_TILE_ROWS; g < end; g += MOE_EXPERT_LOAD_THREADS / QUANT_TILE_ROWS) {
    if (q.stored_bytes[0])
      gguf_repack_stored_group(staging + at[0], staging + at[1], staging + at[2], q.stored_bytes, q.format, G, n, g,
                               w0, w1, meta);
    else
      gguf_repack_group(staging + at[0] + ulong(n) * q.row_bytes, q.format, G, n, g, w0, w1, meta);
  }
}
