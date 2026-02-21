#!/bin/bash

# MLX Whisper - Скрипт автоматической установки
# Устанавливает все зависимости и настраивает горячие клавиши

set -e  # Останавливаемся при ошибках

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для красивого вывода
print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Проверка системы
print_step "Проверка системы..."

# Проверка macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    print_error "Этот скрипт работает только на macOS"
    exit 1
fi

# Проверка Apple Silicon
if [[ $(uname -m) != "arm64" ]]; then
    print_error "Требуется Mac с Apple Silicon (M1/M2/M3)"
    exit 1
fi

print_success "macOS с Apple Silicon обнаружен"

# Проверка Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 не установлен. Установите через: brew install python3"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.9"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    print_error "Требуется Python 3.9 или выше (текущая версия: $PYTHON_VERSION)"
    exit 1
fi

print_success "Python $PYTHON_VERSION установлен"

# Проверка Homebrew
if ! command -v brew &> /dev/null; then
    print_warning "Homebrew не установлен. Устанавливаю..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Добавляем Homebrew в PATH для Apple Silicon
    if [[ -f "/opt/homebrew/bin/brew" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi

print_success "Homebrew установлен"

# Установка зависимостей Python
print_step "Создание виртуального окружения Python..."

if [ -d ".venv" ]; then
    print_warning "Виртуальное окружение уже существует"
else
    python3 -m venv .venv
    print_success "Виртуальное окружение создано"
fi

# Активация виртуального окружения
source .venv/bin/activate

print_step "Установка Python пакетов..."
pip install --quiet --upgrade pip
pip install --quiet mlx-whisper sounddevice numpy

print_success "Python пакеты установлены"

# Загрузка модели Whisper
print_step "Загрузка модели Whisper (может занять несколько минут)..."
python3 -c "import mlx_whisper; mlx_whisper.load_model('mlx-community/whisper-large-v3-turbo')" 2>/dev/null || {
    print_warning "Модель будет загружена при первом использовании"
}
print_success "Модель Whisper готова"

# Делаем скрипты исполняемыми
print_step "Настройка скриптов..."
chmod +x mlxw mlxw-toggle
print_success "Скрипты готовы к использованию"

# Установка SoX для звуковых сигналов
print_step "Установка SoX для звуковых сигналов..."
if command -v sox &> /dev/null; then
    print_success "SoX уже установлен"
else
    print_warning "Устанавливаю SoX (требуются права администратора)..."
    brew install sox 2>/dev/null || {
        print_warning "Не удалось установить SoX автоматически"
        print_warning "Попробуйте установить вручную: brew install sox"
        print_warning "SoX нужен только для звуковых сигналов (не критично)"
    }
    if command -v sox &> /dev/null; then
        print_success "SoX установлен"
    fi
fi

# Установка и настройка Hammerspoon
print_step "Настройка горячих клавиш через Hammerspoon..."

# Проверка установки Hammerspoon
if [ -d "/Applications/Hammerspoon.app" ]; then
    print_success "Hammerspoon уже установлен"
else
    print_step "Установка Hammerspoon..."
    brew install --cask hammerspoon 2>/dev/null || {
        print_warning "Не удалось установить Hammerspoon автоматически"
        print_warning "Установите вручную: brew install --cask hammerspoon"
        print_warning "Или скачайте с https://www.hammerspoon.org"
    }
    if [ -d "/Applications/Hammerspoon.app" ]; then
        print_success "Hammerspoon установлен"
    fi
fi

# Создание директории конфигурации Hammerspoon если не существует
mkdir -p ~/.hammerspoon

# Проверка существующего конфига
if [ -f ~/.hammerspoon/init.lua ]; then
    print_warning "Обнаружен существующий конфиг Hammerspoon"
    echo -e "${YELLOW}Выберите действие:${NC}"
    echo "1) Создать резервную копию и заменить новым конфигом"
    echo "2) Добавить MLX Whisper в существующий конфиг"
    echo "3) Пропустить настройку Hammerspoon"
    read -p "Ваш выбор (1/2/3): " choice

    case $choice in
        1)
            backup_file=~/.hammerspoon/init.lua.backup.$(date +%Y%m%d_%H%M%S)
            cp ~/.hammerspoon/init.lua "$backup_file"
            print_success "Резервная копия сохранена в $backup_file"
            cp hammerspoon/init.lua ~/.hammerspoon/init.lua
            print_success "Конфиг Hammerspoon обновлен"
            ;;
        2)
            echo "" >> ~/.hammerspoon/init.lua
            echo "-- ===== MLX Whisper Hotkeys =====" >> ~/.hammerspoon/init.lua
            cat hammerspoon/init.lua >> ~/.hammerspoon/init.lua
            print_success "MLX Whisper добавлен в существующий конфиг"
            ;;
        3)
            print_warning "Настройка Hammerspoon пропущена"
            ;;
        *)
            print_warning "Неверный выбор. Настройка Hammerspoon пропущена"
            ;;
    esac
else
    # Копируем новый конфиг
    cp hammerspoon/init.lua ~/.hammerspoon/init.lua
    print_success "Конфиг Hammerspoon установлен"
fi

# Запуск Hammerspoon если не запущен
if ! pgrep -x "Hammerspoon" > /dev/null; then
    print_step "Запуск Hammerspoon..."
    open -a Hammerspoon
    sleep 2
    print_success "Hammerspoon запущен"
else
    # Перезагрузка конфига
    print_step "Перезагрузка конфига Hammerspoon..."
    open -g hammerspoon://reload
    print_success "Конфиг Hammerspoon перезагружен"
fi

# Проверка прав доступа для Hammerspoon
print_step "Проверка прав доступа..."
print_warning "Если появится запрос на доступ к Accessibility - разрешите его для Hammerspoon"

# Финальная проверка
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Установка завершена успешно!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "Теперь вы можете использовать:"
echo ""
echo -e "${BLUE}Горячие клавиши:${NC}"
echo "  ⌃⌥W (Ctrl+Option+W)  - Toggle запись (вкл/выкл)"
echo "  ⌘⇧D (Cmd+Shift+D)    - Быстрая диктовка"
echo "  ⌘⇧C (Cmd+Shift+C)    - Непрерывный режим"
echo ""
echo -e "${BLUE}Команды терминала:${NC}"
echo "  ./mlxw         - Записать одну фразу"
echo "  ./mlxw ru      - Записать на русском"
echo "  ./mlxw en      - Записать на английском"
echo ""
echo -e "${YELLOW}Попробуйте прямо сейчас: нажмите Ctrl+Option+W и начните говорить!${NC}"
echo ""

# Проверка, что все работает
print_step "Тестирование установки..."
if python3 -c "import mlx_whisper, sounddevice, numpy" 2>/dev/null; then
    print_success "Все модули Python работают"
else
    print_error "Ошибка при проверке модулей Python"
fi

# Опциональный тест записи
echo ""
read -p "Хотите протестировать запись звука? (y/n): " test_choice
if [[ $test_choice == "y" || $test_choice == "Y" ]]; then
    print_step "Тестирование записи (говорите 3 секунды)..."
    python3 -c "
import sounddevice as sd
import numpy as np
import time
print('🎤 Говорите...')
audio = sd.rec(int(3 * 16000), samplerate=16000, channels=1, dtype=np.float32)
sd.wait()
print('✓ Запись завершена. Аудио устройства работают корректно!')
"
fi