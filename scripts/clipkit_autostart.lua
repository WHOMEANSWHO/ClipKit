-- ClipKit helper
-- Starts Replay Buffer on launch and beeps when a clip or recording saves.
-- The clip sorter shows the main-monitor popup after the file is moved.

local obs = obslua
local ffi = nil
local start_tries = 0
local retry_running = false

local function status_file()
    local appdata = os.getenv("APPDATA")
    if appdata == nil or appdata == "" then
        return nil
    end
    return appdata .. "\\obs-studio\\clipkit-status.txt"
end

local function write_replay_status(on)
    local path = status_file()
    if path == nil then
        return
    end
    local handle = io.open(path, "w")
    if handle == nil then
        return
    end
    if on then
        handle:write("replay=1\n")
    else
        handle:write("replay=0\n")
    end
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

local function on_event(event)
    if event == obs.OBS_FRONTEND_EVENT_FINISHED_LOADING then
        disable_desktop_audio()
        show_obs_window()
        keep_hiding_desktop()
        begin_retry()
    elseif obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED and event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED then
        write_replay_status(true)
    elseif obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STOPPED and event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STOPPED then
        write_replay_status(false)
    elseif event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED then
        try_beep()
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
<p>The clip sorter shows the main-monitor popup after the file is in the game folder.</p>
]]
end

function script_load(settings)
    obs.obs_frontend_add_event_callback(on_event)
    disable_desktop_audio()
    show_obs_window()
    keep_hiding_desktop()
    begin_retry()
end

function script_unload()
    stop_retry()
    pcall(function()
        obs.timer_remove(hide_desktop_tick)
    end)
    obs.obs_frontend_remove_event_callback(on_event)
end
