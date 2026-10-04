"""Fail-closed identity check, without changing CUDA visibility."""
import ctypes
import os
import subprocess
import uuid

EXPECTED_UUID = 'GPU-2c54fc50-8962-5ef4-a42f-45752aedef9d'
EXPECTED_NAME = 'NVIDIA GeForce RTX 2080 Ti'


def verify_gpu():
    mask = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    if os.environ.get('CUDA_DEVICE_ORDER') != 'PCI_BUS_ID':
        raise RuntimeError('CUDA_DEVICE_ORDER must be PCI_BUS_ID')
    # The harness queue emits physical index 1; direct evaluation inherits the UUID.
    if mask not in (EXPECTED_UUID, '1'):
        raise RuntimeError(f'Refusing visibility mask {mask!r}; only the supplied UUID or queue index 1 is allowed')
    result = subprocess.run(['nvidia-smi', '--id=' + EXPECTED_UUID,
                             '--query-gpu=index,uuid,name,memory.total,driver_version',
                             '--format=csv,noheader,nounits'], capture_output=True,
                            text=True, check=True, timeout=10)
    fields = [s.strip() for s in result.stdout.strip().split(',')]
    if fields[:3] != ['1', EXPECTED_UUID, EXPECTED_NAME] or not 10000 < int(fields[3]) < 12000:
        raise RuntimeError(f'Unexpected physical GPU: {fields}')
    cuda = ctypes.CDLL('libcuda.so.1')

    def checked(name, *args):
        code = getattr(cuda, name)(*args)
        if code:
            raise RuntimeError(f'{name} failed with CUDA error {code}')

    checked('cuInit', 0)
    count = ctypes.c_int()
    checked('cuDeviceGetCount', ctypes.byref(count))
    if count.value != 1:
        raise RuntimeError(f'Expected exactly one visible logical GPU, got {count.value}')
    device = ctypes.c_int()
    checked('cuDeviceGet', ctypes.byref(device), 0)
    name = ctypes.create_string_buffer(256)
    checked('cuDeviceGetName', name, 256, device)
    raw_uuid = (ctypes.c_ubyte * 16)()
    checked('cuDeviceGetUuid', ctypes.byref(raw_uuid), device)
    actual_uuid = 'GPU-' + str(uuid.UUID(bytes=bytes(raw_uuid)))
    if actual_uuid != EXPECTED_UUID or name.value.decode() != EXPECTED_NAME:
        raise RuntimeError(f'Logical CUDA device 0 is not the allowed GPU: {actual_uuid}, {name.value!r}')
    return {'physical_index': 1, 'logical_device': 0, 'uuid': actual_uuid,
            'name': name.value.decode(), 'memory_mib': int(fields[3]),
            'driver_version': fields[4], 'visibility_mask': mask}
