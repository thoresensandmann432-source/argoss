#include <hip/hip_runtime.h>
#include <stdio.h>

int main() {
  int runtime = 0, driver = 0;
  hipRuntimeGetVersion(&runtime);
  hipDriverGetVersion(&driver);
  printf("HIP runtime version: %d\n", runtime);
  printf("HIP driver version:  %d\n", driver);

  int count = 0;
  hipError_t err = hipGetDeviceCount(&count);
  if (err != hipSuccess) {
    printf("hipGetDeviceCount error: %s\n", hipGetErrorString(err));
    return 1;
  }
  printf("Device count: %d\n", count);

  for (int i = 0; i < count; ++i) {
    hipDeviceProp_t prop{};
    hipError_t perr = hipGetDeviceProperties(&prop, i);
    if (perr != hipSuccess) {
      printf("Device %d props error: %s\n", i, hipGetErrorString(perr));
      continue;
    }
    printf("%d: %s\n", i, prop.name);
    printf("  gcnArchName: %s\n", prop.gcnArchName);
    printf("  totalGlobalMem: %zu MB\n", (size_t)(prop.totalGlobalMem / (1024 * 1024)));
    printf("  sharedMemPerBlock: %zu KB\n", (size_t)(prop.sharedMemPerBlock / 1024));
    printf("  clockRate: %d KHz\n", prop.clockRate);
    printf("  multiProcessorCount: %d\n", prop.multiProcessorCount);
  }
  return 0;
}
