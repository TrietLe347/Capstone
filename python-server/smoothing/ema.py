import numpy as np
from .base import ISmoother

class EmaSmoother(ISmoother):
    def __init__(self, alpha: float = 0.35) -> None:
        self.alpha = alpha

    def update(self, prev: np.ndarray, new: np.ndarray) -> np.ndarray:
        prev = np.nan_to_num(prev, nan=0.0)
        return (1.0 - self.alpha) * prev + self.alpha * new
