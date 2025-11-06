from typing import List
import numpy as np
from notifier.observer import ISubject, IObserver

class PoseModel(ISubject):
    """Observable data model holding the latest 33x4 landmarks."""
    def __init__(self):
        self._arr = np.full((33, 4), np.nan, dtype=np.float32)
        self._observers: List[IObserver] = []

    def attach(self, observer: IObserver) -> None:
        self._observers.append(observer)

    def detach(self, observer: IObserver) -> None:
        self._observers.remove(observer)

    def notify(self) -> None:
        for obs in list(self._observers):
            try:
                obs.update(self._arr)
            except Exception as e:
                print(f"[Model] Observer failed: {e}")

    def set(self, arr33x4: np.ndarray) -> None:
        self._arr = arr33x4
        self.notify()

    def get(self) -> np.ndarray:
        return self._arr
