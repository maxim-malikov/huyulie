#!/usr/bin/env python3
"""
System Audio Capture with automatic device routing.
Captures system audio through BlackHole with automatic device switching.
"""

import sys
import os
import tempfile
import wave
import time
import subprocess
import json

import mlx_whisper
import pyaudio
import numpy as np
import pyperclip

# Model configuration
MODEL_NAME = os.environ.get(
    "WHISPER_MODEL",
    "mlx-community/whisper-large-v3-turbo"
)

# Audio parameters
FORMAT = pyaudio.paInt16
CHANNELS = 2  # Stereo for system audio
RATE = 44100  # System audio rate
CHUNK = 1024

# Files
STOP_FILE = "/tmp/mlxw-stop"
PID_FILE = "/tmp/mlxw-pid"


class SystemAudioCapture:
    """Manages system audio capture through virtual devices."""

    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.current_output = None
        self.blackhole_index = None
        self.multi_output_index = None

    def find_device(self, name_contains, is_input=True):
        """Find audio device by name."""
        for i in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(i)
            if name_contains.lower() in info['name'].lower():
                if is_input and info['maxInputChannels'] > 0:
                    return i, info
                elif not is_input and info['maxOutputChannels'] > 0:
                    return i, info
        return None, None

    def get_current_output_device(self):
        """Get current system output device using macOS tools."""
        try:
            # Get current output device
            result = subprocess.run(
                ['system_profiler', 'SPAudioDataType', '-json'],
                capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)

            # Parse for current output
            for item in data.get('SPAudioDataType', []):
                if item.get('_name') == 'Output':
                    return item.get('coreaudio_default_audio_output_device', '')
        except:
            pass
        return None

    def setup_blackhole(self):
        """Setup BlackHole for system audio capture."""
        # Find BlackHole device
        self.blackhole_index, blackhole_info = self.find_device('BlackHole', is_input=True)

        if not self.blackhole_index:
            print("⚠️  BlackHole не найден. Устанавливаю...", file=sys.stderr)
            self.install_blackhole()
            self.blackhole_index, blackhole_info = self.find_device('BlackHole', is_input=True)

        if self.blackhole_index:
            print(f"✅ BlackHole найден: {blackhole_info['name']}", file=sys.stderr)
            return True
        else:
            print("❌ BlackHole не удалось настроить", file=sys.stderr)
            return False

    def install_blackhole(self):
        """Install BlackHole if not present."""
        try:
            print("📦 Устанавливаю BlackHole...", file=sys.stderr)
            subprocess.run(['brew', 'install', '--cask', 'blackhole-2ch'], check=True)
            time.sleep(2)  # Wait for device to appear
        except subprocess.CalledProcessError:
            print("❌ Не удалось установить BlackHole", file=sys.stderr)

    def create_multi_output(self):
        """Create Multi-Output Device with current output + BlackHole."""
        try:
            # Use macOS Audio MIDI Setup scripting
            script = '''
            tell application "Audio MIDI Setup"
                activate
                -- Create multi-output device
                make new aggregate device
                set multi to result
                set name of multi to "MLX Multi-Output"

                -- Add current output and BlackHole
                add device "BlackHole 2ch" to multi

                -- Set as default
                set default output device to multi
            end tell
            '''

            subprocess.run(['osascript', '-e', script], check=False)
            print("✅ Multi-Output Device создан", file=sys.stderr)
            return True
        except:
            print("⚠️  Не удалось создать Multi-Output автоматически", file=sys.stderr)
            return False

    def smart_device_selection(self):
        """Intelligently select the best audio capture device."""
        devices = []

        for i in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                # Priority scoring
                priority = 0
                name_lower = info['name'].lower()

                # Highest priority - BlackHole for system audio
                if 'blackhole' in name_lower:
                    priority = 100
                # Multi-output devices
                elif 'multi' in name_lower or 'aggregate' in name_lower:
                    priority = 90
                # Virtual cables
                elif 'soundflower' in name_lower or 'loopback' in name_lower:
                    priority = 80
                # External devices (may have loopback)
                elif 'usb' in name_lower or 'external' in name_lower:
                    priority = 50
                # Headphones/AirPods with possible passthrough
                elif 'airpods' in name_lower or 'headphones' in name_lower:
                    priority = 40
                # Built-in mic (lowest for system audio)
                elif 'built-in' in name_lower or 'internal' in name_lower:
                    priority = 10

                devices.append({
                    'index': i,
                    'name': info['name'],
                    'priority': priority,
                    'channels': info['maxInputChannels'],
                    'rate': info.get('defaultSampleRate', 44100)
                })

        # Sort by priority
        devices.sort(key=lambda x: x['priority'], reverse=True)

        if devices:
            selected = devices[0]
            print(f"🎧 Выбрано устройство: {selected['name']}", file=sys.stderr)

            # Show alternatives
            if len(devices) > 1:
                alts = [d['name'] for d in devices[1:3]]
                print(f"   Альтернативы: {', '.join(alts)}", file=sys.stderr)

            # Warning if not optimal
            if selected['priority'] < 50:
                print("⚠️  Выбран микрофон, а не системный звук!", file=sys.stderr)
                print("   Рекомендуется настроить BlackHole", file=sys.stderr)

            return selected['index']

        return None

    def validate_on_toggle(self):
        """Validate and update audio routing on each toggle."""
        print("🔍 Проверка аудио устройств...", file=sys.stderr)

        # Check if BlackHole is available
        if not self.setup_blackhole():
            print("⚠️  Используется fallback на микрофон", file=sys.stderr)

        # Get best device
        device_index = self.smart_device_selection()

        if device_index is None:
            print("❌ Нет доступных устройств ввода", file=sys.stderr)
            return None

        return device_index

    def record_until_stop(self, device_index):
        """Record system audio until stop signal."""
        try:
            # Adjust parameters based on device
            device_info = self.p.get_device_info_by_index(device_index)
            channels = min(2, device_info['maxInputChannels'])
            rate = int(device_info.get('defaultSampleRate', 44100))

            stream = self.p.open(
                format=FORMAT,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=CHUNK
            )

            print(f"🔴 REC (системный звук, {rate}Hz, {channels}ch)", file=sys.stderr)

            frames = []

            # Write PID for external control
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))

            # Record until stop file appears
            while not os.path.exists(STOP_FILE):
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    frames.append(data)
                except:
                    time.sleep(0.01)

            stream.stop_stream()
            stream.close()

            # Convert to mono 16kHz for Whisper
            audio_data = b''.join(frames)
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # If stereo, convert to mono
            if channels == 2:
                audio_array = audio_array.reshape(-1, 2).mean(axis=1)

            # Resample to 16kHz if needed
            if rate != 16000:
                # Simple downsampling (proper resampling would use scipy)
                ratio = rate / 16000
                indices = np.arange(0, len(audio_array), ratio).astype(int)
                audio_array = audio_array[indices[:min(len(indices), len(audio_array))]]

            return audio_array

        except Exception as e:
            print(f"❌ Ошибка записи: {e}", file=sys.stderr)
            return None
        finally:
            # Cleanup
            if os.path.exists(STOP_FILE):
                os.remove(STOP_FILE)
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)


