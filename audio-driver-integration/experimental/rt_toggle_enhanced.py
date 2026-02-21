#!/usr/bin/env python3
"""
Enhanced Toggle-mode Speech-to-Text with mlx-whisper.
Поддерживает захват системного звука через BlackHole.
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

# Приоритет устройств для захвата (первое найденное используется)
# Можно переопределить через WHISPER_MIC
MIC_PRIORITY = [
    "BlackHole 2ch",           # Виртуальный драйвер для системного звука
    "BlackHole 16ch",          # Альтернативная версия BlackHole
    "Loopback Audio",          # Альтернатива - Loopback от Rogue Amoeba
    "MacBook Pro Microphone",  # Fallback на встроенный микрофон
]

# Переопределение через переменную окружения
CUSTOM_MIC = os.environ.get("WHISPER_MIC", None)
if CUSTOM_MIC:
    MIC_PRIORITY.insert(0, CUSTOM_MIC)

# Сигнальные файлы
STOP_FILE = "/tmp/mlxw-stop"
PID_FILE = "/tmp/mlxw-pid"

# Минимальная длительность
MIN_AUDIO_SECONDS = 0.3


def find_best_mic(p):
    """Найти лучший микрофон по приоритету."""
    # Сначала проверяем приоритетный список
    for preferred_name in MIC_PRIORITY:
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if (info['maxInputChannels'] > 0 and
                preferred_name.lower() in info['name'].lower()):
                return i, info, preferred_name

    # Fallback на default
    default_info = p.get_default_input_device_info()
    return None, default_info, "System Default"


def detect_audio_setup():
    """Определить текущую конфигурацию аудио и дать рекомендации."""
    p = pyaudio.PyAudio()

    # Проверяем наличие BlackHole
    has_blackhole = False
    blackhole_index = None

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if "blackhole" in info['name'].lower():
            has_blackhole = True
            if info['maxInputChannels'] > 0:
                blackhole_index = i
            break

    # Проверяем текущее output устройство
    default_output = p.get_default_output_device_info()

    p.terminate()

    if not has_blackhole:
        print("⚠️  BlackHole не установлен!", file=sys.stderr)
        print("   Для захвата звука в наушниках выполните:", file=sys.stderr)
        print("   brew install --cask blackhole-2ch", file=sys.stderr)
        print("   Или используйте встроенные динамики MacBook", file=sys.stderr)
    elif "multi-output" not in default_output['name'].lower():
        print("⚠️  Multi-Output Device не настроен!", file=sys.stderr)
        print("   Откройте Audio MIDI Setup и создайте Multi-Output с:", file=sys.stderr)
        print("   - BlackHole 2ch", file=sys.stderr)
        print("   - Вашими наушниками", file=sys.stderr)

    return has_blackhole, blackhole_index


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

    # Проверяем конфигурацию
    has_blackhole, _ = detect_audio_setup()

    # Находим лучший микрофон
    mic_index, mic_info, mic_type = find_best_mic(p)

    print(f"🎙 Источник: {mic_info['name']}", file=sys.stderr, flush=True)

    if "blackhole" in mic_info['name'].lower():
        print("✅ Захват системного звука включен", file=sys.stderr, flush=True)
    elif not has_blackhole:
        print("📢 Захват с микрофона (звук должен идти через динамики)", file=sys.stderr, flush=True)
    else:
        print("⚠️  BlackHole доступен, но не используется", file=sys.stderr, flush=True)

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

    # Счетчики для отладки
    silent_chunks = 0
    total_chunks = 0
    max_amplitude = 0

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16)
            frames.append(audio_data.astype(np.float32) / 32768.0)

            # Отладка: проверяем уровень звука
            amplitude = np.max(np.abs(audio_data))
            max_amplitude = max(max_amplitude, amplitude)
            total_chunks += 1

            if amplitude < 100:
                silent_chunks += 1

            # Показываем индикатор активности каждую секунду
            if total_chunks % (RATE // CHUNK) == 0:
                silence_percent = (silent_chunks / total_chunks) * 100
                if silence_percent > 90:
                    print(f"⚠️  Слишком тихо! Max: {max_amplitude}", file=sys.stderr, flush=True)

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

    # Отладочная информация
    if max_amplitude < 500:
        print(f"⚠️  Очень низкий уровень звука: {max_amplitude}", file=sys.stderr, flush=True)
        print("   Проверьте:", file=sys.stderr, flush=True)
        print("   - Громкость системы и приложения", file=sys.stderr, flush=True)
        print("   - Настройки Multi-Output Device", file=sys.stderr, flush=True)

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
        result = mlx_whisper.transcribe(tmp_path, **kwargs)
        text = result.get("text", "").strip()
        detected_lang = result.get("language", "?")
        return text, detected_lang
    finally:
        os.unlink(tmp_path)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--check-setup", action="store_true",
                       help="Проверить настройку аудио и выйти")
    args = parser.parse_args()

    if args.check_setup:
        print("🔍 Проверка конфигурации аудио...", file=sys.stderr)
        p = pyaudio.PyAudio()
        has_blackhole, blackhole_index = detect_audio_setup()

        print("\n📋 Доступные устройства ввода:", file=sys.stderr)
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                marker = " ← РЕКОМЕНДУЕТСЯ" if "blackhole" in info['name'].lower() else ""
                print(f"  [{i}] {info['name']}{marker}", file=sys.stderr)

        p.terminate()

        if has_blackhole and blackhole_index:
            print("\n✅ BlackHole настроен! Используйте:", file=sys.stderr)
            print(f"   export WHISPER_MIC='BlackHole 2ch'", file=sys.stderr)

        sys.exit(0)

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