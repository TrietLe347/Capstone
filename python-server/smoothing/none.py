import numpy as np
from .base import ISmoother

class NoSmoothing(ISmoother):
    def update(self, prev: np.ndarray, new: np.ndarray) -> np.ndarray:
        return new
