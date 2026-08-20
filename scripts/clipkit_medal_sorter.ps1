# ClipKit Medal clip sorter
# Watches Medal's capture folder and renames new videos into
# <capture>\<server or game>\<Name> Clip dd-mm-yy HH-mm-ss.mp4

$ErrorActionPreference = "Continue"
$mutexName = "Global\ClipKitMedalSorter"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
if (-not $mutex.WaitOne(0)) {
    exit 0
}

$appData = Join-Path $env:APPDATA "ClipKit"
if (-not (Test-Path -LiteralPath $appData)) {
    New-Item -ItemType Directory -Path $appData -Force | Out-Null
}
$configPath = Join-Path $appData "medal-sorter.json"
$seenPath = Join-Path $appData "medal-sorter-seen.json"
$cachePath = Join-Path $appData "medal-sorter-cache.json"
$logPath = Join-Path $appData "medal-sorter.log"

$script:VideoExt = @(".mp4", ".mkv", ".mov", ".flv", ".webm")
$script:SkipFolders = @(
    ".thumbnails", "thumbnails", "editor", "edits", "projects", "imported",
    "screenshots", "recycle", "recycle bin", ".tmp", "temp", "cache", "reels"
)
$script:GenericParents = @(
    "clips", "clip", "videos", "video", "medal", "captures", "capture",
    "recordings", "recording", "library", "content", "games", "game", "obs"
)
$script:Reserved = @(
    "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5",
    "com6", "com7", "com8", "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5",
    "lpt6", "lpt7", "lpt8", "lpt9"
)
$script:Seen = @{}
$script:LastServer = "Unknown_Server"
$script:LastServerAt = Get-Date
$script:LastGame = "FiveM"

function Write-SorterLog([string]$message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    try {
        Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
    } catch { }
}

