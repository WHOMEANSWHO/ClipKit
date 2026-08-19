-- ClipKit helper
-- Starts Replay Buffer on launch and beeps when a clip or recording saves.
-- Remembers the last hooked game so it comes back without pressing the switch key.
-- Any FiveM shortcut / build is treated as the same game.
-- The clip sorter shows the main-monitor popup after the file is moved.

local obs = obslua
local ffi = nil
local user32 = nil
local kernel32 = nil
local start_tries = 0
local retry_running = false
local remember_enabled = true
local remember_timer_on = false
local switch_hotkey_id = obs.OBS_INVALID_HOTKEY_ID
local last_applied_spec = ""
local enum_windows_cb = nil
local enum_state = nil

local IGNORE_EXE = {
    obs64 = true,
    obs32 = true,
    obs = true,
    explorer = true,
    dwm = true,
    searchhost = true,
    clipkit = true,
    applicationframehost = true,
    shellexperiencehost = true,
    textinputhost = true,
    startmenuexperiencehost = true,
    systemsettings = true,
    taskmgr = true,
}

local last_status_key = ""
local save_pending = false
local command_timer_on = false
local last_from_source
local read_last_game

local function status_file()
    local appdata = os.getenv("APPDATA")
    if appdata == nil or appdata == "" then
        return nil
    end
    return appdata .. "\\obs-studio\\clipkit-status.txt"
end

local function command_file()
    local appdata = os.getenv("APPDATA")
    if appdata == nil or appdata == "" then
        return nil
    end
    return appdata .. "\\obs-studio\\clipkit-command.txt"
end

local function save_result_file()
    local appdata = os.getenv("APPDATA")
    if appdata == nil or appdata == "" then
        return nil
    end
    return appdata .. "\\obs-studio\\clipkit-save-result.txt"
end

local function last_game_path()
    local appdata = os.getenv("APPDATA")
    if appdata == nil or appdata == "" then
        return nil
    end
    return appdata .. "\\ClipKit\\last-game.json"
end

local function one_line(text)
    return tostring(text or ""):gsub("[\r\n]", " ")
end

local function write_save_result(ok, path, err)
    local dest = save_result_file()
    if dest == nil then
        return
    end
    local handle = io.open(dest, "w")
    if handle == nil then
        return
    end
    if ok then
        handle:write("ok=1\n")
    else
        handle:write("ok=0\n")
    end
    handle:write("path=" .. one_line(path) .. "\n")
    handle:write("error=" .. one_line(err) .. "\n")
    handle:close()
end

local hide_tries = 0

local function disable_desktop_audio()
    -- Channels 1 and 2 are Desktop Audio / Desktop Audio 2. Leave mic (3) alone.
    pcall(obs.obs_set_output_source, 1, nil)
    pcall(obs.obs_set_output_source, 2, nil)
    local sources = obs.obs_enum_sources()
    if sources == nil then
        return
    end
    for _, source in ipairs(sources) do
        local id = obs.obs_source_get_unversioned_id(source)
        if id == "wasapi_output_capture" then
            local priv = obs.obs_source_get_private_settings(source)
            obs.obs_data_set_bool(priv, "mixer_hidden", true)
            obs.obs_data_release(priv)
            pcall(obs.obs_source_set_muted, source, true)
            pcall(obs.obs_source_set_enabled, source, false)
        end
    end
    obs.source_list_release(sources)
end

function hide_desktop_tick()
    hide_tries = hide_tries + 1
    disable_desktop_audio()
    if hide_tries >= 10 then
        obs.timer_remove(hide_desktop_tick)
    end
end

local function keep_hiding_desktop()
    hide_tries = 0
    disable_desktop_audio()
    pcall(function()
        obs.timer_remove(hide_desktop_tick)
    end)
    obs.timer_add(hide_desktop_tick, 400)
end

local function show_obs_window()
    local ok, lib = pcall(require, "ffi")
    if not ok or lib == nil then
        return
    end
    pcall(function()
        lib.cdef[[
            typedef void* HWND;
            HWND GetActiveWindow();
            HWND GetForegroundWindow();
            int ShowWindow(HWND, int);
            int SetForegroundWindow(HWND);
        ]]
        local hwnd = lib.C.GetActiveWindow()
        if hwnd == nil then
            hwnd = lib.C.GetForegroundWindow()
        end
        if hwnd ~= nil then
            lib.C.ShowWindow(hwnd, 9)
            lib.C.SetForegroundWindow(hwnd)
        end
    end)
