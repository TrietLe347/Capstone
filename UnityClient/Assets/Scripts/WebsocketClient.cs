// Assets/Scripts/WebsocketClient.cs
using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class WebsocketClient : MonoBehaviour
{
    [Header("Connection")]
    [SerializeField] private string uri = "ws://127.0.0.1:8765";

    [Header("Visualization (Optional)")]
    [SerializeField] private bool spawnSpheresForPose = true;
    [SerializeField] private float worldWidth = 6f;
    [SerializeField] private float worldHeight = 4f;
    [SerializeField] private float sphereSize = 0.06f;

    private ClientWebSocket _ws;
    private CancellationTokenSource _cts;
    private readonly ConcurrentQueue<string> _inbox = new ConcurrentQueue<string>();
    private Transform[] _points; // 33 spheres for pose

    // ----- DTOs for JsonUtility -----
    [Serializable] private struct PosePoint { public int id; public float x, y, z; }
    [Serializable] private struct Payload { public PosePoint[] pose; }

    private void Awake()
    {
        if (spawnSpheresForPose)
            CreatePoseSpheres();
    }

    private async void Start()
    {
        _ws = new ClientWebSocket();
        _cts = new CancellationTokenSource();

        try
        {
            await _ws.ConnectAsync(new Uri(uri), _cts.Token);
            Debug.Log($"[WS] Connected: {uri}");
            _ = Task.Run(ReceiveLoop); // background receiver
        }
        catch (Exception e)
        {
            Debug.LogError($"[WS] Connect failed: {e}");
        }
    }

    private void Update()
    {
        while (_inbox.TryDequeue(out var json))
        {
            try
            {
                ApplyFrame(json);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[WS] Frame parse/apply error: {e.Message}");
            }
        }
    }

    private async Task ReceiveLoop()
    {
        byte[] buffer = new byte[1 << 20]; // 1 MB
        var segment = new ArraySegment<byte>(buffer);

        try
        {
            while (_ws.State == WebSocketState.Open && !_cts.IsCancellationRequested)
            {
                var result = await _ws.ReceiveAsync(segment, _cts.Token);

                if (result.MessageType == WebSocketMessageType.Close)
                {
                    Debug.Log("[WS] Server closed");
                    await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", _cts.Token);
                    break;
                }

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

                // Decode as UTF-8 JSON (works for text or binary JSON)
                string json = Encoding.UTF8.GetString(buffer, 0, count);
                _inbox.Enqueue(json);
                Debug.Log($"[WS] Enqueued frame: {count} bytes");
            }
        }
        catch (OperationCanceledException) { /* normal on quit */ }
        catch (Exception e)
        {
            Debug.LogError($"[WS] Receive error: {e}");
        }
    }

    private void ApplyFrame(string json)
    {
        // Show first ~120 chars so we know what arrived
        Debug.Log($"[WS] ApplyFrame: {Mathf.Min(json.Length, 120)} chars -> {json.Substring(0, Mathf.Min(json.Length, 120))}...");

        var payload = JsonUtility.FromJson<Payload>(json);
        if (payload.pose == null)
        {
            Debug.LogWarning("[WS] No 'pose' array in JSON");
            return;
        }

        int n = Mathf.Min(payload.pose.Length, 33);

        // Print a few points regardless of visualization availability


        Debug.Log($"[WS] pt {payload.pose[15].id}  x={payload.pose[15].x:F3}  y={payload.pose[15].y:F3}  z={payload.pose[15].z:F3}");


        // Move spheres only if we created them
        if (_points == null || _points.Length == 0) return;
        n = Mathf.Min(n, _points.Length);

        for (int i = 0; i < n; i++)
        {
            var pt = payload.pose[i];
            float wx = (pt.x - 0.5f) * worldWidth;
            float wy = (0.5f - pt.y) * worldHeight;
            _points[i].localPosition = new Vector3(wx, wy, 0f);
        }
    }

    private void CreatePoseSpheres()
    {
        int count = 33; // MediaPipe BlazePose count
        _points = new Transform[count];
        var parent = new GameObject("PosePoints").transform;
        parent.SetParent(transform, false);

        for (int i = 0; i < count; i++)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            go.name = $"pt_{i}";
            go.transform.SetParent(parent, false);
            go.transform.localScale = Vector3.one * sphereSize;
            var col = go.GetComponent<Collider>();
            if (col) Destroy(col);
            _points[i] = go.transform;
        }
    }

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
        catch { }
        finally
        {
            _ws?.Dispose();
            _cts?.Dispose();
        }
    }
}
