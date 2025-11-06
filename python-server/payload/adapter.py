# payload/adapter.py
from abc import ABC, abstractmethod
from datetime import datetime
import json
import numpy as np

class IPayloadAdapter(ABC):
    """Converts the Model's (33x4) ndarray into a transport payload (str/bytes)."""
    @abstractmethod
    def to_text(self, arr33x4: np.ndarray) -> str:
        ...

class UnityPoseAdapter(IPayloadAdapter):
    """
    Builds the Unity JSON we've been using:
      {
        "ts": "...Z",
        "pose": [ { "id": 0, "x": ..., "y": ..., "z": ... }, ... 33 items ... ]
      }
    Options:
      - nan_to_zero: replace NaN with 0.0 for robust JSON
      - round_ndigits: optional rounding to shrink payload size
    """
    def __init__(self, nan_to_zero: bool = True, round_ndigits: int | None = None) -> None:
        self.nan_to_zero = nan_to_zero
        self.round_ndigits = round_ndigits

    def _num(self, v: float) -> float:
        if self.round_ndigits is not None:
            v = round(float(v), self.round_ndigits)
        return float(v)

    def to_text(self, arr33x4: np.ndarray) -> str:
        if self.nan_to_zero:
            safe = np.nan_to_num(arr33x4, nan=0.0)
        else:
            safe = arr33x4

        pose = [
            {
                "id": i,
                "x": self._num(safe[i, 0]),
                "y": self._num(safe[i, 1]),
                "z": self._num(safe[i, 2]),
            }
            for i in range(33)
        ]
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "pose": pose,
        }
        return json.dumps(payload, separators=(",", ":"))  # compact