end

local function try_beep()
    local ok, lib = pcall(require, "ffi")
    if not ok or lib == nil then
        return
    end
    if ffi == nil then
        ffi = lib
        pcall(function()
            ffi.cdef[[ int MessageBeep(unsigned int); ]]
        end)
    end
    pcall(function()
        ffi.C.MessageBeep(0x00000040)
    end)
end

local function replay_is_on()
    local ok, active = pcall(obs.obs_frontend_replay_buffer_active)
    return ok and active
end

local function current_game()
    local game = last_from_source and last_from_source() or nil
    if game == nil and read_last_game then
        game = read_last_game()
    end
    return game
end

local function write_replay_status(on)
    local path = status_file()
    if path == nil then
        return
    end
    local game = current_game()
    local exe = game and one_line(game.exe) or ""
    local title = game and one_line(game.title) or ""
    local family = game and one_line(game.family) or ""
    local key = tostring(on and 1 or 0) .. "|" .. exe .. "|" .. title .. "|" .. family
    if key == last_status_key then
        return
    end
    last_status_key = key
    local handle = io.open(path, "w")
    if handle == nil then
        return
    end
    if on then
        handle:write("replay=1\n")
    else
        handle:write("replay=0\n")
    end
    handle:write("exe=" .. exe .. "\n")
    handle:write("title=" .. title .. "\n")
    handle:write("family=" .. family .. "\n")
    handle:close()
end

local function start_replay()
    if replay_is_on() then
        return true
    end
    pcall(obs.obs_frontend_replay_buffer_start)
    return replay_is_on()
end

local function stop_retry()
    if retry_running then
        obs.timer_remove(retry_start)
        retry_running = false
    end
end

function retry_start()
    start_tries = start_tries + 1
    if start_replay() then
        write_replay_status(true)
        obs.script_log(obs.LOG_INFO, "[ClipKit] Replay Buffer started")
        stop_retry()
        return
    end
    if start_tries >= 10 then
        write_replay_status(false)
        obs.script_log(obs.LOG_WARNING, "[ClipKit] Replay Buffer did not start")
        stop_retry()
    end
end

local function begin_retry()
    start_tries = 0
    if start_replay() then
        write_replay_status(true)
        obs.script_log(obs.LOG_INFO, "[ClipKit] Replay Buffer started")
        return
    end
    if not retry_running then
        obs.timer_add(retry_start, 1000)
        retry_running = true
    end
end

------------------------------------------------------------------------
-- Remember last hooked game / FiveM family
------------------------------------------------------------------------

local function json_escape(text)
    text = tostring(text or "")
    text = text:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\r", " "):gsub("\n", " ")
    return text
end

local function json_field(raw, key)
    return raw:match('"' .. key .. '"%s*:%s*"(.-)"') or ""
end

local function exe_stem(name)
    return tostring(name or ""):lower():gsub("%.exe$", "")
end

local function is_fivem_exe(name)
    local stem = exe_stem(name)
    if stem:find("fivem", 1, true) then
        return true
    end
    return stem:find("gtaprocess", 1, true) ~= nil and stem:find("cfx", 1, true) ~= nil
end

local function fivem_rank(name)
    local stem = exe_stem(name)
    if stem:find("dump", 1, true) or stem:find("crash", 1, true) or
        stem:find("chrome", 1, true) or stem:find("ros", 1, true) or
        stem:find("steamchild", 1, true) or stem:find("launcher", 1, true) then
        return 0
    end
    if stem:find("gtaprocess", 1, true) then
        return 3
    end
    if stem == "fivem" then
        return 1
    end
    if stem:find("fivem", 1, true) then
        return 0
    end
    return -1
end

local function game_family(exe, title)
    local combined = exe_stem(exe) .. " " .. tostring(title or ""):lower()
    if is_fivem_exe(exe) or combined:find("fivem", 1, true) or combined:find("cfx.re", 1, true) then
        return "fivem"
    end
    return exe_stem(exe)
