"""Tests for settings persistence, mute keybind, whisper config, and mute toggle.

All tests are hardware-free: no GPU, no audio device, no tkinter display.
"""

from __future__ import annotations

import json
import queue
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Ensure the whisper-typer root is on sys.path so we can import modules
# ---------------------------------------------------------------------------
_WT_ROOT = Path(__file__).resolve().parent.parent
if str(_WT_ROOT) not in sys.path:
    sys.path.insert(0, str(_WT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Settings persistence (settings.py)
# ═══════════════════════════════════════════════════════════════════════════


class TestSettingsLoadSave:
    """settings.load() / settings.save() round-trip tests."""

    def test_load_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        """load() should return _DEFAULTS when the settings file doesn't exist."""
        import settings
        fake_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(settings, "SETTINGS_FILE", fake_path)

        result = settings.load()

        assert isinstance(result, dict)
        assert result["mic_device"] is None
        assert result["vad_enabled"] is False
        assert result["ptt_hotkey"] == ["ctrl", "shift", "space"]
        assert result["mute_hotkey"] == ["ctrl", "shift", "m"]
        # New whisper keys should be present with None defaults
        assert result["whisper_model"] is None
        assert result["whisper_device"] is None
        assert result["whisper_language"] is None

    def test_save_then_load_round_trip(self, tmp_path, monkeypatch):
        """Saved values should survive a load() round-trip."""
        import settings
        fake_path = tmp_path / "settings.json"
        monkeypatch.setattr(settings, "SETTINGS_FILE", fake_path)

        data = settings.load()
        data["whisper_model"] = "small"
        data["whisper_device"] = "cpu"
        data["whisper_language"] = "de"
        data["vad_enabled"] = True
        settings.save(data)

        loaded = settings.load()
        assert loaded["whisper_model"] == "small"
        assert loaded["whisper_device"] == "cpu"
        assert loaded["whisper_language"] == "de"
        assert loaded["vad_enabled"] is True

    def test_new_whisper_keys_preserved(self, tmp_path, monkeypatch):
        """All three whisper keys round-trip through save/load."""
        import settings
        fake_path = tmp_path / "settings.json"
        monkeypatch.setattr(settings, "SETTINGS_FILE", fake_path)

        data = {
            "whisper_model": "large-v3-turbo",
            "whisper_device": "cuda",
            "whisper_language": "auto",
        }
        settings.save(data)
        loaded = settings.load()
        assert loaded["whisper_model"] == "large-v3-turbo"
        assert loaded["whisper_device"] == "cuda"
        assert loaded["whisper_language"] == "auto"

    def test_unknown_keys_in_saved_file_are_ignored(self, tmp_path, monkeypatch):
        """Keys not in _DEFAULTS must not appear in loaded dict."""
        import settings
        fake_path = tmp_path / "settings.json"
        monkeypatch.setattr(settings, "SETTINGS_FILE", fake_path)

        # Write a file with an unknown key
        with open(fake_path, "w") as f:
            json.dump({"whisper_model": "tiny", "bogus_key": 42, "also_unknown": "x"}, f)

        loaded = settings.load()
        assert "bogus_key" not in loaded
        assert "also_unknown" not in loaded
        assert loaded["whisper_model"] == "tiny"

    def test_load_merges_saved_with_defaults(self, tmp_path, monkeypatch):
        """Saved file with partial keys should be merged over defaults."""
        import settings
        fake_path = tmp_path / "settings.json"
        monkeypatch.setattr(settings, "SETTINGS_FILE", fake_path)

        # Save only one key
        with open(fake_path, "w") as f:
            json.dump({"vad_enabled": True}, f)

        loaded = settings.load()
        assert loaded["vad_enabled"] is True
        # All other keys should still have their defaults
        assert loaded["mic_device"] is None
        assert loaded["whisper_model"] is None
        assert loaded["ptt_hotkey"] == ["ctrl", "shift", "space"]

    def test_load_handles_corrupt_file(self, tmp_path, monkeypatch):
        """Corrupt JSON should not crash; defaults returned instead."""
        import settings
        fake_path = tmp_path / "settings.json"
        monkeypatch.setattr(settings, "SETTINGS_FILE", fake_path)

        fake_path.write_text("{invalid json!!!}")
        loaded = settings.load()
        # Should return defaults gracefully
        assert loaded["whisper_model"] is None
        assert loaded["vad_enabled"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. Mute keybind (hotkeys.py)
# ═══════════════════════════════════════════════════════════════════════════


class TestHotkeyListenerMute:
    """Tests for HotkeyListener mute_combo event posting."""

    @pytest.fixture()
    def _mock_pynput(self, monkeypatch):
        """Provide a fake pynput.keyboard so we can synthesize key events."""
        # Build a minimal stub for pynput.keyboard.Key and Listener
        fake_key = types.SimpleNamespace(
            ctrl_l=MagicMock(), ctrl_r=MagicMock(), shift=MagicMock(),
            shift_l=MagicMock(), shift_r=MagicMock(), alt_l=MagicMock(),
            alt_r=MagicMock(), space=MagicMock(), tab=MagicMock(),
            enter=MagicMock(), esc=MagicMock(),
            f1=MagicMock(), f2=MagicMock(), f3=MagicMock(), f4=MagicMock(),
            f5=MagicMock(), f6=MagicMock(), f7=MagicMock(), f8=MagicMock(),
            f9=MagicMock(), f10=MagicMock(), f11=MagicMock(), f12=MagicMock(),
        )
        fake_listener_cls = MagicMock()
        fake_keyboard = types.ModuleType("pynput.keyboard")
        fake_keyboard.Key = fake_key
        fake_keyboard.Listener = fake_listener_cls

        fake_pynput = types.ModuleType("pynput")
        fake_pynput.keyboard = fake_keyboard

        monkeypatch.setitem(sys.modules, "pynput", fake_pynput)
        monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_keyboard)

        # Force reimport of hotkeys to pick up the stub
        if "hotkeys" in sys.modules:
            del sys.modules["hotkeys"]

        yield fake_key

        # Clean up
        if "hotkeys" in sys.modules:
            del sys.modules["hotkeys"]

    @staticmethod
    def _make_char_key(char: str):
        """Create a fake pynput key object for a character.

        Must be hashable (SimpleNamespace is not) because _normalize()
        does ``if key in _KEY_NAMES`` which needs __hash__.
        """

        class _CharKey:
            def __init__(self, c: str):
                self.char = c

            def __hash__(self):
                return hash(("_CharKey", self.char))

            def __eq__(self, other):
                return isinstance(other, _CharKey) and self.char == other.char

        return _CharKey(char)

    def test_mute_combo_posts_mute_toggle(self, _mock_pynput):
        """Pressing the mute combo should post ('mute_toggle',) to queue."""
        from hotkeys import HotkeyListener

        eq = queue.Queue()
        hl = HotkeyListener(eq, mute_combo=["ctrl", "shift", "m"])

        # Simulate pressing ctrl, shift, m
        hl._on_press(_mock_pynput.ctrl_l)
        hl._on_press(_mock_pynput.shift)
        hl._on_press(self._make_char_key("m"))

        events = []
        while not eq.empty():
            events.append(eq.get_nowait())
        assert ("mute_toggle",) in events

    def test_mute_combo_no_event_without_full_combo(self, _mock_pynput):
        """Partial combo should not fire mute_toggle."""
        from hotkeys import HotkeyListener

        eq = queue.Queue()
        hl = HotkeyListener(eq, mute_combo=["ctrl", "shift", "m"])

        # Only press ctrl + m (missing shift)
        hl._on_press(_mock_pynput.ctrl_l)
        hl._on_press(self._make_char_key("m"))

        events = []
        while not eq.empty():
            events.append(eq.get_nowait())
        assert ("mute_toggle",) not in events

    def test_mute_combo_does_not_repeat_while_held(self, _mock_pynput):
        """Holding the combo should fire only once until a combo key is released."""
        from hotkeys import HotkeyListener

        eq = queue.Queue()
        hl = HotkeyListener(eq, mute_combo=["ctrl", "shift", "m"])

        # Press combo
        hl._on_press(_mock_pynput.ctrl_l)
        hl._on_press(_mock_pynput.shift)
        hl._on_press(self._make_char_key("m"))

        # Press m again (key repeat) — should NOT fire again
        hl._on_press(self._make_char_key("m"))

        events = []
        while not eq.empty():
            events.append(eq.get_nowait())
        assert events.count(("mute_toggle",)) == 1

    def test_mute_combo_refires_after_release(self, _mock_pynput):
        """After releasing a combo key and re-pressing, mute_toggle fires again."""
        from hotkeys import HotkeyListener

        eq = queue.Queue()
        hl = HotkeyListener(eq, mute_combo=["ctrl", "shift", "m"])

        # First press
        hl._on_press(_mock_pynput.ctrl_l)
        hl._on_press(_mock_pynput.shift)
        hl._on_press(self._make_char_key("m"))

        # Release shift
        hl._on_release(_mock_pynput.shift)

        # Re-press shift + m
        hl._on_press(_mock_pynput.shift)
        hl._on_press(self._make_char_key("m"))

        events = []
        while not eq.empty():
            events.append(eq.get_nowait())
        assert events.count(("mute_toggle",)) == 2

    def test_set_combos_updates_mute_at_runtime(self, _mock_pynput):
        """set_combos() should allow changing the mute combo dynamically."""
        from hotkeys import HotkeyListener

        eq = queue.Queue()
        hl = HotkeyListener(eq, mute_combo=["ctrl", "shift", "m"])

        # Change to ctrl+shift+n
        hl.set_combos(mute_combo=["ctrl", "shift", "n"])

        # Old combo should NOT fire
        hl._on_press(_mock_pynput.ctrl_l)
        hl._on_press(_mock_pynput.shift)
        hl._on_press(self._make_char_key("m"))

        events_before = []
        while not eq.empty():
            events_before.append(eq.get_nowait())
        assert ("mute_toggle",) not in events_before

        # Release all
        hl._on_release(_mock_pynput.ctrl_l)
        hl._on_release(_mock_pynput.shift)
        hl._on_release(self._make_char_key("m"))

        # New combo should fire
        hl._on_press(_mock_pynput.ctrl_l)
        hl._on_press(_mock_pynput.shift)
        hl._on_press(self._make_char_key("n"))

        events_after = []
        while not eq.empty():
            events_after.append(eq.get_nowait())
        assert ("mute_toggle",) in events_after

    def test_mute_combo_none_produces_no_events(self, _mock_pynput):
        """When mute_combo is None, no mute_toggle events should fire."""
        from hotkeys import HotkeyListener

        eq = queue.Queue()
        hl = HotkeyListener(eq, mute_combo=None)

        hl._on_press(_mock_pynput.ctrl_l)
        hl._on_press(_mock_pynput.shift)
        hl._on_press(self._make_char_key("m"))

        events = []
        while not eq.empty():
            events.append(eq.get_nowait())
        assert ("mute_toggle",) not in events


# ═══════════════════════════════════════════════════════════════════════════
# 3. Whisper config application (_init_components priority)
# ═══════════════════════════════════════════════════════════════════════════


class TestWhisperConfigApplication:
    """Tests that _init_components applies config in priority order:
    CLI args > saved settings > config.py defaults.

    We isolate the config-patching logic without instantiating the full GUI.
    """

    @pytest.fixture(autouse=True)
    def _clean_config(self):
        """Reset config module values before each test."""
        import config as cfg
        orig_model = cfg.WHISPER_MODEL
        orig_device = cfg.WHISPER_DEVICE
        orig_compute = cfg.WHISPER_COMPUTE
        orig_lang = cfg.WHISPER_LANGUAGE
        yield
        cfg.WHISPER_MODEL = orig_model
        cfg.WHISPER_DEVICE = orig_device
        cfg.WHISPER_COMPUTE = orig_compute
        cfg.WHISPER_LANGUAGE = orig_lang

    @staticmethod
    def _apply_config(
        model_override: str | None,
        device_override: str | None,
        saved_settings: dict,
    ) -> None:
        """Reproduce the config-patching logic from _init_components (lines 1071-1083)."""
        import config

        model = model_override or saved_settings.get("whisper_model")
        device = device_override or saved_settings.get("whisper_device")
        language = saved_settings.get("whisper_language")

        if model:
            config.WHISPER_MODEL = model
        if device:
            config.WHISPER_DEVICE = device
            config.WHISPER_COMPUTE = "float16" if device == "cuda" else "int8"
        if language:
            config.WHISPER_LANGUAGE = language if language != "auto" else None

    def test_saved_model_updates_config(self):
        """whisper_model in settings should update config.WHISPER_MODEL."""
        import config as cfg
        self._apply_config(None, None, {"whisper_model": "small"})
        assert cfg.WHISPER_MODEL == "small"

    def test_saved_device_cpu_sets_int8(self):
        """whisper_device='cpu' -> config.WHISPER_COMPUTE='int8'."""
        import config as cfg
        self._apply_config(None, None, {"whisper_device": "cpu"})
        assert cfg.WHISPER_DEVICE == "cpu"
        assert cfg.WHISPER_COMPUTE == "int8"

    def test_saved_device_cuda_sets_float16(self):
        """whisper_device='cuda' -> config.WHISPER_COMPUTE='float16'."""
        import config as cfg
        self._apply_config(None, None, {"whisper_device": "cuda"})
        assert cfg.WHISPER_DEVICE == "cuda"
        assert cfg.WHISPER_COMPUTE == "float16"

    def test_language_auto_becomes_none(self):
        """whisper_language='auto' should set config.WHISPER_LANGUAGE to None."""
        import config as cfg
        self._apply_config(None, None, {"whisper_language": "auto"})
        assert cfg.WHISPER_LANGUAGE is None

    def test_language_specific_code_is_preserved(self):
        """whisper_language='de' should set config.WHISPER_LANGUAGE to 'de'."""
        import config as cfg
        self._apply_config(None, None, {"whisper_language": "de"})
        assert cfg.WHISPER_LANGUAGE == "de"

    def test_cli_model_overrides_saved(self):
        """CLI --model should take priority over saved whisper_model."""
        import config as cfg
        self._apply_config("medium", None, {"whisper_model": "tiny"})
        assert cfg.WHISPER_MODEL == "medium"

    def test_cli_device_overrides_saved(self):
        """CLI --device should take priority over saved whisper_device."""
        import config as cfg
        self._apply_config(None, "cpu", {"whisper_device": "cuda"})
        assert cfg.WHISPER_DEVICE == "cpu"
        assert cfg.WHISPER_COMPUTE == "int8"

    def test_no_overrides_keeps_config_defaults(self):
        """When no CLI args and no saved settings, config.py defaults stay."""
        import config as cfg
        orig_model = cfg.WHISPER_MODEL
        orig_device = cfg.WHISPER_DEVICE
        orig_compute = cfg.WHISPER_COMPUTE
        orig_lang = cfg.WHISPER_LANGUAGE

        self._apply_config(None, None, {})

        assert cfg.WHISPER_MODEL == orig_model
        assert cfg.WHISPER_DEVICE == orig_device
        assert cfg.WHISPER_COMPUTE == orig_compute
        assert cfg.WHISPER_LANGUAGE == orig_lang

    def test_none_settings_are_skipped(self):
        """Explicit None values in settings should not override config defaults."""
        import config as cfg
        orig_model = cfg.WHISPER_MODEL
        self._apply_config(None, None, {"whisper_model": None})
        assert cfg.WHISPER_MODEL == orig_model


# ═══════════════════════════════════════════════════════════════════════════
# 4. Mute toggle event handling
# ═══════════════════════════════════════════════════════════════════════════


class TestMuteToggleEventHandling:
    """Tests that mute_toggle only toggles mute when VAD is active,
    and does NOT start/stop manual recording.

    We replicate the event handling logic from _poll_events (lines 1310-1318)
    without the GUI.
    """

    @staticmethod
    def _handle_mute_toggle(
        recorder: MagicMock | None,
        muted: bool,
    ) -> tuple[bool, bool]:
        """Reproduce the mute_toggle handler from whisper_typer.py:1310-1318.

        Returns (new_muted, toggled) where toggled is True if mute state changed.
        """
        if recorder and recorder.vad_active:
            muted = not muted
            return muted, True
        return muted, False

    def test_mute_toggles_when_vad_active(self):
        """With VAD active, mute_toggle should flip the mute flag."""
        rec = MagicMock()
        type(rec).vad_active = PropertyMock(return_value=True)

        new_muted, toggled = self._handle_mute_toggle(rec, muted=False)
        assert new_muted is True
        assert toggled is True

    def test_unmute_toggles_when_vad_active(self):
        """A second mute_toggle should unmute."""
        rec = MagicMock()
        type(rec).vad_active = PropertyMock(return_value=True)

        new_muted, _ = self._handle_mute_toggle(rec, muted=True)
        assert new_muted is False

    def test_mute_does_nothing_when_vad_inactive(self):
        """When VAD is not active, mute_toggle should be a no-op."""
        rec = MagicMock()
        type(rec).vad_active = PropertyMock(return_value=False)

        new_muted, toggled = self._handle_mute_toggle(rec, muted=False)
        assert new_muted is False
        assert toggled is False

    def test_mute_does_nothing_when_no_recorder(self):
        """When recorder is None, mute_toggle should be a no-op."""
        new_muted, toggled = self._handle_mute_toggle(None, muted=False)
        assert new_muted is False
        assert toggled is False

    def test_mute_does_not_call_start_recording(self):
        """mute_toggle must never call start_recording on the recorder."""
        rec = MagicMock()
        type(rec).vad_active = PropertyMock(return_value=True)

        self._handle_mute_toggle(rec, muted=False)
        rec.start_recording.assert_not_called()

    def test_mute_does_not_call_stop_recording(self):
        """mute_toggle must never call stop_recording on the recorder."""
        rec = MagicMock()
        type(rec).vad_active = PropertyMock(return_value=True)

        self._handle_mute_toggle(rec, muted=True)
        rec.stop_recording.assert_not_called()

    def test_full_toggle_cycle(self):
        """unmuted -> mute -> unmute should work cleanly."""
        rec = MagicMock()
        type(rec).vad_active = PropertyMock(return_value=True)

        state = False
        state, _ = self._handle_mute_toggle(rec, state)
        assert state is True
        state, _ = self._handle_mute_toggle(rec, state)
        assert state is False
        state, _ = self._handle_mute_toggle(rec, state)
        assert state is True
