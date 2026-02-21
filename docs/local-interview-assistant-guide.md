# Local Interview Assistant — macOS (Apple Silicon)

> **Локальный Whisper (mlx-whisper) + стелс-клиент Pluely**
> Полный пошаговый гайд со всеми командами, конфигами и кодом.

---

## Что получится в итоге

- **Хоткей → говоришь фразу → текст в буфере** (локальное STT, без внешних API)
- **Стелс-overlay Pluely** с подключённой LLM (Claude/GPT/Gemini) — невидим в Zoom/Meet/Teams
- **Связка**: диктуешь вопрос или контекст → Whisper распознаёт → вставляешь в Pluely → получаешь структурированный ответ в overlay

---

## Целевой конфиг

**MacBook Pro M5, 24 GB RAM** — позволяет запускать `whisper-large-v3-turbo` (809M параметров, ~3 GB VRAM) с запасом и получать латенцию ~1-2s на фразу.

## Требования

| Компонент | Минимум | Этот конфиг (M5 / 24 GB) |
|-----------|---------|--------------------------|
| Mac | Apple Silicon (M1+) | MacBook Pro M5 ✅ |
| macOS | 12.3+ (для Metal/MPS) | Sequoia 15.x ✅ |
| Python | 3.10+ | 3.12 ✅ |
| RAM | 8 GB (tiny/base), 16 GB+ (turbo/large) | 24 GB ✅ с запасом |
| Свободное место | ~3 GB (модель + venv) | ✅ |
| API-ключ | OpenAI / Anthropic / другой LLM-провайдер | ✅ |

---

## Шаг 1. Установить зависимости системного уровня

### 1.1 Homebrew (если ещё нет)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 1.2 Python 3.10+

```bash
# Проверить текущую версию
python3 --version

# Если нет или < 3.10 — поставить через Homebrew
brew install python@3.12
```

### 1.3 PortAudio (нужен для PyAudio)

```bash
brew install portaudio
```

---

## Шаг 2. Создать проект и виртуальное окружение

```bash
# Создать рабочую папку
mkdir -p ~/mlxwhisper
cd ~/mlxwhisper

# Создать venv
python3 -m venv .venv

# Активировать
source .venv/bin/activate

# Обновить pip
pip install --upgrade pip

# Установить все зависимости
pip install mlx-whisper pyaudio numpy pyperclip
```

> **Зачем venv?** — обходит ошибку `externally-managed-environment` в Python 3.12+ на macOS.

### 2.1 Проверить, что PyAudio видит микрофон

```bash
python3 -c "
import pyaudio
p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        print(f'  [{i}] {info[\"name\"]} (rate={int(info[\"defaultSampleRate\"])})')
p.terminate()
"
```

Должен показать хотя бы одно устройство ввода (встроенный микрофон или внешний).

---

## Шаг 3. Создать скрипт распознавания речи `rt.py`

```bash
cat > ~/mlxwhisper/rt.py << 'PYEOF'
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
PYEOF
```

---

## Шаг 4. Первый тест

```bash
cd ~/mlxwhisper
source .venv/bin/activate

# Одна фраза (автодетект языка) — по умолчанию используется large-v3-turbo
python rt.py --single

# Одна фраза, принудительно русский
python rt.py --single --lang ru

# Непрерывный режим
python rt.py --lang ru
```

> **Первый запуск** скачает модель `whisper-large-v3-turbo` (~1.6 GB) в `~/.cache/huggingface/`.
> Потом запуски мгновенные — модель уже в кеше.

### 4.1 Почему `large-v3-turbo` — оптимальный выбор для M5 / 24 GB

| Модель | Параметры | Размер | Русский | Латенция (M5) | GPU VRAM | Вердикт |
|--------|-----------|--------|---------|---------------|----------|---------|
| `whisper-tiny` | 39M | 75 MB | Слабый | <0.5s | ~0.5 GB | Русский плохо, галлюцинации |
| `whisper-base` | 74M | 140 MB | Терпимый | ~0.5s | ~0.7 GB | Слишком много ошибок |
| `whisper-small` | 244M | 460 MB | Хороший | ~1s | ~1 GB | Разумный fallback |
| `whisper-medium` | 769M | 1.5 GB | Отличный | ~3-4s | ~3 GB | Медленнее turbo при ≈ том же качестве |
| **`whisper-large-v3-turbo`** | **809M** | **1.6 GB** | **Отличный** | **~1-2s** | **~3 GB** | **★ Оптимум: качество large, скорость small** |
| `whisper-large-v3-mlx` | 1.55B | 3 GB | Лучший | ~5-8s | ~6 GB | Избыточен, 5+ секунд ожидания |
| `distil-whisper-large-v3` | 756M | 1.5 GB | ❌ | ~1-2s | ~3 GB | English-only, не подходит |