end

local function ignored_exe(name)
    return IGNORE_EXE[exe_stem(name)] == true
end

read_last_game = function()
    local path = last_game_path()
    if path == nil then
        return nil
    end
    local handle = io.open(path, "r")
    if handle == nil then
        return nil
    end
    local raw = handle:read("*a") or ""
    handle:close()
    local exe = json_field(raw, "exe")
    if exe == "" then
        return nil
    end
    local title = json_field(raw, "title")
    local class_name = json_field(raw, "class")
    local family = json_field(raw, "family")
    if family == "" then
        family = game_family(exe, title)
    end
    return { exe = exe, title = title, class = class_name, family = family }
end

local function write_last_game(game)
    local path = last_game_path()
    if path == nil or game == nil or game.exe == nil or game.exe == "" then
        return
    end
    local handle = io.open(path, "w")
    if handle == nil then
        return
    end
    handle:write(string.format(
        '{"exe":"%s","class":"%s","title":"%s","family":"%s"}\n',
        json_escape(game.exe),
        json_escape(game.class or ""),
        json_escape(game.title or ""),
        json_escape(game.family or game_family(game.exe, game.title))
    ))
    handle:close()
end

local function window_spec(title, class_name, exe)
    local function token(value)
        return tostring(value or ""):gsub(":", " ")
    end
    return token(title) .. ":" .. token(class_name) .. ":" .. token(exe)
end

local function prepare_capture_ffi()
    if kernel32 ~= nil and user32 ~= nil and ffi ~= nil then
        return true
    end
    local ok, lib = pcall(require, "ffi")
    if not ok or lib == nil then
        return false
    end
    ffi = lib
    pcall(ffi.cdef, [[
        typedef void *HANDLE;
        typedef void *HWND;
        typedef unsigned long DWORD;
        typedef int BOOL;
        typedef long LONG;
        typedef uintptr_t ULONG_PTR;
        typedef intptr_t LPARAM;
        typedef wchar_t WCHAR;
    ]])
    pcall(ffi.cdef, [[
        typedef BOOL (*WNDENUMPROC)(HWND, LPARAM);

        typedef struct {
            DWORD dwSize;
            DWORD cntUsage;
            DWORD th32ProcessID;
            ULONG_PTR th32DefaultHeapID;
            DWORD th32ModuleID;
            DWORD cntThreads;
            DWORD th32ParentProcessID;
            LONG pcPriClassBase;
            DWORD dwFlags;
            WCHAR szExeFile[260];
        } PROCESSENTRY32W;

        HWND GetForegroundWindow();
        BOOL IsWindowVisible(HWND hwnd);
        int GetWindowTextW(HWND hwnd, WCHAR *text, int max);
        int GetClassNameW(HWND hwnd, WCHAR *text, int max);
        DWORD GetWindowThreadProcessId(HWND hwnd, DWORD *pid);
        BOOL EnumWindows(WNDENUMPROC callback, LPARAM lparam);
        short GetAsyncKeyState(int vKey);
        HANDLE OpenProcess(DWORD access, BOOL inherit, DWORD pid);
        BOOL QueryFullProcessImageNameW(HANDLE process, DWORD flags, WCHAR *name, DWORD *size);
        BOOL CloseHandle(HANDLE object);
        HANDLE CreateToolhelp32Snapshot(DWORD flags, DWORD pid);
        BOOL Process32FirstW(HANDLE snapshot, PROCESSENTRY32W *entry);
        BOOL Process32NextW(HANDLE snapshot, PROCESSENTRY32W *entry);
        int WideCharToMultiByte(unsigned int codePage, DWORD flags, const WCHAR *wide,
            int wideCount, char *out, int outCount, const char *def, BOOL *used);
    ]])
    local uok, ulib = pcall(ffi.load, "user32")
    local kok, klib = pcall(ffi.load, "kernel32")
    if not uok or not kok then
        return false
    end
    user32 = ulib
    kernel32 = klib
    return true
end

