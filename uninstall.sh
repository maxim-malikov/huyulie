#!/bin/bash

# MLX Whisper - Полное удаление
# Удаляет все компоненты и конфигурации

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${RED}    MLX Whisper - Полное удаление${NC}"
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Будет удалено:${NC}"
echo "  • MLX Whisper и все файлы проекта"
echo "  • Конфигурация Hammerspoon"
echo "  • Загруженные модели (~1.6GB)"
echo "  • BlackHole (опционально)"
echo "  • Все временные файлы"
echo ""
read -p "Продолжить удаление? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Удаление отменено"
    exit 0
fi

# 1. Остановить все процессы
print_step "Остановка процессов..."
killall Python python3 2>/dev/null || true
killall Hammerspoon 2>/dev/null || true
rm -f /tmp/mlxw-stop /tmp/mlxw-pid
print_success "Процессы остановлены"

# 2. Удалить директорию проекта
print_step "Удаление MLX Whisper..."
if [ -d ~/mlxwhisper ]; then
    rm -rf ~/mlxwhisper
    print_success "MLX Whisper удален"
else
    print_warning "Директория MLX Whisper не найдена"
fi

# 3. Удалить конфиг Hammerspoon
print_step "Удаление конфига Hammerspoon..."
if [ -f ~/.hammerspoon/init.lua ]; then
    # Проверяем, наш ли это конфиг
    if grep -q "MLX Whisper" ~/.hammerspoon/init.lua; then
        # Создаем бэкап на всякий случай
        cp ~/.hammerspoon/init.lua ~/.hammerspoon/init.lua.uninstall_backup
        rm ~/.hammerspoon/init.lua
        print_success "Конфиг Hammerspoon удален (бэкап: init.lua.uninstall_backup)"
    else
        print_warning "Обнаружен пользовательский конфиг Hammerspoon, не удаляем"
    fi
else
    print_warning "Конфиг Hammerspoon не найден"
fi

# 4. Удалить загруженные модели
print_step "Удаление моделей Whisper (~1.6GB)..."
MODELS_FOUND=false
if [ -d ~/.cache/huggingface ]; then
    if ls ~/.cache/huggingface/hub/models--mlx-community--whisper* 1> /dev/null 2>&1; then
        rm -rf ~/.cache/huggingface/hub/models--mlx-community--whisper*
        MODELS_FOUND=true
        print_success "Модели Whisper удалены"
    fi
fi
if [ "$MODELS_FOUND" = false ]; then
    print_warning "Модели Whisper не найдены"
fi

# 5. BlackHole
echo ""
read -p "Удалить BlackHole? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Удаление BlackHole..."

    # Остановить Core Audio
    sudo killall coreaudiod 2>/dev/null || true
    sleep 1

    # Удалить через brew
    brew uninstall --force --cask blackhole-2ch 2>/dev/null || true
    brew uninstall --force --cask blackhole-16ch 2>/dev/null || true

    # Удалить вручную если осталось
    if [ -d "/Library/Audio/Plug-Ins/HAL/BlackHole2ch.driver" ] || [ -d "/Library/Audio/Plug-Ins/HAL/BlackHole16ch.driver" ]; then
        print_warning "Требуются права администратора для удаления драйвера"
        sudo rm -rf /Library/Audio/Plug-Ins/HAL/BlackHole*.driver
        sudo launchctl kickstart -k system/com.apple.audio.coreaudiod
    fi

    print_success "BlackHole удален"
else
    print_warning "BlackHole оставлен"
fi

# 6. Hammerspoon
echo ""
read -p "Удалить Hammerspoon? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Удаление Hammerspoon..."
    brew uninstall --cask hammerspoon 2>/dev/null || true
    rm -rf ~/Library/Application\ Support/Hammerspoon 2>/dev/null || true
    print_success "Hammerspoon удален"
else
    print_warning "Hammerspoon оставлен"
fi

# 7. SoX
echo ""
read -p "Удалить SoX? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Удаление SoX..."
    brew uninstall sox 2>/dev/null || true
    print_success "SoX удален"
else
    print_warning "SoX оставлен"
fi

# 8. Очистка pip кэша
print_step "Очистка кэша pip..."
pip cache purge 2>/dev/null || true
print_success "Кэш очищен"

# 9. Очистка временных файлов
print_step "Очистка временных файлов..."
rm -f /tmp/mlxw* 2>/dev/null || true
rm -rf ~/Library/Caches/mlx* 2>/dev/null || true
print_success "Временные файлы удалены"

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Удаление завершено${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "Удалено:"
echo "  ✓ MLX Whisper и все файлы проекта"
echo "  ✓ Конфигурации и модели"
echo "  ✓ Временные файлы"
echo ""
echo "Для повторной установки выполните:"
echo "git clone https://github.com/maxim-malikov/huyulie.git ~/mlxwhisper && cd ~/mlxwhisper && ./install.sh"
echo ""