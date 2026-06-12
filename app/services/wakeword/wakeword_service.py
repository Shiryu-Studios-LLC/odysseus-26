# services/wakeword/wakeword_service.py
"""Server-side wake word detection using openwakeword + sounddevice.

After detecting the wake word, captures a voice command from the mic,
transcribes it via STT, sends it through the AI chat pipeline, and
plays the TTS response — entirely system-level, no browser required.
"""

import asyncio
import io
import logging
import os
import struct
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "Resoruces"


class WakeWordService:
    """Background wake word detection service."""

    def __init__(self):
        self._model = None
        self._stream = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable] = []
        self._config: dict = {
            "enabled": False,
            "model_path": "",
            "threshold": 0.5,
            "debounce_seconds": 2.0,
            "sample_rate": 16000,
            "chunk_size": 1280,  # 80 ms at 16 kHz
            "vad_threshold": 0.5,
            "noise_suppression": False,
            "voice_capture_enabled": True,   # server-side capture after wake
            "capture_max_seconds": 15,       # max recording length
            "capture_silence_seconds": 2.0,  # stop after this many seconds of silence
            "capture_silence_threshold": 0.01,  # RMS below this = silence
        }
        self._last_detection_time = 0.0
        self._capturing = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── Settings ──────────────────────────────────────────────────────

    def _load_settings(self) -> dict:
        """Read wake word prefs from data/settings.json."""
        try:
            from src.settings import get_setting
            return {
                "enabled": get_setting("wakeword_enabled", False),
                "model_path": get_setting("wakeword_model_path", ""),
                "threshold": float(get_setting("wakeword_threshold", 0.5)),
                "debounce_seconds": float(get_setting("wakeword_debounce", 2.0)),
                "vad_threshold": float(get_setting("wakeword_vad_threshold", 0.5)),
                "noise_suppression": get_setting("wakeword_noise_suppression", True),
                "voice_capture_enabled": get_setting("wakeword_voice_capture", True),
                "capture_max_seconds": int(get_setting("wakeword_capture_max_sec", 15)),
                "capture_silence_seconds": float(get_setting("wakeword_capture_silence_sec", 2.0)),
                "capture_silence_threshold": float(get_setting("wakeword_capture_silence_thresh", 0.01)),
            }
        except Exception:
            return self._config

    def _resolve_model_path(self) -> str:
        """Return absolute path to the ONNX wake word model."""
        raw = self._config.get("model_path", "")
        if raw:
            p = Path(raw)
            if not p.is_absolute():
                p = _MODEL_DIR / p
            if p.exists():
                return str(p)

        # Default location
        for name in ("Shirabi Wakeword.onnx", "shirabi_wakeword.onnx"):
            candidate = _MODEL_DIR / name
            if candidate.exists():
                return str(candidate)
        return ""

    # ── Model ─────────────────────────────────────────────────────────

    def _load_model(self) -> bool:
        try:
            from openwakeword.model import Model as OWWModel
        except ImportError:
            logger.error("openwakeword not installed — run: pip install openwakeword")
            return False

        model_path = self._resolve_model_path()
        if not model_path:
            logger.warning("No wake word ONNX model found — place it in Resoruces/")
            return False

        try:
            # Try with noise suppression first, fall back without it
            ns = self._config.get("noise_suppression", False)
            try:
                self._model = OWWModel(
                    wakeword_models=[model_path],
                    inference_framework="onnx",
                    vad_threshold=self._config.get("vad_threshold", 0.5),
                    enable_speex_noise_suppression=ns,
                )
            except ModuleNotFoundError:
                if ns:
                    logger.info("speexdsp_ns not available — disabling noise suppression")
                    self._model = OWWModel(
                        wakeword_models=[model_path],
                        inference_framework="onnx",
                        vad_threshold=self._config.get("vad_threshold", 0.5),
                        enable_speex_noise_suppression=False,
                    )
                else:
                    raise
            logger.info(f"Wake word model loaded: {model_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load wake word model: {e}")
            return False

    # ── Audio ─────────────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug(f"Audio stream status: {status}")

        audio = (indata[:, 0] * 32767).astype(np.int16)

        if self._model is None:
            return

        prediction = self._model.predict(audio)

        for model_name, score in prediction.items():
            if score >= self._config.get("threshold", 0.5):
                now = time.time()
                if now - self._last_detection_time >= self._config.get("debounce_seconds", 2.0):
                    self._last_detection_time = now
                    logger.info(f"Wake word detected: {model_name} ({score:.3f})")
                    self._fire_callbacks(model_name, float(score))

    def _fire_callbacks(self, wake_word: str, confidence: float):
        for cb in self._callbacks:
            try:
                cb(wake_word, confidence)
            except Exception as e:
                logger.error(f"Wake word callback error: {e}")

        # Server-side voice capture after wake word detection
        if self._config.get("voice_capture_enabled", True) and not self._capturing:
            t = threading.Thread(
                target=self._capture_voice_command,
                args=(wake_word, confidence),
                daemon=True,
                name="wakeword-capture",
            )
            t.start()

    # ── Server-side voice capture ───────────────────────────────────

    def _capture_voice_command(self, wake_word: str, confidence: float):
        """Record audio after wake word, detect silence, transcribe, chat."""
        import sounddevice as sd

        if self._capturing:
            return
        self._capturing = True
        sr = self._config["sample_rate"]
        max_seconds = self._config.get("capture_max_seconds", 15)
        silence_timeout = self._config.get("capture_silence_seconds", 2.0)
        silence_threshold = self._config.get("capture_silence_threshold", 0.01)

        logger.info("[WakeWord] Capturing voice command...")
        audio_chunks = []
        silence_start = None
        start_time = time.time()
        silence_event = threading.Event()

        try:
            time.sleep(0.3)

            def _record_callback(indata, frames, time_info, status):
                nonlocal silence_start
                if status:
                    logger.debug(f"Capture status: {status}")

                audio = indata[:, 0].copy()
                rms = float(np.sqrt(np.mean(audio ** 2)))
                audio_chunks.append(audio.copy())

                elapsed = time.time() - start_time
                if elapsed > 1.0:
                    if rms < silence_threshold:
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start >= silence_timeout:
                            silence_event.set()
                    else:
                        silence_start = None

            with sd.InputStream(
                samplerate=sr,
                channels=1,
                dtype="float32",
                blocksize=self._config.get("chunk_size", 1280),
                callback=_record_callback,
            ):
                # Wait for silence or max duration
                silence_event.wait(timeout=max_seconds)

            if not audio_chunks:
                logger.info("[WakeWord] No audio captured")
                return

            # Concatenate and convert to int16 WAV
            full_audio = np.concatenate(audio_chunks)
            duration = len(full_audio) / sr
            logger.info(f"[WakeWord] Captured {duration:.1f}s of audio")

            # Save as WAV
            wav_path = os.path.join(tempfile.gettempdir(), f"wakeword_capture_{int(time.time())}.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                audio_int16 = (full_audio * 32767).astype(np.int16)
                wf.writeframes(audio_int16.tobytes())

            # Transcribe via STT
            transcript = self._transcribe_audio(wav_path)
            if not transcript:
                logger.info("[WakeWord] No speech detected in captured audio")
                return

            logger.info(f"[WakeWord] Transcribed: {transcript}")

            # Send through chat pipeline
            self._chat_with_transcript(transcript)

        except Exception as e:
            logger.error(f"[WakeWord] Voice capture error: {e}")
        finally:
            self._capturing = False

    def _transcribe_audio(self, wav_path: str) -> str:
        """Transcribe a WAV file using the configured STT provider."""
        import httpx

        try:
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()

            # Use internal tool header to bypass auth
            try:
                from core.middleware import INTERNAL_TOOL_HEADER, INTERNAL_TOOL_TOKEN
                headers = {INTERNAL_TOOL_HEADER: INTERNAL_TOOL_TOKEN}
            except ImportError:
                headers = {}

            # Upload to our own STT endpoint
            files = {"file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")}
            resp = httpx.post(
                "http://127.0.0.1:7000/api/stt/transcribe",
                files=files,
                headers=headers,
                timeout=30.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("text", "").strip()
            else:
                logger.warning(f"[WakeWord] STT returned {resp.status_code}: {resp.text[:200]}")
                return ""
        except Exception as e:
            logger.error(f"[WakeWord] STT error: {e}")
            return ""
        finally:
            # Cleanup temp file
            try:
                os.remove(wav_path)
            except Exception:
                pass

    def _chat_with_transcript(self, text: str):
        """Send transcribed text through the AI chat pipeline and play TTS."""
        import httpx

        try:
            # Use internal tool header to bypass auth
            try:
                from core.middleware import INTERNAL_TOOL_HEADER, INTERNAL_TOOL_TOKEN
                headers = {INTERNAL_TOOL_HEADER: INTERNAL_TOOL_TOKEN}
            except ImportError:
                headers = {}

            # Get default session or create one
            sessions_resp = httpx.get("http://127.0.0.1:7000/api/sessions", headers=headers, timeout=5.0)
            session_id = None
            if sessions_resp.status_code == 200:
                sessions = sessions_resp.json()
                if sessions:
                    session_id = sessions[0].get("id")

            if not session_id:
                # Create a new session
                create_resp = httpx.post("http://127.0.0.1:7000/api/session", headers=headers, timeout=5.0)
                if create_resp.status_code == 200:
                    session_id = create_resp.json().get("id")

            if not session_id:
                logger.error("[WakeWord] Could not create/get session for chat")
                return

            # Send message and get response
            chat_resp = httpx.post(
                "http://127.0.0.1:7000/api/chat",
                json={
                    "session_id": session_id,
                    "message": text,
                    "stream": False,
                },
                headers=headers,
                timeout=60.0,
            )

            if chat_resp.status_code == 200:
                data = chat_resp.json()
                reply = data.get("response", "") or data.get("message", "")
                if reply:
                    logger.info(f"[WakeWord] AI reply: {reply[:100]}...")
                    # Play via TTS
                    self._play_tts(reply)
            else:
                logger.warning(f"[WakeWord] Chat returned {chat_resp.status_code}")

        except Exception as e:
            logger.error(f"[WakeWord] Chat error: {e}")

    def _play_tts(self, text: str):
        """Synthesize speech and play it through the system speakers."""
        import httpx
        import tempfile

        try:
            tts_resp = httpx.post(
                "http://127.0.0.1:7000/api/tts/synthesize",
                json={"text": text},
                timeout=30.0,
            )

            if tts_resp.status_code != 200:
                logger.warning(f"[WakeWord] TTS returned {tts_resp.status_code}")
                return

            # Check if response is audio
            content_type = tts_resp.headers.get("content-type", "")
            if "audio" not in content_type and tts_resp.content[:4] != b"RIFF":
                logger.warning(f"[WakeWord] TTS returned non-audio: {content_type}")
                return

            # Save to temp file and play
            ext = ".wav" if "wav" in content_type or tts_resp.content[:4] == b"RIFF" else ".mp3"
            tts_path = os.path.join(tempfile.gettempdir(), f"wakeword_tts_{int(time.time())}{ext}")
            with open(tts_path, "wb") as f:
                f.write(tts_resp.content)

            logger.info(f"[WakeWord] Playing TTS: {tts_path}")

            # Play with sounddevice (WAV) or winsound (MP3)
            if ext == ".wav":
                import sounddevice as sd
                import soundfile as sf
                data, sr = sf.read(tts_path)
                sd.play(data, sr)
                sd.wait()
            else:
                # Try winsound for MP3
                try:
                    import winsound
                    winsound.PlaySound(tts_path, winsound.SND_FILENAME)
                except Exception:
                    # Fallback: try ffplay or similar
                    os.system(f'start "" "{tts_path}"')

            # Cleanup
            try:
                os.remove(tts_path)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[WakeWord] TTS playback error: {e}")

    def _listen_loop(self):
        try:
            import sounddevice as sd

            self._stream = sd.InputStream(
                samplerate=self._config["sample_rate"],
                channels=1,
                dtype="float32",
                blocksize=self._config["chunk_size"],
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info("Wake word listener started — listening for wake word…")

            while self._running:
                time.sleep(0.2)

        except Exception as e:
            logger.error(f"Wake word listen loop error: {e}")
        finally:
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._config.update(self._load_settings())
        if not self._config.get("enabled", False):
            return
        if not self._load_model():
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="wakeword")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._model is not None:
            try:
                self._model.reset()
            except Exception:
                pass
            self._model = None
        logger.info("Wake word service stopped")

    def restart(self):
        self.stop()
        self.start()

    # ── Public API ────────────────────────────────────────────────────

    def register_callback(self, cb: Callable):
        self._callbacks.append(cb)

    def update_config(self, cfg: dict):
        self._config.update(cfg)
        if self._running:
            self.restart()

    def get_status(self) -> dict:
        model_path = self._resolve_model_path()
        return {
            "enabled": self._config.get("enabled", False),
            "running": self._running,
            "model_path": model_path,
            "model_loaded": self._model is not None,
            "threshold": self._config.get("threshold", 0.5),
            "debounce_seconds": self._config.get("debounce_seconds", 2.0),
            "devices": self._list_devices(),
        }

    @staticmethod
    def _list_devices() -> list[dict]:
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            inputs = []
            for i, d in enumerate(devs):
                if d.get("max_input_channels", 0) > 0:
                    inputs.append({"index": i, "name": d.get("name", ""), "channels": d["max_input_channels"]})
            return inputs
        except Exception:
            return []


# ── Singleton ─────────────────────────────────────────────────────────

_service: Optional[WakeWordService] = None


def get_wakeword_service() -> WakeWordService:
    global _service
    if _service is None:
        _service = WakeWordService()
    return _service