local function from_wide(buf)
    if ffi == nil or buf == nil then
        return ""
    end
    local n = kernel32.WideCharToMultiByte(65001, 0, buf, -1, nil, 0, nil, nil)
    if n <= 1 then
        return ""
    end
    local out = ffi.new("char[?]", n)
    kernel32.WideCharToMultiByte(65001, 0, buf, -1, out, n, nil, nil)
    return ffi.string(out)
end

local function exe_from_pid(pid)
    if pid == nil or pid == 0 then
        return ""
    end
    local handle = kernel32.OpenProcess(0x1000, 0, pid)
    if handle == nil or handle == ffi.cast("HANDLE", 0) then
        return ""
    end
    local size = ffi.new("DWORD[1]", 260)
    local buf = ffi.new("WCHAR[?]", 260)
    local ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, size)
    kernel32.CloseHandle(handle)
    if ok == 0 then
        return ""
    end
    local path = from_wide(buf)
    return path:match("([^\\/]+)$") or path
end

local function window_info(hwnd)
    if hwnd == nil or hwnd == ffi.cast("HWND", 0) then
        return nil
    end
    if user32.IsWindowVisible(hwnd) == 0 then
        return nil
    end
    local pid = ffi.new("DWORD[1]")
    user32.GetWindowThreadProcessId(hwnd, pid)
    local exe = exe_from_pid(pid[0])
    if exe == "" or ignored_exe(exe) then
        return nil
    end
    local title_buf = ffi.new("WCHAR[?]", 512)
    local class_buf = ffi.new("WCHAR[?]", 256)
    user32.GetWindowTextW(hwnd, title_buf, 512)
    user32.GetClassNameW(hwnd, class_buf, 256)
    local title = from_wide(title_buf)
    local class_name = from_wide(class_buf)
    if title == "" and class_name == "" then
        return nil
    end
    return {
        exe = exe,
        title = title,
        class = class_name,
        family = game_family(exe, title),
        rank = fivem_rank(exe),
        pid = tonumber(pid[0]),
    }
end