**Почему turbo идеален для M5:**
- Encoder (32 layers) — тяжёлый, отлично параллелится на GPU Apple Silicon
- Decoder (4 layers вместо 32) — лёгкий, не тормозит
- 3 GB из 24 GB RAM — используется ~12%, даже с Pluely и Zoom одновременно запас огромный
- Качество русского на уровне `large-v2` — деградация только на тайском/кантонском

### 4.2 Переключить модель на лету (без правки кода)

```bash
# Если нужно попробовать другую модель — через env:
WHISPER_MODEL=mlx-community/whisper-small python rt.py --single
WHISPER_MODEL=mlx-community/whisper-large-v3-mlx python rt.py --single
```

### 4.3 Подстройка чувствительности

Если скрипт начинает запись от фонового шума или не ловит тихую речь:

```bash
# Повысить порог (шумное окружение, например кафе)
SILENCE_THRESHOLD=800 python rt.py --single

# Понизить порог (тихий микрофон)
SILENCE_THRESHOLD=300 python rt.py --single

# Увеличить паузу до конца фразы (для длинных предложений)
SILENCE_DURATION=2.5 python rt.py --single
```

---

## Шаг 5. Глобальная команда `mlxw`

### 5.1 Обёртка-скрипт

```bash
cat > ~/mlxwhisper/mlxw << 'EOF'
#!/bin/bash
# mlxw — быстрая голосовая диктовка в буфер обмена
# Использование:
#   mlxw            — одна фраза, автодетект языка
#   mlxw ru         — одна фраза, русский
#   mlxw en         — одна фраза, английский
#   mlxw continuous — непрерывный режим

cd ~/mlxwhisper
source .venv/bin/activate

case "${1:-}" in
  continuous|cont|c)
    python rt.py --lang "${2:-ru}"
    ;;
  "")
    python rt.py --single
    ;;
  *)
    python rt.py --single --lang "$1"
    ;;
esac
EOF

chmod +x ~/mlxwhisper/mlxw
```

### 5.2 Добавить в PATH

```bash
# Вариант A: симлинк (рекомендуется)
sudo ln -sf ~/mlxwhisper/mlxw /usr/local/bin/mlxw

# Вариант B: добавить папку в PATH (в ~/.zshrc)
echo 'export PATH="$HOME/mlxwhisper:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 5.3 Проверка

```bash
# Из любого терминала
mlxw
# Скажите фразу → текст появится в буфере → вставьте Cmd+V куда угодно

mlxw ru
# То же, но принудительно русский
```

---

## Шаг 6. Глобальный хоткей через macOS Shortcuts

### Вариант A: Automator + Keyboard Shortcut

1. Открыть **Automator** → New → **Quick Action**
2. Workflow receives: **no input** in **any application**
3. Добавить действие **Run Shell Script**
4. Shell: `/bin/bash`
5. Вставить:

```bash
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
/usr/local/bin/mlxw ru 2>/dev/null
```

6. Сохранить как `MLX Whisper Dictate`
7. Перейти в **System Settings → Keyboard → Keyboard Shortcuts → Services**
8. Найти `MLX Whisper Dictate` → назначить хоткей, например `⌃⌥W` (Ctrl+Option+W)

### Вариант B: Shortcuts.app (macOS 13+)

1. Открыть **Shortcuts.app** → **+** новый шорткат
2. Добавить действие **Run Shell Script**
3. Вставить:

```bash
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
/usr/local/bin/mlxw ru
```

4. Назвать шорткат `Whisper Dictate`
5. В **System Settings → Keyboard → Keyboard Shortcuts → App Shortcuts** или прямо в Shortcuts.app назначить хоткей

### Вариант C: Raycast / Alfred / Hammerspoon

**Raycast** (бесплатный):
1. Preferences → Extensions → Script Commands → Create Script Command
2. Файл:

```bash
#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Whisper Dictate
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 🎙
# @raycast.packageName MLX Whisper

