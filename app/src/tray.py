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
        # Try to load custom override icon if present (excluding the screenshot docs/odysseus.jpg)
        for logo_name in ["logo.png", "logo.jpg", "favicon.png"]:
            for folder in ["static", "docs"]:
                logo_path = os.path.join(os.path.dirname(__file__), "..", folder, logo_name)
                if os.path.exists(logo_path):
                    try:
                        return Image.open(logo_path)
                    except Exception as e:
                        logger.warning(f"Failed to load logo from {logo_path}: {e}")
        
        # Fallback/Default: Create a beautiful transparent 64x64 icon
        # drawing the official sailboat logo matching the Odysseus theme.
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw left sail (solid red-pink)
        draw.polygon([(32, 8), (32, 44), (12, 44)], fill=(224, 108, 117, 255))
        
        # Draw right sail (semi-transparent red-pink, opacity 0.6)
        draw.polygon([(32, 16), (32, 44), (48, 44)], fill=(224, 108, 117, 153))
        
        # Calculate quadratic Bezier points for the wave boat bottom
        def get_quadratic_bezier_points(p0, p1, p2, steps=20):
            points = []
            for i in range(steps + 1):
                t = i / steps
                x = (1 - t)**2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
                y = (1 - t)**2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
                points.append((x, y))
            return points
            
        curve1 = get_quadratic_bezier_points((8, 48), (20, 40), (32, 48))
        curve2 = get_quadratic_bezier_points((32, 48), (44, 56), (56, 48))
        
        draw.line(curve1, fill=(224, 108, 117, 255), width=5, joint="round")
        draw.line(curve2, fill=(224, 108, 117, 255), width=5, joint="round")
        
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
