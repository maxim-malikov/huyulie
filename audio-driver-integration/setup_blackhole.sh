#!/bin/bash
# Установка и настройка BlackHole для захвата системного звука

echo "🎧 Установка BlackHole для захвата системного звука..."
echo "=" * 60

# Установка BlackHole через Homebrew
if ! brew list blackhole-2ch &>/dev/null; then
    echo "📦 Устанавливаем BlackHole..."
    brew install --cask blackhole-2ch
else
    echo "✅ BlackHole уже установлен"
fi

echo ""
echo "🔧 НАСТРОЙКА (выполните вручную):"
echo "=" * 60
echo ""
echo "1. Откройте 'Audio MIDI Setup' (⌘+Space → Audio MIDI Setup)"
echo ""
echo "2. Создайте Multi-Output Device:"
echo "   - Нажмите '+' внизу слева → 'Create Multi-Output Device'"
echo "   - Отметьте галочками:"
echo "     ✓ BlackHole 2ch"
echo "     ✓ Ваши наушники (AirPods/внешние наушники)"
echo "   - Переименуйте в 'Interview Audio'"
echo ""
echo "3. В System Settings → Sound:"
echo "   - Output: выберите 'Interview Audio'"
echo "   - Теперь звук идёт И в наушники, И в BlackHole"
echo ""
echo "4. Протестируйте:"
echo "   cd ~/mlxwhisper && source .venv/bin/activate"
echo "   python debug_audio.py --list-only"
echo "   # Найдите номер устройства BlackHole 2ch"
echo "   python debug_audio.py --device [НОМЕР_BLACKHOLE]"
echo ""
echo "=" * 60
echo "💡 После настройки звук интервьюера будет захватываться даже в наушниках!"