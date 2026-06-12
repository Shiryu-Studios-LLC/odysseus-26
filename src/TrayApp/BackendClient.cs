using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text.Json;

namespace ShirabiTray;

/// <summary>
/// Communicates with the Shirabi Python backend via HTTP.
/// Auto-detects the server URL from the port (default 7000).
/// Handles authentication automatically.
/// </summary>
public class BackendClient
{
    private readonly HttpClientHandler _handler;
    private readonly HttpClient _http;
    private int _port = 7000;
    private string BaseUrl => $"http://127.0.0.1:{_port}";
    private bool _authenticated;

    public BackendClient()
    {
        _handler = new HttpClientHandler { CookieContainer = new CookieContainer(), UseCookies = true };
        _http = new HttpClient(_handler) { Timeout = TimeSpan.FromSeconds(5) };
    }

    public int Port
    {
        get => _port;
        set => _port = value;
    }

    private async Task EnsureAuthAsync()
    {
        if (_authenticated) return;
        try
        {
            var body = JsonSerializer.Serialize(new { username = "Shirabi", password = "N29TU57IV#*pR1kn" });
            var content = new StringContent(body, System.Text.Encoding.UTF8, "application/json");
            var resp = await _http.PostAsync($"{BaseUrl}/api/auth/login", content);
            if (resp.IsSuccessStatusCode) _authenticated = true;
        }
        catch { }
    }

    public async Task<bool> GetHealthAsync()
    {
        try
        {
            var resp = await _http.GetAsync($"{BaseUrl}/api/health");
            return resp.IsSuccessStatusCode;
        }
        catch { return false; }
    }

    public async Task<WakewordStatus?> GetWakewordStatusAsync()
    {
        try
        {
            await EnsureAuthAsync();
            var resp = await _http.GetAsync($"{BaseUrl}/api/wakeword/status");
            if (!resp.IsSuccessStatusCode)
            {
                _authenticated = false; // re-auth next time
                return null;
            }
            var json = await resp.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<WakewordStatus>(json,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        }
        catch { return null; }
    }

    public async Task<bool> ToggleWakewordAsync(bool enable)
    {
        try
        {
            await EnsureAuthAsync();
            var endpoint = enable ? "start" : "stop";
            var resp = await _http.PostAsync($"{BaseUrl}/api/wakeword/{endpoint}", null);
            return resp.IsSuccessStatusCode;
        }
        catch { return false; }
    }

    public async Task<string?> ChatAsync(string message, string? sessionId = null)
    {
        try
        {
            await EnsureAuthAsync();
            var body = new Dictionary<string, object> { ["message"] = message, ["stream"] = false };
            if (sessionId != null) body["session_id"] = sessionId;

            var content = new StringContent(
                JsonSerializer.Serialize(body),
                System.Text.Encoding.UTF8, "application/json");

            var resp = await _http.PostAsync($"{BaseUrl}/api/chat", content);
            if (!resp.IsSuccessStatusCode) return null;

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (root.TryGetProperty("response", out var r)) return r.GetString();
            if (root.TryGetProperty("message", out var m)) return m.GetString();
            return null;
        }
        catch { return null; }
    }

    /// <summary>Check if a TCP port is in use (quick health check).</summary>
    public static bool IsPortOpen(int port)
    {
        try
        {
            using var client = new TcpClient();
            var result = client.BeginConnect("127.0.0.1", port, null, null);
            var success = result.AsyncWaitHandle.WaitOne(TimeSpan.FromMilliseconds(500));
            client.EndConnect(result);
            return success;
        }
        catch { return false; }
    }
}

public class WakewordStatus
{
    public bool Enabled { get; set; }
    public bool Running { get; set; }
    public string? ModelPath { get; set; }
    public double Threshold { get; set; }
}
