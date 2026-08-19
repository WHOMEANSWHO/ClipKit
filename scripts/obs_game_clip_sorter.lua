-- OBS Game Clip Sorter v1.1.2
-- Automatically sorts replay-buffer clips and recordings into game folders.
-- Windows 11 only. No extra software is required beyond OBS and PowerShell.

local obs = obslua
local SCRIPT_VERSION = "1.1.2"

------------------------------------------------------------------------
-- Easy-to-edit built-in game aliases
--
-- Add entries in the same style if a game has an unfriendly process name.
-- Matching is not case-sensitive. Both names with and without .exe work.
------------------------------------------------------------------------
local BUILT_IN_GAME_ALIASES = {
    ["fivem_gtaprocess.exe"] = "FiveM",
    ["fivem_gtaprocess"] = "FiveM",
    ["fivem.exe"] = "FiveM",
    ["fivem"] = "FiveM",
    ["gta5.exe"] = "Grand Theft Auto V",
    ["gta5"] = "Grand Theft Auto V",
    ["gta5_enhanced.exe"] = "Grand Theft Auto V",
    ["gta5_enhanced"] = "Grand Theft Auto V",
    ["fortniteclient-win64-shipping.exe"] = "Fortnite",
    ["fortniteclient-win64-shipping"] = "Fortnite",
    ["fortnite"] = "Fortnite",
    ["cod.exe"] = "Call of Duty",
    ["cod"] = "Call of Duty",
    ["cod hq"] = "Call of Duty",
    ["call of duty"] = "Call of Duty",
    ["modernwarfare.exe"] = "Call of Duty",
    ["cod22-cod.exe"] = "Call of Duty",
    ["gta"] = "Grand Theft Auto V",
    ["valorant.exe"] = "Valorant",
    ["valorant"] = "Valorant",
    ["cs2.exe"] = "Counter-Strike 2",
    ["cs2"] = "Counter-Strike 2",
    ["csgo.exe"] = "Counter-Strike 2",
    ["league of legends.exe"] = "League of Legends",
    ["league of legends"] = "League of Legends",
    ["r5apex.exe"] = "Apex Legends",
    ["r5apex"] = "Apex Legends",
    ["overwatch.exe"] = "Overwatch",
    ["overwatch"] = "Overwatch",
    ["rust.exe"] = "Rust",
    ["rust"] = "Rust",
    ["rdr2.exe"] = "Red Dead Redemption 2",
    ["rdr2"] = "Red Dead Redemption 2",
    ["rocketleague.exe"] = "Rocket League",
    ["rocketleague"] = "Rocket League",
    ["minecraft.exe"] = "Minecraft",
    ["palworld.exe"] = "Palworld",
    ["helldivers2.exe"] = "Helldivers 2",
    ["helldivers2"] = "Helldivers 2"
}

------------------------------------------------------------------------
-- Settings and current state
------------------------------------------------------------------------
local base_folder_override = ""
local clip_delay_ms = 1500
local recording_delay_ms = 1500
local poll_interval_ms = 10000
local fivem_fallback_server = "Unknown_Server"
local debug_enabled = false
local show_advanced_settings = false
local show_notifications = true
local show_popup = true

local custom_game_aliases = {}
local custom_server_aliases = {}

local cached_game = nil
local cached_server = nil
local cached_process = nil
local cached_title = nil
local last_detection_method = "Not run yet"
local last_obs_source_result = nil
local last_obs_source_name = nil
local last_obs_source_id = nil
local last_windows_fallback_needed = false
local last_explicit_tag_found = false
local last_explicit_tag_origin = nil
local last_explicit_tag_raw = nil
local last_explicit_tag_final = nil
local last_windows_skipped_for_tag = false
local last_folder_creation_error = nil
local last_folder_creation_method = "Windows API CreateDirectory"

local refresh_hotkey_id = obs.OBS_INVALID_HOTKEY_ID
local jobs = {}
local claimed_files = {}
local job_timer_running = false
local poll_timer_running = false
local unloading = false
local replay_buffer_active = false
local recording_active = false

-- The hidden Windows runner is prepared once when the script loads.
-- If LuaJIT FFI is unavailable, PowerShell features are disabled safely.
local ffi = nil
local kernel32 = nil
local shell32 = nil
local hidden_runner_available = false
local hidden_runner_error_logged = false

local VIDEO_EXTENSIONS = {
    ["mp4"] = true,
    ["mkv"] = true,
    ["mov"] = true,
    ["flv"] = true
}

-- Programs that should not replace the cached game when they are foreground.
local IGNORED_PROCESSES = {
    ["obs64"] = true,
    ["obs32"] = true,
    ["explorer"] = true,
    ["dwm"] = true,
    ["taskmgr"] = true,
    ["powershell"] = true,
    ["powershell_ise"] = true,
    ["pwsh"] = true,
    ["cmd"] = true,
    ["conhost"] = true,
    ["searchhost"] = true,
    ["startmenuexperiencehost"] = true,
    ["shellexperiencehost"] = true,
    ["applicationframehost"] = true,
    ["textinputhost"] = true,
    ["systemsettings"] = true,
    ["discord"] = true,
    ["chrome"] = true,
    ["msedge"] = true,
    ["firefox"] = true
}

------------------------------------------------------------------------
-- Logging helpers
------------------------------------------------------------------------
local LOG_PREFIX = "[OBS Game Clip Sorter] "

local function log_info(message)
    obs.script_log(obs.LOG_INFO, LOG_PREFIX .. tostring(message))
end

local function log_debug(message)
    if debug_enabled then
        obs.script_log(obs.LOG_INFO, LOG_PREFIX .. "DEBUG: " .. tostring(message))
    end
end

local function log_error(message)
    obs.script_log(obs.LOG_ERROR, LOG_PREFIX .. tostring(message))
end

------------------------------------------------------------------------
-- Small text and path helpers
------------------------------------------------------------------------
local function trim(value)
    if value == nil then
        return ""
    end
    return tostring(value):match("^%s*(.-)%s*$") or ""
end

local function lowercase(value)
    return string.lower(trim(value))
end

local function normalize_slashes(path)
    path = trim(path):gsub("/", "\\")
    -- Keep C:\ intact, but remove unnecessary trailing slashes elsewhere.
    if not path:match("^%a:\\$") then
        path = path:gsub("\\+$", "")
    end
    return path
end

local function join_path(left, right)
    left = normalize_slashes(left)
    right = tostring(right or ""):gsub("^[\\/]+", "")
    if left:match("\\$") then
        return left .. right
    end
    return left .. "\\" .. right
end

local function expand_environment_variables(path)
    return (tostring(path or ""):gsub("%%([%w_]+)%%", function(name)
        return os.getenv(name) or "%" .. name .. "%"
    end))
end

local function powershell_literal(value)
    -- PowerShell single-quoted strings escape an apostrophe by doubling it.
    return "'" .. tostring(value or ""):gsub("'", "''") .. "'"
end

-- PowerShell's -EncodedCommand avoids command-line quoting problems. It expects
-- UTF-16LE Base64, so these two small helpers also preserve non-English paths.
local BASE64_CHARACTERS =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

