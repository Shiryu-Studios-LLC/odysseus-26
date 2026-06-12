"""Tests for the local companion live bridge target selection/proxying."""

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import companion.live as live


def _response(url, payload, status=200):
    return httpx.Response(status, request=httpx.Request("GET", url), json=payload)


def test_choose_target_prefers_runtime_when_alive():
    probe = {
        "runtime": {"alive": True, "can_command": True},
        "editor_control": {"alive": True, "can_command": False},
        "editor_api": {"alive": True, "can_command": False},
    }
    assert live.choose_target(probe) == "runtime"


def test_choose_target_falls_back_to_editor_visibility():
    probe = {
        "runtime": {"alive": False, "can_command": True},
        "editor_control": {"alive": True, "can_command": False},
        "editor_api": {"alive": False, "can_command": False},
    }
    assert live.choose_target(probe) == "editor_control"


def test_command_rejects_editor_target():
    with pytest.raises(Exception) as exc:
        live.command_target("editor_control", {"action": "set_bool"})
    assert "does not accept live avatar commands" in str(exc.value)


def test_probe_target_returns_status_payload(monkeypatch):
    def fake_get(url, **kwargs):
        return _response(url, {"mode": "runtime", "ok": True})

    monkeypatch.setattr(live.httpx, "get", fake_get)
    result = live.probe_target(live.TARGETS["runtime"])
    assert result["alive"] is True
    assert result["status"]["mode"] == "runtime"


def test_command_target_posts_payload(monkeypatch):
    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs["json"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"ok": True, "action": "set_bool"},
        )

    monkeypatch.setattr(live.httpx, "post", fake_post)
    result = live.command_target("runtime", {"action": "set_bool", "name": "isSitting", "boolValue": True})
    assert result["ok"] is True
    assert seen["url"].endswith("/api/command")
    assert seen["json"]["name"] == "isSitting"


def test_write_speech_file_uses_stable_audio_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "SPEECH_CACHE_DIR", tmp_path)
    path = live.write_speech_file("hello", b"RIFFfake-wave")

    assert path.suffix == ".wav"
    assert path.exists()
    assert path.read_bytes() == b"RIFFfake-wave"


def test_speak_payload_synthesizes_and_sends_speak_file(monkeypatch, tmp_path):
    seen = {}
    audio_path = tmp_path / "speech.wav"
    audio_path.write_bytes(b"RIFFfake-wave")

    monkeypatch.setattr(live, "synthesize_speech_file", lambda text, use_cache=True: audio_path)
    monkeypatch.setattr(live, "choose_target", lambda: "runtime")

    def fake_command(target_key, payload):
        seen["target"] = target_key
        seen["payload"] = payload
        return {"ok": True, "target": target_key, "result": {"ok": True}}

    monkeypatch.setattr(live, "command_target", fake_command)

    result = live.speak_payload({"text": "hey shirabi", "volume": 0.75, "lookAtUser": True})
    assert result["ok"] is True
    assert result["audioPath"] == str(audio_path)
    assert seen["target"] == "runtime"
    assert seen["payload"]["action"] == "speak_file"
    assert seen["payload"]["audioPath"] == str(audio_path)
    assert seen["payload"]["volume"] == 0.75
    assert seen["payload"]["lookAtUser"] is True


def test_local_gptsovits_fallback_posts_root_payload(monkeypatch):
    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs["json"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            content=b"RIFFfake-wave",
        )

    monkeypatch.setattr(live.httpx, "post", fake_post)
    audio = live._synthesize_with_local_gptsovits("real time test")

    assert audio == b"RIFFfake-wave"
    assert seen["url"] == "http://127.0.0.1:9880/"
    assert seen["json"]["text"] == "real time test"
    assert seen["json"]["media_type"] == "wav"
    assert seen["json"]["streaming_mode"] is False
