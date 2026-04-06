#include <hip/hip_runtime.h>
#include <stdio.h>
int main() {
  int count = 0;
  hipError_t err = hipGetDeviceCount(&count);
  if (err != hipSuccess) {
    printf("hipGetDeviceCount error: %s\n", hipGetErrorString(err));
    return 1;
  }
  printf("Device count: %d\n", count);
  for (int i = 0; i < count; ++i) {
    hipDeviceProp_t prop{};
    hipGetDeviceProperties(&prop, i);
    printf("%d: %s\n", i, prop.name);
  }
  return 0;
}
