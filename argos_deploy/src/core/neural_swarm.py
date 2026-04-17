
class NeuralSwarm:
    def __init__(self, core):
        self.core = core
        self.primary_gpu = 0
        self.secondary_gpu = 1
    def get_env(self, task_type):
        import os
        env = os.environ.copy()
        env["HIP_VISIBLE_DEVICES"] = str(self.primary_gpu if task_type in ["evolution", "code_gen"] else self.secondary_gpu)
        return env
