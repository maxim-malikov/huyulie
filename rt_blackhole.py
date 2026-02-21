#!/usr/bin/env python3
"""
BlackHole Audio Capture - ВСЕГДА записывает с BlackHole.
Пользователь сам выбирает в macOS что направить в BlackHole.
"""

import sys
import os
import tempfile
import wave
import time

import mlx_whisper
import pyaudio
import numpy as np
import pyperclip

# Model configuration
MODEL_NAME = os.environ.get(
    "WHISPER_MODEL",
    "mlx-community/whisper-large-v3-turbo"
)

# Audio parameters for BlackHole
FORMAT = pyaudio.paInt16
CHANNELS = 2  # BlackHole 2ch
RATE = 48000  # BlackHole default rate
CHUNK = 1024

# Files
STOP_FILE = "/tmp/mlxw-stop"
PID_FILE = "/tmp/mlxw-pid"

# Minimum audio duration
MIN_AUDIO_SECONDS = 0.3


def find_blackhole():
    """Найти BlackHole устройство."""
    p = pyaudio.PyAudio()
    blackhole_index = None

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if 'blackhole' in info['name'].lower() and info['maxInputChannels'] > 0:
            blackhole_index = i
            print(f"✅ BlackHole найден: {info['name']}", file=sys.stderr)
            print(f"   Каналы: {info['maxInputChannels']}, Частота: {int(info['defaultSampleRate'])}Hz", file=sys.stderr)
            p.terminate()
            return blackhole_index, int(info['defaultSampleRate'])

    p.terminate()
    print("❌ BlackHole не найден!", file=sys.stderr)
    print("   Установите: brew install --cask blackhole-2ch", file=sys.stderr)
    return None, None


def record_until_stop(device_index, sample_rate):
    """Записывать с BlackHole до стоп-сигнала."""
    p = pyaudio.PyAudio()

    try:
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=sample_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )

        print("🔴 REC BlackHole", file=sys.stderr)
        print("   ⚠️  Убедитесь что звук направлен в BlackHole в настройках macOS!", file=sys.stderr)

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
        p.terminate()

        # Convert audio
        audio_data = b''.join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # Convert stereo to mono
        if CHANNELS == 2:
            audio_array = audio_array.reshape(-1, 2).mean(axis=1)

        # Resample to 16kHz for Whisper
        if sample_rate != 16000:
            # Simple downsampling
            ratio = sample_rate / 16000
            indices = np.arange(0, len(audio_array), ratio).astype(int)
            audio_array = audio_array[indices[:min(len(indices), len(audio_array))]]

        duration = len(audio_array) / 16000
        print(f"⏹ Записано {duration:.1f}s", file=sys.stderr)

        if duration < MIN_AUDIO_SECONDS:
            print(f"⚠️ Слишком короткая запись", file=sys.stderr)
            return None

        return audio_array

    except Exception as e:
        print(f"❌ Ошибка записи: {e}", file=sys.stderr)
        return None
    finally:
        p.terminate()
        # Cleanup
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


def save_wav(audio_array, path):
    """Сохранить в WAV для Whisper."""
    wav = wave.open(path, 'wb')
    wav.setnchannels(1)  # Mono
    wav.setsampwidth(2)  # 16-bit
    wav.setframerate(16000)  # 16kHz
    wav.writeframes((audio_array * 32767).astype(np.int16).tobytes())
    wav.close()


def transcribe(audio_array, language=None):
    """Транскрибировать через MLX Whisper."""
    if audio_array is None or len(audio_array) == 0:
        return "", "error"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        save_wav(audio_array, tmp_path)

    try:
        kwargs = {"path_or_hf_repo": MODEL_NAME}
        if language:
            kwargs["language"] = language

        result = mlx_whisper.transcribe(tmp_path, **kwargs)
        text = result.get("text", "").strip()
        detected_lang = result.get("language", "?")
        return text, detected_lang
    except Exception as e:
        print(f"❌ Ошибка транскрипции: {e}", file=sys.stderr)
        return "", "error"
    finally:
        os.unlink(tmp_path)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default=None, help="Язык (ru/en/auto)")
    args = parser.parse_args()

    print(f"📦 Модель: {MODEL_NAME}", file=sys.stderr)
    print("🎯 Режим: BlackHole (системный звук)", file=sys.stderr)

    # Find BlackHole
    device_index, sample_rate = find_blackhole()

    if device_index is None:
        print("\n❌ BlackHole не найден!", file=sys.stderr)
        print("\n⚠️  Установка BlackHole:", file=sys.stderr)
        print("1. brew install --cask blackhole-2ch", file=sys.stderr)
        print("2. sudo killall coreaudiod  (для активации без перезагрузки)", file=sys.stderr)
        print("3. Перезапустите скрипт", file=sys.stderr)
        sys.exit(1)

    print("\n📌 Как использовать:", file=sys.stderr)
    print("1. Откройте System Settings → Sound → Output", file=sys.stderr)
    print("2. Выберите 'BlackHole 2ch' как устройство вывода", file=sys.stderr)
    print("3. Нажмите горячую клавишу для записи", file=sys.stderr)
    print("─" * 40, file=sys.stderr)

    # Record
    audio = record_until_stop(device_index, sample_rate)

    if audio is not None and len(audio) > 0:
        print("🧠 Распознавание...", file=sys.stderr)
        text, lang = transcribe(audio, args.lang)

        if text:
            print(text)  # To stdout for Hammerspoon
            pyperclip.copy(text)
            print(f"📋 [{lang}] → буфер", file=sys.stderr)
        else:
            print("❌ Не распознано", file=sys.stderr)
    else:
        print("❌ Нет аудио или слишком тихо", file=sys.stderr)


if __name__ == "__main__":
    main()