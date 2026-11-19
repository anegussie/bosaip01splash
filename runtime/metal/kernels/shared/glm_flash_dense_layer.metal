#include "metal/abi/HyperConnection.h"
#include "metal/abi/GlmFlashKda.h"
#include "metal/kernels/common/activation.h"

kernel void glm_flash_bfloat(device const float *input [[buffer(0)]],
                              device bfloat *output [[buffer(1)]],
                              constant uint &width [[buffer(2)]],
                              uint2 grid [[thread_position_in_grid]]) {
  if (grid.x >= width) return;
  const ulong index = ulong(grid.y) * width + grid.x;
  output[index] = bfloat(input[index]);
}

template <typename Output>
inline void glm_flash_rms(device const float *input, device const float *weights,
                          device Output *output, uint width, uint row, uint tid, uint lane, uint group,
                          threadgroup float *partial) {
  constexpr uint threads = 256, groups = threads / 32;
  const ulong start = ulong(row) * width;
  float squares = 0.0f;
  for (uint d = tid; d < width; d += threads) squares += input[start + d] * input[start + d];
  const float sum = simd_sum(squares);
  if (lane == 0) partial[group] = sum;
  threadgroup_barrier(mem_flags::mem_threadgroup);
  float total = 0.0f;
  for (uint g = 0; g < groups; ++g) total += partial[g];
  const float inverse = rsqrt(total / float(width) + GLM_FLASH_HC_RMS_EPSILON);
  for (uint d = tid; d < width; d += threads)
    output[start + d] = Output(input[start + d] * inverse * weights[d]);
}

#define GLM_FLASH_RMS_KERNEL(Name, Output)                                      \
  kernel void Name(device const float *input [[buffer(0)]],                      \
                   device const float *weights [[buffer(1)]],                    \
                   device Output *output [[buffer(2)]],                          \
                   constant uint &width [[buffer(3)]],                           \
                   uint row [[threadgroup_position_in_grid]],                   \
                   uint tid [[thread_index_in_threadgroup]],                    \
                   uint lane [[thread_index_in_simdgroup]],                      \
                   uint group [[simdgroup_index_in_threadgroup]]) {              \
    threadgroup float partial[8];                                                \
    glm_flash_rms(input, weights, output, width, row, tid, lane, group, partial);  \
  }
GLM_FLASH_RMS_KERNEL(glm_flash_layer_rms, bfloat)
GLM_FLASH_RMS_KERNEL(glm_flash_layer_rms_f32, float)
#undef GLM_FLASH_RMS_KERNEL

kernel void glm_flash_dense_swiglu(device const float *gate [[buffer(0)]],
                                    device const float *up [[buffer(1)]],
                                    device bfloat *output [[buffer(2)]],
                                    constant uint &width [[buffer(3)]],
                                    uint2 grid [[thread_position_in_grid]]) {
  const ulong index = ulong(grid.y) * width + grid.x;
  output[index] = bfloat(splash_silu(min(gate[index], 10.0f)) * clamp(up[index], -10.0f, 10.0f));
}

kernel void glm_flash_float(device const bfloat *input [[buffer(0)]],
                             device float *output [[buffer(1)]],
                             constant uint &width [[buffer(2)]],
                             uint2 grid [[thread_position_in_grid]]) {
  if (grid.x >= width) return;
  const ulong index = ulong(grid.y) * width + grid.x;
  output[index] = float(input[index]);
}

// Per-head native Q8_0 projection, one SIMD group per output value.
kernel void glm_flash_head_projection(device const float *input [[buffer(0)]],
                                       device const uchar *weights [[buffer(1)]],
                                       device float *output [[buffer(2)]],
                                       constant uint &inputWidth [[buffer(3)]],
                                       uint3 group [[threadgroup_position_in_grid]],
                                       uint3 size [[threadgroups_per_grid]],
                                       uint lane [[thread_index_in_simdgroup]]) {
  const uint blocks = inputWidth / 32;
  const device float *x = input + (ulong(group.x) * size.y + group.y) * inputWidth;
  const device uchar *w = weights + (group.y * size.z + group.z) * blocks * 34;
  float sum = 0.0f;
  for (uint b = 0; b < blocks; ++b) {
    const device uchar *block = w + b * 34;
    const float scale = float(*reinterpret_cast<const device half *>(block));
    const float code = float(reinterpret_cast<const device char *>(block + 2)[lane]);
    sum += (scale * code) * x[b * 32 + lane];
  }
  const float dot = simd_sum(sum);
  if (lane == 0)
    output[(ulong(group.x) * size.y + group.y) * size.z + group.z] = dot;
}

kernel void glm_flash_mean_f32(device const float *streams [[buffer(0)]],
                                device float *output [[buffer(1)]],
                                uint channel [[thread_position_in_grid]]) {
  float sum = 0.0f;
  for (uint stream = 0; stream < GLM_FLASH_HC_STREAMS; ++stream)
    sum += streams[stream * GLM_FLASH_HC_HIDDEN + channel];
  output[channel] = sum / float(GLM_FLASH_HC_STREAMS);
}
