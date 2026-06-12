using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Windows.Forms;

namespace ShirabiTray;

/// <summary>
/// Manages the system tray icon, animation, health polling, and process lifecycle.
/// Single source of truth for the tray — replaces both Python tray.py and Companion tray.
/// </summary>
public class TrayManager
{
    private readonly BackendClient _backend = new();
    private NotifyIcon? _notifyIcon;
    private System.Windows.Forms.Timer? _healthTimer;
    private System.Windows.Forms.Timer? _animationTimer;

    private TrayState _state = TrayState.Idle;
    private int _animationFrame;
    // Live status
    private bool _serverOk;
    private bool _sovitsOk;
    private bool _wakewordRunning;
    private bool _companionRunning;

    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(3) };

    // ── Process management ──────────────────────────────────────────
    private Process? _gptsovitsProcess;

    public void Start()
    {
        CreateNotifyIcon();
        StartGptSoVits();
        StartAnimation();
        StartHealthPolling();

        // Update icon immediately
        UpdateIcon(TrayState.Idle);
        UpdateTooltip("Shirabi — Starting...");
    }

    public void Stop()
    {
        StopGptSoVits();
        KillCompanion();
        _healthTimer?.Stop();
        _animationTimer?.Stop();
        if (_notifyIcon != null)
        {
            _notifyIcon.Visible = false;
            _notifyIcon.Dispose();
        }
    }

    // ── NotifyIcon ──────────────────────────────────────────────────

    private void CreateNotifyIcon()
    {
        _notifyIcon = new NotifyIcon
        {
            Visible = true,
            Text = "Shirabi — Starting..."
        };

        _notifyIcon.MouseClick += OnTrayClick;
        _notifyIcon.DoubleClick += (_, _) => ShowPopup();
    }

    private void OnTrayClick(object? sender, MouseEventArgs e)
    {
        if (e.Button == MouseButtons.Right)
        {
            ShowContextMenu();
        }
    }

    // ── Icon updates ────────────────────────────────────────────────

    private void UpdateIcon(TrayState state)
    {
        _state = state;
        try
        {
            var icon = IconGenerator.MakeIcon(state, _animationFrame);
            _notifyIcon?.Icon?.Dispose();
            _notifyIcon!.Icon = icon;
        }
        catch { }
    }

    private void UpdateTooltip(string text)
    {
        if (_notifyIcon != null)
            _notifyIcon.Text = text.Length > 127 ? text[..127] : text;
    }

    // ── Animation ───────────────────────────────────────────────────

    private void StartAnimation()
    {
        _animationTimer = new System.Windows.Forms.Timer { Interval = 100 }; // 10 FPS
        _animationTimer.Tick += (_, _) =>
        {
            if (_state is TrayState.Listening or TrayState.Processing or TrayState.Speaking)
            {
                _animationFrame++;
                UpdateIcon(_state);
            }
        };
        _animationTimer.Start();
    }

    // ── Health polling ──────────────────────────────────────────────

    private void StartHealthPolling()
    {
        _healthTimer = new System.Windows.Forms.Timer { Interval = 3000 };
        _healthTimer.Tick += async (_, _) => await PollHealth();
        _healthTimer.Start();
        _ = PollHealth(); // immediate first check
    }

    private async Task PollHealth()
    {
        // Server health
        _serverOk = await _backend.GetHealthAsync();

        // GPT-SoVITS (check port)
        _sovitsOk = BackendClient.IsPortOpen(9880);

        // Wake word
        try
        {
            var wk = await _backend.GetWakewordStatusAsync();
            _wakewordRunning = wk?.Running ?? false;
        }
        catch { _wakewordRunning = false; }

        // Companion
        try
        {
            var procs = Process.GetProcessesByName("Shirabi Companion");
            _companionRunning = procs.Length > 0;
        }
        catch { _companionRunning = false; }

        // Update state
        TrayState newState;
        if (!_serverOk)
            newState = TrayState.Error;
        else if (_wakewordRunning)
            newState = TrayState.Listening;
        else
            newState = TrayState.Idle;

        if (newState != _state)
            UpdateIcon(newState);

        // Tooltip
        var parts = new List<string>();
        parts.Add(_serverOk ? "Server ✓" : "Server ✕");
        parts.Add(_sovitsOk ? "TTS ✓" : "TTS ✕");
        parts.Add(_wakewordRunning ? "Listening" : "Wake Off");
        UpdateTooltip($"Shirabi — {string.Join(" | ", parts)}");
    }

    // ── Context menu (right-click) ──────────────────────────────────

    private void ShowContextMenu()
    {
        var menu = new ContextMenuStrip();

        // Status header
        var stateLabel = _state switch
        {
            TrayState.Listening => "◉  Listening",
            TrayState.Processing => "◎  Thinking...",
            TrayState.Speaking => "♪  Speaking",
            TrayState.Error => "✕  Error",
            _ => "○  Idle"
        };
        var stateItem = new ToolStripMenuItem(stateLabel) { Enabled = false };
        menu.Items.Add(stateItem);

        var ttsItem = new ToolStripMenuItem(_sovitsOk ? "◉  TTS — Running" : "○  TTS — Stopped") { Enabled = false };
        menu.Items.Add(ttsItem);
        menu.Items.Add(new ToolStripSeparator());

        // Open Shirabi
        menu.Items.Add(new ToolStripMenuItem("Open Shirabi", null, (_, _) => OpenShirabi()));

        // Toggle wake word
        var wkLabel = _wakewordRunning ? "Stop Wake Word" : "Start Wake Word";
        menu.Items.Add(new ToolStripMenuItem(wkLabel, null, async (_, _) =>
        {
            await _backend.ToggleWakewordAsync(!_wakewordRunning);
        }));

        // Companion
        var compLabel = _companionRunning ? "Companion — Running" : "Launch Companion";
        menu.Items.Add(new ToolStripMenuItem(compLabel, null, (_, _) => LaunchCompanion()));

        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(new ToolStripMenuItem("Restart TTS", null, (_, _) => RestartGptSoVits()));
        menu.Items.Add(new ToolStripMenuItem("Restart Shirabi", null, (_, _) => RestartShirabi()));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(new ToolStripMenuItem("Exit", null, (_, _) => ExitAll()));

        _notifyIcon!.ContextMenuStrip = menu;
        menu.Show(Cursor.Position);
    }

    // ── Popup panel (left-click) ────────────────────────────────────

    private void ShowPopup()
    {
        try
        {
            var popup = new PopupForm(this);
            popup.Show();
        }
        catch (Exception ex)
        {
            ShowNotification("Shirabi", $"Popup error: {ex.Message}", 3000);
        }
    }

    // ── Actions ─────────────────────────────────────────────────────

    public void OpenShirabi()
    {
        try
        {
            var url = "http://127.0.0.1:7000";
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        catch { }
    }

    public async Task<bool> ToggleWakewordAsync()
    {
        var result = await _backend.ToggleWakewordAsync(!_wakewordRunning);
        await PollHealth();
        return result;
    }

    public void LaunchCompanion()
    {
        var path = Paths.CompanionExe;
        if (!File.Exists(path))
        {
            ShowNotification("Shirabi", "Companion not found. Build it first.", 3000);
            return;
        }

        try
        {
            var procs = Process.GetProcessesByName("Shirabi Companion");
            if (procs.Length > 0)
            {
                ShowNotification("Shirabi", "Companion is already running.", 2000);
                return;
            }

            Process.Start(new ProcessStartInfo
            {
                FileName = path,
                UseShellExecute = false,
                CreateNoWindow = true,
            });
        }
        catch (Exception ex)
        {
            ShowNotification("Shirabi", $"Failed to launch Companion: {ex.Message}", 5000);
        }
    }

    public void RestartGptSoVits()
    {
        StopGptSoVits();
        Thread.Sleep(1000);
        StartGptSoVits();
        PollHealth().Wait();
    }

    public void RestartShirabi()
    {
        StopGptSoVits();
        KillCompanion();

        var exe = Path.Combine(Paths.Root, "Shirabi.exe");
        if (File.Exists(exe))
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = exe,
                WorkingDirectory = Paths.Root,
                UseShellExecute = false,
                CreateNoWindow = true,
            });
        }

        Environment.Exit(0);
    }

    public void ExitAll()
    {
        StopGptSoVits();
        KillCompanion();
        Environment.Exit(0);
    }

    // ── GPT-SoVITS process ─────────────────────────────────────────

    private void StartGptSoVits()
    {
        if (BackendClient.IsPortOpen(9880)) return;

        var python = Paths.GptSoVitsPython;
        var apiScript = Paths.GptSoVitsApiScript;
        var workDir = Paths.GptSoVitsDir;

        if (python == null || apiScript == null || workDir == null)
        {
            ShowNotification("Shirabi", "GPT-SoVITS not found. TTS unavailable.", 5000);
            return;
        }

        try
        {
            _gptsovitsProcess = Process.Start(new ProcessStartInfo
            {
                FileName = python,
                Arguments = "-s api.py",
                WorkingDirectory = workDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            });
        }
        catch (Exception ex)
        {
            ShowNotification("Shirabi", $"Failed to start TTS: {ex.Message}", 5000);
        }
    }

    private void StopGptSoVits()
    {
        try
        {
            _gptsovitsProcess?.Kill();
            _gptsovitsProcess = null;
        }
        catch { }

        // Kill by port
        try
        {
            var output = RunCommand("netstat -ano | findstr :9880");
            foreach (var line in output.Split('\n'))
            {
                if (line.Contains("LISTENING"))
                {
                    var parts = line.Trim().Split(' ');
                    var pid = parts[^1];
                    RunCommand($"taskkill /F /PID {pid}");
                }
            }
        }
        catch { }
    }

    private void KillCompanion()
    {
        try { RunCommand("taskkill /F /IM \"Shirabi Companion.exe\""); } catch { }
    }

    // ── Helpers ─────────────────────────────────────────────────────

    public void ShowNotification(string title, string message, int timeoutMs = 3000)
    {
        _notifyIcon?.ShowBalloonTip(timeoutMs, title, message, ToolTipIcon.Info);
    }

    private static string RunCommand(string cmd)
    {
        var psi = new ProcessStartInfo("cmd.exe", $"/c {cmd}")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            CreateNoWindow = true,
        };
        using var proc = Process.Start(psi)!;
        return proc.StandardOutput.ReadToEnd();
    }

    // Expose status for PopupWindow
    public bool ServerOk => _serverOk;
    public bool SovitsOk => _sovitsOk;
    public bool WakewordRunning => _wakewordRunning;
    public bool CompanionRunning => _companionRunning;
    public TrayState CurrentState => _state;
    public BackendClient Backend => _backend;
}
