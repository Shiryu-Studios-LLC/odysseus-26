import logging
import os
import sys
import threading
import signal
import webbrowser

logger = logging.getLogger(__name__)

# Global reference to the tray icon
_tray_icon = None

def get_server_address():
    """Retrieve host and port from environment or command-line arguments."""
    host = os.environ.get("APP_BIND") or "127.0.0.1"
    port = int(os.environ.get("APP_PORT") or "7000")
    
    # Parse sys.argv for uvicorn options
    for i in range(len(sys.argv) - 1):
        if sys.argv[i] == "--host":
            host = sys.argv[i+1]
        elif sys.argv[i] == "--port":
            try:
                port = int(sys.argv[i+1])
            except ValueError:
                pass
                
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    return display_host, port

def setup_tray():
    """Initialize and run the system tray icon in a daemon thread."""
    global _tray_icon
    if _tray_icon is not None:
        logger.warning("Tray icon is already running.")
        return

    # Gracefully handle missing dependencies (e.g. pystray or PIL)
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError as e:
        logger.info(f"System tray icon disabled: dependencies not met ({e}).")
        return
    except Exception as e:
        logger.warning(f"System tray icon disabled: unexpected initialization error: {e}")
        return

    # Check for headless environment or Docker
    if os.path.exists("/.dockerenv") or os.environ.get("DEBIAN_FRONTEND") == "noninteractive":
        logger.info("System tray icon disabled: running in Docker/headless environment.")
        return

    host, port = get_server_address()
    app_url = f"http://{host}:{port}"

    def get_icon_image():
        # Try to load existing logo
        icon_path = os.path.join(os.path.dirname(__file__), "..", "docs", "odysseus.jpg")
        if os.path.exists(icon_path):
            try:
                return Image.open(icon_path)
            except Exception as e:
                logger.warning(f"Failed to load icon from {icon_path}: {e}")
        
        # Fallback: Create a simple 64x64 icon (sailboat shape matching Odysseus theme)
        img = Image.new("RGB", (64, 64), color="#282c34")
        draw = ImageDraw.Draw(img)
        # Draw a simple sailboat shape in red
        draw.polygon([(32, 10), (32, 44), (12, 44)], fill="#e06c75")
        draw.polygon([(32, 18), (32, 44), (48, 44)], fill="#e06c75")
        draw.line([(8, 48), (56, 48)], fill="#e06c75", width=4)
        return img

    def on_clicked(icon, item):
        if str(item) == "Open Odysseus":
            try:
                webbrowser.open(app_url)
            except Exception as e:
                logger.warning(f"Failed to open browser: {e}")
        elif str(item) == "Exit":
            logger.info("Exit requested from system tray icon.")
            icon.stop()
            # Gracefully trigger shutdown in the main thread
            try:
                if sys.platform == "win32":
                    # For Windows, signal.raise_signal(signal.SIGINT) is supported in Python 3.8+
                    # and will gracefully terminate uvicorn.
                    signal.raise_signal(signal.SIGINT)
                else:
                    os.kill(os.getpid(), signal.SIGINT)
            except Exception as e:
                logger.error(f"Failed to send shutdown signal: {e}")
                # Fallback to immediate exit if signal fails
                os._exit(0)

    try:
        menu = pystray.Menu(
            pystray.MenuItem("Open Odysseus", on_clicked, default=True),
            pystray.MenuItem(f"Running on port {port}", lambda: None, enabled=False),
            pystray.MenuItem("Exit", on_clicked)
        )
        
        _tray_icon = pystray.Icon(
            "odysseus",
            get_icon_image(),
            "Odysseus",
            menu=menu
        )

        # Run the icon's loop in a daemon thread so it doesn't block FastAPI's main thread
        tray_thread = threading.Thread(target=_tray_icon.run, name="OdysseusTrayThread", daemon=True)
        tray_thread.start()
        logger.info(f"System tray icon started. Managing server at {app_url}")
    except Exception as e:
        logger.warning(f"Failed to start system tray icon: {e}")
        _tray_icon = None

def stop_tray():
    """Stop the system tray icon loop."""
    global _tray_icon
    if _tray_icon is not None:
        logger.info("Stopping system tray icon...")
        try:
            _tray_icon.stop()
        except Exception as e:
            logger.debug(f"Failed to stop system tray icon: {e}")
        _tray_icon = None
