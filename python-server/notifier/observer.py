# patterns/observer.py
from abc import ABC, abstractmethod
import numpy as np

class IObserver(ABC):
    @abstractmethod
    def update(self, data: np.ndarray) -> None:
        """Called when the subject (Model) has new data."""
        ...

class ISubject(ABC):
    @abstractmethod
    def attach(self, observer: IObserver) -> None: ...
    @abstractmethod
    def detach(self, observer: IObserver) -> None: ...
    @abstractmethod
    def notify(self) -> None: ...
