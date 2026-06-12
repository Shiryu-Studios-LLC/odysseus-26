"""Native Windows system tray for Shirabi — built with pywin32 + tkinter.

Left-click  → Rich popup panel (status, toggles, progress — like iCloud)
Right-click → Native Win32 context menu
Icon animates in real-time (pulsing, spinning, color changes)
"""

import logging
import math
import os
import sys
import threading
import time
import signal
import webbrowser
import atexit
import ctypes

logger = logging.getLogger(__name__)

# ── Win32 constants ─────────────────────────────────────────────────
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
IDI_APPLICATION = 0x7F00
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
TPM_LEFTBUTTON = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100
SW_HIDE = 0
SW_SHOW = 5
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("hWnd", ctypes.c_void_p),
        ("uID", ctypes.c_uint),
        ("uFlags", ctypes.c_uint),
        ("uCallbackMessage", ctypes.c_uint),
        ("hIcon", ctypes.c_void_p),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.c_uint),
        ("dwStateMask", ctypes.c_uint),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", ctypes.c_uint),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.c_uint),
        ("guidItem", ctypes.c_char * 16),
        ("hBalloonIcon", ctypes.c_void_p),
    ]


# ── State ───────────────────────────────────────────────────────────

_tray_hwnd = None
_tray_icon_handle = None
_popup_window = None
_running = False
_icon_state = "idle"  # idle | listening | processing | speaking | error
_state_lock = threading.Lock()
_frame = 0

_status = {
    "server": False,
    "sovits": False,
    "wakeword": False,
    "wakeword_enabled": False,
    "companion": False,
}


def set_tray_state(state: str):
    global _icon_state
    with _state_lock:
        _icon_state = state


def _get_state():
    with _state_lock:
        return _icon_state


# ── Icon generation (PIL → HICON) ──────────────────────────────────

