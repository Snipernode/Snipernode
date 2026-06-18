#!/usr/bin/env python3
"""Discord Portable TTS attachment.

Type text, synthesize it to speech, and play it through VB-CABLE so Discord can
capture it as a mic source.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import numpy as np
import pyttsx3
import sounddevice as sd
import soundfile as sf

try:
    import edge_tts
except Exception:  # pragma: no cover - guarded runtime fallback
    edge_tts = None

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "tts_config.json"

ENGINE_EDGE = "edge"
ENGINE_SYSTEM = "system"
ENGINE_LABELS = {
    ENGINE_EDGE: "Neural (Edge)",
    ENGINE_SYSTEM: "System (Windows)",
}
SECONDARY_DISABLED_LABEL = "Disabled"
SECONDARY_DEFAULT_LABEL = "Default Windows Output"

EDGE_VOICE_PRESETS: list[tuple[str, str]] = [
    ("TF2 Pyro-ish (Muffled) [EN]", "fx-pyro|en-US-GuyNeural"),
    ("TF2 Pyro-ish Alt [EN]", "fx-pyro|en-US-AndrewNeural"),
    ("TF2 Spy-ish (fr-FR-HenriNeural)", "fr-FR-HenriNeural"),
    ("TF2 Spy-ish Alt (fr-FR-RemyMultilingualNeural)", "fr-FR-RemyMultilingualNeural"),
    ("en-US-AriaNeural (F)", "en-US-AriaNeural"),
    ("en-US-JennyNeural (F)", "en-US-JennyNeural"),
    ("en-US-EmmaNeural (F)", "en-US-EmmaNeural"),
    ("en-US-AnaNeural (F)", "en-US-AnaNeural"),
    ("en-US-GuyNeural (M)", "en-US-GuyNeural"),
    ("en-US-AndrewNeural (M)", "en-US-AndrewNeural"),
    ("en-US-RogerNeural (M)", "en-US-RogerNeural"),
    ("en-US-SteffanNeural (M)", "en-US-SteffanNeural"),
    ("en-GB-SoniaNeural (F)", "en-GB-SoniaNeural"),
    ("en-GB-RyanNeural (M)", "en-GB-RyanNeural"),
]

EDGE_VOICE_OVERRIDES: dict[str, dict[str, str]] = {
    "fr-FR-HenriNeural": {"pitch": "-9Hz", "rate": "-8%"},
    "fr-FR-RemyMultilingualNeural": {"pitch": "-7Hz", "rate": "-6%"},
}


class TTSAttachmentApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Discord TTS Attachment")
        self.root.geometry("940x470")

        self._busy = False
        self._active_streams: list[sd.OutputStream] = []
        self._active_streams_lock = threading.Lock()
        self.voice_items: list[tuple[str, str]] = []

        self.config = self._load_config()
        self.output_devices = self._get_output_devices()
        self.cable_output_device = self._find_cable_output_device()
        self.system_voice_items = self._get_system_voices()
        self.edge_voice_items = self._get_edge_voices()
        self.engine_items = self._get_engine_items()
        self.secondary_device_items = self._get_secondary_output_items()

        self.fixed_device_var = tk.StringVar()
        self.engine_var = tk.StringVar()
        self.voice_var = tk.StringVar()
        self.secondary_device_var = tk.StringVar()
        self.rate_var = tk.IntVar(value=self._normalize_rate_percent(self.config.get("rate_percent", 100)))
        self.volume_var = tk.DoubleVar(value=self._normalize_volume(self.config.get("volume", 1.0)))
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._apply_initial_values()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        title = ttk.Label(
            self.root,
            text="Type text and send it to your virtual audio device",
            font=("Segoe UI", 12, "bold"),
        )
        title.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")

        controls = ttk.Frame(self.root)
        controls.grid(row=1, column=0, padx=12, pady=6, sticky="ew")
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)
        controls.columnconfigure(5, weight=1)
        controls.columnconfigure(7, weight=1)

        ttk.Label(controls, text="Virtual output").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.fixed_device_label = ttk.Label(controls, textvariable=self.fixed_device_var)
        self.fixed_device_label.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(controls, text="Engine").grid(row=0, column=2, sticky="w", padx=(10, 8), pady=4)
        self.engine_combo = ttk.Combobox(controls, state="readonly", textvariable=self.engine_var)
        self.engine_combo["values"] = [label for label, _ in self.engine_items]
        self.engine_combo.grid(row=0, column=3, sticky="ew", pady=4)
        self.engine_combo.bind("<<ComboboxSelected>>", self._on_engine_change)

        ttk.Label(controls, text="Voice").grid(row=0, column=4, sticky="w", padx=(10, 8), pady=4)
        self.voice_combo = ttk.Combobox(controls, state="readonly", textvariable=self.voice_var)
        self.voice_combo.grid(row=0, column=5, columnspan=3, sticky="ew", pady=4)

        ttk.Label(controls, text="Rate").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.rate_scale = ttk.Scale(controls, from_=50, to=200, orient="horizontal")
        self.rate_scale.grid(row=1, column=1, sticky="ew", pady=4)
        self.rate_scale.set(self.rate_var.get())
        self.rate_scale.configure(command=self._on_rate_change)

        self.rate_value = ttk.Label(controls, width=6, text=f"{self.rate_var.get()}%")
        self.rate_value.grid(row=1, column=2, sticky="w", padx=(10, 0), pady=4)

        ttk.Label(controls, text="Secondary output").grid(row=1, column=3, sticky="w", padx=(10, 8), pady=4)
        self.secondary_combo = ttk.Combobox(controls, state="readonly", textvariable=self.secondary_device_var)
        self.secondary_combo["values"] = [label for label, _ in self.secondary_device_items]
        self.secondary_combo.grid(row=1, column=4, columnspan=2, sticky="ew", pady=4)

        ttk.Label(controls, text="Volume").grid(row=1, column=6, sticky="w", padx=(10, 8), pady=4)
        self.volume_scale = ttk.Scale(controls, from_=0.1, to=1.5, orient="horizontal")
        self.volume_scale.grid(row=1, column=7, sticky="ew", pady=4)
        self.volume_scale.set(self.volume_var.get())
        self.volume_scale.configure(command=self._on_volume_change)

        text_frame = ttk.Frame(self.root)
        text_frame.grid(row=2, column=0, padx=12, pady=6, sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.text_box = tk.Text(text_frame, wrap="word", font=("Consolas", 11), undo=True)
        self.text_box.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text_box.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_box.configure(yscrollcommand=scrollbar.set)

        button_row = ttk.Frame(self.root)
        button_row.grid(row=3, column=0, padx=12, pady=6, sticky="ew")

        self.speak_button = ttk.Button(button_row, text="Speak", command=self.speak)
        self.speak_button.pack(side="left")

        self.stop_button = ttk.Button(button_row, text="Stop Playback", command=self.stop_playback)
        self.stop_button.pack(side="left", padx=6)

        self.clear_button = ttk.Button(button_row, text="Clear", command=self.clear_text)
        self.clear_button.pack(side="left")

        self.save_button = ttk.Button(button_row, text="Save Settings", command=lambda: self.save_settings(show_status=True))
        self.save_button.pack(side="left", padx=6)

        status = ttk.Label(self.root, textvariable=self.status_var)
        status.grid(row=4, column=0, sticky="w", padx=12, pady=(2, 12))

        self.text_box.bind("<Control-Return>", lambda _event: self.speak())

    def _normalize_rate_percent(self, value: object) -> int:
        try:
            rate = int(float(value))
        except (TypeError, ValueError):
            return 100
        return max(50, min(rate, 200))

    def _normalize_volume(self, value: object) -> float:
        try:
            volume = float(value)
        except (TypeError, ValueError):
            return 1.0
        return max(0.1, min(volume, 1.5))

    def _apply_initial_values(self) -> None:
        if self.cable_output_device:
            self.fixed_device_var.set(self.cable_output_device[0])
        else:
            self.fixed_device_var.set("Not found: CABLE Input (VB-Audio Virtual Cable)")
            self.status_var.set("Virtual cable output not found. Install/enable VB-CABLE.")

        if self.engine_items:
            requested_engine = self.config.get("engine_label", "")
            valid_engine_labels = {label for label, _ in self.engine_items}
            if requested_engine in valid_engine_labels:
                self.engine_var.set(requested_engine)
            else:
                self.engine_var.set(self.engine_items[0][0])
        else:
            self.status_var.set("No TTS engines found.")

        requested_secondary = self.config.get("secondary_output_label", "")
        valid_secondary_labels = {label for label, _ in self.secondary_device_items}
        if requested_secondary in valid_secondary_labels:
            self.secondary_device_var.set(requested_secondary)
        else:
            self.secondary_device_var.set(SECONDARY_DISABLED_LABEL)

        self._refresh_voice_options(select_from_config=True)
        self._refresh_speak_button_state()

    def _refresh_speak_button_state(self) -> None:
        if self._busy:
            self.speak_button.configure(state=tk.DISABLED)
            return
        can_speak = bool(self.cable_output_device and self.voice_items)
        self.speak_button.configure(state=(tk.NORMAL if can_speak else tk.DISABLED))

    def _on_engine_change(self, _event: tk.Event | None = None) -> None:
        self._refresh_voice_options(select_from_config=False)
        self._refresh_speak_button_state()

    def _refresh_voice_options(self, select_from_config: bool) -> None:
        engine_id = self._get_selected_engine_id()
        if engine_id == ENGINE_SYSTEM:
            self.voice_items = self.system_voice_items
        else:
            self.voice_items = self.edge_voice_items

        voice_labels = [label for label, _ in self.voice_items]
        self.voice_combo["values"] = voice_labels

        if not voice_labels:
            self.voice_var.set("")
            self.status_var.set("No voices available for selected engine.")
            return

        requested_voice = self.config.get("voice_label", "") if select_from_config else self.voice_var.get()
        valid_voice_labels = set(voice_labels)
        selected_voice = requested_voice if requested_voice in valid_voice_labels else voice_labels[0]
        self.voice_var.set(selected_voice)

    def _on_rate_change(self, value: str) -> None:
        try:
            rate = self._normalize_rate_percent(float(value))
        except (TypeError, ValueError):
            return
        self.rate_var.set(rate)
        self.rate_value.configure(text=f"{rate}%")

    def _on_volume_change(self, value: str) -> None:
        try:
            self.volume_var.set(self._normalize_volume(float(value)))
        except (TypeError, ValueError):
            return

    def _load_config(self) -> dict:
        default_engine = ENGINE_LABELS[ENGINE_EDGE] if edge_tts is not None else ENGINE_LABELS[ENGINE_SYSTEM]
        defaults = {
            "engine_label": default_engine,
            "voice_label": "",
            "rate_percent": 100,
            "volume": 1.0,
            "secondary_output_label": SECONDARY_DISABLED_LABEL,
        }

        if not CONFIG_PATH.exists():
            return defaults

        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return defaults

        defaults.update(loaded)

        if "secondary_output_label" not in loaded and "monitor_default" in loaded:
            defaults["secondary_output_label"] = (
                SECONDARY_DEFAULT_LABEL if bool(loaded.get("monitor_default")) else SECONDARY_DISABLED_LABEL
            )

        if "rate_percent" not in loaded and "rate" in loaded:
            try:
                legacy_rate = float(loaded["rate"])
                defaults["rate_percent"] = self._normalize_rate_percent((legacy_rate / 175.0) * 100.0)
            except (TypeError, ValueError, ZeroDivisionError):
                defaults["rate_percent"] = 100

        defaults["rate_percent"] = self._normalize_rate_percent(defaults.get("rate_percent", 100))
        defaults["volume"] = self._normalize_volume(defaults.get("volume", 1.0))
        return defaults

    def _get_output_devices(self) -> list[tuple[str, int]]:
        devices: list[tuple[str, int]] = []
        try:
            for idx, device in enumerate(sd.query_devices()):
                if device.get("max_output_channels", 0) > 0:
                    label = f"{idx}: {device.get('name', 'Unknown Device')}"
                    devices.append((label, idx))
        except Exception:
            return []
        return devices

    def _find_cable_output_device(self) -> tuple[str, int] | None:
        first_pass: list[tuple[str, int]] = []
        second_pass: list[tuple[str, int]] = []

        for label, idx in self.output_devices:
            lowered = label.lower()
            if "cable input" in lowered and "vb-audio" in lowered:
                first_pass.append((label, idx))
            elif "cable input" in lowered:
                second_pass.append((label, idx))

        if first_pass:
            return first_pass[0]
        if second_pass:
            return second_pass[0]
        return None

    def _get_system_voices(self) -> list[tuple[str, str]]:
        try:
            engine = pyttsx3.init()
        except Exception:
            return []
        try:
            voices = engine.getProperty("voices") or []
        finally:
            engine.stop()

        options = []
        for voice in voices:
            name = getattr(voice, "name", "Unknown Voice")
            voice_id = getattr(voice, "id", "")
            if voice_id:
                options.append((name, voice_id))
        return options

    def _get_edge_voices(self) -> list[tuple[str, str]]:
        if edge_tts is None:
            return []
        return EDGE_VOICE_PRESETS.copy()

    def _get_engine_items(self) -> list[tuple[str, str]]:
        engines: list[tuple[str, str]] = []
        if self.edge_voice_items:
            engines.append((ENGINE_LABELS[ENGINE_EDGE], ENGINE_EDGE))
        if self.system_voice_items:
            engines.append((ENGINE_LABELS[ENGINE_SYSTEM], ENGINE_SYSTEM))
        return engines

    def _get_secondary_output_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = [
            (SECONDARY_DISABLED_LABEL, "disabled"),
            (SECONDARY_DEFAULT_LABEL, "default"),
        ]
        cable_device_id = self.cable_output_device[1] if self.cable_output_device else None
        for label, device_id in self.output_devices:
            if cable_device_id is not None and device_id == cable_device_id:
                continue
            items.append((label, f"device:{device_id}"))
        return items

    def _get_default_output_device_id(self) -> int | None:
        try:
            default_device = sd.default.device
        except Exception:
            return None

        if isinstance(default_device, (list, tuple)) and len(default_device) >= 2:
            out_id = default_device[1]
            if isinstance(out_id, (int, float)) and int(out_id) >= 0:
                return int(out_id)
        return None

    def _get_selected_engine_id(self) -> str:
        selected = self.engine_var.get()
        for label, engine_id in self.engine_items:
            if label == selected:
                return engine_id
        return ENGINE_EDGE if self.edge_voice_items else ENGINE_SYSTEM

    def _get_selected_voice_id(self) -> str | None:
        selected = self.voice_var.get()
        for label, voice_id in self.voice_items:
            if label == selected:
                return voice_id
        return None

    def _resolve_secondary_device(self, selected_label: str, cable_device_id: int) -> tuple[int | None, str]:
        selected_key = "disabled"
        for label, key in self.secondary_device_items:
            if label == selected_label:
                selected_key = key
                break

        if selected_key == "disabled":
            return None, ""

        if selected_key == "default":
            default_output = self._get_default_output_device_id()
            if default_output is None:
                return None, " (secondary unavailable)"
            if default_output == cable_device_id:
                return None, " (secondary is same as cable)"
            return default_output, " + secondary"

        if selected_key.startswith("device:"):
            try:
                device_id = int(selected_key.split(":", 1)[1])
            except ValueError:
                return None, " (secondary selection invalid)"
            if device_id == cable_device_id:
                return None, " (secondary is same as cable)"
            return device_id, " + secondary"

        return None, " (secondary selection invalid)"

    def _split_voice_style(self, voice_id: str) -> tuple[str | None, str]:
        if voice_id.startswith("fx-pyro|"):
            base_voice = voice_id.split("|", 1)[1].strip()
            if not base_voice:
                base_voice = "en-US-GuyNeural"
            return "pyro", base_voice
        return None, voice_id

    def save_settings(self, show_status: bool) -> None:
        payload = {
            "engine_label": self.engine_var.get(),
            "voice_label": self.voice_var.get(),
            "rate_percent": int(self.rate_var.get()),
            "volume": float(self.volume_var.get()),
            "secondary_output_label": self.secondary_device_var.get(),
        }
        try:
            CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            if show_status:
                self.status_var.set("Settings saved.")
        except OSError as exc:
            self.status_var.set(f"Could not save settings: {exc}")

    def clear_text(self) -> None:
        self.text_box.delete("1.0", tk.END)

    def stop_playback(self) -> None:
        with self._active_streams_lock:
            active_streams = list(self._active_streams)

        for stream in active_streams:
            try:
                stream.abort()
            except Exception:
                pass

        try:
            sd.stop()
        except Exception:
            pass

        self.status_var.set("Playback stopped.")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_speak_button_state()

    def speak(self) -> None:
        if self._busy:
            self.status_var.set("Already speaking.")
            return

        text = self.text_box.get("1.0", tk.END).strip()
        if not text:
            self.status_var.set("Enter text first.")
            return

        if self.cable_output_device is None:
            self.status_var.set("CABLE Input device not found.")
            return

        cable_device_id = self.cable_output_device[1]
        voice_id = self._get_selected_voice_id()
        engine_id = self._get_selected_engine_id()
        secondary_selection = self.secondary_device_var.get()

        if voice_id is None:
            self.status_var.set("Choose a valid voice.")
            return

        self.save_settings(show_status=False)
        self._set_busy(True)
        self.status_var.set("Synthesizing and playing...")

        worker = threading.Thread(
            target=self._speak_worker,
            args=(
                text,
                cable_device_id,
                engine_id,
                voice_id,
                int(self.rate_var.get()),
                float(self.volume_var.get()),
                secondary_selection,
            ),
            daemon=True,
        )
        worker.start()

    def _edge_rate(self, rate_percent: int, voice_id: str) -> str:
        delta = max(-50, min(100, rate_percent - 100))
        voice_style, base_voice = self._split_voice_style(voice_id)
        override = EDGE_VOICE_OVERRIDES.get(voice_id, {}).get("rate") or EDGE_VOICE_OVERRIDES.get(base_voice, {}).get("rate")
        if override:
            try:
                delta += int(override.replace("%", "").strip())
            except ValueError:
                pass
        if voice_style == "pyro":
            delta += 10
        delta = max(-50, min(100, delta))
        return f"{delta:+d}%"

    def _edge_pitch(self, voice_id: str) -> str:
        voice_style, base_voice = self._split_voice_style(voice_id)
        override = EDGE_VOICE_OVERRIDES.get(voice_id, {}).get("pitch") or EDGE_VOICE_OVERRIDES.get(base_voice, {}).get("pitch")
        if override:
            return override
        if voice_style == "pyro":
            return "+18Hz"
        return "+0Hz"

    def _system_rate(self, rate_percent: int) -> int:
        mapped = int(175 * (rate_percent / 100.0))
        return max(80, min(mapped, 350))

    def _synthesize_edge(self, text: str, voice_id: str, rate_percent: int, output_path: str) -> None:
        if edge_tts is None:
            raise RuntimeError("Neural engine package missing.")
        _voice_style, base_voice = self._split_voice_style(voice_id)
        communicate = edge_tts.Communicate(
            text,
            voice=base_voice,
            rate=self._edge_rate(rate_percent, voice_id),
            pitch=self._edge_pitch(voice_id),
        )
        asyncio.run(communicate.save(output_path))

    def _synthesize_system(self, text: str, voice_id: str, rate_percent: int, volume: float, output_path: str) -> None:
        engine = pyttsx3.init()
        try:
            engine.setProperty("voice", voice_id)
            engine.setProperty("rate", self._system_rate(rate_percent))
            engine.setProperty("volume", max(0.1, min(volume, 1.0)))
            engine.save_to_file(text, output_path)
            engine.runAndWait()
        finally:
            engine.stop()

    def _prepare_audio_data(self, audio_data) -> list | object:
        if audio_data.ndim == 1:
            audio_data = audio_data.reshape(-1, 1)
        elif audio_data.ndim != 2:
            raise RuntimeError("Unsupported audio shape returned by TTS engine.")
        return audio_data.astype("float32", copy=False)

    def _apply_pyro_effect(self, audio_data, sample_rate: int):
        channels = audio_data.shape[1]
        mono = audio_data.mean(axis=1) if channels > 1 else audio_data[:, 0]
        if mono.size == 0:
            return audio_data

        spectrum = np.fft.rfft(mono)
        freqs = np.fft.rfftfreq(mono.shape[0], d=1.0 / sample_rate)
        band_mask = (freqs >= 250.0) & (freqs <= 2600.0)
        spectrum *= band_mask
        band_limited = np.fft.irfft(spectrum, n=mono.shape[0]).astype("float32")

        drive = 2.8
        distorted = np.tanh(band_limited * drive) / np.tanh(drive)

        t = np.arange(distorted.shape[0], dtype=np.float32) / float(sample_rate)
        mod = 0.88 + 0.12 * np.sin(2.0 * np.pi * 42.0 * t)
        modulated = distorted * mod

        mixed = 0.35 * mono + 0.65 * modulated
        peak = float(np.max(np.abs(mixed)))
        if peak > 0.99:
            mixed = mixed / peak * 0.99

        if channels > 1:
            return np.repeat(mixed[:, np.newaxis], channels, axis=1).astype("float32")
        return mixed.reshape(-1, 1).astype("float32")

    def _fit_channels_for_device(self, audio_data, device_id: int):
        try:
            device_info = sd.query_devices(device_id)
            max_output_channels = int(device_info.get("max_output_channels", 0))
        except Exception as exc:
            raise RuntimeError(f"Could not query output device {device_id}: {exc}") from exc

        if max_output_channels <= 0:
            raise RuntimeError(f"Output device {device_id} has no output channels.")

        channels = audio_data.shape[1]
        if channels <= max_output_channels:
            return audio_data

        if max_output_channels == 1:
            return audio_data.mean(axis=1, keepdims=True).astype("float32")

        return audio_data[:, :max_output_channels]

    def _resample_audio(self, audio_data, src_rate: int, dst_rate: int):
        """Simple linear resampling to dst_rate. Returns (resampled_audio, dst_rate)."""
        if int(src_rate) == int(dst_rate):
            return audio_data, int(dst_rate)
        # Use numpy interpolation per-channel
        try:
            import numpy as np
        except Exception:
            return audio_data, int(dst_rate)

        src_len = int(audio_data.shape[0])
        if src_len <= 1:
            return audio_data, int(dst_rate)

        duration = src_len / float(src_rate)
        dst_len = max(1, int(round(duration * float(dst_rate))))
        orig_indices = np.arange(src_len)
        new_indices = np.linspace(0, src_len - 1, num=dst_len)

        # Mono or single-channel
        if audio_data.ndim == 1 or (audio_data.ndim == 2 and audio_data.shape[1] == 1):
            mono = audio_data.reshape(-1)
            res = np.interp(new_indices, orig_indices, mono).astype("float32")
            return res.reshape(-1, 1), int(dst_rate)

        # Multi-channel
        channels = audio_data.shape[1]
        resampled = np.empty((dst_len, channels), dtype="float32")
        for ch in range(channels):
            resampled[:, ch] = np.interp(new_indices, orig_indices, audio_data[:, ch])
        return resampled, int(dst_rate)

    def _play_on_device(self, audio_data, sample_rate: int, device_id: int) -> None:
        # Force target samplerate to 48000Hz for browser/microphone compatibility
        TARGET_SR = 48000

        # Resample to TARGET_SR if needed
        try:
            audio_data, sample_rate = self._resample_audio(audio_data, int(sample_rate), TARGET_SR)
        except Exception:
            # Fall back to original sample_rate on failure
            sample_rate = int(sample_rate)

        # Convert to mono (typical microphone input is mono)
        try:
            if audio_data.shape[1] > 1:
                mono = audio_data.mean(axis=1, keepdims=True).astype("float32")
            else:
                mono = audio_data.astype("float32", copy=False)
        except Exception:
            mono = audio_data.astype("float32", copy=False)

        # Query device and duplicate channels if device requires more than 1 channel
        try:
            device_info = sd.query_devices(device_id)
            max_output_channels = int(device_info.get("max_output_channels", 0))
        except Exception:
            max_output_channels = 1

        if max_output_channels <= 0:
            raise RuntimeError(f"Output device {device_id} has no output channels.")

        if max_output_channels == 1:
            device_audio = mono
        else:
            # Duplicate mono across available channels
            device_audio = np.repeat(mono, max_output_channels, axis=1).astype("float32")

        stream = sd.OutputStream(
            device=device_id,
            samplerate=int(sample_rate),
            channels=device_audio.shape[1],
            dtype="float32",
        )

        with self._active_streams_lock:
            self._active_streams.append(stream)

        try:
            stream.start()
            stream.write(device_audio)
        finally:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
            with self._active_streams_lock:
                if stream in self._active_streams:
                    self._active_streams.remove(stream)

    def _play_to_devices(self, audio_data, sample_rate: int, device_ids: list[int]) -> dict[int, str]:
        errors: dict[int, str] = {}
        errors_lock = threading.Lock()
        threads: list[threading.Thread] = []

        def run(device_id: int) -> None:
            try:
                self._play_on_device(audio_data, sample_rate, device_id)
            except Exception as exc:
                with errors_lock:
                    errors[device_id] = str(exc)

        for device_id in device_ids:
            thread = threading.Thread(target=run, args=(device_id,), daemon=True)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        return errors

    def _speak_worker(
        self,
        text: str,
        cable_device_id: int,
        engine_id: str,
        voice_id: str,
        rate_percent: int,
        volume: float,
        secondary_selection: str,
    ) -> None:
        temp_file_path = ""
        try:
            suffix = ".mp3" if engine_id == ENGINE_EDGE else ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                temp_file_path = handle.name

            if engine_id == ENGINE_EDGE:
                self._synthesize_edge(text, voice_id, rate_percent, temp_file_path)
            else:
                self._synthesize_system(text, voice_id, rate_percent, volume, temp_file_path)

            audio_data, sample_rate = sf.read(temp_file_path, dtype="float32")
            audio_data = self._prepare_audio_data(audio_data)
            voice_style, _base_voice = self._split_voice_style(voice_id)

            if voice_style == "pyro":
                audio_data = self._apply_pyro_effect(audio_data, sample_rate)

            if volume != 1.0:
                audio_data = (audio_data * volume).clip(-1.0, 1.0).astype("float32")

            target_device_ids = [cable_device_id]
            secondary_note = ""
            secondary_device_id, secondary_note = self._resolve_secondary_device(secondary_selection, cable_device_id)
            if secondary_device_id is not None and secondary_device_id not in target_device_ids:
                target_device_ids.append(secondary_device_id)

            playback_errors = self._play_to_devices(audio_data, sample_rate, target_device_ids)
            if cable_device_id in playback_errors:
                raise RuntimeError(f"CABLE playback failed: {playback_errors[cable_device_id]}")

            if secondary_device_id is not None and secondary_device_id in playback_errors:
                secondary_note = " (secondary failed)"

            self.root.after(0, lambda: self.status_var.set(f"Speech sent to CABLE Input{secondary_note}."))
        except Exception as exc:  # pylint: disable=broad-except
            self.root.after(0, lambda: self.status_var.set(f"Error: {exc}"))
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass
            self.root.after(0, lambda: self._set_busy(False))


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    elif "clam" in style.theme_names():
        style.theme_use("clam")

    app = TTSAttachmentApp(root)
    app.text_box.insert(
        "1.0",
        "Type your message here. Press Ctrl+Enter or click Speak.\n"
        "Output is locked to CABLE Input (VB-Audio Virtual Cable).",
    )
    root.mainloop()


if __name__ == "__main__":
    main()
