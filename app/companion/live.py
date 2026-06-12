"""Local live bridge to the Unity companion runtime/editor.

The pairing endpoints in companion.routes expose Shirabi to companion clients.
This module goes the other direction: Shirabi probes local Unity companion
surfaces and forwards commands to whichever target is actually alive.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, HTTPException, Query


@dataclass(frozen=True)
class CompanionTarget:
    key: str
    label: str
    base_url: str
    can_command: bool


TARGETS: dict[str, CompanionTarget] = {
    "runtime": CompanionTarget(
        key="runtime",
        label="Shirabi Companion App",
        base_url="http://127.0.0.1:9878",
        can_command=True,
    ),
    "editor_control": CompanionTarget(
        key="editor_control",
        label="Unity Editor Control",
        base_url="http://127.0.0.1:9877",
        can_command=False,
    ),
    "editor_api": CompanionTarget(
        key="editor_api",
        label="Unity Editor API",
        base_url="http://127.0.0.1:9876",
        can_command=False,
    ),
}

SPEECH_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "tts_cache" / "companion_live"


def probe_target(target: CompanionTarget, timeout: float = 0.35) -> dict[str, Any]:
    """Return a structured health record for one local companion target."""
    url = f"{target.base_url}/api/status"
    try:
        response = httpx.get(url, timeout=timeout, trust_env=False)
        response.raise_for_status()
        try:
            payload: Any = response.json()
        except ValueError:
            payload = {"raw": response.text[:500]}
        return {
            "key": target.key,
            "label": target.label,
            "url": target.base_url,
            "alive": True,
            "can_command": target.can_command,
            "status": payload,
        }
    except httpx.HTTPError as exc:
        return {
            "key": target.key,
            "label": target.label,
            "url": target.base_url,
            "alive": False,
            "can_command": target.can_command,
            "error": exc.__class__.__name__,
        }


def probe_all_targets() -> dict[str, Any]:
    targets = {key: probe_target(target) for key, target in TARGETS.items()}
    preferred = choose_target(targets)
    return {
        "ok": preferred is not None,
        "preferred": preferred,
        "targets": targets,
    }


def choose_target(probe: dict[str, dict[str, Any]] | None = None) -> str | None:
    """Pick the best live target for live avatar control.

    The runtime app is the only target that can drive live avatar state. Editor
    endpoints are still reported for visibility and future editor automation.
    """
    probe = probe or {key: probe_target(target) for key, target in TARGETS.items()}
    runtime = probe.get("runtime")
    if runtime and runtime.get("alive") and runtime.get("can_command"):
        return "runtime"
    for key in ("editor_control", "editor_api"):
        status = probe.get(key)
        if status and status.get("alive"):
            return key
    return None


def command_target(target_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    target = TARGETS.get(target_key)
    if not target:
        raise HTTPException(400, f"Unknown companion target: {target_key}")
    if not target.can_command:
        raise HTTPException(409, f"Target '{target_key}' is visible but does not accept live avatar commands yet")

    try:
        response = httpx.post(
            f"{target.base_url}/api/command",
            json=payload,
            timeout=2.5,
            trust_env=False,
        )
        response.raise_for_status()
        try:
            result: Any = response.json()
        except ValueError:
            result = {"raw": response.text[:1000]}
        return {
            "ok": True,
            "target": target_key,
            "result": result,
        }
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Companion target '{target_key}' command failed: {exc}") from exc


def audio_extension(audio: bytes) -> str:
    if audio.startswith(b"ID3") or audio[:2] == b"\xff\xfb":
        return ".mp3"
    if audio.startswith(b"OggS"):
        return ".ogg"
    return ".wav"


def write_speech_file(text: str, audio: bytes) -> Path:
    if not audio:
        raise HTTPException(502, "TTS returned empty audio")
    SPEECH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(text.encode("utf-8") + b"\0" + audio).hexdigest()[:24]
    path = SPEECH_CACHE_DIR / f"speech_{digest}{audio_extension(audio)}"
    if not path.exists():
        path.write_bytes(audio)
    return path


def _synthesize_with_app_tts(text: str, use_cache: bool) -> bytes | None:
    try:
        from services.tts.tts_service import TTSService

        return TTSService(cache_dir=str(SPEECH_CACHE_DIR)).synthesize(text, use_cache=use_cache)
    except Exception:
        return None


def _synthesize_with_local_gptsovits(text: str) -> bytes | None:
    payload = {
        "refer_wav_path": r"I:\Shirabi26\Resoruces\Elevenlabs\dataset\clip_005.mp3",
        "prompt_text": "Hello again. I have everything ready for your next task.",
        "prompt_language": "en",
        "text": text,
        "text_language": "en",
        "media_type": "wav",
        "streaming_mode": False,
        "speed": 1.0,
    }
    try:
        response = httpx.post(
            "http://127.0.0.1:9880/",
            json=payload,
            timeout=120.0,
            trust_env=False,
        )
        response.raise_for_status()
        return response.content
    except httpx.HTTPError:
        return None


def synthesize_speech_file(text: str, use_cache: bool = True) -> Path:
    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(400, "Missing speech text")

    audio = _synthesize_with_app_tts(cleaned, use_cache)
    if not audio:
        audio = _synthesize_with_local_gptsovits(cleaned)
    if not audio:
        raise HTTPException(502, "Could not synthesize speech audio")

    return write_speech_file(cleaned, audio)


def speak_payload(payload: dict[str, Any], target_key: str = "auto") -> dict[str, Any]:
    audio_path = payload.get("audioPath")
    text = str(payload.get("text") or "").strip()
    if not audio_path:
        audio_path = str(synthesize_speech_file(text, bool(payload.get("useCache", True))))

    target = choose_target() if target_key == "auto" else target_key
    if not target:
        raise HTTPException(503, "No companion runtime target is reachable")

    command = {
        "action": "speak_file",
        "audioPath": str(audio_path),
        "volume": float(payload.get("volume", 1.0)),
        "lookAtUser": bool(payload.get("lookAtUser", True)),
    }
    result = command_target(target, command)
    result["audioPath"] = str(audio_path)
    return result


def register_live_routes(router):
    @router.get("/live/status")
    def live_status():
        """Probe the Unity companion app and editor endpoints."""
        return probe_all_targets()

    @router.post("/live/command")
    def live_command(
        payload: dict[str, Any] = Body(default_factory=dict),
        target: str = Query("auto"),
    ):
        """Forward a live avatar command to the best available local target."""
        if target == "auto":
            target = choose_target()
        if not target:
            raise HTTPException(503, "No companion runtime/editor target is reachable")
        return command_target(target, payload)

    @router.post("/live/speak")
    def live_speak(
        payload: dict[str, Any] = Body(default_factory=dict),
        target: str = Query("auto"),
    ):
        """Synthesize custom-voice speech and hand one local audio file to Unity."""
        return speak_payload(payload, target)
