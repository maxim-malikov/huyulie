#!/usr/bin/env python3
"""
Enhanced RT module with automatic audio device detection and switching.
Automatically selects the best available microphone based on priority.
"""

import argparse
import sys
import os
import tempfile
import wave
import time

import mlx_whisper
import pyaudio
import numpy as np
import pyperclip
import sounddevice as sd

# Model configuration
MODEL_NAME = os.environ.get(
    "WHISPER_MODEL",
    "mlx-community/whisper-large-v3-turbo"
)

# Audio parameters
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

# Silence detection parameters
SILENCE_THRESHOLD = 1000
SILENCE_DURATION = 1.5

class SmartAudioDevice:
    """Smart audio device selector with priority-based selection."""

    # Device priority (higher = better)
    DEVICE_PRIORITIES = {
        # External devices (highest priority)
        'usb': 100,           # USB микрофоны
        'thunderbolt': 95,    # Thunderbolt аудио интерфейсы

        # Wireless devices
        'airpods': 80,        # AirPods (хорошее качество)
        'bluetooth': 70,      # Другие Bluetooth устройства

        # Virtual devices
        'blackhole': 60,      # BlackHole для записи системного звука
        'multi-output': 55,   # Multi-Output Device
        'aggregate': 50,      # Aggregate Device

        # Built-in devices (lowest priority)
        'macbook': 30,        # Встроенный микрофон MacBook
        'built-in': 25,       # Другие встроенные
        'default': 20         # Системный по умолчанию
    }

    @classmethod
    def detect_device_type(cls, device_name):
        """Определяет тип устройства по имени."""
        name_lower = device_name.lower()

        # External
        if 'usb' in name_lower or 'yeti' in name_lower or 'blue' in name_lower:
            return 'usb'
        if 'thunderbolt' in name_lower or 'apollo' in name_lower:
            return 'thunderbolt'

        # Wireless
        if 'airpods' in name_lower:
            return 'airpods'
        if 'bluetooth' in name_lower or 'bt' in name_lower:
            return 'bluetooth'

        # Virtual
        if 'blackhole' in name_lower:
            return 'blackhole'
        if 'multi-output' in name_lower:
            return 'multi-output'
        if 'aggregate' in name_lower:
            return 'aggregate'

        # Built-in
        if 'macbook' in name_lower or 'internal' in name_lower:
            return 'macbook'
        if 'built-in' in name_lower:
            return 'built-in'

        return 'default'

    @classmethod
    def get_best_device(cls):
        """Возвращает лучшее доступное устройство ввода."""
        p = pyaudio.PyAudio()
        devices = []

        # Собираем все доступные устройства ввода
        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    device_type = cls.detect_device_type(info['name'])
                    priority = cls.DEVICE_PRIORITIES.get(device_type, 0)
                    devices.append({
                        'index': i,
                        'name': info['name'],
                        'type': device_type,
                        'priority': priority,
                        'channels': info['maxInputChannels']
                    })
            except Exception:
                continue

        p.terminate()

        if not devices:
            return None

        # Сортируем по приоритету (и количеству каналов как вторичный критерий)
        devices.sort(key=lambda x: (x['priority'], x['channels']), reverse=True)

        best_device = devices[0]

        # Логирование выбора
        print(f"🎤 Выбрано устройство: {best_device['name']} ({best_device['type']})",
              file=sys.stderr)

        # Если есть альтернативы, показываем их
        if len(devices) > 1:
            print(f"   Доступны также: {', '.join(d['name'] for d in devices[1:3])}",
                  file=sys.stderr)

        return best_device['index']

    @classmethod
    def monitor_device_changes(cls, callback=None):
        """Мониторинг изменений аудио устройств (для будущего использования)."""
        # Можно реализовать через polling или system events
        pass

