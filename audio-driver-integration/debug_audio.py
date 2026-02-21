#!/usr/bin/env python3
"""
Диагностический скрипт для проверки захвата аудио.
Показывает все аудио устройства и тестирует запись.
"""

import pyaudio
import numpy as np
import time
import sys

def list_audio_devices():
    """Список всех аудио устройств."""
    p = pyaudio.PyAudio()

    print("=" * 60)
    print("AUDIO DEVICES:")
    print("=" * 60)

    # Получаем дефолтные устройства безопасно
    try:
        default_input = p.get_default_input_device_info()['index']
    except:
        default_input = None

    try:
        default_output = p.get_default_output_device_info()['index']
    except:
        default_output = None

    # Устройства ввода
    print("\n📥 INPUT DEVICES (микрофоны):")
    print("-" * 40)
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            is_default = " [DEFAULT]" if i == default_input else ""
            print(f"  [{i}] {info['name']}")
            print(f"      Channels: {info['maxInputChannels']}, Rate: {int(info['defaultSampleRate'])} Hz{is_default}")

    # Устройства вывода
    print("\n📤 OUTPUT DEVICES (динамики/наушники):")
    print("-" * 40)
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxOutputChannels'] > 0:
            is_default = " [DEFAULT]" if i == default_output else ""
            print(f"  [{i}] {info['name']}")
            print(f"      Channels: {info['maxOutputChannels']}, Rate: {int(info['defaultSampleRate'])} Hz{is_default}")

    p.terminate()
    return default_input

def test_recording(device_index=None, duration=5):
    """Тестовая запись с визуализацией уровня."""
    p = pyaudio.PyAudio()

    if device_index is not None:
        device_info = p.get_device_info_by_index(device_index)
        print(f"\n🎙 Тестируем устройство [{device_index}]: {device_info['name']}")
    else:
        device_info = p.get_default_input_device_info()
        print(f"\n🎙 Тестируем DEFAULT устройство: {device_info['name']}")

    stream_kwargs = {
        'format': pyaudio.paInt16,
        'channels': 1,
        'rate': 16000,
        'input': True,
        'frames_per_buffer': 1024
    }

    if device_index is not None:
        stream_kwargs['input_device_index'] = device_index

    try:
        stream = p.open(**stream_kwargs)
        print(f"📊 Запись {duration} секунд... (говорите или воспроизведите звук)")
        print("   Уровень громкости:")

        start_time = time.time()
        max_amplitude = 0

        while time.time() - start_time < duration:
            data = stream.read(1024, exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16)
            amplitude = np.max(np.abs(audio_data))
            max_amplitude = max(max_amplitude, amplitude)

            # Визуализация уровня
            bar_length = int(amplitude / 1000)
            bar = "█" * min(bar_length, 50)
            sys.stdout.write(f"\r   [{bar:<50}] {amplitude:5d}")
            sys.stdout.flush()

        print(f"\n✅ Максимальная амплитуда: {max_amplitude}")

        if max_amplitude < 100:
            print("⚠️  Очень тихо! Возможно, микрофон не захватывает звук.")
        elif max_amplitude < 500:
            print("⚠️  Тихо. Проверьте уровень громкости или расстояние до источника.")
        else:
            print("✅ Уровень звука нормальный.")

        stream.stop_stream()
        stream.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        p.terminate()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Диагностика аудио захвата")
    parser.add_argument('--device', type=int, help='Индекс устройства для тестирования')
    parser.add_argument('--duration', type=int, default=5, help='Длительность теста в секундах')
    parser.add_argument('--list-only', action='store_true', help='Только показать список устройств')
    args = parser.parse_args()

    default_device = list_audio_devices()

    if args.list_only:
        return

    print("\n" + "=" * 60)
    print("ТЕСТ ЗАПИСИ")
    print("=" * 60)

    if args.device is not None:
        test_recording(args.device, args.duration)
    else:
        # Тест default устройства
        test_recording(None, args.duration)

        # Предложить тест BlackHole если установлен
        print("\n" + "-" * 60)
        print("💡 ПОДСКАЗКА:")
        print("   Если звук идёт через наушники и не захватывается,")
        print("   вам нужен виртуальный аудио драйвер (BlackHole или Loopback).")
        print("   Это позволит захватывать системный звук вместо микрофона.")
        print("-" * 60)

if __name__ == "__main__":
    main()