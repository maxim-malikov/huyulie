#!/usr/bin/env python3
"""
Toggle-mode Speech-to-Text with mlx-whisper.
Starts recording immediately.
Stops when /tmp/mlxw-stop file appears.
Transcribes, copies to clipboard, prints to stdout.
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

# ──────────────────────────────────────────────
# Конфигурация модели
# ──────────────────────────────────────────────
MODEL_NAME = os.environ.get(
    "WHISPER_MODEL",
    "mlx-community/whisper-large-v3-turbo"
)

# PyAudio
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

# Предпочтительный микрофон (поиск по подстроке в имени)
# Если найден — используется он, если нет — системный default
PREFERRED_MIC = os.environ.get("WHISPER_MIC", "MacBook Pro Microphone")

# Сигнальный файл для остановки
STOP_FILE = "/tmp/mlxw-stop"
PID_FILE = "/tmp/mlxw-pid"

# Минимальная длительность
MIN_AUDIO_SECONDS = 0.3


def find_mic(p):
    """Найти микрофон по имени. Возвращает (device_index, device_info) или (None, default)."""
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0 and PREFERRED_MIC.lower() in info['name'].lower():
            return i, info
    # Fallback на default
    default_info = p.get_default_input_device_info()
    return None, default_info


def save_wav(audio_array, path):
    int_data = (audio_array * 32767).astype(np.int16)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(int_data.tobytes())


def record_until_stop():
    """Записывает аудио до появления STOP_FILE."""
    if os.path.exists(STOP_FILE):
        os.unlink(STOP_FILE)

    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    p = pyaudio.PyAudio()
    mic_index, mic_info = find_mic(p)

    print(f"🎙 Микрофон: {mic_info['name']}", file=sys.stderr, flush=True)

    stream_kwargs = dict(
        format=FORMAT, channels=CHANNELS, rate=RATE,
        input=True, frames_per_buffer=CHUNK
    )
    if mic_index is not None:
        stream_kwargs['input_device_index'] = mic_index

    stream = p.open(**stream_kwargs)

    print("🔴 REC", file=sys.stderr, flush=True)
    frames = []
    start_time = time.time()

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16)
            frames.append(audio_data.astype(np.float32) / 32768.0)

            if os.path.exists(STOP_FILE):
                break
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        if os.path.exists(STOP_FILE):
            os.unlink(STOP_FILE)
        if os.path.exists(PID_FILE):
            os.unlink(PID_FILE)

    duration = time.time() - start_time
    print(f"⏹  Стоп. Записано {duration:.1f}s", file=sys.stderr, flush=True)

    if not frames or duration < MIN_AUDIO_SECONDS:
        return None

    return np.concatenate(frames)


def transcribe(audio_array, language=None):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        save_wav(audio_array, tmp_path)

    try:
        kwargs = {"path_or_hf_repo": MODEL_NAME}
        if language:
            kwargs["language"] = language

        # Загружаем модель при первом вызове (кэшируется автоматически)
        try:
            result = mlx_whisper.transcribe(tmp_path, **kwargs)
        except Exception as e:
            print(f"❌ Ошибка: {e}", file=sys.stderr)
            print(f"   Попробуйте загрузить модель вручную:", file=sys.stderr)
            print(f"   python -c \"import mlx_whisper; mlx_whisper.transcribe('test.wav', path_or_hf_repo='{MODEL_NAME}')\"", file=sys.stderr)
            return "", "error"

        text = result.get("text", "").strip()
        detected_lang = result.get("language", "?")
        return text, detected_lang
    finally:
        os.unlink(tmp_path)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", type=str, default=None)
    args = parser.parse_args()

    print(f"📦 Модель: {MODEL_NAME}", file=sys.stderr, flush=True)

    audio = record_until_stop()
    if audio is None:
        print("❌ Нет аудио", file=sys.stderr, flush=True)
        sys.exit(1)

    print("🧠 Распознавание...", file=sys.stderr, flush=True)
    text, lang = transcribe(audio, language=args.lang)

    if not text:
        print("❌ Пустая транскрипция", file=sys.stderr, flush=True)
        sys.exit(1)

    pyperclip.copy(text)
    print(text)
    print(f"📋 [{lang}] → буфер", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
