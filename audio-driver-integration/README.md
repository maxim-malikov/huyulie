# Audio Driver Integration

Эта директория содержит конфигурации и скрипты для интеграции с виртуальным аудио драйвером BlackHole.

## Зачем это нужно?

BlackHole позволяет:
- Записывать системный звук (например, из браузера, Zoom, Discord)
- Создавать сложные аудио маршруты
- Транскрибировать звук из любых приложений
- Использовать MLX Whisper с виртуальными аудио устройствами

## Файлы в этой директории

### Основные скрипты

- `install_blackhole.sh` — автоматическая установка BlackHole
- `setup_blackhole.sh` — настройка Multi-Output Device для одновременного вывода на динамики и BlackHole
- `after_reboot.sh` — скрипт для восстановления настроек после перезагрузки

### Документация

- `SETUP_INSTRUCTIONS.md` — подробная инструкция по настройке BlackHole
- `FIX_HEADPHONES.md` — решение проблем с наушниками при использовании BlackHole

### Утилиты

- `debug_audio.py` — диагностика аудио устройств и тестирование записи

## Быстрая установка BlackHole

```bash
cd audio-driver-integration
./install_blackhole.sh
```

## Использование

### 1. Запись системного звука

После установки BlackHole вы можете записывать звук из любого приложения:

```bash
# Переключите вывод звука на Multi-Output Device в настройках macOS
# Затем используйте MLX Whisper как обычно
../mlxw
```

### 2. Транскрибация звонков

Идеально для транскрибации Zoom, Teams, Discord:
1. Настройте Multi-Output Device через `setup_blackhole.sh`
2. В приложении выберите Multi-Output Device как устройство вывода
3. Запустите toggle-режим: `../mlxw-toggle`

### 3. Диагностика проблем

```bash
# Проверить доступные аудио устройства
python debug_audio.py

# Тест записи с конкретного устройства
python debug_audio.py --device "BlackHole 2ch"
```

## Важные замечания

⚠️ **После перезагрузки Mac:**
- Multi-Output Device может сбросить настройки
- Запустите `./after_reboot.sh` для восстановления

⚠️ **Проблемы с наушниками:**
- См. `FIX_HEADPHONES.md` для решения

⚠️ **Совместимость:**
- BlackHole требует macOS 10.10+
- Рекомендуется BlackHole 2ch для стерео

## Альтернативы

Если BlackHole не подходит, можно использовать:
- **Loopback** (платный, $99) — более удобный GUI
- **Soundflower** (бесплатный) — старый, но работает
- **Ground Control Caster** (бесплатный) — для стриминга

## Ссылки

- [BlackHole GitHub](https://github.com/ExistentialAudio/BlackHole)
- [BlackHole Wiki](https://github.com/ExistentialAudio/BlackHole/wiki)