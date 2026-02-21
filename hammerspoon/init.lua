-- ═══════════════════════════════════════════════════════
-- MLX Whisper - Конфигурация Hammerspoon
-- Горячие клавиши для голосовой диктовки
-- ═══════════════════════════════════════════════════════

-- ===== НАСТРОЙКИ ГОРЯЧИХ КЛАВИШ =====
-- Измените эти настройки на удобные вам сочетания клавиш
local HOTKEYS = {
    -- Быстрая диктовка (одна фраза)
    quickDictation = {
        modifiers = {"cmd", "shift"},  -- Модификаторы: cmd, shift, ctrl, alt, fn
        key = "D",                     -- Основная клавиша
        lang = "ru"                    -- Язык по умолчанию: ru, en или nil для автодетекта
    },

    -- Toggle-режим (включение/выключение записи)
    toggleDictation = {
        modifiers = {"ctrl", "alt"},
        key = "W",
        lang = "ru"
    },

    -- Непрерывный режим
    continuousDictation = {
        modifiers = {"cmd", "shift"},
        key = "C",
        lang = "ru"
    },

    -- Перезагрузка конфига Hammerspoon
    reload = {
        modifiers = {"ctrl", "alt"},
        key = "R"
    }
}

-- ===== ПУТИ К СКРИПТАМ =====
-- Измените путь если установили mlxwhisper в другое место
local MLXW_PATH = os.getenv("HOME") .. "/mlxwhisper"
local MLXW = MLXW_PATH .. "/mlxw"
local MLXW_TOGGLE = MLXW_PATH .. "/mlxw-toggle"

-- ===== ВНУТРЕННИЕ ПЕРЕМЕННЫЕ =====
local mlxwTask = nil       -- ссылка на запущенный процесс
local isRecording = false  -- текущее состояние toggle-режима
local STOP_FILE = "/tmp/mlxw-stop"
local PID_FILE = "/tmp/mlxw-pid"

-- ═══════════════════════════════════════════════════════
-- 1. БЫСТРАЯ ДИКТОВКА (одна фраза)
-- ═══════════════════════════════════════════════════════
hs.hotkey.bind(HOTKEYS.quickDictation.modifiers, HOTKEYS.quickDictation.key, function()
    hs.alert.show("🎤 Слушаю...", 1)

    local langArg = HOTKEYS.quickDictation.lang or ""

    hs.task.new("/bin/bash", function(exitCode, stdOut, stdErr)
        if exitCode == 0 and stdOut and #stdOut:gsub("%s+", "") > 0 then
            local text = stdOut:gsub("%s+$", "")
            hs.pasteboard.setContents(text)
            -- Показать первые 80 символов результата
            local preview = #text > 80 and text:sub(1, 80) .. "…" or text
            hs.alert.show("✅ " .. preview, 2)
        else
            hs.alert.show("❌ Не распознано", 2)
        end
    end, {"-c", MLXW .. " " .. langArg}):start()
end)

-- ═══════════════════════════════════════════════════════
-- 2. TOGGLE-РЕЖИМ (вкл/выкл записи)
-- ═══════════════════════════════════════════════════════
hs.hotkey.bind(HOTKEYS.toggleDictation.modifiers, HOTKEYS.toggleDictation.key, function()

    if not isRecording then
        -- ══ СТАРТ ЗАПИСИ ══
        isRecording = true
        hs.alert.show("🔴 REC — говорите...", 1.5)

        local langArg = HOTKEYS.toggleDictation.lang or "ru"

        mlxwTask = hs.task.new("/bin/bash", function(exitCode, stdOut, stdErr)
            -- Коллбэк: вызывается когда процесс завершился
            isRecording = false
            mlxwTask = nil

            if exitCode == 0 and stdOut and #stdOut:gsub("%s+", "") > 0 then
                local text = stdOut:gsub("%s+$", "")
                hs.pasteboard.setContents(text)
                -- Показать первые 80 символов
                local preview = #text > 80 and text:sub(1, 80) .. "…" or text
                hs.alert.show("📋 " .. preview, 3)
            else
                hs.alert.show("❌ Не распознано", 2)
            end
        end, {"-c", MLXW_TOGGLE .. " " .. langArg})

        mlxwTask:start()
    else
        -- ══ СТОП ЗАПИСИ ══
        hs.alert.show("⏹ Стоп. Распознаю...", 2)
        -- Создать стоп-файл — скрипт увидит его и остановится
        local f = io.open(STOP_FILE, "w")
        if f then
            f:write("stop")
            f:close()
        end
    end
end)

-- ═══════════════════════════════════════════════════════
-- 3. НЕПРЕРЫВНЫЙ РЕЖИМ
-- ═══════════════════════════════════════════════════════
hs.hotkey.bind(HOTKEYS.continuousDictation.modifiers, HOTKEYS.continuousDictation.key, function()
    hs.alert.show("🎙 Непрерывный режим", 1.5)

    local langArg = HOTKEYS.continuousDictation.lang or "ru"

    -- Запускаем в терминале для интерактивного режима
    hs.execute("open -a Terminal " .. MLXW_PATH)
    hs.timer.doAfter(1, function()
        hs.eventtap.keyStroke({}, "return")
        hs.timer.doAfter(0.5, function()
            hs.eventtap.keyStrokes("./mlxw continuous " .. langArg)
            hs.eventtap.keyStroke({}, "return")
        end)
    end)
end)

-- ═══════════════════════════════════════════════════════
-- 4. ПЕРЕЗАГРУЗКА КОНФИГА
-- ═══════════════════════════════════════════════════════
hs.hotkey.bind(HOTKEYS.reload.modifiers, HOTKEYS.reload.key, function()
    -- Cleanup при перезагрузке
    if mlxwTask then
        mlxwTask:terminate()
        mlxwTask = nil
    end
    isRecording = false
    os.remove(STOP_FILE)
    os.remove(PID_FILE)
    hs.alert.show("♻️ Перезагрузка конфига...", 1)
    hs.reload()
end)

-- ═══════════════════════════════════════════════════════
-- ИНИЦИАЛИЗАЦИЯ
-- ═══════════════════════════════════════════════════════

-- Cleanup при старте
os.remove(STOP_FILE)
os.remove(PID_FILE)

-- Показать активные горячие клавиши при загрузке
local function formatHotkey(hotkey)
    local mods = table.concat(hotkey.modifiers, "+")
    return mods .. "+" .. hotkey.key
end

hs.alert.show("MLX Whisper готов\n" ..
    "🎤 " .. formatHotkey(HOTKEYS.quickDictation) .. " — быстрая диктовка\n" ..
    "🔴 " .. formatHotkey(HOTKEYS.toggleDictation) .. " — toggle-режим\n" ..
    "🎙 " .. formatHotkey(HOTKEYS.continuousDictation) .. " — непрерывный", 3)