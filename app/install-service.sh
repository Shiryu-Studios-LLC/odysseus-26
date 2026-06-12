#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/shirabi-ui.service"

if [ ! -f "$SERVICE_FILE" ]; then
  echo "Error: shirabi-ui.service not found in $SCRIPT_DIR"
  exit 1
fi

echo "Installing Shirabi UI service..."
echo "Make sure you've edited shirabi-ui.service with your username and paths first!"
echo ""

sudo cp "$SERVICE_FILE" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable shirabi-ui
sudo systemctl start shirabi-ui
sudo systemctl status shirabi-ui