local function running_processes()
    local found = {}
    if not prepare_capture_ffi() then
        return found
    end
    local snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snap == nil or snap == ffi.cast("HANDLE", -1) then
        return found
    end
    local entry = ffi.new("PROCESSENTRY32W")
    entry.dwSize = ffi.sizeof(entry)
    if kernel32.Process32FirstW(snap, entry) ~= 0 then
        while true do
            local name = from_wide(entry.szExeFile)
            if name ~= "" then
                found[#found + 1] = { exe = name, pid = tonumber(entry.th32ProcessID) }
            end
            if kernel32.Process32NextW(snap, entry) == 0 then
                break
            end
        end
    end
    kernel32.CloseHandle(snap)
    return found
end

local function best_window_for_pids(wanted)
    if enum_windows_cb == nil then
        enum_windows_cb = ffi.cast("WNDENUMPROC", function(hwnd, _lparam)
            local info = window_info(hwnd)
            if info ~= nil and enum_state ~= nil and enum_state.wanted[info.pid] then
                local current = enum_state.best
                if current == nil or (info.rank or 0) > (current.rank or 0) then
                    enum_state.best = info
                end
            end
            return true
        end)
    end
    enum_state = { wanted = wanted, best = nil }
    user32.EnumWindows(enum_windows_cb, 0)
    local best = enum_state.best
    enum_state = nil
    return best
end

local function find_target(last)
    if not prepare_capture_ffi() then
        return nil
    end
    local processes = running_processes()
    local wanted = {}
    local best_rank = -1
    for _, proc in ipairs(processes) do
        local use = false
        local rank = 1
        if last ~= nil and last.family == "fivem" then
            rank = fivem_rank(proc.exe)
            use = rank >= 1
        elseif last ~= nil and last.exe ~= "" then
            use = exe_stem(proc.exe) == exe_stem(last.exe)
        end
        if use then
            wanted[proc.pid] = true
            if rank > best_rank then
                best_rank = rank
            end
        end
    end
    if next(wanted) == nil then
        return nil
    end
    return best_window_for_pids(wanted)
end

local function set_game_capture(game)
    if game == nil or game.exe == nil or game.exe == "" then
        return
    end
    local spec = window_spec(game.title, game.class, game.exe)
    if spec == last_applied_spec then
        return
    end
    local source = obs.obs_get_source_by_name("Game Capture")
    if source == nil then
        return
    end
    local settings = obs.obs_data_create()
    obs.obs_data_set_string(settings, "capture_mode", "window")
    obs.obs_data_set_string(settings, "window", spec)
    obs.obs_data_set_int(settings, "priority", 2)
    obs.obs_data_set_bool(settings, "capture_audio", true)
    obs.obs_source_update(source, settings)
    obs.obs_data_release(settings)
    obs.obs_source_release(source)
    last_applied_spec = spec
    obs.script_log(obs.LOG_INFO, "[ClipKit] Capturing " .. game.exe)
end

local function capture_mode_is_any()
    local source = obs.obs_get_source_by_name("Game Capture")
    if source == nil then
        return false
    end
    local settings = obs.obs_source_get_settings(source)
    local mode = obs.obs_data_get_string(settings, "capture_mode") or ""
    obs.obs_data_release(settings)
    obs.obs_source_release(source)
    return mode == "any"
end

local function parse_window_spec(spec)
    spec = tostring(spec or "")
    if spec == "" then
        return nil
    end
    local parts = {}
    for part in (spec .. ":"):gmatch("(.-):") do
        parts[#parts + 1] = part
    end
    if #parts < 3 then
        return nil
    end
    local exe = parts[#parts]
    local class_name = parts[#parts - 1]
    local title = table.concat(parts, ":", 1, #parts - 2)
    if exe == "" then
        return nil
    end
    return {
        exe = exe,
        class = class_name,
        title = title,
        family = game_family(exe, title),
    }
end

last_from_source = function()
    local source = obs.obs_get_source_by_name("Game Capture")
    if source == nil then
        return nil
    end
    local settings = obs.obs_source_get_settings(source)
    local spec = obs.obs_data_get_string(settings, "window") or ""
    obs.obs_data_release(settings)
    obs.obs_source_release(source)
    local parsed = parse_window_spec(spec)
    if parsed ~= nil and not ignored_exe(parsed.exe) then
        return parsed
    end
    return nil
end

function remember_tick()
    if not remember_enabled or capture_mode_is_any() then
        write_replay_status(replay_is_on())
        return
    end
    local last = read_last_game()
    if last == nil then
        last = last_from_source()
        if last ~= nil then
            write_last_game(last)
        end
    end
    if last == nil then
        write_replay_status(replay_is_on())
        return
    end
    local target = find_target(last)
    if target ~= nil then
        if last.family == "fivem" then
            target.family = "fivem"
        end
        write_last_game(target)
        set_game_capture(target)
    end
    write_replay_status(replay_is_on())
end

local function start_remember()
    if remember_timer_on then
        return
    end
    remember_tick()
    obs.timer_add(remember_tick, 1500)
    remember_timer_on = true
end

local function stop_remember()
    if remember_timer_on then
        obs.timer_remove(remember_tick)
        remember_timer_on = false
    end
end

------------------------------------------------------------------------
-- Push to talk: poll keys so mouse 4/5 still work in-game
------------------------------------------------------------------------

local ptt_enabled = false
local ptt_vks = {}
local ptt_timer_on = false
local ptt_talking = false
local ptt_release_at = 0

local OBS_TO_VK = {
    OBS_KEY_MOUSE1 = 0x01,
    OBS_KEY_MOUSE2 = 0x02,
    OBS_KEY_MOUSE3 = 0x04,
    OBS_KEY_MOUSE4 = 0x05,
    OBS_KEY_MOUSE5 = 0x06,
    OBS_KEY_SPACE = 0x20,
    OBS_KEY_RETURN = 0x0D,
    OBS_KEY_TAB = 0x09,
    OBS_KEY_SHIFT = 0x10,
    OBS_KEY_CONTROL = 0x11,
    OBS_KEY_ALT = 0x12,
    OBS_KEY_CAPSLOCK = 0x14,
    OBS_KEY_ESCAPE = 0x1B,
    OBS_KEY_PAGEUP = 0x21,
    OBS_KEY_PAGEDOWN = 0x22,
    OBS_KEY_END = 0x23,
    OBS_KEY_HOME = 0x24,
    OBS_KEY_LEFT = 0x25,
    OBS_KEY_UP = 0x26,
    OBS_KEY_RIGHT = 0x27,
    OBS_KEY_DOWN = 0x28,
    OBS_KEY_INSERT = 0x2D,
    OBS_KEY_DELETE = 0x2E,
    OBS_KEY_NUMPLUS = 0x6B,
    OBS_KEY_NUMMINUS = 0x6D,
    OBS_KEY_NUMMULTIPLY = 0x6A,
    OBS_KEY_NUMDIVIDE = 0x6F,
    OBS_KEY_NUMPERIOD = 0x6E,
    OBS_KEY_NUMENTER = 0x0D,
}

local function vk_for_obs_key(obs_key)
    if obs_key == nil or obs_key == "" then
        return nil
    end
    if OBS_TO_VK[obs_key] then
        return OBS_TO_VK[obs_key]
    end
    local letter = obs_key:match("^OBS_KEY_([A-Z])$")
    if letter then
        return string.byte(letter)
    end
    local digit = obs_key:match("^OBS_KEY_([0-9])$")
    if digit then
        return 0x30 + tonumber(digit)
    end
    local fkey = obs_key:match("^OBS_KEY_F(%d+)$")
    if fkey then
        return 0x70 + tonumber(fkey) - 1
    end
    local num = obs_key:match("^OBS_KEY_NUM(%d)$")
    if num then
        return 0x60 + tonumber(num)
    end
    return nil
end

local function set_mic_talking(on)
    local source = obs.obs_get_source_by_name("Mic")
    if source == nil then
        return
    end
    obs.obs_source_set_muted(source, not on)
    obs.obs_source_release(source)
end

local function ptt_key_held()
    if user32 == nil or not prepare_capture_ffi() then
        return false
    end
    for i = 1, #ptt_vks do
        if user32.GetAsyncKeyState(ptt_vks[i]) < 0 then
            return true
        end
    end
    return false
end

function ptt_tick()
    if not ptt_enabled then
        return
    end
    local now = os.clock()
    if ptt_key_held() then
        ptt_release_at = now + 0.20
        if not ptt_talking then
            ptt_talking = true
            set_mic_talking(true)
        end
        return
    end
    if ptt_talking and now >= ptt_release_at then
        ptt_talking = false
        set_mic_talking(false)
    end
end

local function start_ptt()
    if ptt_timer_on or not ptt_enabled or #ptt_vks == 0 then
        return
    end
    prepare_capture_ffi()
    set_mic_talking(false)
    obs.timer_add(ptt_tick, 30)
    ptt_timer_on = true
    obs.script_log(obs.LOG_INFO, "[ClipKit] Push to talk is on")
end

local function stop_ptt()
    if ptt_timer_on then
        obs.timer_remove(ptt_tick)
        ptt_timer_on = false
    end
end

local function load_ptt(settings)
    ptt_vks = {}
    local raw = obs.obs_data_get_string(settings, "ptt_keys") or ""
    for token in string.gmatch(raw, "[^,]+") do
        local vk = vk_for_obs_key(token:gsub("^%s+", ""):gsub("%s+$", ""))
        if vk ~= nil then
            ptt_vks[#ptt_vks + 1] = vk
        end
    end
    if obs.obs_data_has_user_value(settings, "ptt_enabled") then
        ptt_enabled = obs.obs_data_get_bool(settings, "ptt_enabled")
    else
        ptt_enabled = true
    end
    if ptt_enabled and #ptt_vks == 0 then
        -- Mouse 4, mouse 5, and middle-click until ClipKit writes the chosen keys.
        ptt_vks = { 0x05, 0x06, 0x04 }
    end
end

local function on_switch_game(pressed)
    if not pressed or not remember_enabled then
        return
    end
    if not prepare_capture_ffi() then
        return
    end
    local hwnd = user32.GetForegroundWindow()
    local info = window_info(hwnd)
    if info == nil then
        return
    end
    write_last_game(info)
    set_game_capture(info)
    obs.script_log(obs.LOG_INFO, "[ClipKit] Switch game → " .. info.exe)
end

local function load_switch_hotkey(settings)
    if switch_hotkey_id ~= obs.OBS_INVALID_HOTKEY_ID then
        return
    end
    switch_hotkey_id = obs.obs_hotkey_register_frontend(
        "clipkit.switch_game",
        "ClipKit: Switch game",
        on_switch_game
    )
    local arr = obs.obs_data_get_array(settings, "switch_game")
    if arr ~= nil then
        obs.obs_hotkey_load(switch_hotkey_id, arr)
        obs.obs_data_array_release(arr)
    end
end

local function save_replay_now()
    if not replay_is_on() then
        start_replay()
        if not replay_is_on() then
            save_pending = true
            return
        end
    end
    save_pending = false
    local ok = pcall(obs.obs_frontend_replay_buffer_save)
    if not ok then
        write_save_result(false, "", "OBS could not save the replay buffer")
    end
end

function command_tick()
    if save_pending then
        if replay_is_on() then
            save_replay_now()
        end
        return
    end
    local path = command_file()
    if path == nil then
        return
    end
    local handle = io.open(path, "r")
    if handle == nil then
        return
    end
    local cmd = handle:read("*a") or ""
    handle:close()
    pcall(os.remove, path)
    if cmd:find("save", 1, true) then
        save_replay_now()
    end
end

local function start_command()
    if command_timer_on then
        return
    end
    obs.timer_add(command_tick, 250)
    command_timer_on = true
end

local function stop_command()
    if command_timer_on then
        obs.timer_remove(command_tick)
        command_timer_on = false
    end
    save_pending = false
end

local function on_event(event)
    if event == obs.OBS_FRONTEND_EVENT_FINISHED_LOADING then
        disable_desktop_audio()
        show_obs_window()
        keep_hiding_desktop()
        begin_retry()
        start_remember()
    elseif obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED and event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED then
        write_replay_status(true)
    elseif obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STOPPED and event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STOPPED then
        write_replay_status(false)
    elseif event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED then
        try_beep()
        local clip_path = ""
        pcall(function()
            clip_path = obs.obs_frontend_get_last_replay() or ""
        end)
        write_save_result(true, clip_path, "")
        obs.script_log(obs.LOG_INFO, "[ClipKit] Clip saved")
    elseif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED then
        try_beep()
        obs.script_log(obs.LOG_INFO, "[ClipKit] Recording saved")
    end
end

function script_description()
    return [[
<h2>ClipKit Helper</h2>
<p>Starts Replay Buffer when OBS opens, and beeps when a clip or recording saves.</p>
<p>Remembers the last game you hooked. FiveM recaptures from any shortcut or build.</p>
<p>Saves a test clip when ClipKit asks, and reports which game is hooked.</p>
<p>The clip sorter shows the main-monitor popup after the file is in the game folder.</p>
]]
end

function script_load(settings)
    if obs.obs_data_has_user_value(settings, "remember_game") then
        remember_enabled = obs.obs_data_get_bool(settings, "remember_game")
    else
        remember_enabled = true
    end
    obs.obs_frontend_add_event_callback(on_event)
    disable_desktop_audio()
    show_obs_window()
    keep_hiding_desktop()
    begin_retry()
    load_ptt(settings)
    start_ptt()
    start_command()
    if remember_enabled then
        load_switch_hotkey(settings)
        start_remember()
    end
end

function script_save(settings)
    if switch_hotkey_id ~= obs.OBS_INVALID_HOTKEY_ID then
        local arr = obs.obs_hotkey_save(switch_hotkey_id)
        obs.obs_data_set_array(settings, "switch_game", arr)
        obs.obs_data_array_release(arr)
    end
end

function script_unload()
    stop_retry()
    stop_remember()
    stop_ptt()
    stop_command()
    pcall(function()
        obs.timer_remove(hide_desktop_tick)
    end)
    if switch_hotkey_id ~= obs.OBS_INVALID_HOTKEY_ID then
        obs.obs_hotkey_unregister(switch_hotkey_id)
        switch_hotkey_id = obs.OBS_INVALID_HOTKEY_ID
    end
    if enum_windows_cb ~= nil then
        enum_windows_cb:free()
        enum_windows_cb = nil
    end
    obs.obs_frontend_remove_event_callback(on_event)
end
