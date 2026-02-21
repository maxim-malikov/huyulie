# Local Interview Assistant — Архитектура и описание

> Документация по реализованному решению.
> Дата: 2026-02-18

---

## Обзор

Локальный AI-ассистент для технических собеседований на macOS (Apple Silicon). Распознаёт русскую речь офлайн через Whisper, отправляет в LLM через стелс-overlay Pluely.

**Ключевое свойство:** вся обработка речи происходит локально на GPU Apple Silicon — никакие аудиоданные не покидают машину. Только текстовые запросы уходят в LLM API.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│  Ctrl+Option+W (toggle)                                     │
│       │                                                      │
│       ▼                                                      │
│  ┌──────────┐    /tmp/mlxw-stop    ┌──────────────────┐     │
│  │Hammerspoon├──────────────────────►  rt_toggle.py    │     │
│  │ (init.lua)│  создаёт стоп-файл  │  (Python + venv) │     │
│  └──────────┘                      └────────┬─────────┘     │
│       ▲                                      │               │
│       │ коллбэк (stdout)                     ▼               │
│       │                            ┌──────────────────┐     │
│       │                            │   PyAudio        │     │
│       │                            │   (микрофон)     │     │
│       │                            └────────┬─────────┘     │
│       │                                      │               │
│       │                                      ▼               │
│       │                            ┌──────────────────┐     │
│       │                            │  mlx-whisper     │     │
│       │                            │  large-v3-turbo  │     │
│       │                            │  (GPU Metal)     │     │
│       │                            └────────┬─────────┘     │
│       │                                      │               │
│       │                              текст в stdout          │
│       │                              + pyperclip.copy()      │
│       │◄─────────────────────────────────────┘               │
│       │                                                      │
│       ▼                                                      │
│  ┌──────────┐     Cmd+V          ┌──────────────────┐       │
│  │  Буфер   ├────────────────────►    Pluely        │       │
│  │  обмена  │                    │  (стелс overlay)  │       │
│  └──────────┘                    └────────┬─────────┘       │
│                                           │                  │
│                                           ▼                  │
│                                  ┌──────────────────┐       │
│                                  │   Claude API     │       │
│                                  │   (или другой)   │       │
│                                  └────────┬─────────┘       │
│                                           │                  │
│                                    ответ в overlay           │
└─────────────────────────────────────────────────────────────┘
```

---

## Компоненты

### 1. rt_toggle.py — запись и распознавание речи

**Расположение:** `~/mlxwhisper/rt_toggle.py`

**Что делает:**
- Запускается, сразу начинает записывать звук с микрофона через PyAudio (16 kHz, mono, 16-bit)
- Записывает всё аудио в память (массив numpy float32)
- Каждый чанк (~64ms) проверяет наличие файла `/tmp/mlxw-stop`
- Когда стоп-файл появляется → останавливает запись
- Сохраняет аудио во временный WAV
- Отправляет в `mlx_whisper.transcribe()` с моделью `whisper-large-v3-turbo`
- Результат: текст в stdout + копия в буфер обмена через `pyperclip`
- Удаляет временные файлы (`/tmp/mlxw-stop`, `/tmp/mlxw-pid`)

**Модель:** `mlx-community/whisper-large-v3-turbo`
- 809M параметров, ~1.6 GB на диске
- Encoder: 32 layers (тяжёлый, ложится на GPU)
- Decoder: 4 layers (лёгкий, быстрый)
- Качество русского на уровне large-v2
- Латенция на M5: ~1-2 секунды на фразу

**Переменные окружения:**
- `WHISPER_MODEL` — переопределить модель (по умолчанию `mlx-community/whisper-large-v3-turbo`)

### 2. mlxw-toggle — shell-обёртка

**Расположение:** `~/mlxwhisper/mlxw-toggle`

**Что делает:**
- Простой bash-скрипт, вызывает `rt_toggle.py` через абсолютный путь к Python из venv
- Нужен потому что Hammerspoon запускает процессы с минимальным окружением (без PATH, без venv)
- Принимает один аргумент — код языка (по умолчанию `ru`)

**Содержимое:**
```bash
#!/bin/bash
cd ~/mlxwhisper
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
~/mlxwhisper/.venv/bin/python ~/mlxwhisper/rt_toggle.py --lang "${1:-ru}"
```

**Критический момент:** использование `~/mlxwhisper/.venv/bin/python` вместо `source .venv/bin/activate && python` — `source` не работает надёжно при вызове из Hammerspoon.

### 3. init.lua — конфигурация Hammerspoon

**Расположение:** `~/.hammerspoon/init.lua`

**Что делает:**
- Регистрирует глобальный хоткей `Ctrl+Option+W` (работает в любой раскладке, включая русскую)
- Toggle-логика на state machine с двумя состояниями:
  - `isRecording = false` → первое нажатие → запускает `mlxw-toggle` как фоновый процесс, `isRecording = true`
  - `isRecording = true` → второе нажатие → создаёт файл `/tmp/mlxw-stop`, скрипт завершается
- Коллбэк при завершении процесса: читает stdout, копирует в буфер, показывает alert
- Отдельный хоткей `Ctrl+Option+R` для перезагрузки конфига

**Механизм коммуникации:** файловый сигнал через `/tmp/mlxw-stop`
- Hammerspoon создаёт файл → Python-скрипт видит его при следующей проверке (каждые ~64ms) → останавливается
- Альтернативы (kill -SIGTERM, stdin pipe) менее надёжны с `hs.task`

### 4. Pluely — стелс AI-overlay

**Расположение:** `/Applications/Pluely.app`

**Что делает:**
- Плавающее окно поверх всех приложений
- Невидимо при screen share / записи в Zoom, Meet, Teams
- Принимает текстовый ввод → отправляет в LLM API → показывает ответ
- Поддерживает любого провайдера через curl (Anthropic, OpenAI, Gemini, Grok)

**Хоткеи Pluely:**
| Действие | Хоткей |
|----------|--------|
| Показать/скрыть | `Cmd + \` |
| Dashboard | `Cmd + Shift + D` |
| Voice input | `Cmd + Shift + A` |
| Screenshot | `Cmd + Shift + S` |
| System Audio | `Cmd + Shift + M` |

---

## Поток данных на интервью

```
Интервьюер задаёт вопрос
        │
        ▼
