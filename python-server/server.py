import asyncio, contextlib, json, threading
from datetime import datetime

import cv2
import mediapipe as mp
import numpy as np
from absl import logging as absl_logging
from websockets.asyncio.server import serve, ServerConnection

# ------------------ CONFIG ------------------
HOST = "127.0.0.1"
PORT = 8765

FPS_BROADCAST = 30.0        # send to Unity at ~30 FPS (independent of camera FPS)
VIS_THRESH = 0.5            # only update if visibility >= threshold
USE_SMOOTHING = True        # EMA smoothing for accepted points
EMA_ALPHA = 0.35            # smoothing factor (0..1). higher = snappier
MODEL_COMPLEXITY = 0        # 0 (fast) / 1 (balanced) / 2 (accurate)

# ------------------ GLOBAL STATE ------------------
absl_logging.set_verbosity(absl_logging.ERROR)

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

clients: set[ServerConnection] = set()   # connected Unity clients
latest_payload_text: str | None = None   # latest JSON text to send
stop_event = threading.Event()           # clean shutdown signal

# last_good = last reliable (x,y,z,visibility) for 33 landmarks
last_good = np.full((33, 4), np.nan, dtype=np.float32)

# ------------------ UTILS ------------------
def ema_update(prev: np.ndarray, new: np.ndarray, alpha: float) -> np.ndarray:
    """EMA update for a slice of landmarks (broadcast-friendly)."""
    out = prev.copy()
    sel_nan = np.isnan(prev)
    out[sel_nan] = new[sel_nan]
    out[~sel_nan] = (1.0 - alpha) * prev[~sel_nan] + alpha * new[~sel_nan]
    return out

def merge_frame(cur33x4: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Merge current frame into last_good using visibility threshold."""
    global last_good
    if np.isnan(last_good).all():
        mask = cur33x4[:, 3] >= VIS_THRESH
        last_good[mask] = cur33x4[mask]
        return last_good.copy(), mask

    accept = cur33x4[:, 3] >= VIS_THRESH
    merged = last_good.copy()
    if USE_SMOOTHING:
        merged[accept] = ema_update(last_good[accept], cur33x4[accept], EMA_ALPHA)
    else:
        merged[accept] = cur33x4[accept]
    last_good = merged
    return merged, accept

def to_unity_payload_text(merged33x4: np.ndarray) -> str:
    """Build compact JSON Unity expects: {pose:[{id,x,y,z} x33]}.
       Replace NaNs with 0.0 so JSON is valid.
    """
    safe = np.nan_to_num(merged33x4, nan=0.0)
    pose = [
        {"id": i, "x": float(safe[i, 0]), "y": float(safe[i, 1]), "z": float(safe[i, 2])}
        for i in range(33)
    ]
    return json.dumps({"ts": datetime.utcnow().isoformat() + "Z", "pose": pose})

# ------------------ CAMERA THREAD ------------------
def camera_worker():
    """Runs in a normal thread; updates 'latest_payload_text' with newest pose."""
    global latest_payload_text

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open camera 0")
        stop_event.set()
        return

    try:
        with mp_pose.Pose(
            static_image_mode=False,
            model_complexity=MODEL_COMPLEXITY,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as pose:

            while not stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = pose.process(rgb)

                if res.pose_landmarks:
                    cur = np.zeros((33, 4), dtype=np.float32)
                    for i, lm in enumerate(res.pose_landmarks.landmark):
                        cur[i] = [lm.x, lm.y, lm.z, lm.visibility]

                    merged, updated_mask = merge_frame(cur)

                    # Draw for local preview
                    mp_drawing.draw_landmarks(frame, res.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                    cv2.putText(
                        frame, f"Updated: {int(updated_mask.sum())}/33",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2
                    )

                    # Build/send JSON to Unity (via global latest_payload_text)
                    latest_payload_text = to_unity_payload_text(merged)
                else:
                    cv2.putText(
                        frame, "No pose detected (holding last good)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2
                    )

                cv2.imshow("BlazePose → Unity (preview)", frame)
                if cv2.waitKey(1) & 0xFF in (27, ord('q')):
                    stop_event.set()
                    break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()

# ------------------ WEBSOCKET SERVER (ASYNCIO) ------------------
async def handler(ws: ServerConnection) -> None:
    clients.add(ws)
    try:
        # drain any client messages (not used, but keeps connection healthy)
        async for _ in ws:
            pass
    finally:
        clients.discard(ws)

async def broadcast_loop() -> None:
    """Sends the most recent payload to all clients at a steady rate."""
    global latest_payload_text
    period = 1.0 / FPS_BROADCAST
    while not stop_event.is_set():
        if clients and latest_payload_text:
            # snapshot to avoid race with camera thread
            text = latest_payload_text
            send_tasks = []
            for c in list(clients):
                # send text (WebSocket TEXT frame)
                send_tasks.append(c.send(text))
            # fire all; ignore per-client errors (e.g., closed sockets)
            results = await asyncio.gather(*send_tasks, return_exceptions=True)
            # Optionally: prune clients that errored—handler will also remove on close
        await asyncio.sleep(period)

async def main_async() -> None:
    print(f"Server listening on ws://{HOST}:{PORT}")
    async with serve(handler, HOST, PORT, max_size=10_000_000) as server:
        await broadcast_loop()

def main():
    # Start camera/pose thread
    th = threading.Thread(target=camera_worker, daemon=True)
    th.start()

    # Run asyncio server in main thread
    try:
        asyncio.run(main_async())
    finally:
        stop_event.set()
        th.join(timeout=2.0)

if __name__ == "__main__":
    main()
