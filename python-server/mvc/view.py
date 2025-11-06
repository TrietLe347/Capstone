# mvc/view.py
import numpy as np
from notifier.observer import IObserver  # if you added Observer interfaces
from payload.adapter import IPayloadAdapter

class ConsoleView(IObserver):
    def update(self, arr33x4: np.ndarray) -> None:
        if arr33x4 is None or np.isnan(arr33x4).all():
            print("[View] No pose yet.")
            return
        pts = arr33x4[:3, :3]
        print(f"[View] Pose updated | first 3 pts: {pts}")

class JsonPrintView(IObserver):
    """Observer that converts pose → Unity JSON via Adapter, then prints it."""
    def __init__(self, adapter: IPayloadAdapter, preview_chars: int = 160) -> None:
        self.adapter = adapter
        self.preview_chars = preview_chars

    def update(self, arr33x4: np.ndarray) -> None:
        text = self.adapter.to_text(arr33x4)
        preview = text[: self.preview_chars] + ("..." if len(text) > self.preview_chars else "")
        print(f"[JSON] {preview}")
