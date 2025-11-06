# 🧍 Pose → Unity Bridge

This project streams **real-time human pose keypoints** from a webcam (via **MediaPipe BlazePose** in Python 3.10.14) directly into **Unity** over **WebSockets**.  
It’s a lightweight bridge between computer-vision tracking and 3D visualization.

---

## 🏗️ Architecture
Webcam → MediaPipe (BlazePose, Python) → WebSocket Server → Unity Client → 3D Spheres / Avatar

- **`python-server/`** → Runs BlazePose, smooths keypoints, and broadcasts JSON frames.  
- **`unity-client/`** → Connects to the WebSocket and animates 33 spheres (or any rig).

---

## 🧩 Folder Structure
pose-unity-bridge/
│
├── python-server/
│ ├── server_pose_ws.py # BlazePose + WebSocket server
│ ├── requirements.txt # Python dependencies
│ ├── README.md # optional detailed server docs
│ └── venv310/ (ignored) # local Python 3.10.14 virtual env
│
├── unity-client/
│ ├── Assets/
│ │ ├── Scenes/
│ │ └── Scripts/
│ │ └── WebSocketClient.cs
│ ├── Packages/
│ └── ProjectSettings/
│
├── .gitignore
└── README.md ← this file

---

## 🧠 Requirements

### 🐍 Python Environment
- **Python 3.10.14 (64-bit)** — verified working  
  > ⚠️ MediaPipe doesn’t yet support Python 3.12+, so keep 3.8 – 3.11.  
  > You can install 3.10.14 alongside other versions without conflict.

### 📦 Dependencies
mediapipe==0.10.14
opencv-python==4.10.0.84
numpy==1.26.4
websockets==15.0.1


### 🎮 Unity Environment
- **Unity 2021 LTS or newer**
- **API Compatibility Level = .NET 4.x**
- Tested on **Windows 10/11**

---

## ⚙️ Setup Instructions

### 1️⃣ Python Server (Pose Tracker)
``` bash
cd python-server
py -3.10 -m venv venv310
venv310\Scripts\activate             # (source venv310/bin/activate on macOS/Linux)
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python server_pose_ws.py

✅ Expected output:
Server listening on ws://127.0.0.1:8765

A preview window shows your webcam with the BlazePose skeleton.
2️⃣ Unity Client (Visualizer)

  1. Open unity-client/ in Unity Hub.

  2. Load your main scene (e.g. SampleScene.unity).

  3. Select NetworkManager → WebSocketClient component.

      URI: ws://127.0.0.1:8765

  4. Press Play ▶️
    → 33 spheres move in real-time following your body pose.

Each frame sent from Python → Unity:

{
  "ts": "2025-11-05T21:23:10.123Z",
  "pose": [
    {"id":0,"x":0.52,"y":0.48,"z":-0.12},
    {"id":1,"x":0.45,"y":0.35,"z":-0.05},
    ...
  ]
}
Unity parses this JSON and updates sphere transforms accordingly.


🧰 Future Enhancements

Face + hand tracking (MediaPipe Holistic)

Secure WebSocket (wss://) support

Real avatar animation instead of spheres

Adjustable smoothing & visibility thresholds from Unity UI

Minh Triet Le

Built with 💻 Python 3.10.14 · Unity 2021+ · Windows 11


🪪 License

MIT License — free to use, modify, and share for personal or educational projects.

📸 Preview (Optional)

Add a GIF or image showing Unity spheres following your body pose.