def _make_hicon(state: str = "idle", frame: int = 0):
    """Create a Windows HICON from state + animation frame."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return ctypes.windll.user32.LoadIconW(None, IDI_APPLICATION)

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = 32, 32

    if state == "idle":
        r, g, b = 160, 160, 170
        draw.ellipse([6, 6, 58, 58], fill=(r, g, b, 40), outline=(r, g, b, 180), width=2)
        draw.polygon([(32, 16), (32, 42), (20, 42)], fill=(r, g, b, 220))
        draw.polygon([(32, 22), (32, 42), (42, 42)], fill=(r, g, b, 140))
        draw.line([(16, 46), (24, 42), (32, 46), (40, 50), (48, 46)], fill=(r, g, b, 180), width=3)

    elif state == "listening":
        r, g, b = 80, 160, 255
        pulse = (math.sin(frame * 0.3) + 1) / 2
        radius = int(24 + 3 * pulse)
        pr = radius + int(4 * pulse)
        draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], outline=(r, g, b, int(80 + 80 * pulse)), width=2)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                      fill=(r, g, b, int(30 + 20 * pulse)), outline=(r, g, b, 200), width=2)
        draw.rounded_rectangle([27, 18, 37, 32], radius=5, fill=(r, g, b, 230))
        draw.arc([23, 28, 41, 42], 0, 180, fill=(r, g, b, 230), width=2)
        draw.line([32, 42, 32, 48], fill=(r, g, b, 230), width=2)
        draw.line([27, 48, 37, 48], fill=(r, g, b, 230), width=2)
        for i in range(3):
            wr = 10 + i * 5 + int(2 * pulse)
            wa = max(0, 180 - i * 60 - int(40 * pulse))
            draw.arc([cx - wr, cy - wr + 6, cx + wr, cy + wr + 6], -35, 35, fill=(r, g, b, wa), width=2)

    elif state == "processing":
        r, g, b = 255, 180, 60
        off = frame * 8
        draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], outline=(r, g, b, 200), width=3)
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(r, g, b, 220))
        for i in range(6):
            rad = math.radians(off + i * 60)
            x1 = cx + 10 * math.cos(rad)
            y1 = cy + 10 * math.sin(rad)
            x2 = cx + 14 * math.cos(rad)
            y2 = cy + 14 * math.sin(rad)
            draw.line([x1, y1, x2, y2], fill=(r, g, b, 200), width=3)

    elif state == "speaking":
        r, g, b = 100, 210, 130
        pulse = (math.sin(frame * 0.4) + 1) / 2
        draw.ellipse([6, 6, 58, 58], fill=(r, g, b, 30), outline=(r, g, b, 160), width=2)
        draw.polygon([(26, 26), (26, 40), (32, 40), (38, 46), (38, 20), (32, 26)], fill=(r, g, b, 230))
        for i in range(3):
            wr = 8 + i * 6 + int(3 * pulse)
            wa = max(0, 200 - i * 70 - int(50 * pulse))
            draw.arc([cx - wr, cy - wr, cx + wr, cy + wr], -40, 40, fill=(r, g, b, wa), width=2)

    elif state == "error":
        r, g, b = 240, 70, 70
        draw.ellipse([6, 6, 58, 58], fill=(r, g, b, 40), outline=(r, g, b, 200), width=2)
        draw.rounded_rectangle([29, 16, 35, 38], radius=2, fill=(r, g, b, 230))
        draw.ellipse([29, 42, 35, 48], fill=(r, g, b, 230))

    # Convert PIL → HICON
    try:
        from PIL import ImageWin
        hdc = ctypes.windll.user32.GetDC(0)
        bmp = ImageWin.Dib(img)
        hicon = ctypes.windll.user32.CreateIconIndirect(bmp)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return hicon
    except Exception:
        return ctypes.windll.user32.LoadIconW(None, IDI_APPLICATION)


def _update_tray_icon():
    """Update the tray icon image."""
    global _tray_icon_handle
    if not _tray_hwnd:
        return
    state = _get_state()
    hicon = _make_hicon(state, _frame)
    nid = NOTIFYICONDATA()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
    nid.hWnd = _tray_hwnd
    nid.uID = 1
    nid.uFlags = NIF_ICON
    nid.hIcon = hicon
    ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
    # Clean up old icon
    if _tray_icon_handle:
        ctypes.windll.user32.DestroyIcon(_tray_icon_handle)
    _tray_icon_handle = hicon


def _set_tray_tooltip(text: str):
    if not _tray_hwnd:
        return
    nid = NOTIFYICONDATA()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
    nid.hWnd = _tray_hwnd
    nid.uID = 1
    nid.uFlags = NIF_TIP
    nid.szTip = text[:127]
    ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))


def _show_notification(title: str, message: str, timeout_ms: int = 3000):
    """Show a Windows balloon notification."""
    if not _tray_hwnd:
        return
    nid = NOTIFYICONDATA()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
    nid.hWnd = _tray_hwnd
    nid.uID = 1
    nid.uFlags = NIF_INFO
    nid.szInfoTitle = title[:63]
    nid.szInfo = message[:255]
    nid.uTimeoutOrVersion = timeout_ms
    nid.dwInfoFlags = 0x01  # NIIF_INFO
    ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))


# ── Win32 tray window procedure ────────────────────────────────────

_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)


def _wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_TRAYICON:
        if lparam == WM_LBUTTONUP:
            _show_popup()
        elif lparam == WM_RBUTTONUP:
            _show_context_menu()
    elif msg == WM_COMMAND:
        cmd = wparam & 0xFFFF
        if cmd == 1001:
            _action_open()
        elif cmd == 1002:
            _action_toggle_wakeword()
        elif cmd == 1003:
            _action_restart_tts()
        elif cmd == 1004:
            _action_restart()
        elif cmd == 1005:
            _action_exit()
    elif msg == WM_DESTROY:
        ctypes.windll.post_quit_message(0)
    return ctypes.windll.def_window_procW(hwnd, msg, wparam, lparam)


_wnd_proc_ptr = _WNDPROC(_wnd_proc)


def _create_hidden_window():
    global _tray_hwnd
    wc = ctypes.wintypes.WNDCLASS()
    wc.lpfnWndProc = _wnd_proc_ptr
    wc.lpszClassName = "ShirabiTray"
    wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
    ctypes.windll.user32.RegisterClassW(ctypes.byref(wc))
    _tray_hwnd = ctypes.windll.user32.CreateWindowExW(
        0, "ShirabiTray", "Shirabi", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, 0)
    if _tray_hwnd:
        style = ctypes.windll.user32.GetWindowLongW(_tray_hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(_tray_hwnd, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW)
        ctypes.windll.user32.ShowWindow(_tray_hwnd, SW_HIDE)
    return _tray_hwnd


def _message_loop():
    """Win32 message pump — required for the tray icon to receive events."""
    msg = ctypes.wintypes.MSG()
    while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
        ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
        ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))


def _add_tray_icon():
    global _tray_icon_handle
    if not _tray_hwnd:
        return
    hicon = _make_hicon("idle")
    _tray_icon_handle = hicon
    nid = NOTIFYICONDATA()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
    nid.hWnd = _tray_hwnd
    nid.uID = 1
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAYICON
    nid.hIcon = hicon
    nid.szTip = "Shirabi — Starting..."
    ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))


def _remove_tray_icon():
    global _tray_icon_handle
    if not _tray_hwnd:
        return
    nid = NOTIFYICONDATA()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
    nid.hWnd = _tray_hwnd
    nid.uID = 1
    ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
    if _tray_icon_handle:
        ctypes.windll.user32.DestroyIcon(_tray_icon_handle)
        _tray_icon_handle = None


# ── Context menu ────────────────────────────────────────────────────

def _show_context_menu():
    hmenu = ctypes.windll.user32.CreatePopupMenu()
    items = [
        (1001, "Open Shirabi"),
        (0, ""),  # separator
        (1002, "Toggle Wake Word"),
        (1003, "Restart TTS"),
        (0, ""),
        (1004, "Restart Shirabi"),
        (1005, "Exit"),
    ]
    for i, (cmd, label) in enumerate(items):
        if not label:
            ctypes.windll.user32.AppendMenuW(hmenu, 0x00000800, 0, "")  # MF_SEPARATOR
        else:
            flags = 0x00000000  # MF_ENABLED
            ctypes.windll.user32.AppendMenuW(hmenu, flags, cmd, label)

    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    ctypes.windll.user32.SetForegroundWindow(_tray_hwnd)
    cmd = ctypes.windll.user32.TrackPopupMenu(
        hmenu, TPM_LEFTBUTTON | TPM_RIGHTBUTTON | TPM_NONOTIFY | TPM_RETURNCMD,
        pt.x, pt.y, 0, _tray_hwnd, 0)
    ctypes.windll.user32.PostMessageW(_tray_hwnd, WM_USER, 0, 0)
    ctypes.windll.user32.DestroyMenu(hmenu)

    if cmd == 1001: _action_open()
    elif cmd == 1002: _action_toggle_wakeword()
    elif cmd == 1003: _action_restart_tts()
    elif cmd == 1004: _action_restart()
    elif cmd == 1005: _action_exit()


# ── Rich popup (tkinter) ───────────────────────────────────────────

def _show_popup():
    """Show the rich status popup panel on left-click."""
    global _popup_window
    if _popup_window and _popup_window.winfo_exists():
        _popup_window.lift()
        _popup_window.focus_force()
        return
    threading.Thread(target=_create_popup, daemon=True).start()


def _create_popup():
    global _popup_window
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#1a1a2e")

    _popup_window = root

    # Position near tray
    try:
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        root.geometry(f"320x380+{pt.x - 280}+{pt.y - 390}")
    except Exception:
        root.geometry("320x380+100+100")

    # Close on focus loss
    def on_focus_out(event):
        if root.focus_get() is None:
            root.destroy()
    root.bind("<FocusOut>", on_focus_out)
    root.bind("<Escape>", lambda e: root.destroy())

    # ── Header ──
    header = tk.Frame(root, bg="#16213e", padx=16, pady=12)
    header.pack(fill="x")
    tk.Label(header, text="Shirabi", font=("Segoe UI", 16, "bold"),
             fg="#e0e0e0", bg="#16213e").pack(anchor="w")
    state_label = {"idle": "Idle", "listening": "Listening", "processing": "Thinking...",
                   "speaking": "Speaking", "error": "Error"}
    tk.Label(header, text=state_label.get(_get_state(), _get_state()),
             font=("Segoe UI", 10), fg="#888888", bg="#16213e").pack(anchor="w")

    # ── Services ──
    svc_frame = tk.Frame(root, bg="#1a1a2e", padx=16, pady=8)
    svc_frame.pack(fill="x")

    def _add_service(parent, label, running, toggle_cb=None):
        row = tk.Frame(parent, bg="#1a1a2e", pady=4)
        row.pack(fill="x")
        dot = "◉" if running else "○"
        color = "#4ade80" if running else "#666666"
        lbl = tk.Label(row, text=f"{dot}  {label}", font=("Segoe UI", 11),
                       fg=color, bg="#1a1a2e", anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        if toggle_cb and not running:
            btn = tk.Button(row, text="Start", font=("Segoe UI", 9), fg="#888888",
                           bg="#2a2a4a", relief="flat", padx=8, pady=2,
                           command=lambda: [toggle_cb(), root.after(100, lambda: _refresh_popup(root))])
            btn.pack(side="right")
        elif toggle_cb and running:
            btn = tk.Button(row, text="Stop", font=("Segoe UI", 9), fg="#ff6b6b",
                           bg="#2a2a4a", relief="flat", padx=8, pady=2,
                           command=lambda: [toggle_cb(), root.after(100, lambda: _refresh_popup(root))])
            btn.pack(side="right")

    _add_service(svc_frame, "Wake Word", _status.get("wakeword", False), _action_toggle_wakeword)
    _add_service(svc_frame, "TTS Voice", _status.get("sovits", False), _action_restart_tts)
    _add_service(svc_frame, "Companion", _status.get("companion", False))

    # ── Separator ──
    tk.Frame(root, bg="#333355", height=1).pack(fill="x", padx=16, pady=4)

    # ── URL ──
    url_frame = tk.Frame(root, bg="#1a1a2e", padx=16, pady=4)
    url_frame.pack(fill="x")
    host, port = get_server_address()
    tunnel = os.environ.get("TUNNEL_URL")
    url = tunnel or f"http://{host}:{port}"
    tk.Label(url_frame, text=url, font=("Segoe UI", 9), fg="#6b8aff", bg="#1a1a2e",
             cursor="hand2").pack(anchor="w")

    # ── Actions ──
    btn_frame = tk.Frame(root, bg="#1a1a2e", padx=16, pady=8)
    btn_frame.pack(fill="x", side="bottom")

    def _styled_btn(parent, text, fg, bg, cb):
        btn = tk.Button(parent, text=text, font=("Segoe UI", 10, "bold"), fg=fg, bg=bg,
                       activebackground=bg, activeforeground=fg, relief="flat",
                       padx=12, pady=6, cursor="hand2", command=cb)
        btn.pack(side="left", padx=4, fill="x", expand=True)
        return btn

    _styled_btn(btn_frame, "Open", "#ffffff", "#3b5998", lambda: [_action_open(), root.destroy()])
    _styled_btn(btn_frame, "Restart", "#ffffff", "#8b5e3c", lambda: [_action_restart()])
    _styled_btn(btn_frame, "Exit", "#ffffff", "#c0392b", lambda: [_action_exit()])


def _refresh_popup(root):
    """Rebuild popup content to reflect new state."""
    # Just destroy and recreate
    try:
        root.destroy()
    except Exception:
        pass
    _show_popup()


# ── Actions ─────────────────────────────────────────────────────────

def _action_open():
    host, port = get_server_address()
    tunnel = os.environ.get("TUNNEL_URL")
    webbrowser.open(tunnel or f"http://{host}:{port}")


def _action_toggle_wakeword():
    try:
        import httpx
        if _status.get("wakeword", False):
            httpx.post("http://127.0.0.1:7000/api/wakeword/stop", timeout=5.0)
            _status["wakeword"] = False
            _status["wakeword_enabled"] = False
        else:
            httpx.post("http://127.0.0.1:7000/api/wakeword/start", timeout=5.0)
            _status["wakeword"] = True
            _status["wakeword_enabled"] = True
    except Exception as e:
        logger.error(f"Wakeword toggle failed: {e}")


def _action_restart_tts():
    stop_gptsovits()
    time.sleep(1)
    start_gptsovits()
    _status["sovits"] = _is_gptsovits_running()


def _action_restart():
    global _running
    _running = False
    _remove_tray_icon()
    stop_gptsovits()
    try:
        import subprocess
        exe = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "Shirabi.exe"))
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        subprocess.Popen([exe], cwd=os.path.dirname(exe),
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                         startupinfo=si, close_fds=True)
    except Exception:
        pass
    os._exit(0)


def _action_exit():
    global _running
    _running = False
    _remove_tray_icon()
    stop_gptsovits()
    try:
        import subprocess
        subprocess.run(["taskkill", "/F", "/IM", "Shirabi Companion.exe"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass
    try:
        signal.raise_signal(signal.SIGINT)
    except Exception:
        os._exit(0)


# ── GPT-SoVITS ─────────────────────────────────────────────────────

_gptsovits_process = None
_gptsovits_base_dir = r"I:\Shirabi26\GPT-SoVITS"
_gptsovits_python = os.path.join(_gptsovits_base_dir, "venv", "Scripts", "pythonw.exe")

if sys.platform == "win32":
    try:
        from ctypes import wintypes
        _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.POINTER(ctypes.c_ulong)), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_uint64), ("WriteOperationCount", ctypes.c_uint64),
                        ("OtherOperationCount", ctypes.c_uint64), ("ReadTransferCount", ctypes.c_uint64),
                        ("WriteTransferCount", ctypes.c_uint64), ("OtherTransferCount", ctypes.c_uint64)]
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        _job_handle = _kernel32.CreateJobObjectW(None, None)
        if _job_handle:
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0x2000
            _kernel32.SetInformationJobObject(_job_handle, 9, ctypes.byref(info), ctypes.sizeof(info))
    except Exception:
        _job_handle = None
else:
    _job_handle = None


def _is_gptsovits_running():
    import subprocess
    try:
        out = subprocess.check_output('netstat -ano | findstr ":9880"', shell=True, text=True, stderr=subprocess.DEVNULL)
        return "LISTENING" in out
    except Exception:
        return False


def _kill_gptsovits():
    import subprocess
    try:
        out = subprocess.check_output('netstat -ano | findstr ":9880"', shell=True, text=True, stderr=subprocess.DEVNULL)
        for line in out.strip().split("\n"):
            if "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


def _kill_child_processes():
    import subprocess
    try:
        pid = os.getpid()
        out = subprocess.check_output(f"wmic process where ParentProcessId={pid} get ProcessId",
                                       shell=True, text=True, stderr=subprocess.DEVNULL)
        for line in out.strip().split("\n"):
            line = line.strip()
            if line.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", line], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


def start_gptsovits():
    global _gptsovits_process
    if _is_gptsovits_running():
        return
    if not os.path.exists(_gptsovits_python):
        return
    import subprocess
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    try:
        _gptsovits_process = subprocess.Popen(
            [_gptsovits_python, "api.py"], cwd=_gptsovits_base_dir,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), startupinfo=si)
        if _job_handle and sys.platform == "win32":
            try:
                h = ctypes.windll.kernel32.OpenProcess(0x0001 | 0x0100, False, _gptsovits_process.pid)
                if h:
                    ctypes.windll.kernel32.AssignProcessToJobObject(_job_handle, h)
                    ctypes.windll.kernel32.CloseHandle(h)
            except Exception:
                pass
    except Exception:
        _gptsovits_process = None


def stop_gptsovits():
    global _gptsovits_process
    if _gptsovits_process:
        try:
            _gptsovits_process.kill()
        except Exception:
            pass
        _gptsovits_process = None
    _kill_gptsovits()
    _kill_child_processes()


atexit.register(stop_gptsovits)


def get_server_address():
    host = os.environ.get("APP_BIND") or "127.0.0.1"
    port = int(os.environ.get("APP_PORT") or "7000")
    for i in range(len(sys.argv) - 1):
        if sys.argv[i] == "--host":
            host = sys.argv[i + 1]
        elif sys.argv[i] == "--port":
            try:
                port = int(sys.argv[i + 1])
            except ValueError:
                pass
    return ("127.0.0.1" if host == "0.0.0.0" else host), port


# ── Background threads ──────────────────────────────────────────────

def _animation_thread():
    global _frame
    while _running:
        state = _get_state()
        if state not in ("idle", "error"):
            _frame += 1
            _update_tray_icon()
            time.sleep(0.1)
        else:
            time.sleep(0.5)


def _health_thread():
    while _running:
        time.sleep(3)

        try:
            import httpx
            r = httpx.get("http://127.0.0.1:7000/api/health", timeout=3.0)
            _status["server"] = r.status_code == 200
        except Exception:
            _status["server"] = False

        _status["sovits"] = _is_gptsovits_running()

        try:
            import httpx
            r = httpx.get("http://127.0.0.1:7000/api/wakeword/status", timeout=3.0)
            if r.status_code == 200:
                data = r.json()
                _status["wakeword"] = data.get("running", False)
                _status["wakeword_enabled"] = data.get("enabled", False)
        except Exception:
            _status["wakeword"] = False

        try:
            import subprocess
            out = subprocess.check_output('tasklist /FI "IMAGENAME eq Shirabi Companion.exe"',
                                           shell=True, text=True, stderr=subprocess.DEVNULL)
            _status["companion"] = "Shirabi Companion.exe" in out
        except Exception:
            _status["companion"] = False

        # Update tooltip
        parts = []
        parts.append("Server ✓" if _status["server"] else "Server ✕")
        parts.append("TTS ✓" if _status["sovits"] else "TTS ✕")
        parts.append("Listening" if _status["wakeword"] else "Wake Off")
        _set_tray_tooltip(f"Shirabi — {' | '.join(parts)}")

        # Update state
        if not _status["server"]:
            new_state = "error"
        elif _status["wakeword"]:
            new_state = "listening"
        else:
            new_state = "idle"

        set_tray_state(new_state)
        _update_tray_icon()


# ── Setup ───────────────────────────────────────────────────────────

def setup_tray():
    global _running
    if _running:
        return

    if os.path.exists("/.dockerenv") or os.environ.get("DEBIAN_FRONTEND") == "noninteractive":
        logger.info("System tray disabled: Docker/headless")
        return

    start_gptsovits()

    if not _create_hidden_window():
        logger.warning("Failed to create tray window")
        return

    _add_tray_icon()
    _running = True

    # Win32 message pump (required for tray icon events)
    threading.Thread(target=_message_loop, name="TrayMsg", daemon=True).start()
    threading.Thread(target=_animation_thread, name="TrayAnim", daemon=True).start()
    threading.Thread(target=_health_thread, name="TrayHealth", daemon=True).start()

    logger.info("Native Windows tray started")


def stop_tray():
    global _running
    _running = False
    _remove_tray_icon()
    stop_gptsovits()