export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
/usr/local/bin/mlxw ru
```

3. В Raycast назначить хоткей на эту команду.

**Hammerspoon** (для гиков):

```lua
-- ~/.hammerspoon/init.lua
hs.hotkey.bind({"ctrl", "alt"}, "W", function()
    hs.task.new("/usr/local/bin/mlxw", nil, {"ru"}):start()
end)
```

---

## Шаг 7. Установить Pluely (стелс AI-ассистент)

### 7.1 Скачать и установить

1. Перейти на https://pluely.com/downloads или https://github.com/iamsrikanthnani/pluely/releases
2. Скачать последний `.dmg` для macOS (Universal / Apple Silicon)
3. Открыть `.dmg` → перетащить Pluely в Applications

**Если macOS блокирует запуск:**

```bash
# Вариант 1: через System Settings
# System Settings → Privacy & Security → Security →
# найти "pluely was blocked" → нажать "Allow Anyway"

# Вариант 2: через терминал
xattr -cr /Applications/Pluely.app
```

### 7.2 Запуск и первоначальная настройка

1. Запустить Pluely из Applications
2. Откроется Dashboard — `Cmd+Shift+D`

### 7.3 Настроить LLM-провайдер

Pluely поддерживает любого провайдера через curl-команду. Вот примеры настройки:

**Anthropic Claude (рекомендуется):**

В Pluely Settings → AI Providers → Add Custom Provider:
- Name: `Claude`
- Type: curl
- Command:

```bash
curl -s https://api.anthropic.com/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 4096,
    "system": "You are a Senior DevOps/SRE Engineer interview coach. You help structure and improve answers for technical interviews. Answer in the same language as the question. Be concise and focus on practical experience. Format answers in clear, structured paragraphs.",
    "messages": [{"role": "user", "content": "{{INPUT}}"}]
  }'
```

**OpenAI GPT:**

```bash
curl -s https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "You are a Senior DevOps/SRE Engineer interview coach. You help structure and improve answers for technical interviews. Answer in the same language as the question. Be concise and focus on practical experience."},
      {"role": "user", "content": "{{INPUT}}"}
    ]
  }'
```

> **Замени** `YOUR_ANTHROPIC_API_KEY` / `YOUR_OPENAI_API_KEY` на свои реальные ключи.

### 7.4 Хоткеи Pluely (стандартные)

| Действие | macOS |
|----------|-------|
| Показать/скрыть окно | `Cmd + \` |
| Dashboard | `Cmd + Shift + D` |
| Системное аудио (транскрипция) | `Cmd + Shift + M` |
| Голосовой ввод | `Cmd + Shift + A` |
| Скриншот | `Cmd + Shift + S` |

### 7.5 Настроить стелс-режим

В Settings:
- **Always on Top**: ✅ включить
- **Transparency**: настроить под комфортную прозрачность (50-70%)
- **Hide from Dock**: ✅ включить (иконка исчезнет из Dock, приложение работает в фоне)

---

## Шаг 8. Подготовить system prompt для интервью

Создать файл с системным промптом, который можно вставить в Pluely:

```bash
cat > ~/mlxwhisper/interview-prompt.txt << 'EOF'
You are an expert interview coach for a Senior DevOps/SRE Engineer position.

Context about the candidate:
- 15+ years of infrastructure automation experience
- Deep expertise: AWS, GCP, Azure, Kubernetes (EKS/GKE/AKS), Docker, Terraform, ArgoCD, FluxCD
- Strong in: Salt/Ansible configuration management, CI/CD pipelines, monitoring (Prometheus/Grafana/CloudWatch/Datadog)
- Current role: SRE at an international iGaming company (root team), working with ClickHouse, Kafka, Debezium, EKS migrations
- Languages: Russian, English, Georgian

Your task:
1. When given a rough answer draft or interview question, restructure it into a clear, impressive response
2. Highlight relevant practical experience and specific technologies
3. Use the STAR method when appropriate (Situation, Task, Action, Result)
4. Keep answers concise (2-3 minutes speaking time)
5. Answer in the SAME LANGUAGE as the input
6. Include specific metrics and results where possible

Format: Clear paragraphs, no bullet points (this will be read aloud).
EOF
```

---

## Шаг 9. Рабочий процесс на интервью

### Подготовка (за 5 минут до звонка)

```bash
# 1. Запустить Pluely (если не запущен)
open -a Pluely

# 2. Проверить, что mlxw работает
mlxw ru

