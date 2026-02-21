#!/usr/bin/env python3
"""
Real-time Speech-to-Text with mlx-whisper.
Modes:
  --single          одна фраза → в буфер → выход
  --single --lang ru принудительно русский язык
  (без флагов)      непрерывный режим, стоп по слову "exit" / "выход"
"""

import argparse
import sys
import os
import tempfile
import wave

import mlx_whisper
import pyaudio
import numpy as np
import pyperclip

# ──────────────────────────────────────────────
# Конфигурация модели
# ──────────────────────────────────────────────
# Выбор модели для MacBook Pro M5 / 24 GB RAM:
#
#   "mlx-community/whisper-large-v3-turbo"     — 809M, ~1.6 GB, ★ ЛУЧШИЙ ВЫБОР ★
#       Это large-v3 с 4 decoder layers вместо 32.
#       Качество = large-v2, скорость = tiny/base.
#       Тяжёлый encoder идеально ложится на GPU M5.
#       Отличный русский. Латенция ~1-2s на фразу.
#
# Альтернативы (если нужно):
#   "mlx-community/whisper-small"              — 244M, ~460 MB, если нужна минимальная латенция (<1s)
#   "mlx-community/whisper-large-v3-mlx"       — 1.55B, ~3 GB, максимальное качество, но ~5-8s на фразу
#   "mlx-community/distil-whisper-large-v3"    — 756M, ~1.5 GB, ⚠️ ТОЛЬКО английский
#
MODEL_NAME = os.environ.get(
    "WHISPER_MODEL",
    "mlx-community/whisper-large-v3-turbo"
)

# ──────────────────────────────────────────────
# Параметры PyAudio
# ──────────────────────────────────────────────
FORMAT = pyaudio.paInt16     # 16-bit
CHANNELS = 1                 # моно
RATE = 16000                 # 16 kHz (Whisper ожидает именно это)
CHUNK = 1024                 # размер буфера

# ──────────────────────────────────────────────
# Параметры детекции тишины
# ──────────────────────────────────────────────
SILENCE_THRESHOLD = int(os.environ.get("SILENCE_THRESHOLD", "500"))
SILENCE_DURATION = float(os.environ.get("SILENCE_DURATION", "1.5"))   # секунд тишины = конец фразы
SILENCE_CHUNKS = int(SILENCE_DURATION * RATE / CHUNK)

# Минимальная длительность записи (секунды) — защита от ложных срабатываний
MIN_AUDIO_SECONDS = 0.5


def record_until_silence():
    """Записывает аудио с микрофона до паузы в речи. Возвращает np.array float32."""
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=FORMAT, channels=CHANNELS, rate=RATE,
        input=True, frames_per_buffer=CHUNK
    )

    print("🎙  Ожидание речи...", file=sys.stderr)

    frames = []
    silent_chunks = 0
    speech_started = False

    try:
        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16)
            amplitude = np.max(np.abs(audio_data))

            if amplitude >= SILENCE_THRESHOLD:
                if not speech_started:
                    speech_started = True
                    print("🔴  Запись...", file=sys.stderr)
                silent_chunks = 0
                frames.append(audio_data.astype(np.float32) / 32768.0)
            else:
                if speech_started:
                    frames.append(audio_data.astype(np.float32) / 32768.0)
                    silent_chunks += 1
                    if silent_chunks >= SILENCE_CHUNKS:
                        break
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

    if not frames:
        return None

    audio_array = np.concatenate(frames)
    duration = len(audio_array) / RATE

    if duration < MIN_AUDIO_SECONDS:
        print(f"⚠️  Слишком короткая запись ({duration:.1f}s), пропуск.", file=sys.stderr)
        return None

    print(f"⏹  Записано {duration:.1f}s аудио.", file=sys.stderr)
    return audio_array


def save_wav(audio_array, path):
    """Сохраняет float32 массив в WAV (нужен для mlx_whisper.transcribe)."""
    int_data = (audio_array * 32767).astype(np.int16)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(int_data.tobytes())


def transcribe(audio_array, language=None):
    """Распознаёт аудио через mlx-whisper. Возвращает текст."""
    # mlx_whisper.transcribe принимает путь к файлу или numpy array
    # Для надёжности сохраняем во временный WAV
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
    parser = argparse.ArgumentParser(
        description="Real-time STT через mlx-whisper на Apple Silicon"
    )
    parser.add_argument(
        "--single", action="store_true",
        help="Одна фраза → в буфер → выход"
    )
    parser.add_argument(
        "--lang", type=str, default=None,
        help="Принудительный язык (ru, en, ka, ...); без флага — автодетект"
    )
    parser.add_argument(
        "--output-file", type=str, default=None,
        help="Сохранить транскрипцию в файл (только --single)"
    )
    parser.add_argument(
        "--no-clipboard", action="store_true",
        help="Не копировать в буфер обмена"
    )
    args = parser.parse_args()

    print(f"📦  Модель: {MODEL_NAME}", file=sys.stderr)
    print(f"🔇  Порог тишины: {SILENCE_THRESHOLD}, пауза: {SILENCE_DURATION}s", file=sys.stderr)
    if args.lang:
        print(f"🌐  Язык: {args.lang}", file=sys.stderr)
    else:
        print(f"🌐  Язык: автодетект", file=sys.stderr)
    print("─" * 40, file=sys.stderr)

    if args.single:
        # ── Режим одной фразы ──
        audio = record_until_silence()
        if audio is None:
            print("Нет аудио.", file=sys.stderr)
            sys.exit(1)

        text, lang = transcribe(audio, language=args.lang)
        if not text:
            print("Пустая транскрипция.", file=sys.stderr)
            sys.exit(1)

        # Результат в stdout (для пайпов)
        print(text)

        # В буфер обмена
        if not args.no_clipboard:
            pyperclip.copy(text)
            print(f"📋  Скопировано в буфер (язык: {lang})", file=sys.stderr)

        # В файл
        if args.output_file:
            with open(args.output_file, 'w', encoding='utf-8') as f:
                f.write(text + "\n")
            print(f"💾  Сохранено в {args.output_file}", file=sys.stderr)

    else:
        # ── Непрерывный режим ──
        print("♾️  Непрерывный режим. Скажите 'exit' или 'выход' для остановки.", file=sys.stderr)
        while True:
            audio = record_until_silence()
            if audio is None:
                continue

            text, lang = transcribe(audio, language=args.lang)
            if not text:
                continue

            print(text)

            if not args.no_clipboard:
                pyperclip.copy(text)
                print(f"📋  [{lang}] → буфер", file=sys.stderr)

            # Стоп-слова
            lower = text.lower().strip().rstrip(".")
            if lower in ("exit", "выход", "стоп", "stop"):
                print("👋  Завершение.", file=sys.stderr)
                break

            print("─" * 40, file=sys.stderr)


if __name__ == "__main__":
    main()
