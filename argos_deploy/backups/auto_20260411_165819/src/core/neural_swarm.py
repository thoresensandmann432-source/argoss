"""
NeuralSwarm - GPU-Драйвер Сознания v2.5
Распределяет нагрузку между GPU
"""
import os

class NeuralSwarm:
    def __init__(self, core):
        self.core = core
        self.primary_gpu = 0  # RX 580 (8GB)
        self.secondary_gpu = 1  # RX 560 (4GB)

    def get_env(self, task_type):
        """Возвращает окружение с нужным GPU"""
        env = os.environ.copy()
        if task_type in ["evolution", "code_gen", "training"]:
            env["HIP_VISIBLE_DEVICES"] = str(self.primary_gpu)
        else:
            env["HIP_VISIBLE_DEVICES"] = str(self.secondary_gpu)
        return env

    def select_gpu(self, task_complexity):
        """Выбирает GPU по сложности задачи"""
        if task_complexity == "high":
            return self.primary_gpu
        return self.secondary_gpu
