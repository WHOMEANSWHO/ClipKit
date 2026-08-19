# ClipKit

One-click OBS clipping setup for Windows. ClipKit looks at the PC, installs official OBS Studio if it is missing, and writes a ready-to-use **ClipKit** profile: replay buffer, keys, game audio, mic, and folders for clips.

People in a Discord community can run **one file**. They do not need Python. The first run installs ClipKit as a Windows app (Start menu and Settings → Apps).

## What you get

- A separate OBS profile named **ClipKit** (your existing Untitled profile is left alone)
- Replay buffer already running, so a hotkey saves the last 30 seconds, 1 minute, 2 minutes, or 5 minutes
- Optional full recordings at the same quality
- Game audio on track 1, mic on track 2 (push to talk, always on, or off)
- Desktop / Discord audio left out
- Clips sorted by game. FiveM goes into `FiveM\Server name`. Other games get their own folder, for example `Fortnite`
- Files named like `Clip_Server_Name_18-08-26_23-59-12.mp4`
- Windows notification and/or an on-screen popup when a clip or recording saves
- **Test clip** saves the buffer and opens the clips folder so you know it works
- **Open** next to the clips path shows that folder
- Health check names the hooked game, not only whether OBS and the replay buffer are on
- OBS opened as a normal window (not hidden in the tray)
- Optional start with Windows, with clipping already on

Quality is **Low / Medium / High** from the PC’s GPU and display. Bitrate defaults to **14 Mbps** (same as 14000 in OBS). Encoder is picked automatically: NVIDIA NVENC, AMD, Intel Quick Sync, or x264.

## Requirements

- Windows 10 or 11, 64-bit
- Internet the first time, if OBS is not installed yet
- A folder for clips

## Download

- **Finished app:** [ClipKit.exe](https://github.com/WHOMEANSWHO/ClipKit/releases/latest/download/ClipKit.exe) — latest [Release](https://github.com/WHOMEANSWHO/ClipKit/releases/latest), one file, no Python.
- **Unbuilt source:** the rest of this repo (`clipkit/`, `scripts/`, `build.py`).

Do not download `release/ClipKit.exe` from the repo tree. That copy can sit behind the newest Release.

## How to use it

1. Download **ClipKit.exe**.
2. Double-click it. Windows may ask to allow it — ClipKit then installs itself under your user account.
3. Open it from the **Start menu** next time. Uninstall from **Settings → Apps**.
4. Pick a clips folder, clip length, bitrate, and keys if you want to change them. ClipKit remembers these next time. **Open** next to the path shows that folder.
5. Close OBS if it is already open (check the tray too).
6. Click **Install OBS and set up**, or **Apply to OBS** if OBS is already installed.
7. Wait for the health check: OBS should be open on **ClipKit**, with the replay buffer on, and it should name the hooked game if you have already captured one.
8. Click **Test clip** once OBS is open. ClipKit saves the buffer and opens the clips folder so you know it works before you play.
9. Play. Press the save-clip key after something happens.

Windows SmartScreen may appear because the app is not signed. **More info → Run anyway**.

If OBS is missing, ClipKit installs the official 64-bit OBS Studio, then sets everything else up and opens OBS on the ClipKit profile.

## Keys (defaults)

| Action | Default |
| --- | --- |
| Save clip | Page Up |
| Start / stop clipping | Num − |
| Start / stop recording | Num + |
| Switch captured game | F7 |
| Push to talk | Mouse 4 and Mouse 5 (side buttons) |

Any of these can be rebound in ClipKit.

## FiveM and other games

Use **borderless / windowed fullscreen** if you can. Press the **switch game** key while in the game so clips follow that title.

FiveM clips land in `YourClipsFolder\FiveM\Server name`. Other games land in `YourClipsFolder\Game name`.

If the OBS preview is black or game audio is missing, run OBS as administrator.

## Build from source

```text
python -m pip install -r requirements.txt
python clipkit.py
python clipkit.py --detect
python build.py
```

`build.py` writes `dist\ClipKit.exe` and copies it to `release\ClipKit.exe`. Ship that file as a GitHub Release asset — that is what the download link above uses.

`--detect` prints GPU, RAM, and the recommended preset without changing OBS.

## Notes

- ClipKit installs for your user to `%LOCALAPPDATA%\Programs\ClipKit`. Uninstall from **Settings → Apps**.
- OBS must be fully closed while ClipKit applies settings.
- ClipKit searches common install folders, the registry, shortcuts, and other drives for OBS before it installs a new copy.
- A backup of `user.ini` is stored in `%APPDATA%\obs-studio\clipkit-backups\`.
- Last folder, keys, bitrate, and the rest of the setup are stored in `%APPDATA%\ClipKit\settings.json`.
- **Fresh OBS install** in the app wipes OBS, then downloads the newest official Windows x64 installer and applies ClipKit.
- Switch back anytime in OBS: **Profile → Untitled**.

## License

MIT. See [LICENSE](LICENSE). You can use, share, and change ClipKit.