# 3. Открыть Pluely (Cmd+\), убедиться что overlay на месте и прозрачный
# 4. Вбить system prompt из interview-prompt.txt в настройки провайдера
```

### Во время интервью

```
┌─────────────────────────────────────────────────────┐
│  ZOOM / Google Meet / Teams (полный экран)           │
│                                                      │
│  Интервьюер задаёт вопрос                            │
│          ↓                                           │
│  1. Нажимаешь Ctrl+Option+W (хоткей mlxw)            │
│  2. Диктуешь черновик ответа / пересказ вопроса      │
│  3. Whisper локально распознаёт → текст в буфере     │
│          ↓                                           │
│  4. Cmd+\ → открывается Pluely overlay               │
│  5. Cmd+V → вставляешь текст из буфера               │
│  6. Pluely отправляет в Claude/GPT                    │
│  7. Читаешь структурированный ответ в overlay         │
│  8. Cmd+\ → скрываешь Pluely                          │
│  9. Отвечаешь интервьюеру своими словами              │
│                                                      │
│  ┌──────────────────────┐ ← Pluely overlay (стелс)   │
│  │ AI response here...  │    невидим в screen share   │
│  │ ...                  │                             │
│  └──────────────────────┘                             │
└─────────────────────────────────────────────────────┘
```

### Альтернативный сценарий: Pluely System Audio

Pluely умеет захватывать системное аудио и транскрибировать его через встроенный Whisper. Это значит, что можно транскрибировать вопросы интервьюера автоматически:

1. `Cmd+Shift+M` — включить System Audio capture
2. Pluely будет транскрибировать звук из Zoom/Meet в реальном времени
3. Ты видишь текст вопроса в overlay
4. Добавляешь свой контекст через `Cmd+Shift+A` (voice input) или текстом
5. Pluely генерирует ответ

---

## Шаг 10. Продвинутые настройки

### 10.1 Скрипт-обёртка с уведомлением

Чтобы получать macOS-нотификацию после распознавания:

```bash
cat > ~/mlxwhisper/mlxw-notify << 'EOF'
#!/bin/bash
# mlxw с нативным уведомлением macOS
cd ~/mlxwhisper
source .venv/bin/activate

RESULT=$(python rt.py --single --lang "${1:-ru}" 2>/dev/null)

if [ -n "$RESULT" ]; then
    echo "$RESULT" | pbcopy
    osascript -e "display notification \"$RESULT\" with title \"🎙 Whisper\" subtitle \"Скопировано в буфер\""
else
    osascript -e "display notification \"Не удалось распознать\" with title \"🎙 Whisper\" subtitle \"Ошибка\""
fi
EOF

chmod +x ~/mlxwhisper/mlxw-notify
sudo ln -sf ~/mlxwhisper/mlxw-notify /usr/local/bin/mlxw-notify
```

### 10.2 Пайплайн: Whisper → Claude API напрямую (без Pluely)

Если хочешь отправлять распознанный текст сразу в Claude API:

```bash
cat > ~/mlxwhisper/ask-claude << 'EOF'
#!/bin/bash
# Распознать речь → отправить в Claude → показать ответ
# Использование: ask-claude [язык]

cd ~/mlxwhisper
source .venv/bin/activate

LANG="${1:-ru}"
API_KEY="${ANTHROPIC_API_KEY}"

if [ -z "$API_KEY" ]; then
    echo "Установи ANTHROPIC_API_KEY в ~/.zshrc"
    exit 1
fi

echo "🎙  Говорите..." >&2
TEXT=$(python rt.py --single --lang "$LANG" --no-clipboard 2>/dev/null)

if [ -z "$TEXT" ]; then
    echo "❌  Не удалось распознать." >&2
    exit 1
fi

echo "📝  Распознано: $TEXT" >&2
echo "🤖  Отправка в Claude..." >&2

RESPONSE=$(curl -s https://api.anthropic.com/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d "{
    \"model\": \"claude-sonnet-4-20250514\",
    \"max_tokens\": 2048,
    \"system\": \"Ты помощник на собеседовании для Senior DevOps/SRE. Дай структурированный ответ на вопрос. Отвечай на том же языке. Кратко, по делу.\",
    \"messages\": [{\"role\": \"user\", \"content\": \"$TEXT\"}]
  }" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for block in data.get('content', []):
    if block.get('type') == 'text':
        print(block['text'])
")

echo ""
echo "$RESPONSE"
echo "$RESPONSE" | pbcopy
echo "" >&2
echo "📋  Ответ скопирован в буфер." >&2
EOF