function Get-JsonObject([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) {
        return $null
    }
    try {
        return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Read-Seen {
    $script:Seen = @{}
    $data = Get-JsonObject $seenPath
    if ($null -eq $data) {
        return
    }
    foreach ($prop in $data.PSObject.Properties) {
        $script:Seen[$prop.Name] = [string]$prop.Value
    }
}

function Save-Seen {
    try {
        $keys = @($script:Seen.Keys)
        if ($keys.Count -gt 2500) {
            $keys = $keys | Select-Object -Last 2000
            $trimmed = @{}
            foreach ($key in $keys) {
                $trimmed[$key] = $script:Seen[$key]
            }
            $script:Seen = $trimmed
        }
        ConvertTo-Json -InputObject $script:Seen -Compress |
            Set-Content -LiteralPath $seenPath -Encoding UTF8
    } catch { }
}

function Read-Cache {
    $data = Get-JsonObject $cachePath
    if ($null -eq $data) {
        return
    }
    if ($data.server) {
        $script:LastServer = [string]$data.server
    }
    if ($data.game) {
        $script:LastGame = [string]$data.game
    }
    if ($data.at) {
        try { $script:LastServerAt = [datetime]$data.at } catch { }
    }
}

function Save-Cache {
    try {
        $payload = @{
            game = $script:LastGame
            server = $script:LastServer
            at = $script:LastServerAt.ToString("o")
        } | ConvertTo-Json -Compress
        Set-Content -LiteralPath $cachePath -Value $payload -Encoding UTF8
    } catch { }
}

function Get-DefaultWatchFolders {
    $folders = @(
        "D:\vids\medal",
        "C:\Medal",
        (Join-Path $env:USERPROFILE "Videos\Medal"),
        "D:\Medal"
    )
    $found = New-Object System.Collections.Generic.List[string]
    foreach ($folder in $folders) {
        if (Test-Path -LiteralPath $folder) {
            $found.Add((Resolve-Path -LiteralPath $folder).Path)
        }
    }
    return $found
}

function Read-Config {
    $watch = New-Object System.Collections.Generic.List[string]
    $output = Join-Path $env:USERPROFILE "Videos\ClipKit"
    $data = Get-JsonObject $configPath
    if ($null -ne $data) {
        if ($data.output) {
            $output = [string]$data.output
        }
        if ($data.watch) {
            foreach ($item in @($data.watch)) {
                $path = [string]$item
                if ($path -and (Test-Path -LiteralPath $path)) {
                    $watch.Add((Resolve-Path -LiteralPath $path).Path)
                }
            }
        }
    }
    if ($watch.Count -eq 0) {
        foreach ($folder in (Get-DefaultWatchFolders)) {
            $watch.Add($folder)
        }
    }
    return @{ Watch = $watch; Output = $output }
}

function Sanitize-Name([string]$value, [string]$fallback) {
    if ($null -eq $value) { $value = "" }
    $clean = $value.Trim()
    $clean = [regex]::Replace($clean, '[<>:"/\\|?*\p{C}]', " ")
    $clean = [regex]::Replace($clean, '\s+', " ").Trim()
    $clean = $clean.TrimEnd(".", " ")
    if (-not $clean) {
        $clean = $fallback
    }
    $first = ($clean.Split(".")[0]).ToLowerInvariant()
    if ($script:Reserved -contains $first) {
        $clean = $clean + "_"
    }
    if ($clean.Length -gt 80) {
        $clean = $clean.Substring(0, 80).TrimEnd(".", " ")
    }
    if (-not $clean) {
        $clean = $fallback
    }
    return $clean
}

function Filename-Part([string]$value, [string]$fallback) {
    $safe = Sanitize-Name $value $fallback
    $safe = [regex]::Replace($safe, '\s+', "_")
    $safe = [regex]::Replace($safe, '_+', "_")
    return $safe
}

function Test-JunkName([string]$value) {
    $lower = ($value | Out-String).ToLowerInvariant()
    return ($lower -match "xmlns" -or $lower -match "<objs" -or $lower -match "schemas.microsoft.com")
}

function Remove-Word([string]$text, [string]$word) {
    $pattern = [regex]::Escape($word)
    return [regex]::Replace($text, $pattern, " ", "IgnoreCase")
}

function Test-FiveM([string]$processName, [string]$windowTitle) {
    $combined = (($processName + " " + $windowTitle).ToLowerInvariant())
    if ($combined -match "fivem" -or $combined -match "cfx\.re") {
        return $true
    }
    $process = $processName.ToLowerInvariant() -replace "\.exe$", ""
    if ($process -match "gtaprocess" -and $process -match "fivem") {
        return $true
    }
    if ($process -match "^fivem_b\d+_gtaprocess$") {
        return $true
    }
    return ($combined -match "cfx" -and $combined -match "gta")
}

function Get-FiveMServer([string]$title) {
    $original = if ($null -eq $title) { "" } else { $title.Trim() }
    $lower = $original.ToLowerInvariant()
    if (-not $original -or $lower -match "loading" -or $lower -match "connecting") {
        return "Unknown_Server"
    }
    $clean = $original
    $clean = [regex]::Replace($clean, "(?i)FiveM_b\d+_GTAProcess(?:\.exe)?", " ")
    $clean = [regex]::Replace($clean, "(?i)FiveM(?:\.exe)?", " ")
    $clean = Remove-Word $clean "GTAProcess"
    $clean = [regex]::Replace($clean, "(?i)Version\s*=\s*[\w.]+", " ")
    $clean = Remove-Word $clean "Objs"
    $clean = Remove-Word $clean "xmlns"
    $clean = [regex]::Replace($clean, "https?://\S+", " ")
    $clean = [regex]::Replace($clean, "(?i)by\s+Cfx\.re", " ")
    $clean = Remove-Word $clean "FiveM"
    $clean = Remove-Word $clean "Cfx.re"
    $clean = Remove-Word $clean "loading"
    $clean = Remove-Word $clean "connecting"
    $clean = $clean.Replace([char]0x00AE, " ")
    $clean = [regex]::Replace($clean, "[\[\](){}]", " ")
    $clean = [regex]::Replace($clean, "[|]+", " ")
    $clean = $clean.Replace([char]0x2013, " ").Replace([char]0x2014, " ")
    $clean = [regex]::Replace($clean, "\s*-+\s*", " ")
    $clean = [regex]::Replace($clean, "\s+", " ").Trim()
    $clean = [regex]::Replace($clean, "(?i)^by\s+", "")
    $clean = $clean.Trim()
    $roleplay = [regex]::Match($clean, "(?i)([A-Za-z][\w\s\-']*?Roleplay)")
    if ($roleplay.Success) {
        $clean = $roleplay.Groups[1].Value.Trim()
    }
    $clean = Sanitize-Name $clean ""
    if (-not $clean -or $clean.Length -lt 2 -or (Test-JunkName $clean)) {
        return "Unknown_Server"
    }
    if ($clean.Length -gt 40) {
        $clean = $clean.Substring(0, 40).TrimEnd(".", " ")
    }
    return (Sanitize-Name $clean "Unknown_Server")
}

function Update-GameCache {
    $named = $null
    $fallback = $null
    try {
        foreach ($proc in Get-Process -ErrorAction SilentlyContinue) {
            $name = [string]$proc.ProcessName
            $title = [string]$proc.MainWindowTitle
            if (-not $title) { continue }
            if (-not (Test-FiveM $name $title)) { continue }
            $server = Get-FiveMServer $title
            if ($server -ne "Unknown_Server") {
                $named = $server
                break
            }
            if ($null -eq $fallback) {
                $fallback = $server
            }
        }
    } catch { }
    if (-not $named -and -not $fallback) {
        return
    }
    $script:LastGame = "FiveM"
    if ($named) {
        $script:LastServer = $named
        $script:LastServerAt = Get-Date
        Save-Cache
        return
    }
    if ((Get-Date) - $script:LastServerAt -gt [TimeSpan]::FromMinutes(10)) {
        $script:LastServer = "Unknown_Server"
        Save-Cache
    }
}

function Test-AlreadySorted([string]$name) {
    $lower = $name.ToLowerInvariant()
    return [bool]($lower -match " clip \d{2}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}" -or
        $lower -match "^clip_.+_\d{2}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}" -or
        $lower -match "^recording_.+_\d{2}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")
}

function Test-SkipPath([string]$path) {
    foreach ($part in $path.Split("\")) {
        if ($script:SkipFolders -contains $part.ToLowerInvariant()) {
            return $true
        }
    }
    return $false
}

function Get-ParentGame([string]$path, [string]$watchRoot) {
    try {
        $file = Get-Item -LiteralPath $path -ErrorAction Stop
        $dir = $file.Directory
        $root = $null
        if ($watchRoot -and (Test-Path -LiteralPath $watchRoot)) {
            $root = (Resolve-Path -LiteralPath $watchRoot).Path
        }
        while ($null -ne $dir) {
            if ($root -and $dir.FullName.Equals($root, [StringComparison]::OrdinalIgnoreCase)) {
                break
            }
            $name = Sanitize-Name $dir.Name ""
            $key = $name.ToLowerInvariant()
            if ($name -and $script:GenericParents -notcontains $key) {
                return $name
            }
            $dir = $dir.Parent
        }
    } catch { }
    return ""
}

function Wait-FileReady([string]$path) {
    $stable = 0
    $last = -1L
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $item = Get-Item -LiteralPath $path -ErrorAction Stop
            if ($item.Length -le 0) {
                Start-Sleep -Milliseconds 400
                continue
            }
            if ($item.Length -eq $last) {
                $stable++
            } else {
                $stable = 0
                $last = $item.Length
            }
            if ($stable -ge 3) {
                try {
                    $stream = [IO.File]::Open($path, "Open", "Read", "Read")
                    $stream.Close()
                    return $true
                } catch {
                    Start-Sleep -Milliseconds 400
                }
            } else {
                Start-Sleep -Milliseconds 400
            }
        } catch {
            Start-Sleep -Milliseconds 400
        }
    }
    return $false
}

function Get-UniquePath([string]$folder, [string]$stem, [string]$ext) {
    $target = Join-Path $folder ($stem + "." + $ext)
    $n = 2
    while (Test-Path -LiteralPath $target) {
        $target = Join-Path $folder ("{0}_{1}.{2}" -f $stem, $n, $ext)
        $n++
    }
    return $target
}

function Sort-Clip([string]$source, [string]$output, [string]$watchRoot) {
    if (-not (Wait-FileReady $source)) {
        Write-SorterLog ("Not ready yet: " + $source)
        return $false
    }
    Update-GameCache
    $parent = Get-ParentGame $source $watchRoot
    $game = $script:LastGame
    $server = $script:LastServer
    if ($parent) {
        if ($parent -match "(?i)fivem") {
            $game = "FiveM"
        } else {
            $game = $parent
            $server = $null
        }
    }
    $item = Get-Item -LiteralPath $source -ErrorAction Stop
    $fresh = ((Get-Date) - $item.LastWriteTime) -lt [TimeSpan]::FromMinutes(20)
    if ($game -eq "FiveM") {
        if ($fresh -and $server -and $server -ne "Unknown_Server") {
            $folderName = Sanitize-Name $server "FiveM"
        } else {
            $folderName = "FiveM"
        }
    } else {
        $folderName = Sanitize-Name $game "Unknown_Game"
    }
    $date = $item.LastWriteTime.ToString("dd-MM-yy")
    $time = $item.LastWriteTime.ToString("HH-mm-ss")
    $stem = "{0} Clip {1} {2}" -f $folderName, $date, $time
    $ext = ([IO.Path]::GetExtension($source).TrimStart(".")).ToLowerInvariant()
    $destFolder = Join-Path $output $folderName
    if (-not (Test-Path -LiteralPath $destFolder)) {
        New-Item -ItemType Directory -Path $destFolder -Force | Out-Null
    }
    $dest = Get-UniquePath $destFolder $stem $ext
    if ($source.Equals($dest, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    try {
        Move-Item -LiteralPath $source -Destination $dest -Force
        Write-SorterLog ("Renamed {0} -> {1}" -f $source, $dest)
        return $true
    } catch {
        Write-SorterLog ("Rename failed {0}: {1}" -f $source, $_.Exception.Message)
        return $false
    }
}

function Get-SeenKey([System.IO.FileInfo]$item) {
    return "{0}|{1}|{2}" -f $item.FullName.ToLowerInvariant(), $item.Length, $item.LastWriteTimeUtc.Ticks
}

function Scan-WatchFolder([string]$watchRoot, [string]$output, [bool]$markOnly) {
    if (-not (Test-Path -LiteralPath $watchRoot)) {
        return
    }
    Get-ChildItem -LiteralPath $watchRoot -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $script:VideoExt -contains $_.Extension.ToLowerInvariant() } |
        ForEach-Object {
            $item = $_
            if (Test-SkipPath $item.FullName) { return }
            if (Test-AlreadySorted $item.Name) { return }
            $id = $item.FullName.ToLowerInvariant()
            if ($markOnly) {
                $script:Seen[$id] = Get-SeenKey $item
                return
            }
            $ok = Sort-Clip $item.FullName $output $watchRoot
            if ($ok) {
                $script:Seen.Remove($id)
            }
        }
}

Read-Seen
Read-Cache
Write-SorterLog "Medal clip sorter started"
$loops = 0
try {
    while ($true) {
        $config = Read-Config
        $output = [string]$config.Output
        if ($output) {
            New-Item -ItemType Directory -Path $output -Force | Out-Null
        }
        Update-GameCache
        foreach ($watch in @($config.Watch)) {
            Scan-WatchFolder $watch $output $false
        }
        if ($loops % 5 -eq 0) {
            Save-Seen
        }
        $loops++
        Start-Sleep -Seconds 2
    }
} finally {
    Save-Seen
    try { $mutex.ReleaseMutex() } catch { }
}
