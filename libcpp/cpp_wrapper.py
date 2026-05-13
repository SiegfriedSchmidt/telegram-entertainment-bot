from libcpp.linker import Linker
from pathlib import Path
import ctypes

linker = Linker(Path(__file__).parent / "./build/reward_function_lib.so")
reward_function_cpp = linker(
    (ctypes.c_ulonglong, ctypes.c_ulonglong, ctypes.c_ulonglong),
    ctypes.c_ulonglong,
    "reward_function"
)


def reward_function(base_reward: int, block_height: int, block_nonce: int) -> int:
    return reward_function_cpp(base_reward, block_height, block_nonce)


if __name__ == '__main__':
    print(reward_function(2000, 2, 67))
    print(reward_function(2000, 101, 1))