[Ctrl+Option+W]  ← первое нажатие, старт записи
        │
   Диктуешь черновик ответа / пересказ вопроса
        │
        ▼
[Ctrl+Option+W]  ← второе нажатие, стоп
        │
   Whisper распознаёт локально (~1-2s)
        │
   Текст автоматически в буфере обмена
        │
        ▼
[Cmd+\]  ← открыть Pluely overlay
        │
[Cmd+V]  ← вставить текст
        │
   Pluely → Claude API → структурированный ответ
        │
   Читаешь ответ в overlay (невидим для интервьюера)
        │
        ▼
[Cmd+\]  ← скрыть Pluely
        │
   Отвечаешь своими словами
```

---

## Структура файлов

```
~/mlxwhisper/
├── .venv/                    # Python virtual environment
│   └── bin/python            # ← используется напрямую из mlxw-toggle
├── rt_toggle.py              # Основной скрипт: запись + распознавание (toggle mode)
├── rt.py                     # Старый скрипт: запись по тишине (single/continuous mode)
├── mlxw-toggle               # Shell-обёртка для Hammerspoon
├── mlxw                      # Shell-обёртка для старого rt.py
├── preload.py                # Предзагрузка модели в кеш
└── interview-prompt.txt      # System prompt для LLM

~/.hammerspoon/
└── init.lua                  # Глобальные хоткеи (toggle recording)

~/.cache/huggingface/
└── hub/models--mlx-community--whisper-large-v3-turbo/
    └── ...                   # Кеш модели (~1.6 GB, скачивается один раз)

/Applications/
└── Pluely.app                # Стелс AI-overlay

/tmp/
├── mlxw-stop                 # Сигнальный файл (создаётся при стопе, удаляется скриптом)
└── mlxw-pid                  # PID записывающего процесса
```

---

## Зависимости

### Python (внутри venv)
| Пакет | Назначение |
|-------|-----------|
| `mlx-whisper` | Whisper на Apple MLX (GPU Metal) |
| `pyaudio` | Захват аудио с микрофона |
| `numpy` | Обработка аудио-массивов |
| `pyperclip` | Копирование в буфер обмена |

### Системные
| Компонент | Назначение |
|-----------|-----------|
| `portaudio` (brew) | C-библиотека для PyAudio |
| `Hammerspoon.app` | Глобальные хоткеи и автоматизация |
| `Pluely.app` | Стелс AI-overlay |

---

## Известные особенности

1. **Русская раскладка и Hammerspoon:** при активной русской раскладке Hammerspoon показывает предупреждение `key 'w' not found in active keymap` и маппит на `ц`. Хоткей работает корректно по физической клавише.

2. **Gatekeeper на macOS:** Pluely не подписан Apple Developer сертификатом. При первом запуске macOS покажет "is damaged and can't be opened". Решение: `xattr -cr /Applications/Pluely.app`

3. **Первый запуск модели:** при первом вызове `rt_toggle.py` скачивается модель (~1.6 GB) в `~/.cache/huggingface/`. Последующие запуски мгновенные.

4. **venv и Hammerspoon:** `hs.task` запускает процессы с минимальным окружением. `source .venv/bin/activate` не работает. Решение — абсолютный путь: `~/mlxwhisper/.venv/bin/python`.
