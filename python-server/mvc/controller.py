import threading
import cv2
import mediapipe as mp
import numpy as np
from absl import logging as absl_logging
from typing import Optional
from smoothing.base import ISmoother
from smoothing.none import NoSmoothing

absl_logging.set_verbosity(absl_logging.ERROR)

class TrackerController:
    """
    Controller:
      - reads frames from camera (no display)
      - runs MediaPipe BlazePose
      - partial updates by visibility threshold
      - applies smoothing strategy on accepted points
      - writes merged (33,4) landmarks to the Model
    """
    def __init__(self,
                 model,
                 camera_index: int = 0,
                 model_complexity: int = 0,
                 vis_thresh: float = 0.5,
                 smoother: Optional[ISmoother] = None) -> None:
        self.model = model
        self.camera_index = camera_index
        self.model_complexity = model_complexity
        self.vis_thresh = vis_thresh
        self.smoother = smoother or NoSmoothing()

        self._stop = False
        self._th = None
        self._last = np.full((33, 4), np.nan, dtype=np.float32)

    def start(self) -> None:
        self._stop = False
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._stop = True
        if self._th:
            self._th.join(timeout=2.0)

    def _merge(self, cur: np.ndarray) -> np.ndarray:
        # First frame: seed visible points
        if np.isnan(self._last).all():
            mask = cur[:, 3] >= self.vis_thresh
            self._last[mask] = cur[mask]
            return self._last

        accept = cur[:, 3] >= self.vis_thresh
        merged = self._last.copy()
        if accept.any():
            merged[accept] = self.smoother.update(self._last[accept], cur[accept])
        self._last = merged
        return merged

    def _loop(self) -> None:
        mp_pose = mp.solutions.pose
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print(f"Controller: could not open camera {self.camera_index}")
            return

        try:
            with mp_pose.Pose(
                static_image_mode=False,
                model_complexity=self.model_complexity,
                enable_segmentation=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            ) as pose:

                while not self._stop:
                    ok, frame = cap.read()
                    if not ok:
                        continue

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    res = pose.process(rgb)

                    if res.pose_landmarks:
                        cur = np.zeros((33, 4), dtype=np.float32)
                        for i, lm in enumerate(res.pose_landmarks.landmark):
                            cur[i] = [lm.x, lm.y, lm.z, lm.visibility]

                        merged = self._merge(cur)
                        self.model.set(merged)
                    # else: hold last (do nothing)
        finally:
            cap.release()
