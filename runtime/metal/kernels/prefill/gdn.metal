#include "metal/abi/ExecutionGeometry.h"
#include "metal/abi/KernelABI.h"
#include "metal/kernels/common/gdn_primitives.h"
#include "metal/kernels/common/rms_inverse.h"

constant constexpr uint GdnScanBlock = 16;

// One threadgroup carries SPLASH_GDN_SCAN_STATE_ROWS rows of a value head's
// 128 x 128 recurrent state through the whole chunk in fp32, token by token:
// S = d S; m = S k; S += k (v - m) beta; o = S q. State is the stored
// element: float, or bfloat, widened as it is loaded and rounded to nearest
// even as it is stored at the chunk's end. A lane owns sixteen key columns of
// two rows, so eight lanes share each row and each key-dimension dot product
// costs three shuffle steps while interleaving two independent rows hides
// shuffle latency and halves q/k loads; a simdgroup covers eight rows. Blocks
// of GdnScanBlock tokens of q, k and v stay bf16 in threadgroup memory; decay
// and beta stay fp32. Values widen only where the fp32 recurrence reads them,
// preserving the exact input values while halving q/k/v staging. They are
// staged in threadgroup memory while the following block is prefetched into
// registers, so the dependent per-token chain reads only threadgroup memory.
// Outputs stage through threadgroup memory for coalesced bfloat4 stores.
// The math is the decode recurrence; only the summation order of the dot
// products differs from its per-lane form.
template <uint KeyHeads, uint ValueHeads, uint HeadDim, class State>
inline void gdn_scan_prefill_phase(
    device const bfloat *q, device const bfloat *k, device const bfloat *v,
    device const float *decay, device const bfloat *beta,
    device const State *state_in, device State *state_out,
    device bfloat *output, uint tokens,
    threadgroup bfloat *keys, threadgroup bfloat *queries,
    threadgroup bfloat *values, threadgroup float *gates,
    threadgroup bfloat *out_stage,
    uint group, uint thread_index, uint lane, uint simd_group) {
  constexpr uint Columns = 16;
  constexpr uint LanesPerRow = HeadDim / Columns;
  constexpr uint RowsPerThread = 2;
  constexpr uint Rows = SPLASH_GDN_SCAN_STATE_ROWS;
  constexpr uint Threads = SPLASH_GDN_SCAN_THREADS;
  constexpr uint Block = GdnScanBlock;
  constexpr uint HeadsPerKey = ValueHeads / KeyHeads;
  constexpr uint GroupsPerHead = HeadDim / Rows;
  static_assert(Rows == RowsPerThread * (Threads / 32) * (32 / LanesPerRow),
                "the simdgroups of a threadgroup cover its state rows");
  static_assert(Block * HeadDim == Threads * 16,
                "every thread stages sixteen keys and sixteen queries");
  static_assert(Block * Rows == Threads * 4,
                "every thread stages four values");

  const uint value_head = group / GroupsPerHead;
  const uint key_head = value_head / HeadsPerKey;
  const uint row_base = (group % GroupsPerHead) * Rows;
  const uint row0 = simd_group * (32 / LanesPerRow) + lane / LanesPerRow;
  const uint row1 = row0 + Rows / 2;
  const uint column = (lane % LanesPerRow) * Columns;
  const ulong state_base0 =
      (ulong(value_head) * HeadDim + row_base + row0) * HeadDim + column;
  const ulong state_base1 =
      (ulong(value_head) * HeadDim + row_base + row1) * HeadDim + column;

  float4 state0[Columns / 4], state1[Columns / 4];
#pragma unroll
  for (uint c = 0; c < Columns / 4; ++c) {
    state0[c] = float4(
        reinterpret_cast<device const vec<State, 4> *>(state_in + state_base0)[c]);
    state1[c] = float4(
        reinterpret_cast<device const vec<State, 4> *>(state_in + state_base1)[c]);
  }

  bfloat4 key_fetch[4] = {}, query_fetch[4] = {}, value_fetch = {};
  float decay_fetch = 0.0f, beta_fetch = 0.0f;
  auto fetch = [&](uint start) {
    const uint element = thread_index * 16;
    const uint token = start + element / HeadDim;
    if (token < tokens) {
      const ulong base =
          (ulong(token) * KeyHeads + key_head) * HeadDim + element % HeadDim;
#pragma unroll
      for (uint h = 0; h < 4; ++h) {
        key_fetch[h] = reinterpret_cast<device const bfloat4 *>(k + base)[h];
        query_fetch[h] = reinterpret_cast<device const bfloat4 *>(q + base)[h];
      }
    }
    const uint value_element = thread_index * 4;
    const uint value_token = start + value_element / Rows;
    if (value_token < tokens) {
      const ulong base =
          (ulong(value_token) * ValueHeads + value_head) * HeadDim + row_base +
          value_element % Rows;
      value_fetch = *reinterpret_cast<device const bfloat4 *>(v + base);
    }
    if (thread_index < Block && start + thread_index < tokens) {
      const uint gate = (start + thread_index) * ValueHeads + value_head;
      decay_fetch = decay[gate];
      beta_fetch = float(beta[gate]);
    }
  };
  auto stage = [&]() {
    const uint element = thread_index * 16;
#pragma unroll
    for (uint h = 0; h < 4; ++h) {
      reinterpret_cast<threadgroup bfloat4 *>(keys + element)[h] = key_fetch[h];
      reinterpret_cast<threadgroup bfloat4 *>(queries + element)[h] =
          query_fetch[h];
    }
    *reinterpret_cast<threadgroup bfloat4 *>(values + thread_index * 4) =
        value_fetch;
    if (thread_index < Block) {
      gates[thread_index] = decay_fetch;
      gates[Block + thread_index] = beta_fetch;
    }
  };

  fetch(0);
  stage();
  threadgroup_barrier(mem_flags::mem_threadgroup);
  for (uint start = 0; start < tokens; start += Block) {
    const bool more = start + Block < tokens;
    if (more)
      fetch(start + Block);
    const uint count = min(Block, tokens - start);
    for (uint t = 0; t < count; ++t) {
      const float d = gates[t], b = gates[Block + t];
      const threadgroup bfloat4 *key =
          reinterpret_cast<const threadgroup bfloat4 *>(keys + t * HeadDim +
                                                        column);
      const threadgroup bfloat4 *query =
          reinterpret_cast<const threadgroup bfloat4 *>(queries + t * HeadDim +
                                                        column);
      float4 kv[Columns / 4];
      float4 p0 = 0.0f, p1 = 0.0f;
#pragma unroll
      for (uint c = 0; c < Columns / 4; ++c) {
        kv[c] = float4(key[c]);
        state0[c] *= d;
        state1[c] *= d;
        p0 = fma(state0[c], kv[c], p0);
        p1 = fma(state1[c], kv[c], p1);
      }
      float mem0 = (p0.x + p0.y) + (p0.z + p0.w);
      float mem1 = (p1.x + p1.y) + (p1.z + p1.w);
      mem0 += simd_shuffle_xor(mem0, 1);
      mem1 += simd_shuffle_xor(mem1, 1);
      mem0 += simd_shuffle_xor(mem0, 2);
      mem1 += simd_shuffle_xor(mem1, 2);
      mem0 += simd_shuffle_xor(mem0, 4);
      mem1 += simd_shuffle_xor(mem1, 4);
      const float delta0 = (float(values[t * Rows + row0]) - mem0) * b;
      const float delta1 = (float(values[t * Rows + row1]) - mem1) * b;
      p0 = 0.0f;
      p1 = 0.0f;
#pragma unroll
      for (uint c = 0; c < Columns / 4; ++c) {
        const float4 qv = float4(query[c]);
        state0[c] = fma(kv[c], delta0, state0[c]);
        state1[c] = fma(kv[c], delta1, state1[c]);
        p0 = fma(state0[c], qv, p0);
        p1 = fma(state1[c], qv, p1);
      }
      float res0 = (p0.x + p0.y) + (p0.z + p0.w);
      float res1 = (p1.x + p1.y) + (p1.z + p1.w);
      res0 += simd_shuffle_xor(res0, 1);
      res1 += simd_shuffle_xor(res1, 1);
      res0 += simd_shuffle_xor(res0, 2);
      res1 += simd_shuffle_xor(res1, 2);
      res0 += simd_shuffle_xor(res0, 4);
      res1 += simd_shuffle_xor(res1, 4);
      if (lane % LanesPerRow == 0) {
        out_stage[t * Rows + row0] = bfloat(res0);
        out_stage[t * Rows + row1] = bfloat(res1);
      }
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    {
      const uint t = thread_index >> 3;
      const uint c4 = thread_index & 7u;
      if (t < count) {
        reinterpret_cast<device bfloat4 *>(
            output + (ulong(start + t) * ValueHeads + value_head) * HeadDim +
            row_base)[c4] =
            reinterpret_cast<threadgroup const bfloat4 *>(out_stage +
                                                          t * Rows)[c4];
      }
    }
    if (more) {
      stage();
      threadgroup_barrier(mem_flags::mem_threadgroup);
    }
  }
#pragma unroll
  for (uint c = 0; c < Columns / 4; ++c) {
    reinterpret_cast<device vec<State, 4> *>(state_out + state_base0)[c] =
        vec<State, 4>(state0[c]);
    reinterpret_cast<device vec<State, 4> *>(state_out + state_base1)[c] =
        vec<State, 4>(state1[c]);
  }
}

#define GDN_SCAN_PREFILL_KERNEL(Name, KeyHeads, ValueHeads, HeadDim, State)    \
  kernel void Name(                                                           \
      device const bfloat *q [[buffer(0)]],                                   \
      device const bfloat *k [[buffer(1)]],                                   \
      device const bfloat *v [[buffer(2)]],                                   \
      device const float *decay [[buffer(3)]],                                \
      device const bfloat *beta [[buffer(4)]],                                \
      device const State *state_in [[buffer(5)]],                             \
      device State *state_out [[buffer(6)]],                                  \
      device bfloat *output [[buffer(7)]],                                    \
      constant GDNPrefillParams &params [[buffer(8)]],                        \
      uint group [[threadgroup_position_in_grid]],                            \
      uint thread_index [[thread_index_in_threadgroup]],                      \
      uint lane [[thread_index_in_simdgroup]],                                \
      uint simd_group [[simdgroup_index_in_threadgroup]]) {                   \
    threadgroup bfloat keys[GdnScanBlock * HeadDim];                           \
    threadgroup bfloat queries[GdnScanBlock * HeadDim];                        \
    threadgroup bfloat values[GdnScanBlock * SPLASH_GDN_SCAN_STATE_ROWS];    \
    threadgroup float gates[2 * GdnScanBlock];                                \
    threadgroup bfloat out_stage[GdnScanBlock * SPLASH_GDN_SCAN_STATE_ROWS];   \
    gdn_scan_prefill_phase<KeyHeads, ValueHeads, HeadDim, State>(             \
        q, k, v, decay, beta, state_in, state_out, output, params.tokens,     \
        keys, queries, values, gates, out_stage, group, thread_index, lane,   \
        simd_group);                                                          \
  }
// Each geometry's scan over an fp32 state and, as Name_bf16_state, a bf16 one.
#define GDN_SCAN_PREFILL_ENTRY(Name, KeyHeads, ValueHeads, HeadDim)            \
  GDN_SCAN_PREFILL_KERNEL(Name, KeyHeads, ValueHeads, HeadDim, float)          \
  GDN_SCAN_PREFILL_KERNEL(Name##_bf16_state, KeyHeads, ValueHeads, HeadDim,    \
                          bfloat)

GDN_SCAN_PREFILL_ENTRY(prefill_gdn_scan, 16, 48, 128)
GDN_SCAN_PREFILL_ENTRY(prefill_gdn_scan_vh32, 16, 32, 128)
GDN_SCAN_PREFILL_ENTRY(prefill_gdn_scan_vh64, 16, 64, 128)
#undef GDN_SCAN_PREFILL_ENTRY
#undef GDN_SCAN_PREFILL_KERNEL

// Prepares one token of one key head: causal convolution, SiLU, q/k RMS
// normalization, value-head gates and (from the first token) convolution carry.
// Round q/k to bf16 before applying the 1/128 and 1/sqrt(128) scales.
template <uint KeyHeads, uint ValueHeads, uint HeadDim, uint ConvDim,
          uint PackedWidth>
inline void gdn_prepare_prefill_phase(
    device const bfloat *packed, device const bfloat *conv_weights,
    device const bfloat *conv_state_in, device bfloat *conv_state_out,
    device bfloat *q, device bfloat *k, device bfloat *v,
    device const float *a_scale, device const bfloat *dt_bias,
    device float *decay, device bfloat *beta,
    constant GDNPrefillParams &params, threadgroup float *reductions,
    uint task, uint thread_index, uint lane, uint simd_group) {
  constexpr uint KeyWidth = KeyHeads * HeadDim;
  constexpr uint ValueWidth = ValueHeads * HeadDim;
  constexpr uint HeadsPerKey = ValueHeads / KeyHeads;
  constexpr uint BOffset = ConvDim + ValueWidth;
  constexpr uint AOffset = BOffset + ValueHeads;
  static_assert(HeadDim == 4 * 32, "one simdgroup per 32 head dimensions");
  const uint token = task / KeyHeads;
  const uint key_head = task % KeyHeads;
  const uint query_channel = key_head * HeadDim + thread_index;
  const uint key_channel = KeyWidth + query_channel;
  const uint value_channel =
      2 * KeyWidth + key_head * HeadsPerKey * HeadDim + thread_index;

  const GdnConvTaps taps = gdn_conv_taps(
      packed, PackedWidth, gdn_conv_history(conv_state_in, packed, ConvDim, PackedWidth, 0), token);
  const float query = float(gdn_conv_silu(taps, conv_weights, query_channel));
  const float key = float(gdn_conv_silu(taps, conv_weights, key_channel));
  const float query_sum = simd_sum(query * query);
  const float key_sum = simd_sum(key * key);
  if (lane == 0) {
    reductions[simd_group] = query_sum;
    reductions[4 + simd_group] = key_sum;
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  if (thread_index == 0) {
    reductions[0] =
        rsqrt((reductions[0] + reductions[1] + reductions[2] + reductions[3]) /
                  HeadDim +
              kRmsEpsilon);
    reductions[4] =
        rsqrt((reductions[4] + reductions[5] + reductions[6] + reductions[7]) /
                  HeadDim +
              kRmsEpsilon);
  }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  const ulong key_row = ulong(token) * KeyWidth;
  q[key_row + query_channel] =
      bfloat(float(bfloat(query * reductions[0])) * 0.0078125f);
  k[key_row + query_channel] =
      bfloat(float(bfloat(key * reductions[4])) * 0.08838834765f);
  for (uint head = 0; head < HeadsPerKey; ++head) {
    const uint channel = value_channel + head * HeadDim;
    v[ulong(token) * ValueWidth + channel - 2 * KeyWidth] =
        gdn_conv_silu(taps, conv_weights, channel);
  }
  if (thread_index < HeadsPerKey) {
    const uint head = key_head * HeadsPerKey + thread_index;
    const uint gate = token * ValueHeads + head;
    const GdnGates gates = gdn_gates(packed + token * PackedWidth, dt_bias,
                                     a_scale, BOffset, AOffset, head);
    beta[gate] = gates.beta;
    decay[gate] = gates.decay;
  }
  if (token == 0) {
    const GdnConvHistory carry =
        gdn_conv_history(conv_state_in, packed, ConvDim, PackedWidth, params.tokens);
    for (uint row = 0; row < SPLASH_GDN_CONVOLUTION_TAPS - 1; ++row) {
      for (uint head = 0; head < HeadsPerKey + 2; ++head) {
        const uint channel = head == 0   ? query_channel
                             : head == 1 ? key_channel
                                         : value_channel + (head - 2) * HeadDim;
        conv_state_out[row * ConvDim + channel] = carry.at(row, channel);
      }
    }
  }
}

#define GDN_PREPARE_PREFILL_ENTRY(Name, KeyHeads, ValueHeads, HeadDim,        \
                                  ConvDim, PackedWidth)                       \
  kernel void Name(                                                           \
      device const bfloat *packed [[buffer(0)]],                              \
      device const bfloat *conv_weights [[buffer(1)]],                        \
      device const bfloat *conv_state_in [[buffer(2)]],                       \
      device bfloat *conv_state_out [[buffer(3)]],                            \
      device bfloat *q [[buffer(4)]], device bfloat *k [[buffer(5)]],         \
      device bfloat *v [[buffer(6)]],                                         \
      device const float *a_scale [[buffer(7)]],                              \
      device const bfloat *dt_bias [[buffer(8)]],                             \
      device float *decay [[buffer(9)]], device bfloat *beta [[buffer(10)]],  \
      constant GDNPrefillParams &params [[buffer(11)]],                       \
      uint task [[threadgroup_position_in_grid]],                             \
      uint thread_index [[thread_index_in_threadgroup]],                      \
      uint lane [[thread_index_in_simdgroup]],                                \
      uint simd_group [[simdgroup_index_in_threadgroup]]) {                   \
    threadgroup float reductions[8];                                          \
    gdn_prepare_prefill_phase<KeyHeads, ValueHeads, HeadDim, ConvDim,         \
                              PackedWidth>(                                   \
        packed, conv_weights, conv_state_in, conv_state_out, q, k, v, a_scale,\
        dt_bias, decay, beta, params, reductions, task, thread_index, lane,   \
        simd_group);                                                          \
  }

GDN_PREPARE_PREFILL_ENTRY(prefill_gdn_prepare, 16, 48, 128, 10240, 16640)
GDN_PREPARE_PREFILL_ENTRY(prefill_gdn_prepare_vh32, 16, 32, 128, 8192, 12544)
GDN_PREPARE_PREFILL_ENTRY(prefill_gdn_prepare_vh64, 16, 64, 128, 12288, 20736)
// Qwen3.8-Flash-Next packs the 48-head rows to 16512 columns.
GDN_PREPARE_PREFILL_ENTRY(prefill_gdn_prepare_p16512, 16, 48, 128, 10240, 16512)
#undef GDN_PREPARE_PREFILL_ENTRY

// W: the norm weights' stored type (float: a GGUF's F32 norms, _f32).
#define GDN_GATE_PREFILL_ENTRY(Name, KeyHeads, ValueHeads, HeadDim, ConvDim,  \
                               PackedWidth, W)                                \
  kernel void Name(                                                           \
      device const bfloat *recurrent [[buffer(0)]],                           \
      device const bfloat *packed [[buffer(1)]],                              \
      device const W *norm_weight [[buffer(2)]],                              \
      device bfloat *hidden [[buffer(3)]],                                    \
      constant GDNGatePrefillParams &params [[buffer(4)]],                    \
      uint task [[threadgroup_position_in_grid]],                             \
      uint thread_index [[thread_index_in_threadgroup]],                      \
      uint lane [[thread_index_in_simdgroup]],                                \
      uint simd_group [[simdgroup_index_in_threadgroup]]) {                   \
    threadgroup float reductions[4];                                          \
    gdn_gate_phase<KeyHeads, ValueHeads, HeadDim, ConvDim, PackedWidth>(      \
        recurrent, packed, norm_weight, hidden, task,                         \
        (params.flags & GDN_TILED_HEADS) != 0, reductions, thread_index,      \
        lane, simd_group, (params.flags & GDN_SIGMOID_GATE) != 0);            \
  }

GDN_GATE_PREFILL_ENTRY(prefill_gdn_gate, 16, 48, 128, 10240, 16640, bfloat)
GDN_GATE_PREFILL_ENTRY(prefill_gdn_gate_vh32, 16, 32, 128, 8192, 12544, bfloat)
GDN_GATE_PREFILL_ENTRY(prefill_gdn_gate_f32, 16, 48, 128, 10240, 16640, float)
GDN_GATE_PREFILL_ENTRY(prefill_gdn_gate_vh32_f32, 16, 32, 128, 8192, 12544,
                       float)
GDN_GATE_PREFILL_ENTRY(prefill_gdn_gate_vh64, 16, 64, 128, 12288, 20736, bfloat)
GDN_GATE_PREFILL_ENTRY(prefill_gdn_gate_vh64_f32, 16, 64, 128, 12288, 20736,
                       float)
// Qwen3.8-Flash-Next's norms load as F32 from its GGUFs and its MLX images
// (model/SafetensorsImage.hpp float32Norms).
GDN_GATE_PREFILL_ENTRY(prefill_gdn_gate_p16512_f32, 16, 48, 128, 10240, 16512, float)
#undef GDN_GATE_PREFILL_ENTRY
