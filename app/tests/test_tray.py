import os
import sys
import unittest
from unittest.mock import patch

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tray import get_server_address, setup_tray, stop_tray

class TestTrayModule(unittest.TestCase):
    def test_get_server_address_default(self):
        """Test that get_server_address falls back to default values when no args are passed."""
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, 'argv', ['app.py']):
            host, port = get_server_address()
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(port, 7000)

    def test_get_server_address_env(self):
        """Test that get_server_address respects APP_BIND and APP_PORT env vars."""
        with patch.dict(os.environ, {"APP_BIND": "192.168.1.10", "APP_PORT": "8000"}), patch.object(sys, 'argv', ['app.py']):
            host, port = get_server_address()
            self.assertEqual(host, "192.168.1.10")
            self.assertEqual(port, 8000)

    def test_get_server_address_args(self):
        """Test that get_server_address respects command-line args."""
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, 'argv', ['app.py', '--host', '10.0.0.5', '--port', '9000']):
            host, port = get_server_address()
            self.assertEqual(host, "10.0.0.5")
            self.assertEqual(port, 9000)

    def test_get_server_address_args_override_env(self):
        """Test that command-line args override env vars."""
        with patch.dict(os.environ, {"APP_BIND": "192.168.1.10", "APP_PORT": "8000"}), patch.object(sys, 'argv', ['app.py', '--host', '10.0.0.5', '--port', '9000']):
            host, port = get_server_address()
            self.assertEqual(host, "10.0.0.5")
            self.assertEqual(port, 9000)

    def test_get_server_address_wildcard_host(self):
        """Test that 0.0.0.0 is mapped to 127.0.0.1 for browser opening."""
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, 'argv', ['app.py', '--host', '0.0.0.0']):
            host, port = get_server_address()
            self.assertEqual(host, "127.0.0.1")

    def test_setup_and_stop_tray_no_crash(self):
        """Test that setup_tray and stop_tray can be called without raising exceptions."""
        # Even if dependencies are missing, it should just log and return gracefully.
        try:
            setup_tray()
            stop_tray()
        except Exception as e:
            self.fail(f"setup_tray or stop_tray raised an exception: {e}")

if __name__ == "__main__":
    unittest.main()
