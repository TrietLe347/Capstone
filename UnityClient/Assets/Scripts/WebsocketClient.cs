// Description:
//   Handles real-time WebSocket communication between Unity and an external Python process (e.g. Mediapipe).
//   Receives JSON-encoded pose data and optionally visualizes it as spheres in the Unity scene.
//
// Usage:
//   - Attach this script to an empty GameObject in your Unity scene.
//   - Set the `uri` to your WebSocket server (Python or otherwise).
//   - Optionally enable `spawnSpheresForPose` to visualize the 33 pose keypoints as spheres.
//
// Extension Notes:
//   - You can modify `ApplyFrame()` to send data to animations, avatars, or UI instead of spheres.
//   - You can also adapt the JSON payload structure to fit your model or protocol.
//
// Dependencies:
//   - Requires System.Net.WebSockets (C# built-in).
//   - Compatible with Unity 2021+ (tested).
// ----------------------------------------------------------------------------------------------------

using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class WebsocketClient : MonoBehaviour
{
    // ----- WebSocket Connection -----
    [Header("Connection")]
    [SerializeField] private string uri = "ws://127.0.0.1:8765";
    // The WebSocket server address (e.g. your Python pose sender)

    // ----- Optional Visualization Settings -----
    [Header("Visualization (Optional)")]
    [SerializeField] private bool spawnSpheresForPose = true; // Whether to spawn spheres for each keypoint
    [SerializeField] private float worldWidth = 6f;  // Scales X coordinate from [0,1] to Unity world units
    [SerializeField] private float worldHeight = 4f; // Scales Y coordinate
    [SerializeField] private float sphereSize = 0.30f; // Size of each pose sphere

    // ----- Internal State -----
    private ClientWebSocket _ws;                    // Main WebSocket client
    private CancellationTokenSource _cts;           // Used to cancel async tasks on quit
    private readonly ConcurrentQueue<string> _inbox = new(); // Thread-safe queue for received messages
    private Transform[] _points;                    // Optional: holds sphere transforms (33 total for BlazePose)

    // ----- JSON Data Structures -----
    // Matches the JSON payload coming from Python (or another WebSocket source)
    [Serializable] private struct PosePoint { public int id; public float x, y, z; }
    [Serializable] private struct Payload { public PosePoint[] pose; }

    // ---- Missing-joint handling & smoothing ----
    [SerializeField] private float smoothTime = 0.05f;          // seconds for SmoothDamp
    [SerializeField] private float missingGrace = 0.25f;        // seconds to keep last value if a joint is missing
    [SerializeField] private float fadeAfter = 0.30f;           // seconds after which we hide the joint
    [SerializeField] private bool flipX = true;                 // toggle mirroring if needed


    [SerializeField] private float fadeDuration = 0.15f; // seconds

    private Vector3[] _vel;                // per-joint velocity for SmoothDamp
    private float[] _lastSeen;             // last time (Time.time) a joint was updated this frame
    private Renderer[] _rend;              // cached renderers to fade/hide


    // ----- BlazePose Keypoint Names -----
    // Used for debugging/logging to know which landmark corresponds to which index
    private string[] blazepose_names = new string[]
    {
        "nose",
        "left_eye_inner", "left_eye", "left_eye_outer",
        "right_eye_inner", "right_eye", "right_eye_outer",
        "left_ear", "right_ear",
        "mouth_left", "mouth_right",
        "left_shoulder", "right_shoulder",
        "left_elbow", "right_elbow",
        "left_wrist", "right_wrist",
        "left_pinky", "right_pinky",
        "left_index", "right_index",
        "left_thumb", "right_thumb",
        "left_hip", "right_hip",
        "left_knee", "right_knee",
        "left_ankle", "right_ankle",
        "left_heel", "right_heel",
        "left_foot_index", "right_foot_index"
    };

    // ----------------------------------------------------------------------------------------------------
    // Unity Lifecycle
    // ----------------------------------------------------------------------------------------------------

    private void Awake()
    {
        // Optionally create visualization spheres before connection starts
        if (spawnSpheresForPose)
            CreatePoseSpheres();
    }

    private async void Start()
    {
        // Establish a WebSocket connection asynchronously
        _ws = new ClientWebSocket();
        _cts = new CancellationTokenSource();

        try
        {
            await _ws.ConnectAsync(new Uri(uri), _cts.Token);
            Debug.Log($"[WS] Connected: {uri}");

            // Start background task for continuous message receiving
            _ = Task.Run(ReceiveLoop);
        }
        catch (Exception e)
        {
            Debug.LogError($"[WS] Connect failed: {e}");
        }
    }

    private void Update()
    {
        // Drain queue but only apply the newest frame once
        string last = null;
        while (_inbox.TryDequeue(out var json)) last = json;
        if (last != null)
        {
            try { ApplyFrame(last); }
            catch (Exception e) { Debug.LogWarning($"[WS] Frame parse/apply error: {e.Message}"); }
        }

        // Handle missing joints (fade/hide) each frame
        // Handle missing joints (fade or hide)
        if (_points != null)
        {
            for (int i = 0; i < _points.Length; i++)
            {
                float age = Time.time - _lastSeen[i];

                if (_rend[i] == null) continue;
                var mat = _rend[i].material; // Instance copy for per-sphere alpha

                // Compute fade factor: 1 → fully visible, 0 → invisible
                float alpha;
                if (age <= missingGrace)
                {
                    alpha = 1f; // just seen
                }
                else if (age <= fadeAfter)
                {
                    alpha = Mathf.InverseLerp(fadeAfter, fadeAfter - fadeDuration, age);
                }
                else
                {
                    alpha = 0f; // gone
                }

                // Apply alpha to material color
                var c = mat.color;
                c.a = alpha;
                mat.color = c;

                // Enable or disable renderer based on alpha
                _rend[i].enabled = alpha > 0.02f;
            }
        }



    }


    // ----------------------------------------------------------------------------------------------------
    // WebSocket Background Receiver
    // ----------------------------------------------------------------------------------------------------
    private async Task ReceiveLoop()
    {
        byte[] buffer = new byte[1 << 20]; // 1 MB buffer for incoming JSON
        var segment = new ArraySegment<byte>(buffer);

        try
        {
            while (_ws.State == WebSocketState.Open && !_cts.IsCancellationRequested)
            {
                // Receive message data (can be partial)
                var result = await _ws.ReceiveAsync(segment, _cts.Token);

                // If the server requested closure
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    Debug.Log("[WS] Server closed");
                    await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", _cts.Token);
                    break;
                }

                // Combine message chunks if message was fragmented
                int count = result.Count;
                while (!result.EndOfMessage)
                {
                    if (count >= buffer.Length)
                    {
                        Debug.LogError("[WS] Frame too large, increase buffer");
                        return;
                    }
                    result = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer, count, buffer.Length - count), _cts.Token);
                    count += result.Count;
                }

                // Convert bytes → UTF-8 string → enqueue for main thread processing
                string json = Encoding.UTF8.GetString(buffer, 0, count);
                _inbox.Enqueue(json);
                Debug.Log($"[WS] Enqueued frame: {count} bytes");
            }
        }
        catch (OperationCanceledException)
        {
            // Normal exit on app quit
        }
        catch (Exception e)
        {
            Debug.LogError($"[WS] Receive error: {e}");
        }
    }

    // ----------------------------------------------------------------------------------------------------
    // Frame Handling / Visualization
    // ----------------------------------------------------------------------------------------------------
    private void ApplyFrame(string json)
    {
        var payload = JsonUtility.FromJson<Payload>(json);
        if (payload.pose == null || _points == null) return;

        // Track which joints were updated this frame
        Span<bool> updated = stackalloc bool[_points.Length];
        for (int i = 0; i < updated.Length; i++) updated[i] = false;

        // Apply all joints present in this frame (by id)
        foreach (var pt in payload.pose)
        {
            int id = pt.id;
            if (id < 0 || id >= _points.Length) continue;

            float wx = (flipX ? (0.5f - pt.x) : (pt.x - 0.5f)) * worldWidth;
            float wy = (0.5f - pt.y) * worldHeight;
            var target = new Vector3(wx, wy, 0f);

            // SmoothDamp from current position toward the target
            var current = _points[id].localPosition;
            var v = _vel[id];
            var next = Vector3.SmoothDamp(current, target, ref v, smoothTime);
            _vel[id] = v;
            _points[id].localPosition = next;

            _lastSeen[id] = Time.time;
            updated[id] = true;

            // ensure visible when freshly updated
            if (_rend[id] != null && !_rend[id].enabled) _rend[id].enabled = true;
        }

        // For joints NOT updated this frame: keep for a short grace, then fade/hide
        for (int i = 0; i < _points.Length; i++)
        {
            if (updated[i]) continue;

            float age = Time.time - _lastSeen[i];

            if (age <= missingGrace)
            {
                // Keep last position (do nothing). Optionally add light damping to reduce jitter:
                _points[i].localPosition = Vector3.SmoothDamp(
                    _points[i].localPosition, _points[i].localPosition, ref _vel[i], smoothTime);
            }
            else if (age > fadeAfter)
            {
                // Hide after fade window (renderer toggled in Update)
                // Optionally also shrink instead of hide:
                // _points[i].localScale = Vector3.zero;
            }
        }
    }


    // ----------------------------------------------------------------------------------------------------
    // Helper: Create Visual Spheres
    // ----------------------------------------------------------------------------------------------------
    private void CreatePoseSpheres()
    {
        int count = 33; // MediaPipe BlazePose has 33 landmarks
        _points = new Transform[count];
        var parent = new GameObject("PosePoints").transform;
        parent.SetParent(transform, false);

        for (int i = 0; i < count; i++)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            go.name = $"pt_{i}";
            go.transform.SetParent(parent, false);
            go.transform.localScale = Vector3.one * sphereSize;

            // Remove collider for performance/cleaner scene
            var col = go.GetComponent<Collider>();
            if (col) Destroy(col);

            _points[i] = go.transform;
        }

        _vel = new Vector3[_points.Length];
        _lastSeen = new float[_points.Length];
        _rend = new Renderer[_points.Length];
        for (int i = 0; i < _points.Length; i++)
        {
            _lastSeen[i] = -999f;
            _rend[i] = _points[i].GetComponent<Renderer>();
        }

    }

    // ----------------------------------------------------------------------------------------------------
    // Cleanup on Application Quit
    // ----------------------------------------------------------------------------------------------------
    private async void OnApplicationQuit()
    {
        try
        {
            _cts?.Cancel();
            if (_ws is { State: WebSocketState.Open or WebSocketState.CloseReceived })
            {
                await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "quit", CancellationToken.None);
            }
        }
        catch { /* ignore errors on shutdown */ }
        finally
        {
            _ws?.Dispose();
            _cts?.Dispose();
        }
    }
}