-- ClipKit Clip Saved v1.0
-- Medal-style popup when a clip or recording saves.
-- ClipKit copies this into OBS. After Apply, ClipKit.exe is not needed.

local obs = obslua
local ffi = nil
local kernel32 = nil
local runner_ready = false
local last_shown_ms = 0

local function scripts_dir()
    local ok, folder = pcall(script_path)
    if ok and folder ~= nil and folder ~= "" then
        return folder
    end
    local appdata = os.getenv("APPDATA")
    if appdata == nil or appdata == "" then
        return nil
    end
    return appdata .. "\\obs-studio\\clipkit-scripts\\"
end

local function toast_script()
    local folder = scripts_dir()
    if folder == nil then
        return nil
    end
    return folder .. "clipkit_toast.ps1"
end

local function prepare_runner()
    local loaded, ffi_module = pcall(require, "ffi")
    if not loaded or ffi_module == nil then
        return false
    end
    ffi = ffi_module
    local ok = pcall(ffi.cdef, [[
        typedef void *HANDLE;
        typedef unsigned long DWORD;
        typedef int BOOL;
        typedef unsigned short WORD;
        typedef unsigned char BYTE;
        typedef void *LPVOID;
        typedef struct {
            DWORD cb;
            char *lpReserved;
            char *lpDesktop;
            char *lpTitle;
            DWORD dwX;
            DWORD dwY;
            DWORD dwXSize;
            DWORD dwYSize;
            DWORD dwXCountChars;
            DWORD dwYCountChars;
            DWORD dwFillAttribute;
            DWORD dwFlags;
            WORD wShowWindow;
            WORD cbReserved2;
            BYTE *lpReserved2;
            HANDLE hStdInput;
            HANDLE hStdOutput;
            HANDLE hStdError;
        } STARTUPINFOA;
        typedef struct {
            HANDLE hProcess;
            HANDLE hThread;
            DWORD dwProcessId;
            DWORD dwThreadId;
        } PROCESS_INFORMATION;
        BOOL CreateProcessA(const char *applicationName, char *commandLine,
            LPVOID processAttributes, LPVOID threadAttributes,
            BOOL inheritHandles, DWORD creationFlags, LPVOID environment,
            const char *currentDirectory, STARTUPINFOA *startupInfo,
            PROCESS_INFORMATION *processInformation);
        BOOL CloseHandle(HANDLE object);
    ]])
    if not ok then
        -- Script reload can hit "redefinition" in a shared LuaJIT state.
    end
    local lib_ok, library = pcall(ffi.load, "kernel32")
    if not lib_ok or library == nil then
        return false
    end
    kernel32 = library
    return true
end

local function start_hidden(application, command_line)
    if not runner_ready then
        return false
    end
    local startup = ffi.new("STARTUPINFOA")
    startup.cb = ffi.sizeof(startup)
    startup.dwFlags = 0x00000001
    startup.wShowWindow = 0
    local process = ffi.new("PROCESS_INFORMATION")
    local mutable_command = ffi.new("char[?]", #command_line + 1)
    ffi.copy(mutable_command, command_line)
    local created = kernel32.CreateProcessA(
        application,
        mutable_command,
        nil,
        nil,
        0,
        0x08000000,
        nil,
        nil,
        startup,
        process
    )
    if created == 0 then
        return false
    end
    kernel32.CloseHandle(process.hThread)
    kernel32.CloseHandle(process.hProcess)
    return true
end

local function now_ms()
    return math.floor(obs.os_gettime_ns() / 1000000)
end

local function show_saved(title)
    local t = now_ms()
    if t - last_shown_ms < 800 then
        return
    end
    last_shown_ms = t
    local ps1 = toast_script()
    if ps1 == nil then
        return
    end
    local system_root = os.getenv("SystemRoot") or "C:\\Windows"
    local powershell = system_root .. "\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
    local command = '"' .. powershell .. '" -NoLogo -NoProfile -NonInteractive ' ..
        '-WindowStyle Hidden -ExecutionPolicy Bypass -File "' .. ps1 ..
        '" -Popup -Title "' .. title .. '"'
    start_hidden(powershell, command)
end

local function on_event(event)
    if event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED then
        show_saved("Clip saved")
    elseif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED then
        show_saved("Recording saved")
    end
end

function script_description()
    return "ClipKit Clip Saved\n\nMedal-style popup when you save a clip or stop a recording. Installed by ClipKit."
end

function script_load(settings)
    runner_ready = prepare_runner()
    obs.obs_frontend_add_event_callback(on_event)
end

function script_unload()
    pcall(function()
        obs.obs_frontend_remove_event_callback(on_event)
    end)
end
