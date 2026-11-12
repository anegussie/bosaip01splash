// Gyro: H(Dx), normalized Sylvester-Walsh-Hadamard blocks of 128.
#pragma clang fp reassociate(off)
#include "metal/abi/MoE.h"
#include <metal_stdlib>
using namespace metal;
kernel void moe_gyro_rotate(device bfloat *values [[buffer(0)]], device const char *signs [[buffer(1)]],
    device const MoeTileDescriptor *tiles [[buffer(2)]], device const MoeTileCount *count [[buffer(3)]],
    constant MoeGyroRotationParams &p [[buffer(4)]], uint2 group [[threadgroup_position_in_grid]],
    uint tid [[thread_index_in_threadgroup]]) {
  if (group.y >= count->tiles || tiles[group.y].expert >= p.experts) return;
  threadgroup float stage[128];
  const uint column = group.x * 128 + tid;
  for (uint r = 0; r < tiles[group.y].rows; ++r) {
    const ulong at = (ulong(group.y) * p.tileRows + r) * p.width + column;
    stage[tid] = float(values[at]) * float(signs[column]);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    for (uint stride = 1; stride < 128; stride *= 2) {
      const float x = stage[tid], y = stage[tid ^ stride];
      threadgroup_barrier(mem_flags::mem_threadgroup);
      stage[tid] = (tid & stride) ? y - x : x + y;
      threadgroup_barrier(mem_flags::mem_threadgroup);
    }
    values[at] = bfloat(stage[tid] * 0.08838834764831845f);
    threadgroup_barrier(mem_flags::mem_threadgroup);
  }
}