chmod +x ~/mlxwhisper/ask-claude
sudo ln -sf ~/mlxwhisper/ask-claude /usr/local/bin/ask-claude
```

Добавить API-ключ в `~/.zshrc`:

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-api03-XXXXX"' >> ~/.zshrc
source ~/.zshrc
```

Использование:

```bash
ask-claude ru    # говоришь вопрос → получаешь структурированный ответ
ask-claude en    # то же на английском
```

### 10.3 Предзагрузка модели (убрать задержку первого запуска)

```bash
cat > ~/mlxwhisper/preload.py << 'PYEOF'
#!/usr/bin/env python3
"""Предзагрузить модель Whisper в кеш HuggingFace."""
import mlx_whisper
import os
import tempfile
import wave
import numpy as np

model = os.environ.get("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
print(f"Загрузка модели: {model}")

# Создать пустой WAV для прогрева
with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    tmp = f.name
    with wave.open(tmp, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(np.zeros(16000, dtype=np.int16).tobytes())

result = mlx_whisper.transcribe(tmp, path_or_hf_repo=model)
os.unlink(tmp)
print(f"✅  Модель загружена и прогрета: {model}")
PYEOF

# Запустить один раз (скачает ~1.6 GB модель и прогреет кеш)
cd ~/mlxwhisper && source .venv/bin/activate && python preload.py
```

> На M5 с 24 GB прогрев занимает ~10-15 секунд. После этого каждый вызов `mlxw` стартует мгновенно.

### 10.4 Опционально: добавить в автозагрузку

```bash
# Добавить Pluely в автозагрузку
osascript -e 'tell application "System Events" to make login item at end with properties {path:"/Applications/Pluely.app", hidden:true}'
```

---

## Шаг 11. Устранение проблем

### PyAudio не ставится

```bash
# Убедиться, что portaudio установлен
brew install portaudio

# Если всё равно ошибка — указать путь
pip install pyaudio --global-option="build_ext" \
  --global-option="-I$(brew --prefix portaudio)/include" \
  --global-option="-L$(brew --prefix portaudio)/lib"
```

### Микрофон не работает / нет доступа

```bash
# macOS требует разрешение на микрофон для Terminal
# System Settings → Privacy & Security → Microphone → включить Terminal / iTerm
```

### Whisper галлюцинирует (повторяет слова, выдаёт мусор)

На `large-v3-turbo` галлюцинации редки, но возможны при длинной тишине или фоновом шуме:

```bash
# Решение 1: повысить порог тишины (не записывать шум)
SILENCE_THRESHOLD=800 python rt.py --single

# Решение 2: зафиксировать язык (убрать автодетект)
python rt.py --single --lang ru

# Решение 3: если turbo всё равно галлюцинирует — попробовать full large-v3
WHISPER_MODEL=mlx-community/whisper-large-v3-mlx python rt.py --single --lang ru
```

### Pluely видно в screen share

```bash
# Убедиться что:
# 1. Always on Top включён
# 2. Transparency включена
# 3. В macOS: System Settings → Privacy & Security → Screen Recording →
#    Pluely НЕ должен быть в списке (или убрать галочку)
```

---

## Итоговая структура файлов

```
~/mlxwhisper/
├── .venv/                 # виртуальное окружение Python
├── rt.py                  # основной скрипт STT
├── mlxw                   # обёртка для быстрого вызова
├── mlxw-notify            # обёртка с macOS-уведомлением
├── ask-claude             # пайплайн: STT → Claude API
├── preload.py             # предзагрузка модели
└── interview-prompt.txt   # system prompt для интервью

/usr/local/bin/
├── mlxw -> ~/mlxwhisper/mlxw
├── mlxw-notify -> ~/mlxwhisper/mlxw-notify
└── ask-claude -> ~/mlxwhisper/ask-claude
```

---

## Чеклист перед интервью

- [ ] `mlxw ru` работает, текст попадает в буфер
- [ ] Pluely запущен, overlay виден только тебе
- [ ] API-ключ провайдера настроен в Pluely
- [ ] Хоткей для mlxw назначен и работает
- [ ] Микрофон работает (проверить через `mlxw`)
- [ ] System Audio в Pluely включён (опционально)
- [ ] Pluely скрыт из Dock
- [ ] Тестовый прогон: хоткей → фраза → буфер → Pluely → ответ
