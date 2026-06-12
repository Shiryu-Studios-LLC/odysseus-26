// static/js/wakeword.js

/**
 * Wake word WebSocket client.
 *
 * Connects to the server's wake word detection service and
 * auto-starts mic recording when the wake word is detected.
 */

let _ws = null;
let _onDetection = null;
let _reconnectTimer = null;
let _failCount = 0;
const MAX_RECONNECT_DELAY = 60000;

/**
 * Connect to the wake word WebSocket.
 * @param {function(string, number): void} onDetection - called with (wakeWord, confidence)
 */
export function connect(onDetection) {
  if (_ws && _ws.readyState <= WebSocket.OPEN) return;
  _onDetection = onDetection;

  // Skip WebSocket on remote/tunnel access — they often don't support WS upgrades
  if (location.hostname !== 'localhost' && location.hostname !== '127.0.0.1' && location.hostname !== '0.0.0.0') {
    console.log('[WakeWord] Skipped — remote access detected (' + location.hostname + ')');
    return;
  }

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/api/wakeword/ws`;

  try {
    _ws = new WebSocket(url);
  } catch (e) {
    console.warn('[WakeWord] WebSocket connect failed:', e);
    _scheduleReconnect();
    return;
  }

  _ws.onopen = () => {
    console.log('[WakeWord] Connected');
    _failCount = 0;
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  };

  _ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'detection' && _onDetection) {
        console.log(`[WakeWord] Detected: ${msg.wake_word} (${msg.confidence})`);
        _onDetection(msg.wake_word, msg.confidence);
      }
    } catch (e) {
      console.warn('[WakeWord] Bad message:', e);
    }
  };

  _ws.onclose = () => {
    console.log('[WakeWord] Disconnected');
    _ws = null;
    _scheduleReconnect();
  };

  _ws.onerror = () => {
    _ws?.close();
  };
}

function _scheduleReconnect() {
  if (_reconnectTimer) return;
  _failCount++;
  var delay = Math.min(5000 * Math.pow(1.5, _failCount - 1), MAX_RECONNECT_DELAY);
  _reconnectTimer = setTimeout(() => {
    _reconnectTimer = null;
    connect(_onDetection);
  }, delay);
}

/**
 * Disconnect from the wake word WebSocket.
 */
export function disconnect() {
  if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  if (_ws) { _ws.close(); _ws = null; }
}

/**
 * Send a config update to the server.
 */
export function updateConfig(config) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({ type: 'config', config }));
  }
}

/**
 * Check if connected.
 */
export function isConnected() {
  return _ws !== null && _ws.readyState === WebSocket.OPEN;
}

const wakewordModule = { connect, disconnect, updateConfig, isConnected };
export default wakewordModule;