local function base64_encode(data)
    local result = {}
    local index = 1
    while index <= #data do
        local first = data:byte(index) or 0
        local second = data:byte(index + 1)
        local third = data:byte(index + 2)
        local combined = first * 65536 + (second or 0) * 256 + (third or 0)
        local a = math.floor(combined / 262144) % 64
        local b = math.floor(combined / 4096) % 64
        local c = math.floor(combined / 64) % 64
        local d = combined % 64
        result[#result + 1] = BASE64_CHARACTERS:sub(a + 1, a + 1)
        result[#result + 1] = BASE64_CHARACTERS:sub(b + 1, b + 1)
        result[#result + 1] = second and BASE64_CHARACTERS:sub(c + 1, c + 1) or "="
        result[#result + 1] = third and BASE64_CHARACTERS:sub(d + 1, d + 1) or "="
        index = index + 3
    end
    return table.concat(result)
end

local function utf8_to_utf16le(text)
    local result = {}
    local index = 1
    while index <= #text do
        local first = text:byte(index)
        local codepoint
        local length
        if first < 0x80 then
            codepoint, length = first, 1
        elseif first < 0xE0 then
            codepoint = (first - 0xC0) * 0x40 + (text:byte(index + 1) - 0x80)
            length = 2
        elseif first < 0xF0 then
            codepoint = (first - 0xE0) * 0x1000 +
                (text:byte(index + 1) - 0x80) * 0x40 + (text:byte(index + 2) - 0x80)
            length = 3
        else
            codepoint = (first - 0xF0) * 0x40000 +
                (text:byte(index + 1) - 0x80) * 0x1000 +
                (text:byte(index + 2) - 0x80) * 0x40 + (text:byte(index + 3) - 0x80)
            length = 4
        end

        if codepoint <= 0xFFFF then
            result[#result + 1] = string.char(codepoint % 256, math.floor(codepoint / 256))
        else
            codepoint = codepoint - 0x10000
            local high = 0xD800 + math.floor(codepoint / 0x400)
            local low = 0xDC00 + (codepoint % 0x400)
            result[#result + 1] = string.char(high % 256, math.floor(high / 256))
            result[#result + 1] = string.char(low % 256, math.floor(low / 256))
        end
        index = index + length
    end
    return table.concat(result)
end

local function prepare_hidden_windows_runner()
    local loaded, ffi_module = pcall(require, "ffi")
    if not loaded or ffi_module == nil then
        return false, "LuaJIT FFI is unavailable"
    end
    ffi = ffi_module

    -- These are the small parts of the Windows API needed to start a process
    -- with CREATE_NO_WINDOW and collect its output through a hidden pipe.
    local declarations_ok, declarations_error = pcall(ffi.cdef, [[
        typedef void *HANDLE;
        typedef unsigned long DWORD;
        typedef int BOOL;
        typedef unsigned short WORD;
        typedef unsigned char BYTE;
        typedef void *LPVOID;

        typedef struct {
            DWORD nLength;
            LPVOID lpSecurityDescriptor;
            BOOL bInheritHandle;
        } SECURITY_ATTRIBUTES;

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

        BOOL CreatePipe(HANDLE *readPipe, HANDLE *writePipe,
            SECURITY_ATTRIBUTES *attributes, DWORD size);
        BOOL SetHandleInformation(HANDLE object, DWORD mask, DWORD flags);
        BOOL CreateProcessA(const char *applicationName, char *commandLine,
            LPVOID processAttributes, LPVOID threadAttributes,
            BOOL inheritHandles, DWORD creationFlags, LPVOID environment,
            const char *currentDirectory, STARTUPINFOA *startupInfo,
            PROCESS_INFORMATION *processInformation);
        BOOL ReadFile(HANDLE file, LPVOID buffer, DWORD bytesToRead,
            DWORD *bytesRead, LPVOID overlapped);
        DWORD WaitForSingleObject(HANDLE object, DWORD milliseconds);
        BOOL GetExitCodeProcess(HANDLE process, DWORD *exitCode);
        BOOL CloseHandle(HANDLE object);
        HANDLE ShellExecuteW(HANDLE window, const WORD *operation,
            const WORD *file, const WORD *parameters,
            const WORD *directory, int showCommand);
    ]])
    if not declarations_ok then
        local message = tostring(declarations_error)
        -- Reloading an OBS script can leave identical FFI declarations in the
        -- shared LuaJIT state. That harmless case can continue.
        if not message:find("redefin", 1, true) then
            return false, "Windows FFI declarations failed: " .. message
        end
    end

    -- Keep the v1.0.6 folder declarations separate. OBS can retain earlier
    -- FFI declarations while reloading a script, and a redefinition in the
    -- main block must not prevent these new functions from being declared.
    local folder_declarations_ok, folder_declarations_error = pcall(ffi.cdef, [[
        BOOL CreateDirectoryW(const WORD *pathName, LPVOID securityAttributes);
        DWORD GetFileAttributesW(const WORD *fileName);
        DWORD GetLastError(void);
        BOOL MoveFileW(const WORD *existingFileName, const WORD *newFileName);
        BOOL CopyFileW(const WORD *existingFileName, const WORD *newFileName, BOOL failIfExists);
        BOOL DeleteFileW(const WORD *fileName);
    ]])
    if not folder_declarations_ok then
        local message = tostring(folder_declarations_error)
        if not message:find("redefin", 1, true) then
            return false, "Folder FFI declarations failed: " .. message
        end
    end

    local ok, library = pcall(ffi.load, "kernel32")
    if not ok or library == nil then
        return false, "Windows kernel32 could not be loaded"
    end
    kernel32 = library

    local shell_ok, shell_library = pcall(ffi.load, "shell32")
    if shell_ok then
        shell32 = shell_library
    end
    return true, nil
end

local function run_hidden_process(application, command_line)
    if not hidden_runner_available then
        return nil, "Hidden Windows process runner is unavailable"
    end

    local read_pipe = ffi.new("HANDLE[1]")
    local write_pipe = ffi.new("HANDLE[1]")
    local security = ffi.new("SECURITY_ATTRIBUTES")
    security.nLength = ffi.sizeof(security)
    security.lpSecurityDescriptor = nil
    security.bInheritHandle = 1

    if kernel32.CreatePipe(read_pipe, write_pipe, security, 0) == 0 then
        return nil, "Windows could not create the hidden output pipe"
    end

    -- The parent keeps the read side; only the child inherits the write side.
    kernel32.SetHandleInformation(read_pipe[0], 1, 0)

    local startup = ffi.new("STARTUPINFOA")
    startup.cb = ffi.sizeof(startup)
    startup.dwFlags = 0x00000101 -- STARTF_USESTDHANDLES + STARTF_USESHOWWINDOW
    startup.wShowWindow = 0      -- SW_HIDE
    startup.hStdInput = nil
    startup.hStdOutput = write_pipe[0]
    startup.hStdError = write_pipe[0]

    local process = ffi.new("PROCESS_INFORMATION")
    local mutable_command = ffi.new("char[?]", #command_line + 1)
    ffi.copy(mutable_command, command_line)

    local created = kernel32.CreateProcessA(
        application, mutable_command, nil, nil, 1,
        0x08000000, -- CREATE_NO_WINDOW
        nil, nil, startup, process)

    kernel32.CloseHandle(write_pipe[0])
    if created == 0 then
        kernel32.CloseHandle(read_pipe[0])
        return nil, "Windows could not start the hidden process"
    end

    -- Read until PowerShell closes its output. This is normally brief and the
    -- polling frequency is deliberately low to avoid unnecessary OBS work.
    local pieces = {}
    local buffer = ffi.new("char[4096]")
    local bytes_read = ffi.new("DWORD[1]")
    while kernel32.ReadFile(read_pipe[0], buffer, 4096, bytes_read, nil) ~= 0 and
        bytes_read[0] > 0 do
        pieces[#pieces + 1] = ffi.string(buffer, bytes_read[0])
    end

    kernel32.WaitForSingleObject(process.hProcess, 0xFFFFFFFF)
    local exit_code = ffi.new("DWORD[1]")
    kernel32.GetExitCodeProcess(process.hProcess, exit_code)
    kernel32.CloseHandle(read_pipe[0])
    kernel32.CloseHandle(process.hThread)
    kernel32.CloseHandle(process.hProcess)

    local output = trim(table.concat(pieces))
    if exit_code[0] ~= 0 then
        return output, "Hidden PowerShell exited with code " .. tostring(exit_code[0])
    end
    return output, nil
end

local function run_powershell(script)
    if not hidden_runner_available then
        if not hidden_runner_error_logged then
            log_error("LuaJIT FFI is unavailable. PowerShell detection is disabled " ..
                "to prevent visible console windows.")
            hidden_runner_error_logged = true
        end
        return nil, "Hidden PowerShell runner is unavailable"
    end

    -- -EncodedCommand avoids quoting problems and keeps the command line ASCII.
    script = "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); " .. script
    local encoded = base64_encode(utf8_to_utf16le(script))
    local system_root = os.getenv("SystemRoot") or "C:\\Windows"
    local application = join_path(system_root,
        "System32\\WindowsPowerShell\\v1.0\\powershell.exe")
    local command = '"' .. application .. '" -NoLogo -NoProfile -NonInteractive ' ..
        "-ExecutionPolicy Bypass -EncodedCommand " .. encoded
    return run_hidden_process(application, command)
end

local function wide_string(value)
    local bytes = utf8_to_utf16le(tostring(value or "")) .. "\0\0"
    local buffer = ffi.new("BYTE[?]", #bytes)
    ffi.copy(buffer, bytes, #bytes)
    return buffer
end

local function open_folder_in_explorer(path)
    if not hidden_runner_available or shell32 == nil then
        return false, "The hidden Windows Explorer launcher is unavailable"
    end

    -- ShellExecuteW opens Explorer directly. It does not start PowerShell or
    -- cmd, and the wide-character call supports non-English folder names.
    local operation = wide_string("open")
    local folder = wide_string(path)
    local result = shell32.ShellExecuteW(nil,
        ffi.cast("const WORD *", operation),
        ffi.cast("const WORD *", folder), nil, nil, 1)
    local result_number = tonumber(ffi.cast("uintptr_t", result)) or 0
    if result_number <= 32 then
        return false, "Windows Explorer returned error " .. tostring(result_number)
    end
    return true, nil
end

local function directory_exists(path)
    if ffi ~= nil and kernel32 ~= nil then
        local wide_path = wide_string(path)
        local attributes = tonumber(kernel32.GetFileAttributesW(
            ffi.cast("const WORD *", wide_path)))
        if attributes == nil or attributes == 0xFFFFFFFF then
            return false
        end
        -- FILE_ATTRIBUTE_DIRECTORY is 0x10.
        return math.floor(attributes / 0x10) % 2 == 1
    end

    local ok, exists = pcall(obs.os_file_exists, path)
    return ok and exists or false
end

local function create_one_directory(path)
    if directory_exists(path) then
        return true, nil
    end

    local wide_path = wide_string(path)
    local created = kernel32.CreateDirectoryW(
        ffi.cast("const WORD *", wide_path), nil)
    if created ~= 0 then
        return true, nil
    end

    local error_code = tonumber(kernel32.GetLastError()) or 0
    if error_code == 183 and directory_exists(path) then -- ERROR_ALREADY_EXISTS
        return true, nil
    end
    return false, "CreateDirectoryW failed for " .. path ..
        " (Windows error " .. tostring(error_code) .. ")"
end

local function make_directory(path)
    path = normalize_slashes(path)
    last_folder_creation_error = nil
    last_folder_creation_method = "Windows API CreateDirectory"

    if path == "" then
        last_folder_creation_error = "Folder path is empty"
        return false, last_folder_creation_error
    end

    if ffi == nil or kernel32 == nil then
        -- Safe compatibility fallback only. It does not launch a command.
        last_folder_creation_method = "OBS os_mkdirs fallback"
        local ok, result = pcall(obs.os_mkdirs, path)
        if ok and (result == 0 or result == true or directory_exists(path)) then
            return true, nil
        end
        last_folder_creation_error = "Windows API and OBS os_mkdirs are unavailable"
        return false, last_folder_creation_error
    end

    local current = ""
    local remainder = path
    if path:match("^%a:\\") then
        current = path:sub(1, 3)
        remainder = path:sub(4)
    elseif path:match("^\\\\") then
        local server, share, rest = path:match("^\\\\([^\\]+)\\([^\\]+)\\?(.*)$")
        if not server or not share then
            last_folder_creation_error = "Invalid network folder path: " .. path
            return false, last_folder_creation_error
        end
        current = "\\\\" .. server .. "\\" .. share
        remainder = rest or ""
    end

    for segment in remainder:gmatch("[^\\]+") do
        current = current == "" and segment or join_path(current, segment)
        local created, err = create_one_directory(current)
        if not created then
            last_folder_creation_error = err
            return false, err
        end
    end

    if directory_exists(path) then
        return true, nil
    end
    last_folder_creation_error = "Folder was not available after creation: " .. path
    return false, last_folder_creation_error
end

local RESERVED_NAMES = {
    ["con"] = true, ["prn"] = true, ["aux"] = true, ["nul"] = true,
    ["com1"] = true, ["com2"] = true, ["com3"] = true,
    ["com4"] = true, ["com5"] = true, ["com6"] = true,
    ["com7"] = true, ["com8"] = true, ["com9"] = true,
    ["lpt1"] = true, ["lpt2"] = true, ["lpt3"] = true,
    ["lpt4"] = true, ["lpt5"] = true, ["lpt6"] = true,
    ["lpt7"] = true, ["lpt8"] = true, ["lpt9"] = true
}

local function sanitize_windows_name(value, fallback)
    value = trim(value)
    value = value:gsub('[<>:"/\\|%?%*]', " ")
    value = value:gsub("[%c]", " ")
    value = value:gsub("%s+", " ")
    value = trim(value):gsub("[%. ]+$", "")
    if value == "" then
        value = fallback or "Unknown"
    end
    -- Windows also reserves forms such as CON.txt, not only plain CON.
    local first_name_part = lowercase(value):match("^([^%.]+)") or lowercase(value)
    if RESERVED_NAMES[first_name_part] then
        value = value .. "_"
    end
    -- This leaves plenty of room for the rest of the Windows path.
    if #value > 80 then
        value = trim(value:sub(1, 80)):gsub("[%. ]+$", "")
    end
    return value
end

local function filename_part(value, fallback)
    local safe = sanitize_windows_name(value, fallback)
    safe = safe:gsub("%s+", "_")
    safe = safe:gsub("_+", "_")
    return safe
end

local function readable_process_name(process_name)
    local name = trim(process_name):gsub("%.[Ee][Xx][Ee]$", "")
    name = name:gsub("[_%-]+", " ")
    name = name:gsub("(%l)(%u)", "%1 %2")
    return sanitize_windows_name(name, "Unknown_Game")
end

------------------------------------------------------------------------
-- Alias parsing and matching
------------------------------------------------------------------------
local function parse_aliases(text)
    local aliases = {}
    text = tostring(text or ""):gsub("\r", "")
    for line in (text .. "\n"):gmatch("(.-)\n") do
        line = trim(line)
        if line ~= "" and not line:match("^#") then
            local source, destination = line:match("^(.-)=(.+)$")
            source = trim(source)
            destination = trim(destination)
            if source ~= "" and destination ~= "" then
                aliases[lowercase(source)] = sanitize_windows_name(destination, destination)
            end
        end
    end
    return aliases
end

local function alias_lookup(aliases, value)
    local key = lowercase(value)
    if key == "" then
        return nil
    end
    return aliases[key]
end

local function game_alias(value)
    return alias_lookup(custom_game_aliases, value) or
        alias_lookup(BUILT_IN_GAME_ALIASES, value)
end

local function server_alias(value)
    return alias_lookup(custom_server_aliases, value)
end

------------------------------------------------------------------------
-- OBS output-folder detection
------------------------------------------------------------------------
local function profile_config_value(section, key)
    local ok, value = pcall(function()
        local config = obs.obs_frontend_get_profile_config()
        if config == nil then
            return nil
        end
        return obs.config_get_string(config, section, key)
    end)
    if ok then
        return trim(value)
    end
    log_debug("OBS profile setting " .. section .. "/" .. key .. " was unavailable")
    return ""
end

local function detected_output_folder()
    if trim(base_folder_override) ~= "" then
        return normalize_slashes(expand_environment_variables(base_folder_override)), "override"
    end

    local advanced_path = profile_config_value("AdvOut", "RecFilePath")
    if advanced_path ~= "" then
        return normalize_slashes(expand_environment_variables(advanced_path)), "advanced output"
    end

    local simple_path = profile_config_value("SimpleOutput", "FilePath")
    if simple_path ~= "" then
        return normalize_slashes(expand_environment_variables(simple_path)), "simple output"
    end

    local user_profile = os.getenv("USERPROFILE") or "C:\\Users\\Public"
    return join_path(user_profile, "Videos"), "fallback"
end

local function log_selected_output_folder(folder, source, debug_only)
    local message
    if source == "override" then
        message = "Using custom output folder: " .. folder
    else
        message = "Using OBS output folder: " .. folder
    end

    if debug_only then
        log_debug(message)
    else
        log_info(message)
    end
end

------------------------------------------------------------------------
-- Foreground game and FiveM server detection
------------------------------------------------------------------------
local function is_fivem(process_name, window_title)
    local combined = lowercase(process_name) .. " " .. lowercase(window_title)
    if combined:find("fivem", 1, true) ~= nil or combined:find("cfx.re", 1, true) ~= nil then
        return true
    end
    -- FiveM_b3258_GTAProcess.exe and similar CitizenFX builds.
    local process = lowercase(process_name):gsub("%.exe$", "")
    if process:find("gtaprocess", 1, true) and process:find("fivem", 1, true) then
        return true
    end
    if process:match("^fivem_b%d+_gtaprocess$") then
        return true
    end
    return combined:find("cfx", 1, true) ~= nil and combined:find("gta", 1, true) ~= nil
end

local function remove_word_case_insensitive(text, word)
    local pattern = word:gsub("%a", function(character)
        return "[" .. character:lower() .. character:upper() .. "]"
    end)
    return text:gsub(pattern, " ")
end

local function clean_window_title(title)
    local clean = trim(title)
    clean = clean:gsub('[<>:"/\\%?%*]', " ")
    clean = clean:gsub("[%[%]%(%){}]", " ")
    clean = clean:gsub("[%|]+", " ")
    clean = clean:gsub("%s+[-–—]+%s+", " ")
    clean = clean:gsub("[_]+", " ")
    clean = clean:gsub("%s+", " ")
    return sanitize_windows_name(clean, "")
end

local function clean_fivem_server(title)
    local original = trim(title)
    local lower = lowercase(original)
    if lower == "" or lower:find("loading", 1, true) or
        lower:find("connecting", 1, true) then
        return sanitize_windows_name(fivem_fallback_server, "Unknown_Server")
    end

    local clean = original
    -- Remove the full branding phrase first. Doing this before removing Cfx.re
    -- prevents a leftover leading "by" (for example, "by Arena").
    clean = clean:gsub("[Bb][Yy]%s+[Cc][Ff][Xx]%.[Rr][Ee]", " ")
    clean = remove_word_case_insensitive(clean, "FiveM®")
    clean = remove_word_case_insensitive(clean, "FiveM")
    clean = remove_word_case_insensitive(clean, "Cfx%.re")
    clean = remove_word_case_insensitive(clean, "loading")
    clean = remove_word_case_insensitive(clean, "connecting")
    clean = clean:gsub("®", " ")
    clean = clean:gsub("[%[%]%(%){}]", " ")
    clean = clean:gsub("[%|]+", " ")
    clean = clean:gsub("%s*[-–—]+%s*", " ")
    clean = clean:gsub("%s+", " ")
    clean = trim(clean)
    clean = clean:gsub("^[Bb][Yy]%s+", "")
    clean = trim(clean)
    clean = sanitize_windows_name(clean, "")

    local aliased = server_alias(clean) or server_alias(original)
    if aliased then
        clean = aliased
    end

    if clean == "" or #clean < 2 then
        return sanitize_windows_name(fivem_fallback_server, "Unknown_Server")
    end
    return sanitize_windows_name(clean, "Unknown_Server")
end

local function choose_game_name(process_name, window_title)
    if is_fivem(process_name, window_title) then
        return "FiveM"
    end

    local cleaned_process = readable_process_name(process_name)
    local process_alias = game_alias(cleaned_process) or game_alias(process_name)
    if process_alias then
        return sanitize_windows_name(process_alias, "Unknown_Game")
    end

    local without_exe = trim(process_name):gsub("%.[Ee][Xx][Ee]$", "")
    process_alias = game_alias(without_exe)
    if process_alias then
        return sanitize_windows_name(process_alias, "Unknown_Game")
    end

    local title = clean_window_title(window_title)
    local title_alias = game_alias(title) or game_alias(window_title)
    if title_alias then
        return sanitize_windows_name(title_alias, "Unknown_Game")
    end

    -- A useful window title is normally friendlier than an executable name.
    if title ~= "" and lowercase(title) ~= lowercase(process_name) then
        return sanitize_windows_name(title, "Unknown_Game")
    end
    return cleaned_process
end

------------------------------------------------------------------------
-- OBS scene/source game detection
------------------------------------------------------------------------
local function extract_explicit_tag(text)
    text = tostring(text or "")
    local matches = {}

    local function add_match(kind, pattern)
        local first, last, value = text:find(pattern)
        value = trim(value)
        if first and value ~= "" then
            matches[#matches + 1] = {
                kind = kind, value = value, position = first
            }
        end
    end

    add_match("Game", "%[[Gg][Aa][Mm][Ee]%s*[:=]%s*([^%]]+)%]")
    add_match("FiveM", "%[[Ff][Ii][Vv][Ee][Mm]%s*[:=]%s*([^%]]+)%]")
    add_match("Game", "#[Gg][Aa][Mm][Ee]%s*:%s*(.+)$")
    add_match("FiveM", "#[Ff][Ii][Vv][Ee][Mm]%s*:%s*(.+)$")

    table.sort(matches, function(left, right)
        return left.position < right.position
    end)
    return matches[1]
end

local function clean_explicit_tag(tag)
    local cleaned = sanitize_windows_name(tag.value,
        tag.kind == "FiveM" and "Unknown_Server" or "Unknown_Game")
    if tag.kind == "FiveM" then
        cleaned = server_alias(cleaned) or server_alias(tag.value) or cleaned
        return "FiveM", sanitize_windows_name(cleaned, "Unknown_Server")
    end
    cleaned = game_alias(cleaned) or game_alias(tag.value) or cleaned
    return sanitize_windows_name(cleaned, "Unknown_Game"), nil
end

local GENERIC_SOURCE_NAMES = {
    ["game"] = true,
    ["game capture"] = true,
    ["window capture"] = true,
    ["display capture"] = true,
    ["monitor capture"] = true,
    ["capture"] = true,
    ["gameplay"] = true
}

local function game_looks_generic(name)
    local n = lowercase(name or "")
    return n == "" or n == "unknown_game" or GENERIC_SOURCE_NAMES[n]
end

local function source_id(source)
    local ok, value = pcall(obs.obs_source_get_unversioned_id, source)
    if ok and value then
        return tostring(value)
    end
    ok, value = pcall(obs.obs_source_get_id, source)
    return ok and tostring(value or "") or ""
end

local function find_source_tag_in_items(items, depth)
    if items == nil or depth > 4 then
        return nil
    end

    for _, item in ipairs(items) do
        local source = obs.obs_sceneitem_get_source(item)
        if source ~= nil then
            local name = trim(obs.obs_source_get_name(source))
            local tag = extract_explicit_tag(name)
            if tag then
                tag.origin = "source name"
                tag.container_name = name
                tag.source_id = source_id(source)
                return tag
            end
        end

        -- Also inspect sources placed inside an OBS group.
        local group_ok, is_group = pcall(obs.obs_sceneitem_is_group, item)
        if group_ok and is_group then
            local group_items = obs.obs_sceneitem_group_enum_items(item)
            local nested_tag = find_source_tag_in_items(group_items, depth + 1)
            if group_items ~= nil then
                obs.sceneitem_list_release(group_items)
            end
            if nested_tag then
                return nested_tag
            end
        end
    end
    return nil
end

local function detect_explicit_obs_tag()
    local scene_source = obs.obs_frontend_get_current_scene()
    if scene_source == nil then
        return nil
    end

    local items = nil
    local ok, tag_or_error = pcall(function()
        local scene_name = trim(obs.obs_source_get_name(scene_source))
        local scene_tag = extract_explicit_tag(scene_name)
        if scene_tag then
            scene_tag.origin = "scene name"
            scene_tag.container_name = scene_name
            scene_tag.source_id = source_id(scene_source)
            return scene_tag
        end

        local scene = obs.obs_scene_from_source(scene_source)
        if scene ~= nil then
            items = obs.obs_scene_enum_items(scene)
            return find_source_tag_in_items(items, 1)
        end
        return nil
    end)

    if items ~= nil then
        obs.sceneitem_list_release(items)
    end
    obs.obs_source_release(scene_source)
    if not ok then
        error(tag_or_error)
    end
    return tag_or_error
end

local function source_setting(settings, names)
    for _, name in ipairs(names) do
        local ok, value = pcall(obs.obs_data_get_string, settings, name)
        value = ok and trim(value) or ""
        if value ~= "" then
            return value
        end
    end
    return ""
end

local function split_obs_window_setting(value)
    value = trim(value)
    if value == "" then
        return "", ""
    end

    -- OBS commonly stores a window as title:window-class:executable.
    local title, process_name = value:match("^(.-):[^:]*:([^:]*)$")
    if title then
        return trim(title), trim(process_name)
    end
    return value, ""
end

local function clean_source_name(name)
    local clean = trim(name)
    clean = remove_word_case_insensitive(clean, "Game Capture")
    clean = remove_word_case_insensitive(clean, "Window Capture")
    clean = remove_word_case_insensitive(clean, "Display Capture")
    clean = remove_word_case_insensitive(clean, "Monitor Capture")
    clean = clean:gsub("^[%s%-–—_]+", ""):gsub("[%s%-–—_]+$", "")
    return sanitize_windows_name(clean, "")
end

local function inspect_obs_source(source)
    local name = trim(obs.obs_source_get_name(source))
    local id = source_id(source)
    local id_lower = lowercase(id)
    local is_game_capture = id_lower:find("game_capture", 1, true) ~= nil
    local is_window_capture = id_lower:find("window_capture", 1, true) ~= nil
    local is_monitor_capture = id_lower:find("monitor_capture", 1, true) ~= nil or
        id_lower:find("display_capture", 1, true) ~= nil or
        id_lower:find("duplicator", 1, true) ~= nil

    if not is_game_capture and not is_window_capture and not is_monitor_capture then
        return nil
    end

    local settings = obs.obs_source_get_settings(source)
    local window_value = ""
    local explicit_process = ""
    local explicit_title = ""
    local capture_mode = ""
    if settings ~= nil then
        window_value = source_setting(settings,
            {"window", "capture_window", "window_name"})
        explicit_process = source_setting(settings,
            {"process", "executable", "application"})
        explicit_title = source_setting(settings, {"title", "window_title"})
        capture_mode = lowercase(source_setting(settings, {"capture_mode", "mode"}))
        obs.obs_data_release(settings)
    end

    -- ClipKit hotkey / any capture must not lock folders to a leftover hooked
    -- window. Otherwise a Fortnite clip stays in the old FiveM server folder.
    if is_game_capture and (capture_mode == "hotkey" or capture_mode == "any") then
        return nil
    end

    local window_title, window_process = split_obs_window_setting(window_value)
    if explicit_title ~= "" then
        window_title = explicit_title
    end
    local process_name = explicit_process ~= "" and explicit_process or window_process
    local combined = name .. " " .. window_title .. " " .. process_name
    local base_score = is_game_capture and 100 or (is_window_capture and 80 or 20)

    if is_fivem(process_name, combined) then
        local server = nil
        if window_title ~= "" then
            local cleaned = clean_fivem_server(window_title)
            if cleaned ~= sanitize_windows_name(fivem_fallback_server, "Unknown_Server") then
                server = cleaned
            end
        end
        return {
            game = "FiveM", server = server, source_name = name,
            source_id = id, process = process_name, window_title = window_title,
            score = base_score + 100
        }
    end

    local process_alias = game_alias(process_name)
    if process_alias then
        return {
            game = process_alias, source_name = name, source_id = id,
            process = process_name, window_title = window_title,
            score = base_score + 80
        }
    end

    if process_name ~= "" then
        local game = choose_game_name(process_name, window_title)
        if game ~= "Unknown_Game" and not GENERIC_SOURCE_NAMES[lowercase(game)] then
            return {
                game = game, source_name = name, source_id = id,
                process = process_name, window_title = window_title,
                score = base_score + 70
            }
        end
    end

    if window_title ~= "" then
        local game = choose_game_name(process_name, window_title)
        if game ~= "Unknown_Game" and not GENERIC_SOURCE_NAMES[lowercase(game)] then
            return {
                game = game, source_name = name, source_id = id,
                process = process_name, window_title = window_title,
                score = base_score + 60
            }
        end
    end

    local direct_alias = game_alias(name)
    if direct_alias then
        return {
            game = direct_alias, source_name = name, source_id = id,
            process = process_name, window_title = window_title,
            score = base_score + 50
        }
    end

    local cleaned_name = clean_source_name(name)
    if cleaned_name ~= "" and not GENERIC_SOURCE_NAMES[lowercase(name)] and
        not GENERIC_SOURCE_NAMES[lowercase(cleaned_name)] then
        return {
            game = game_alias(cleaned_name) or cleaned_name,
            source_name = name, source_id = id, process = process_name,
            window_title = window_title, score = base_score + 30
        }
    end
    return nil
end

local function detect_game_from_obs_sources()
    local scene_source = obs.obs_frontend_get_current_scene()
    if scene_source == nil then
        return nil
    end

    local items = nil
    local ok, best_or_error = pcall(function()
        local best = nil
        local scene = obs.obs_scene_from_source(scene_source)
        if scene ~= nil then
            items = obs.obs_scene_enum_items(scene)
        end
        if items ~= nil then
            for _, item in ipairs(items) do
                local visible_ok, visible = pcall(obs.obs_sceneitem_visible, item)
                if not visible_ok or visible then
                    local source = obs.obs_sceneitem_get_source(item)
                    if source ~= nil then
                        local ok, candidate = pcall(inspect_obs_source, source)
                        if ok and candidate and
                            (best == nil or candidate.score > best.score) then
                            best = candidate
                        elseif not ok then
                            log_debug("Could not inspect OBS source: " .. tostring(candidate))
                        end
                    end
                end
            end
        end
        return best
    end)

    if items ~= nil then
        obs.sceneitem_list_release(items)
    end
    obs.obs_source_release(scene_source)
    if not ok then
        error(best_or_error)
    end
    return best_or_error
end

local function foreground_process()
    local script = table.concat({
        "$ErrorActionPreference='Stop';",
        "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class OGSWindow { [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow(); [DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId); }';",
        "$h=[OGSWindow]::GetForegroundWindow();",
        "[uint32]$id=0; [void][OGSWindow]::GetWindowThreadProcessId($h,[ref]$id);",
        "$p=Get-Process -Id $id -ErrorAction Stop;",
        "$title=($p.MainWindowTitle -replace \"`t|`r|`n\",' ');",
        "Write-Output ($p.ProcessName + [char]9 + $title)"
    }, " ")

    local output, err = run_powershell(script)
    if err then
        log_debug("Game detection failed: " .. err)
        return nil, nil
    end
    local process_name, title = output:match("^([^\t\r\n]+)\t?(.*)$")
    return trim(process_name), trim(title)
end

local function detect_game_from_windows()
    local process_name, window_title = foreground_process()
    if process_name == nil or process_name == "" then
        return nil
    end

    local process_key = lowercase(process_name):gsub("%.exe$", "")
    if IGNORED_PROCESSES[process_key] then
        log_debug("Foreground program ignored: " .. process_name)
        return nil
    end

    if is_fivem(process_name, window_title) then
        return {
            game = "FiveM",
            server = clean_fivem_server(window_title),
            process = process_name,
            window_title = window_title
        }
    end
    return {
        game = choose_game_name(process_name, window_title),
        server = nil,
        process = process_name,
        window_title = window_title
    }
end

local function log_detected_result()
    if cached_game == "FiveM" then
        log_info("Detected: FiveM / " ..
            (cached_server or sanitize_windows_name(
                fivem_fallback_server, "Unknown_Server")) ..
            " via " .. last_detection_method)
    else
        log_info("Detected: " .. (cached_game or "Unknown_Game") ..
            " via " .. last_detection_method)
    end
end

local function detect_current_game(force_log, force_windows_when_unclear)
    last_obs_source_result = nil
    last_obs_source_name = nil
    last_obs_source_id = nil
    last_windows_fallback_needed = false
    last_explicit_tag_found = false
    last_explicit_tag_origin = nil
    last_explicit_tag_raw = nil
    last_explicit_tag_final = nil
    last_windows_skipped_for_tag = false

    local tag_ok, explicit_tag = pcall(detect_explicit_obs_tag)
    if not tag_ok then
        log_debug("OBS tag detection failed: " .. tostring(explicit_tag))
        explicit_tag = nil
    end

    if explicit_tag then
        local game, server = clean_explicit_tag(explicit_tag)
        cached_game = game
        cached_server = server
        last_explicit_tag_found = true
        last_explicit_tag_origin = explicit_tag.origin
        last_explicit_tag_raw = explicit_tag.value
        last_explicit_tag_final = game == "FiveM" and server or game
        last_windows_skipped_for_tag = true
        last_obs_source_result = explicit_tag.kind .. " explicit tag"
        last_obs_source_name = explicit_tag.container_name
        last_obs_source_id = explicit_tag.source_id
        last_detection_method = "explicit OBS " .. explicit_tag.origin .. " tag"
        log_debug("Explicit OBS tag selected " .. game ..
            (server and (" / " .. server) or "") .. " from " ..
            tostring(explicit_tag.origin))
        if force_log then
            log_detected_result()
        end
        return true
    end

    local obs_ok, obs_result = pcall(detect_game_from_obs_sources)
    if not obs_ok then
        log_debug("OBS source detection failed: " .. tostring(obs_result))
        obs_result = nil
    end

    if obs_result then
        last_obs_source_result = obs_result.game
        last_obs_source_name = obs_result.source_name
        last_obs_source_id = obs_result.source_id
        cached_game = sanitize_windows_name(obs_result.game, "Unknown_Game")
        if trim(obs_result.process) ~= "" then
            cached_process = obs_result.process
        end
        if trim(obs_result.window_title) ~= "" then
            cached_title = obs_result.window_title
        end

        if cached_game == "FiveM" then
            local server = obs_result.server
            if (server == nil or server == "") and cached_server and
                cached_server ~= "Unknown_Server" then
                server = cached_server
            end

            -- OBS can identify FiveM from a source name without exposing the
            -- server title. Only then use the hidden Windows fallback.
            if server == nil or server == "" then
                last_windows_fallback_needed = true
                local windows_result = detect_game_from_windows()
                if windows_result and windows_result.game == "FiveM" then
                    server = windows_result.server
                    cached_process = windows_result.process
                    cached_title = windows_result.window_title
                end
            end
            cached_server = sanitize_windows_name(
                server or fivem_fallback_server, "Unknown_Server")
        else
            cached_server = nil
        end

        last_detection_method = "OBS scene/source"
        log_debug("OBS source detected " .. cached_game .. " from " ..
            tostring(last_obs_source_name) .. " (" .. tostring(last_obs_source_id) .. ")")
        if force_log then
            log_detected_result()
        end
        return true
    end

    last_obs_source_result = "No clear game source"
    last_windows_fallback_needed = true
    local windows_result = detect_game_from_windows()
    if windows_result then
        cached_game = windows_result.game
        cached_server = windows_result.server
        cached_process = windows_result.process
        cached_title = windows_result.window_title
        last_detection_method = "hidden Windows fallback"
        log_debug("Windows fallback detected " .. cached_game ..
            " (process: " .. cached_process .. ")")
        if force_log then
            log_detected_result()
        end
        return true
    end

    if cached_game then
        last_detection_method = "cached game/server after Windows fallback"
    else
        last_detection_method = "Unknown fallback"
        cached_game = "Unknown_Game"
        cached_server = nil
    end

    if force_log then
        log_detected_result()
    end
    return cached_game ~= "Unknown_Game"
end

local function poll_game_timer()
    -- Poll only while OBS is actively buffering or recording. Event-based
    -- detection still runs at starts, saves, stops, and manual refreshes.
    if not unloading and (replay_buffer_active or recording_active) then
        local ok, err = pcall(detect_current_game, false)
        if not ok then
            log_error("Unexpected game-detection error: " .. tostring(err))
        end
    end
end

local function refresh_hotkey_pressed(pressed)
    if pressed then
        local ok, err = pcall(detect_current_game, true, true)
        if not ok then
            log_error("Hotkey refresh failed: " .. tostring(err))
        end
    end
end

------------------------------------------------------------------------
-- Safe video-file discovery and movement
------------------------------------------------------------------------
local function file_extension(path)
    return lowercase(path:match("%.([^%.\\/]+)$") or "")
end

local function already_renamed(path)
    local filename = path:match("([^\\/]+)$") or path
    filename = lowercase(filename)
    -- Clip_Server_18-08-26_23-59-12.mp4  /  Recording_Fortnite_18-08-26_23-59-12.mp4
    if filename:match("^clip_.+_%d%d%-%d%d%-%d%d_%d%d%-%d%d%-%d%d") or
        filename:match("^recording_.+_%d%d%-%d%d%-%d%d_%d%d%-%d%d%-%d%d") then
        return true
    end
    -- Older FiveM_Server_Clip_18-08-26_23-59-12.mp4 layout
    local clip = filename:match("_clip_%d%d%-%d%d%-%d%d_%d%d%-%d%d%-%d%d%.[%w]+$") or
        filename:match("_clip_%d%d%-%d%d%-%d%d_%d%d%-%d%d%-%d%d_%d+%.[%w]+$")
    local recording = filename:match("_recording_%d%d%-%d%d%-%d%d_%d%d%-%d%d%-%d%d%.[%w]+$") or
        filename:match("_recording_%d%d%-%d%d%-%d%d_%d%d%-%d%d%-%d%d_%d+%.[%w]+$")
    return clip ~= nil or recording ~= nil
end

local function newest_video_file(folder)
    local script = "$ErrorActionPreference='Stop'; " ..
        "Get-ChildItem -LiteralPath " .. powershell_literal(folder) .. " -File | " ..
        "Where-Object { @('.mp4','.mkv','.mov','.flv') -contains $_.Extension.ToLowerInvariant() } | " ..
        "Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 30 -ExpandProperty FullName"
    local output, err = run_powershell(script)
    if err then
        return nil, err
    end

    for line in (output .. "\n"):gmatch("(.-)\r?\n") do
        local path = trim(line)
        if path ~= "" and VIDEO_EXTENSIONS[file_extension(path)] and
            not already_renamed(path) and not claimed_files[lowercase(path)] then
            return path, nil
        end
    end
    return nil, nil
end

local function obs_frontend_last_path(kind)
    local getter
    if kind == "Clip" then
        getter = obs.obs_frontend_get_last_replay
    else
        getter = obs.obs_frontend_get_last_recording
    end
    if type(getter) ~= "function" then
        return nil
    end

    local ok, path = pcall(getter)
    path = ok and trim(path) or ""
    if path ~= "" then
        return normalize_slashes(path)
    end
    return nil
end

local function obs_last_saved_video(kind)
    local path = obs_frontend_last_path(kind)
    if path == nil then
        return nil
    end
    if path ~= "" and VIDEO_EXTENSIONS[file_extension(path)] and
        not already_renamed(path) then
        return path
    end
    return nil
end

local function get_file_size(path)
    local ok, size = pcall(obs.os_get_file_size, path)
    if ok and size and size >= 0 then
        return size
    end

    local file = io.open(path, "rb")
    if file == nil then
        return nil
    end
    local size = file:seek("end")
    file:close()
    return size
end

local function file_exists(path)
    local ok, exists = pcall(obs.os_file_exists, path)
    if ok then
        return exists
    end

    local file = io.open(path, "rb")
    if file then
        file:close()
        return true
    end
    return false
end

local function unique_target_path(folder, stem, extension)
    local target = join_path(folder, stem .. "." .. extension)
    local number = 2
    while file_exists(target) do
        target = join_path(folder, stem .. "_" .. tostring(number) .. "." .. extension)
        number = number + 1
    end
    return target
end

local function target_folder_for(base_folder, game, server)
    local game_name = sanitize_windows_name(game or "Unknown_Game", "Unknown_Game")
    if game_name == "FiveM" then
        local safe_server = sanitize_windows_name(
            server or fivem_fallback_server, "Unknown_Server")
        return join_path(join_path(base_folder, "FiveM"), safe_server)
    end
    return join_path(base_folder, game_name)
end

local function target_details(job, source_path)
    local game_name = sanitize_windows_name(job.game or "Unknown_Game", "Unknown_Game")
    local kind = filename_part(job.kind, "Clip")
    local stamp = job.timestamp
    local target_folder
    local stem

    if game_name == "FiveM" then
        local server = sanitize_windows_name(job.server or fivem_fallback_server, "Unknown_Server")
        target_folder = target_folder_for(job.base_folder, game_name, server)
        stem = kind .. "_" .. filename_part(server, "Unknown_Server") .. "_" .. stamp
    else
        target_folder = target_folder_for(job.base_folder, game_name, nil)
        stem = kind .. "_" .. filename_part(game_name, "Unknown_Game") .. "_" .. stamp
    end

    local extension = file_extension(source_path)
    return target_folder, unique_target_path(target_folder, stem, extension)
end

local function toast_saved(title, message)
    if not show_notifications and not show_popup then
        return
    end
    local ok_path, folder = pcall(script_path)
    if not ok_path or folder == nil or folder == "" then
        return
    end
    local ps1 = folder .. "clipkit_toast.ps1"
    if not file_exists(ps1) then
        return
    end
    title = tostring(title or "ClipKit"):gsub('"', "'")
    message = tostring(message or ""):gsub('"', "'")
    local flags = ""
    if show_notifications then
        flags = flags .. " -Toast"
    end
    if show_popup then
        flags = flags .. " -Popup"
    end
    local cmd = string.format(
        'cmd /c start "" /b powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%s" -Title "%s" -Message "%s"%s',
        ps1, title, message, flags)
    os.execute(cmd)
end

local function display_spaces(value)
    return tostring(value or ""):gsub("_", " ")
end

local function toast_for_job(job)
    local title = job.kind == "Clip" and "Clip" or "Recording"
    local when = job.display_time or os.date("%d/%m/%Y %H:%M:%S")
    local where
    if job.game == "FiveM" then
        where = display_spaces(job.server or fivem_fallback_server or "Unknown Server")
    else
        where = display_spaces(job.game or "Unknown Game")
    end
    toast_saved(title, where .. "@@" .. when)
end

local function move_with_windows_api(source_path, target_path)
    if ffi == nil or kernel32 == nil then
        return false, "Windows move API is unavailable"
    end
    local from_path = wide_string(source_path)
    local to_path = wide_string(target_path)
    if kernel32.MoveFileW(ffi.cast("const WORD *", from_path),
        ffi.cast("const WORD *", to_path)) ~= 0 then
        return true, nil
    end
    -- Cross-drive fallback: copy then delete.
    if kernel32.CopyFileW(ffi.cast("const WORD *", from_path),
        ffi.cast("const WORD *", to_path), 1) ~= 0 then
        kernel32.DeleteFileW(ffi.cast("const WORD *", from_path))
        return true, nil
    end
    local error_code = tonumber(kernel32.GetLastError()) or 0
    return false, "MoveFileW/CopyFileW failed (Windows error " .. tostring(error_code) .. ")"
end

local function move_job_file(job)
    local folder, target = target_details(job, job.source_path)
    local made, make_error = make_directory(folder)
    if not made then
        return false, "Could not create folder " .. folder .. ": " .. tostring(make_error)
    end

    local obs_ok, obs_result = pcall(obs.os_rename, job.source_path, target)
    if obs_ok and obs_result == 0 then
        job.target_path = target
        return true, nil
    end

    local win_ok, win_err = move_with_windows_api(job.source_path, target)
    if win_ok then
        job.target_path = target
        return true, nil
    end

    -- Compatibility fallback for an OBS build without os_rename in Lua.
    local moved, rename_error = os.rename(job.source_path, target)
    if not moved then
        return false, "Could not move " .. job.source_path .. " to " .. target ..
            ": " .. tostring(rename_error or win_err or obs_result)
    end
    job.target_path = target
    return true, nil
end

local function finish_job(index)
    local job = jobs[index]
    if job and job.source_path then
        claimed_files[lowercase(job.source_path)] = nil
    end
    table.remove(jobs, index)
end

local function process_job(index, now_ms)
    local job = jobs[index]
    if now_ms < job.next_check_ms then
        return false
    end

    if job.state == "find" then
        local path
        local err

        -- Modern OBS provides the exact saved file. Prefer it because this
        -- avoids an extra PowerShell process and cannot select the wrong file.
        if job.source_hint and file_exists(job.source_hint) and
            not claimed_files[lowercase(job.source_hint)] then
            path = job.source_hint
        elseif job.source_hint and job.attempts < 4 then
            log_debug("OBS saved path is not ready yet; checking again")
        else
            path, err = newest_video_file(job.base_folder)
        end
        if err then
            log_debug("File search failed: " .. err)
        end
        if path == nil then
            job.attempts = job.attempts + 1
            if job.attempts >= 10 then
                log_error("No new video file was found for the " .. job.kind .. " event in " .. job.base_folder)
                finish_job(index)
                return true
            end
            job.next_check_ms = now_ms + 500
            log_debug("No unclaimed video found yet; checking again")
            return false
        end
        job.source_path = path
        claimed_files[lowercase(path)] = true
        job.first_size = get_file_size(path)
        job.state = "stability"
        job.next_check_ms = now_ms + 500
        log_debug("First stability check for " .. path .. ": " .. tostring(job.first_size) .. " bytes")
        return false
    end

    if job.state == "stability" then
        local second_size = get_file_size(job.source_path)
        log_debug("Second stability check for " .. job.source_path .. ": " ..
            tostring(second_size) .. " bytes")

        if second_size ~= nil and second_size > 0 and second_size == job.first_size then
            local moved, err = move_job_file(job)
            if moved then
                log_info(job.kind .. " moved to: " .. job.target_path)
                toast_for_job(job)
                finish_job(index)
                return true
            end
            log_error(err .. "; retrying once in 1 second")
            job.state = "move_retry"
            job.next_check_ms = now_ms + 1000
            return false
        end

        job.attempts = job.attempts + 1
        if job.attempts >= 10 then
            log_error("File did not become stable, so it was left unchanged: " .. job.source_path)
            finish_job(index)
            return true
        end
        job.first_size = second_size
        job.next_check_ms = now_ms + 500
        log_debug("File is still changing; stability check will retry")
        return false
    end

    if job.state == "move_retry" then
        local moved, err = move_job_file(job)
        if moved then
            log_info(job.kind .. " moved to: " .. job.target_path)
            toast_for_job(job)
        else
            log_error(err .. "; the original file was left unchanged")
        end
        finish_job(index)
        return true
    end
    return false
end

local function current_time_ms()
    return math.floor(obs.os_gettime_ns() / 1000000)
end

local function job_timer()
    if unloading then
        return
    end
    local now_ms = current_time_ms()
    local index = #jobs
    while index >= 1 do
        local ok, removed_or_error = pcall(process_job, index, now_ms)
        if not ok then
            log_error("Unexpected file-processing error: " .. tostring(removed_or_error))
            finish_job(index)
        end
        index = index - 1
    end

    if #jobs == 0 and job_timer_running then
        obs.timer_remove(job_timer)
        job_timer_running = false
    end
end

local function queue_file_job(kind, delay_ms)
    -- Name the folder from the game in front at save time, so switching from
    -- FiveM to Fortnite creates vids\Fortnite instead of staying in
    -- vids\FiveM\Server. If OBS or the desktop is in front, keep the last game.
    local windows_result = detect_game_from_windows()
    if windows_result and not game_looks_generic(windows_result.game) then
        cached_game = windows_result.game
        cached_server = windows_result.server
        cached_process = windows_result.process
        cached_title = windows_result.window_title
        last_detection_method = "Windows foreground at save"
    else
        detect_current_game(false)
    end
    local folder, source = detected_output_folder()
    if folder == "" then
        log_error("The OBS output folder is empty; no file job was queued")
        return
    end
    log_selected_output_folder(folder, source, false)

    local job = {
        kind = kind,
        base_folder = folder,
        game = cached_game or "Unknown_Game",
        server = cached_server or sanitize_windows_name(fivem_fallback_server, "Unknown_Server"),
        timestamp = os.date("%d-%m-%y_%H-%M-%S"),
        display_time = os.date("%d/%m/%Y %H:%M:%S"),
        source_hint = obs_last_saved_video(kind),
        state = "find",
        attempts = 0,
        next_check_ms = current_time_ms() + math.max(0, delay_ms)
    }
    table.insert(jobs, job)
    log_info(kind .. " will go in " .. target_folder_for(folder, job.game, job.server))

    if not job_timer_running then
        obs.timer_add(job_timer, 100)
        job_timer_running = true
    end
end

------------------------------------------------------------------------
-- OBS events
------------------------------------------------------------------------
local function frontend_event(event)
    if event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED then
        log_debug("OBS event: replay buffer saved")
        queue_file_job("Clip", clip_delay_ms)
    elseif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED then
        log_debug("OBS event: recording stopped")
        queue_file_job("Recording", recording_delay_ms)
        recording_active = false
    elseif event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED then
        log_debug("OBS event: replay buffer started")
        replay_buffer_active = true
        detect_current_game(false)
    elseif event == obs.OBS_FRONTEND_EVENT_RECORDING_STARTED then
        log_debug("OBS event: recording started")
        recording_active = true
        detect_current_game(false)
    elseif event == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STOPPED then
        replay_buffer_active = false
    end
end

------------------------------------------------------------------------
-- First-run diagnostic buttons
------------------------------------------------------------------------
local function yes_or_no(value)
    return value and "Yes" or "No"
end

local function run_diagnostics_button(properties, property)
    log_info("========== Diagnostics ==========")
    log_info("Script version: " .. SCRIPT_VERSION)
    log_info("Custom output folder: " ..
        (trim(base_folder_override) == "" and "Blank (automatic OBS path)" or "Set"))

    local advanced_path = profile_config_value("AdvOut", "RecFilePath")
    local simple_path = profile_config_value("SimpleOutput", "FilePath")
    local final_folder, folder_source = detected_output_folder()
    log_info("OBS advanced output path detected: " ..
        (advanced_path ~= "" and advanced_path or "Not available"))
    log_info("OBS simple output path detected: " ..
        (simple_path ~= "" and simple_path or "Not available"))
    log_selected_output_folder(final_folder, folder_source, false)

    local last_replay = obs_frontend_last_path("Clip")
    local last_recording = obs_frontend_last_path("Recording")
    log_info("Last replay path: " .. (last_replay or "Not available"))
    log_info("Last recording path: " .. (last_recording or "Not available"))

    -- Clicking a button brings OBS to the foreground. Detection therefore
    -- keeps and reports the most recently cached game instead of calling OBS
    -- itself a game.
    detect_current_game(false)
    local detected_fivem = cached_game == "FiveM"
    local output_folder_exists = directory_exists(final_folder)
    local diagnostic_game = cached_game or "Unknown_Game"
    local diagnostic_server = cached_server or sanitize_windows_name(
        fivem_fallback_server, "Unknown_Server")
    local diagnostic_folder = target_folder_for(
        final_folder, diagnostic_game, diagnostic_server)
    local can_create_test_folder, diagnostic_folder_error =
        make_directory(diagnostic_folder)

    log_info("Output folder exists: " .. yes_or_no(output_folder_exists))
    log_info("Can create test folder: " .. yes_or_no(can_create_test_folder))
    log_info("Folder creation method: " .. last_folder_creation_method)
    log_info("Last folder creation error: " ..
        (diagnostic_folder_error or last_folder_creation_error or "None"))
    log_info("Explicit OBS tag found: " .. yes_or_no(last_explicit_tag_found))
    log_info("Explicit tag came from: " ..
        (last_explicit_tag_origin or "Not applicable"))
    log_info("Explicit tag raw value: " ..
        (last_explicit_tag_raw or "Not applicable"))
    log_info("Explicit tag final cleaned result: " ..
        (last_explicit_tag_final or "Not applicable"))
    log_info("Windows detection skipped because of tag: " ..
        yes_or_no(last_windows_skipped_for_tag))
    log_info("OBS source detection result: " ..
        (last_obs_source_result or "No result"))
    log_info("OBS source name used: " ..
        (last_obs_source_name or "Not applicable"))
    log_info("OBS source type/id used: " ..
        (last_obs_source_id or "Not applicable"))
    log_info("Windows fallback was needed: " ..
        yes_or_no(last_windows_fallback_needed))
    log_info("Final chosen game name: " .. (cached_game or "Unknown_Game"))
    if detected_fivem then
        log_info("Final chosen FiveM server name: " ..
            (cached_server or sanitize_windows_name(
                fivem_fallback_server, "Unknown_Server")))
    else
        log_info("Final chosen FiveM server name: Not applicable")
    end
    log_info("Current detected process name: " .. (cached_process or "Unknown"))
    log_info("Current detected window title: " .. (cached_title or "Unknown"))
    log_info("Cleaned game name: " .. (cached_game or "Unknown_Game"))
    log_info("FiveM detected: " .. yes_or_no(detected_fivem))
    if detected_fivem then
        log_info("FiveM raw window title: " .. (cached_title or "Unknown"))
        log_info("Cleaned FiveM server name: " ..
            (cached_server or sanitize_windows_name(
                fivem_fallback_server, "Unknown_Server")))
    else
        log_info("FiveM raw window title: Not applicable")
        log_info("Cleaned FiveM server name: Not applicable")
    end

    log_info("Debug logging is on: " .. yes_or_no(debug_enabled))
    local polling_active = poll_timer_running and
        (replay_buffer_active or recording_active)
    log_info("Polling active: " .. yes_or_no(polling_active))
    log_info("Hidden process runner is being used: " ..
        yes_or_no(hidden_runner_available) ..
        (hidden_runner_available and " (CreateProcessA / CREATE_NO_WINDOW)" or ""))
    log_info("========== Diagnostics complete ==========")
    return true
end

local function test_folder_creation_button(properties, property)
    detect_current_game(false)
    local base_folder, source = detected_output_folder()
    log_selected_output_folder(base_folder, source, false)

    local game = cached_game or "Unknown_Game"
    local server = cached_server or sanitize_windows_name(
        fivem_fallback_server, "Unknown_Server")
    local folder = target_folder_for(base_folder, game, server)
    local made, err = make_directory(folder)
    if made then
        log_info("Test folder created or already available: " .. folder)
        log_info("Folder test only: no video was moved, renamed, or deleted")
    else
        log_error("Folder creation test failed for " .. folder .. ": " .. tostring(err))
    end
    return true
end

local function open_output_folder_button(properties, property)
    local folder, source = detected_output_folder()
    log_selected_output_folder(folder, source, false)

    local made, make_error = make_directory(folder)
    if not made then
        log_error("Could not prepare the output folder: " .. tostring(make_error))
        return false
    end

    local opened, open_error = open_folder_in_explorer(folder)
    if opened then
        log_info("Opened output folder in Windows Explorer: " .. folder)
    else
        log_error("Could not open the output folder: " .. tostring(open_error))
    end
    return opened
end

------------------------------------------------------------------------
-- Required OBS script functions
------------------------------------------------------------------------
function script_description()
    return [[
<h2>OBS Game Clip Sorter</h2>
<p><b>Version 1.1.2</b></p>
<p>Automatically moves replay-buffer clips and recordings into folders for the current game.</p>
<p>FiveM files go into a server subfolder, for example <code>FiveM\Server Name</code>. Other games get their own folder, for example <code>Fortnite</code>.</p>
<p>After a move, you can get a Windows notification (works over fullscreen) and/or an on-screen popup on the main monitor.</p>
<p><b>Leave the custom output folder blank to use your OBS save path automatically.</b></p>
<p>Advanced settings are optional and hidden by default.</p>
]]
end

local ADVANCED_PROPERTY_NAMES = {
    "clip_delay_ms",
    "recording_delay_ms",
    "poll_interval_ms",
    "fivem_fallback_server",
    "game_aliases",
    "server_aliases"
}

local function set_advanced_properties_visible(properties, visible)
    for _, name in ipairs(ADVANCED_PROPERTY_NAMES) do
        local property = obs.obs_properties_get(properties, name)
        if property ~= nil then
            obs.obs_property_set_visible(property, visible)
        end
    end
end

local function advanced_settings_changed(properties, property, settings)
    local visible = obs.obs_data_get_bool(settings, "show_advanced_settings")
    show_advanced_settings = visible
    set_advanced_properties_visible(properties, visible)
    return true
end

local function debug_setting_changed(properties, property, settings)
    -- Update immediately when the checkbox changes, not only when OBS later
    -- calls script_update.
    debug_enabled = obs.obs_data_get_bool(settings, "debug_enabled")
    return false
end

function script_properties()
    local properties = obs.obs_properties_create()

    obs.obs_properties_add_path(properties, "base_folder_override",
        "Custom output folder, optional", obs.OBS_PATH_DIRECTORY, nil, nil)
    local debug_property = obs.obs_properties_add_bool(properties,
        "debug_enabled", "Debug logging")
    obs.obs_property_set_modified_callback(debug_property, debug_setting_changed)
    obs.obs_properties_add_bool(properties, "show_notifications",
        "Windows notification when a clip saves")
    obs.obs_properties_add_bool(properties, "show_popup",
        "On-screen popup on the main monitor")
    local advanced_toggle = obs.obs_properties_add_bool(properties,
        "show_advanced_settings", "Show advanced settings")
    obs.obs_property_set_modified_callback(advanced_toggle, advanced_settings_changed)

    obs.obs_properties_add_button(properties, "run_diagnostics",
        "Run diagnostics", run_diagnostics_button)
    obs.obs_properties_add_button(properties, "test_folder_creation",
        "Test folder creation only", test_folder_creation_button)
    obs.obs_properties_add_button(properties, "open_output_folder",
        "Open output folder", open_output_folder_button)

    obs.obs_properties_add_int(properties, "clip_delay_ms",
        "Clip rename delay (milliseconds)", 0, 30000, 100)
    obs.obs_properties_add_int(properties, "recording_delay_ms",
        "Recording rename delay (milliseconds)", 0, 30000, 100)
    obs.obs_properties_add_int(properties, "poll_interval_ms",
        "Active game poll interval (milliseconds)", 2000, 60000, 500)
    obs.obs_properties_add_text(properties, "fivem_fallback_server",
        "FiveM fallback server name", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_text(properties, "game_aliases",
        "Game alias mapping (one Old Name=New Name per line)", obs.OBS_TEXT_MULTILINE)
    obs.obs_properties_add_text(properties, "server_aliases",
        "FiveM server alias mapping (one Old Name=New Name per line)", obs.OBS_TEXT_MULTILINE)

    set_advanced_properties_visible(properties, show_advanced_settings)

    return properties
end

function script_defaults(settings)
    obs.obs_data_set_default_string(settings, "base_folder_override", "")
    obs.obs_data_set_default_int(settings, "clip_delay_ms", 1500)
    obs.obs_data_set_default_int(settings, "recording_delay_ms", 1500)
    obs.obs_data_set_default_int(settings, "poll_interval_ms", 10000)
    obs.obs_data_set_default_string(settings, "fivem_fallback_server", "Unknown_Server")
    obs.obs_data_set_default_bool(settings, "debug_enabled", false)
    obs.obs_data_set_default_bool(settings, "show_notifications", true)
    obs.obs_data_set_default_bool(settings, "show_popup", true)
    obs.obs_data_set_default_bool(settings, "show_advanced_settings", false)
    obs.obs_data_set_default_string(settings, "game_aliases", "")
    obs.obs_data_set_default_string(settings, "server_aliases", "")
end

function script_update(settings)
    base_folder_override = trim(obs.obs_data_get_string(settings, "base_folder_override"))
    clip_delay_ms = obs.obs_data_get_int(settings, "clip_delay_ms")
    recording_delay_ms = obs.obs_data_get_int(settings, "recording_delay_ms")
    poll_interval_ms = math.max(2000, obs.obs_data_get_int(settings, "poll_interval_ms"))
    fivem_fallback_server = sanitize_windows_name(
        obs.obs_data_get_string(settings, "fivem_fallback_server"), "Unknown_Server")
    debug_enabled = obs.obs_data_get_bool(settings, "debug_enabled")
    show_notifications = obs.obs_data_get_bool(settings, "show_notifications")
    show_popup = obs.obs_data_get_bool(settings, "show_popup")
    show_advanced_settings = obs.obs_data_get_bool(settings, "show_advanced_settings")
    custom_game_aliases = parse_aliases(obs.obs_data_get_string(settings, "game_aliases"))
    custom_server_aliases = parse_aliases(obs.obs_data_get_string(settings, "server_aliases"))

    if poll_timer_running then
        obs.timer_remove(poll_game_timer)
        poll_timer_running = false
    end
    if not unloading then
        obs.timer_add(poll_game_timer, poll_interval_ms)
        poll_timer_running = true
    end

    local folder, source = detected_output_folder()
    log_selected_output_folder(folder, source, true)
end

function script_load(settings)
    unloading = false
    local runner_error
    hidden_runner_available, runner_error = prepare_hidden_windows_runner()
    if not hidden_runner_available then
        log_error(tostring(runner_error) .. ". Game detection is disabled to prevent " ..
            "visible PowerShell windows.")
        hidden_runner_error_logged = true
    end

    obs.obs_frontend_add_event_callback(frontend_event)

    refresh_hotkey_id = obs.obs_hotkey_register_frontend(
        "obs_game_clip_sorter.refresh",
        "OBS Game Clip Sorter: Refresh current game/server",
        refresh_hotkey_pressed)
    local hotkey_data = obs.obs_data_get_array(settings, "refresh_hotkey")
    obs.obs_hotkey_load(refresh_hotkey_id, hotkey_data)
    obs.obs_data_array_release(hotkey_data)

    replay_buffer_active = obs.obs_frontend_replay_buffer_active()
    recording_active = obs.obs_frontend_recording_active()
    detect_current_game(false)
    local folder, source = detected_output_folder()
    log_selected_output_folder(folder, source, false)
    log_info("Loaded v" .. SCRIPT_VERSION)
end

function script_save(settings)
    -- Explicitly save the live checkbox value so it survives script reloads.
    obs.obs_data_set_bool(settings, "debug_enabled", debug_enabled)
    local hotkey_data = obs.obs_hotkey_save(refresh_hotkey_id)
    obs.obs_data_set_array(settings, "refresh_hotkey", hotkey_data)
    obs.obs_data_array_release(hotkey_data)
end

function script_unload()
    unloading = true
    obs.obs_frontend_remove_event_callback(frontend_event)

    if poll_timer_running then
        obs.timer_remove(poll_game_timer)
        poll_timer_running = false
    end
    if job_timer_running then
        obs.timer_remove(job_timer)
        job_timer_running = false
    end

    jobs = {}
    claimed_files = {}
    log_info("Unloaded; timers were removed")
end
