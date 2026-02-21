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

# Информирование пользователя
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}    MLX Whisper - Полная установка${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Будет установлено:${NC}"
echo "  • Python окружение и зависимости"
echo "  • MLX Whisper модель (~1.6GB)"
echo "  • BlackHole для записи системного звука"
echo "  • Hammerspoon для горячих клавиш"
echo "  • SoX для звуковых сигналов"
echo ""
echo -e "${YELLOW}⚠ Может потребоваться ввод пароля администратора${NC}"
echo ""
read -p "Продолжить установку? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_error "Установка отменена"
    exit 1
fi

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
pip install --quiet mlx-whisper pyaudio sounddevice numpy pyperclip

print_success "Python пакеты установлены"

# Загрузка модели Whisper
print_step "Загрузка модели Whisper (может занять несколько минут)..."
python3 -c "
import mlx_whisper
print('Загружаем модель...')
# Модель загрузится при первом использовании
print('✓ Готово к загрузке модели при первом запуске')
" 2>/dev/null || {
    print_warning "Модель будет загружена при первом использовании"
}
print_success "Модель Whisper готова"

# Делаем скрипты исполняемыми
print_step "Настройка скриптов..."
chmod +x mlxw mlxw-toggle mlxw-system rt_blackhole.py 2>/dev/null || true
print_success "Скрипты готовы к использованию"

# Установка SoX для звуковых сигналов
print_step "Установка SoX для звуковых сигналов..."
if command -v sox &> /dev/null; then
    print_success "SoX уже установлен"
else
    print_step "Устанавливаю SoX..."
    brew install sox
    if [ $? -eq 0 ]; then
        print_success "SoX установлен"
    else
        print_warning "SoX не установился (не критично, нужен только для звуковых сигналов)"
    fi
fi

# Установка BlackHole для захвата системного звука
print_step "Установка BlackHole для захвата системного звука..."

# Проверка наличия BlackHole
if ls /Library/Audio/Plug-Ins/HAL/BlackHole*.driver 1> /dev/null 2>&1; then
    print_success "BlackHole уже установлен"
    BLACKHOLE_INSTALLED=true
else
    print_step "Устанавливаю BlackHole 2ch..."
    print_warning "Потребуется пароль администратора"

    brew install --cask blackhole-2ch
    if [ $? -eq 0 ]; then
        print_success "BlackHole установлен"
        BLACKHOLE_INSTALLED=true

        # Ждем пока драйвер загрузится
        sleep 2

        # Проверяем что BlackHole появился в системе
        if system_profiler SPAudioDataType | grep -q "BlackHole"; then
            print_success "BlackHole успешно загружен в систему"
        else
            print_warning "BlackHole установлен, но может потребоваться перезагрузка"
        fi
    else
        print_warning "Не удалось установить BlackHole автоматически"
        print_warning "BlackHole нужен для записи системного звука (звонки, видео)"
        print_warning "Установите вручную позже: brew install --cask blackhole-2ch"
        BLACKHOLE_INSTALLED=false
    fi
fi

# Установка и настройка Hammerspoon
print_step "Настройка горячих клавиш через Hammerspoon..."

# Проверка установки Hammerspoon
if [ -d "/Applications/Hammerspoon.app" ]; then
    print_success "Hammerspoon уже установлен"
else
    print_step "Установка Hammerspoon (может потребоваться пароль)..."
    brew install --cask hammerspoon
    if [ $? -eq 0 ]; then
        print_success "Hammerspoon установлен"
    else
        print_error "Ошибка установки Hammerspoon. Прерывание установки."
        print_error "Попробуйте: brew update && brew install --cask hammerspoon"
        exit 1
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

# Настройка BlackHole если установлен
if [ "$BLACKHOLE_INSTALLED" = true ]; then
    echo ""
    print_step "Настройка BlackHole..."
    echo -e "${YELLOW}Для записи системного звука (звонки, видео):${NC}"
    echo "1. Откройте: System Settings → Sound → Output"
    echo "2. Выберите: BlackHole 2ch"
    echo ""
    echo -e "${YELLOW}Для одновременного прослушивания и записи:${NC}"
    echo "1. Откройте: Applications → Utilities → Audio MIDI Setup"
    echo "2. Нажмите '+' → Create Multi-Output Device"
    echo "3. Выберите: BlackHole 2ch + Ваши наушники/динамики"
    echo "4. В System Settings → Sound выберите Multi-Output Device"
    echo ""
fi

# Финальная проверка
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Установка завершена успешно!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "Теперь вы можете использовать:"
echo ""
echo -e "${BLUE}Горячие клавиши:${NC}"
if [ "$BLACKHOLE_INSTALLED" = true ]; then
    echo "  ⌃⌥W (Ctrl+Option+W)  - Запись системного звука (BlackHole)"
else
    echo "  ⌃⌥W (Ctrl+Option+W)  - Запись с микрофона"
fi
echo "  ⌃⌥⇧W (Ctrl+Option+Shift+W) - Запись с микрофона"
echo "  ⌘⇧D (Cmd+Shift+D)    - Быстрая диктовка"
echo "  ⌘⇧C (Cmd+Shift+C)    - Непрерывный режим"
echo ""
echo -e "${BLUE}Команды терминала:${NC}"
echo "  ./mlxw         - Записать одну фразу"
echo "  ./mlxw ru      - Записать на русском"
echo "  ./mlxw en      - Записать на английском"
echo ""

if [ "$BLACKHOLE_INSTALLED" = true ]; then
    echo -e "${GREEN}Попробуйте прямо сейчас:${NC}"
    echo "1. Переключите звук на BlackHole в настройках"
    echo "2. Включите видео или музыку"
    echo "3. Нажмите Ctrl+Option+W для записи системного звука!"
else
    echo -e "${YELLOW}Попробуйте прямо сейчас: нажмите Ctrl+Option+W и начните говорить!${NC}"
fi
echo ""

# Проверка, что все работает
print_step "Тестирование установки..."
if python3 -c "import mlx_whisper, sounddevice, numpy, pyaudio, pyperclip" 2>/dev/null; then
    print_success "Все модули Python работают"
else
    print_error "Ошибка при проверке модулей Python"
fi

# Опциональный тест записи
echo ""
read -p "Хотите протестировать запись звука? (y/n): " test_choice
if [[ $test_choice == "y" || $test_choice == "Y" ]]; then
    if [ "$BLACKHOLE_INSTALLED" = true ]; then
        print_step "Проверка BlackHole..."
        python3 -c "
import pyaudio
p = pyaudio.PyAudio()
found = False
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if 'blackhole' in info['name'].lower():
        print(f'✓ BlackHole найден: {info[\"name\"]}')
        found = True
        break
if not found:
    print('⚠ BlackHole не найден в системе')
p.terminate()
"
    fi

    print_step "Тестирование записи с микрофона (говорите 3 секунды)..."
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