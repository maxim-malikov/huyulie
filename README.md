# MLX Whisper - Быстрая голосовая диктовка для macOS

Минималистичная утилита для транскрибации речи в текст на macOS с использованием MLX и Whisper. Работает локально на Apple Silicon без отправки данных в облако.

## Что это?

После установки вы сможете:
- **⌃ Ctrl + ⌥ Option + W** — начать/остановить запись голоса → текст сразу в буфер обмена
- **⌘ Cmd + ⇧ Shift + D** — записать одну фразу → в буфер обмена
- **⌘ Cmd + ⇧ Shift + C** — непрерывная запись нескольких фраз

## Быстрая установка (copy-paste)

**Требования:** macOS с Apple Silicon (M1/M2/M3), Python 3.9+

### Шаг 1: Клонируйте репозиторий и установите зависимости

```bash
# Клонируем репозиторий
cd ~
git clone https://github.com/maxim-malikov/huyulie.git mlxwhisper
cd mlxwhisper

# Создаем виртуальное окружение Python
python3 -m venv .venv
source .venv/bin/activate

# Устанавливаем MLX Whisper и зависимости
pip install mlx-whisper sounddevice numpy

# Делаем скрипты исполняемыми
chmod +x mlxw mlxw-toggle

# Скачиваем модель Whisper (при первом запуске)
python -c "import mlx_whisper; mlx_whisper.load_model('mlx-community/whisper-large-v3-turbo')"
```

### Шаг 2: Установите Hammerspoon (для горячих клавиш)

```bash
# Устанавливаем Hammerspoon через Homebrew
brew install --cask hammerspoon

# Запускаем Hammerspoon
open -a Hammerspoon

# Разрешаем доступ к Accessibility в настройках macOS (появится запрос)
```

### Шаг 3: Установите SoX (для звуковых сигналов)

```bash
# Устанавливаем SoX для звуков начала/конца записи
brew install sox
```

### Шаг 4: Настройте горячие клавиши

```bash
# Копируем готовый конфиг Hammerspoon
cp ~/mlxwhisper/hammerspoon/init.lua ~/.hammerspoon/init.lua

# Перезагружаем Hammerspoon для применения настроек
open -g hammerspoon://reload
```

## Готово! Теперь нажмите:

**⌃ Ctrl + ⌥ Option + W** — начать запись (говорите)
**⌃ Ctrl + ⌥ Option + W** — остановить запись → текст в буфере обмена

Или используйте другие горячие клавиши:
- **⌘ Cmd + ⇧ Shift + D** — быстрая диктовка одной фразы
- **⌘ Cmd + ⇧ Shift + C** — непрерывный режим

## Использование из терминала

```bash
cd ~/mlxwhisper

# Одна фраза на русском
./mlxw ru

# Одна фраза на английском
./mlxw en

# Автоопределение языка
./mlxw

# Непрерывный режим
./mlxw continuous
```

## Настройка горячих клавиш

Чтобы изменить горячие клавиши, откройте `~/.hammerspoon/init.lua` и найдите секцию в начале файла:

```lua
local HOTKEYS = {
    -- Toggle-режим (включение/выключение записи)
    toggleDictation = {
        modifiers = {"ctrl", "alt"},   -- Измените на свои
        key = "W",                      -- Измените на свою клавишу
        lang = "ru"                     -- ru, en или nil для автодетекта
    },
    -- ... другие настройки
}
```

**Доступные модификаторы:**
- `"cmd"` — ⌘ Command
- `"shift"` — ⇧ Shift
- `"alt"` или `"option"` — ⌥ Option
- `"ctrl"` — ⌃ Control

После изменений нажмите **⌃ Ctrl + ⌥ Alt + R** или выполните:
```bash
open -g hammerspoon://reload
```

## Решение проблем

### Если Hammerspoon не реагирует на горячие клавиши

1. Откройте **Системные настройки → Защита и безопасность → Конфиденциальность → Универсальный доступ**
2. Добавьте Hammerspoon в список и включите галочку
3. Перезапустите Hammerspoon

### Если нет звука при записи

```bash
# Проверьте установку SoX
brew list sox || brew install sox
```

### Если модель не скачалась

```bash
cd ~/mlxwhisper
source .venv/bin/activate
python -c "import mlx_whisper; mlx_whisper.load_model('mlx-community/whisper-large-v3-turbo')"
```

## Архитектура

- `rt.py` — основной модуль записи и транскрибации
- `rt_toggle.py` — модуль для toggle-режима
- `mlxw` — обертка для командной строки
- `mlxw-toggle` — обертка для toggle-режима
- `hammerspoon/init.lua` — конфигурация горячих клавиш

Подробная документация в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Лицензия

MIT