def record_until_silence(device_index=None):
    """Записывает аудио с автоматическим выбором устройства."""

    # Автоматический выбор устройства если не указано
    if device_index is None:
        device_index = SmartAudioDevice.get_best_device()

    audio = pyaudio.PyAudio()

    # Параметры для открытия потока
    stream_kwargs = {
        'format': FORMAT,
        'channels': CHANNELS,
        'rate': RATE,
        'input': True,
        'frames_per_buffer': CHUNK
    }

    # Добавляем индекс устройства если определен
    if device_index is not None:
        stream_kwargs['input_device_index'] = device_index

    try:
        stream = audio.open(**stream_kwargs)
    except Exception as e:
        print(f"⚠️  Ошибка открытия устройства, использую системное по умолчанию",
              file=sys.stderr)
        # Fallback на дефолтное устройство
        stream_kwargs.pop('input_device_index', None)
        stream = audio.open(**stream_kwargs)

    print("🎙  Ожидание речи...", file=sys.stderr)

    frames = []
    silent_chunks = 0
    has_sound = False
    is_speaking = False

    # Звуковой сигнал начала записи
    os.system("play -n synth 0.1 sine 1000 2>/dev/null &")

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_chunk = np.frombuffer(data, dtype=np.int16)

            volume = np.abs(audio_chunk).mean()

            if volume > SILENCE_THRESHOLD:
                silent_chunks = 0
                if not is_speaking:
                    is_speaking = True
                    has_sound = True
                    print("🔴 Запись...", file=sys.stderr)
                frames.append(data)
            else:
                if is_speaking:
                    frames.append(data)
                    silent_chunks += 1
                    if silent_chunks > int(SILENCE_DURATION * RATE / CHUNK):
                        print("⏸  Пауза обнаружена", file=sys.stderr)
                        break

    except KeyboardInterrupt:
        pass

    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

    if not has_sound:
        return np.array([])

    # Звуковой сигнал конца записи
    os.system("play -n synth 0.1 sine 800 2>/dev/null &")

    audio_data = b''.join(frames)
    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

    return audio_array

def transcribe_audio(audio_array, language=None):
    """Транскрибирует аудио с помощью MLX Whisper."""
    if len(audio_array) == 0:
        return ""

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
        wav_file = wave.open(tmp_file.name, 'wb')
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)
        wav_file.setframerate(RATE)
        wav_file.writeframes((audio_array * 32768).astype(np.int16).tobytes())
        wav_file.close()

        options = {}
        if language:
            options['language'] = language

        result = mlx_whisper.transcribe(
            tmp_file.name,
            path_or_hf_repo=MODEL_NAME,
            verbose=False,
            **options
        )

        os.unlink(tmp_file.name)

    return result.get("text", "").strip()

def list_devices():
    """Показывает список всех доступных аудио устройств с приоритетами."""
    print("\n📋 Доступные аудио устройства:\n")
    print(f"{'№':<4} {'Имя':<40} {'Тип':<15} {'Приоритет':<10} {'Каналы'}")
    print("-" * 80)

    p = pyaudio.PyAudio()
    devices = []

    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                device_type = SmartAudioDevice.detect_device_type(info['name'])
                priority = SmartAudioDevice.DEVICE_PRIORITIES.get(device_type, 0)
                devices.append({
                    'index': i,
                    'name': info['name'][:39],
                    'type': device_type,
                    'priority': priority,
                    'channels': info['maxInputChannels']
                })
        except Exception:
            continue

    devices.sort(key=lambda x: x['priority'], reverse=True)

    for d in devices:
        star = "⭐" if d == devices[0] else "  "
        print(f"{star}{d['index']:<2} {d['name']:<40} {d['type']:<15} {d['priority']:<10} {d['channels']}")

    p.terminate()

    print("\n⭐ = Будет выбрано автоматически")
    print("\nИспользование: ./mlxw --device <номер> для выбора конкретного устройства")

def main():
    """Загружает модель при старте (один раз)."""
    print(f"📦 Загрузка модели {MODEL_NAME}...", file=sys.stderr)

    try:
        # Предзагрузка модели для уменьшения латенции
        _ = mlx_whisper.load_model(path_or_hf_repo=MODEL_NAME)
    except Exception as e:
        print(f"❌ Ошибка загрузки модели: {e}", file=sys.stderr)
        sys.exit(1)

    print("✅ Модель загружена!", file=sys.stderr)

def run_single(language=None, device_index=None):
    """Режим одной фразы с автоматическим выбором устройства."""
    audio = record_until_silence(device_index)

    if len(audio) == 0:
        print("❌ Речь не обнаружена", file=sys.stderr)
        return

    print("🔄 Распознавание...", file=sys.stderr)
    text = transcribe_audio(audio, language)

    if text:
        pyperclip.copy(text)
        print(text)
        print("✅ Скопировано в буфер обмена!", file=sys.stderr)
    else:
        print("❌ Не удалось распознать", file=sys.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time STT with smart device selection")
    parser.add_argument("--single", action="store_true", help="Одна фраза и выход")
    parser.add_argument("--lang", type=str, help="Язык (ru/en/auto)")
    parser.add_argument("--device", type=int, help="Индекс устройства (см. --list-devices)")
    parser.add_argument("--list-devices", action="store_true", help="Показать все устройства")

    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        sys.exit(0)

    main()

    if args.single:
        run_single(args.lang, args.device)
    else:
        # Непрерывный режим
        print("📢 Непрерывный режим. Скажите 'выход' или 'exit' для остановки.",
              file=sys.stderr)
        while True:
            audio = record_until_silence(args.device)
            if len(audio) > 0:
                text = transcribe_audio(audio, args.lang)
                if text:
                    print(f"📝 {text}")
                    if "выход" in text.lower() or "exit" in text.lower():
                        break