def transcribe(audio_array, language=None):
    """Transcribe audio using MLX Whisper."""
    if audio_array is None or len(audio_array) == 0:
        return "", "error"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        # Save as 16kHz mono WAV
        wav = wave.open(tmp.name, 'wb')
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes((audio_array * 32767).astype(np.int16).tobytes())
        wav.close()
        tmp_path = tmp.name

    try:
        kwargs = {"path_or_hf_repo": MODEL_NAME}
        if language:
            kwargs["language"] = language

        result = mlx_whisper.transcribe(tmp_path, **kwargs)
        text = result.get("text", "").strip()
        lang = result.get("language", "?")
        return text, lang
    except Exception as e:
        print(f"❌ Ошибка транскрипции: {e}", file=sys.stderr)
        return "", "error"
    finally:
        os.unlink(tmp_path)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="ru", help="Language")
    parser.add_argument("--setup", action="store_true", help="Setup BlackHole")
    args = parser.parse_args()

    print(f"📦 Модель: {MODEL_NAME}", file=sys.stderr)
    print("🎯 Режим: Захват системного звука", file=sys.stderr)

    # Initialize capture system
    capture = SystemAudioCapture()

    if args.setup:
        print("Настройка BlackHole для захвата системного звука...")
        capture.setup_blackhole()
        capture.create_multi_output()
        print("\n✅ Готово! Выберите 'MLX Multi-Output' в настройках звука")
        return

    # Validate devices on start
    device_index = capture.validate_on_toggle()

    if device_index is None:
        print("❌ Не удалось найти устройство для записи", file=sys.stderr)
        sys.exit(1)

    # Record
    audio = capture.record_until_stop(device_index)

    if audio is not None and len(audio) > 0:
        duration = len(audio) / 16000
        print(f"⏹ Записано {duration:.1f}s", file=sys.stderr)

        print("🧠 Распознавание...", file=sys.stderr)
        text, lang = transcribe(audio, args.lang)

        if text:
            print(text)  # To stdout for Hammerspoon
            pyperclip.copy(text)
            print(f"📋 [{lang}] → буфер", file=sys.stderr)
        else:
            print("❌ Не распознано", file=sys.stderr)
    else:
        print("❌ Нет аудио", file=sys.stderr)


if __name__ == "__main__":
    main()