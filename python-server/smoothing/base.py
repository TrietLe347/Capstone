from abc import ABC, abstractmethod
import numpy as np

class ISmoother(ABC):
    @abstractmethod
    def update(self, prev: np.ndarray, new: np.ndarray) -> np.ndarray:
        """Return smoothed values for the accepted subset."""
        
