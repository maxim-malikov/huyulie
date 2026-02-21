#!/bin/bash
# Скрипт для выполнения после перезагрузки

echo "🔍 Проверка BlackHole после перезагрузки..."
echo "============================================"

cd ~/mlxwhisper
source .venv/bin/activate

echo ""
echo "1️⃣ Список аудио устройств:"
python debug_audio.py --list-only 2>/dev/null | grep -E "(BlackHole|Interview)"

echo ""
echo "2️⃣ Настройка Multi-Output Device:"
echo "   Откройте Audio MIDI Setup (⌘+Space → Audio MIDI Setup)"
echo "   - Найдите 'Interview Audio' (или создайте новый Multi-Output Device)"
echo "   - Убедитесь что отмечены:"
echo "     ✅ BlackHole 2ch"
echo "     ✅ PLT Focus (ваши наушники)"
echo "   - Включите 'Drift Correction' для BlackHole 2ch"

echo ""
echo "3️⃣ Тест записи системного звука:"
echo "   # Включите любое видео на YouTube"
echo "   # Убедитесь что Output = Interview Audio"
echo "   # Запустите тест:"
echo "   python debug_audio.py --device [НОМЕР_BLACKHOLE] --duration 10"

echo ""
echo "4️⃣ Проверка автоопределения:"
python rt_toggle.py --check-setup 2>/dev/null | grep -i blackhole

echo ""
echo "============================================"
echo "✅ Если видите BlackHole 2ch в списке - всё готово!"
echo "❌ Если нет - попробуйте еще раз перезагрузить Mac"