-- ClipKit helper
-- Starts Replay Buffer on launch and beeps when a clip or recording saves.
-- The clip sorter shows the main-monitor popup after the file is moved.

local obs = obslua
local ffi = nil
local start_tries = 0
local retry_running = false

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
        obs.script_log(obs.LOG_INFO, "[ClipKit] Replay Buffer started")
        stop_retry()
        return
    end
    if start_tries >= 10 then
        obs.script_log(obs.LOG_WARNING, "[ClipKit] Replay Buffer did not start")
        stop_retry()
    end
end

local function begin_retry()
    start_tries = 0
    if start_replay() then
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
        begin_retry()
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
    begin_retry()
end

function script_unload()
    stop_retry()
    obs.obs_frontend_remove_event_callback(on_event)
end
