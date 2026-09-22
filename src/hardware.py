"""
Управление ресурсами ПК: приоритет процесса и потоки CPU.

ECO  — днём: приоритет ниже среднего, 4 потока, PowerMill не лагает.
TURBO — ночью: обычный приоритет, ~10 потоков, выжимаем максимум.
"""
import os
import sys

import psutil

try:
    import torch
except ImportError:  # torch опционален для приоритета процесса
    torch = None


def set_process_priority(mode: str = "eco") -> None:
    """Настраивает приоритет текущего процесса и число потоков."""
    if sys.platform != "win32":
        return

    process = psutil.Process(os.getpid())
    try:
        if mode == "eco":
            process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            threads = "4"
            print("🟢 Режим [ECO]: приоритет ниже среднего, 4 потока CPU")
        else:
            process.nice(psutil.NORMAL_PRIORITY_CLASS)
            threads = "10"
            print("🚀 Режим [TURBO]: обычный приоритет, 10 потоков CPU")

        os.environ["OMP_NUM_THREADS"] = threads
        os.environ["MKL_NUM_THREADS"] = threads
        if torch is not None:
            torch.set_num_threads(int(threads))
    except Exception as e:
        print(f"⚠️ Не удалось задать приоритет: {e}")


def get_vram_free_gb() -> float:
    """Свободная видеопамять GPU в ГБ (0.0, если CUDA недоступна)."""
    if torch is not None and torch.cuda.is_available():
        free, _total = torch.cuda.mem_get_info()
        return free / (1024 ** 3)
    return 0.0
