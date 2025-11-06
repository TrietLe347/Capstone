# app.py
import asyncio
from mvc.model import PoseModel
from mvc.view import ConsoleView   # keep for debugging; optional
from mvc.controller import TrackerController
from smoothing.ema import EmaSmoother
from payload.adapter import UnityPoseAdapter
from transport.websocket_view import WebSocketView

HOST = "127.0.0.1"
PORT = 8765
BROADCAST_HZ = 30.0

async def main():
    # Model
    model = PoseModel()

    # Views (Observers)
    console_view = ConsoleView()  # optional: comment out if too chatty
    ws_view = WebSocketView(
        adapter=UnityPoseAdapter(nan_to_zero=True, round_ndigits=4),
        host=HOST, port=PORT, hz=BROADCAST_HZ
    )

    # Attach observers
    model.attach(console_view)
    model.attach(ws_view)

    # Controller (Strategy = EMA smoothing)
    ctrl = TrackerController(
        model=model,
        camera_index=0,
        model_complexity=0,
        vis_thresh=0.5,
        smoother=EmaSmoother(alpha=0.15),
    )

    print("[APP] Starting controller…")
    ctrl.start()
    print("[APP] MVC + Strategy + Adapter + WebSocketView running. Press Ctrl+C to stop.")

    try:
        # Run the WebSocket server (blocks until cancelled)
        await ws_view.run()
    except KeyboardInterrupt:
        pass
    finally:
        ctrl.stop()
        print("[APP] Stopped.")

if __name__ == "__main__":
    asyncio.run(main())
