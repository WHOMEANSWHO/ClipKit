# ClipKit

One-click OBS clipping setup for Windows. ClipKit looks at the PC, installs official OBS Studio if it is missing, and writes a ready-to-use **ClipKit** profile: replay buffer, keys, Game Capture, and a clips folder.

People in a Discord community can run **one file**, then delete it. They do not need Python, and they do not need to keep ClipKit installed. After Apply, OBS does the clipping.

## What you get

- A separate OBS profile named **ClipKit** (your existing Untitled profile is left alone)
- Replay buffer already running, so a hotkey saves the last 30 seconds, 1 minute, 2 minutes, or 5 minutes
- Optional full recordings at the same quality
- Game audio on track 1, mic on track 2. ClipKit picks your microphone, turns on OBS push-to-talk, and sets Settings → Audio (desktop disabled, mic set to that device).
- Desktop / Discord audio left out
- Clips saved as normal OBS files, then sorted: FiveM goes to `your folder\Server name\Clip_Server_date_time.mp4`. Other games get `your folder\Game\Clip_Game_date_time.mp4`
- A **Clip saved** popup (Medal-style) when you save a clip. ClipKit only installs that script; OBS runs it.
- **Test clip** opens that folder so you can press Save in OBS and confirm a file appears
- **Open** next to the clips path shows that folder
- Health check confirms OBS is open on **ClipKit**, and names the Game Capture window if you already picked one
- OBS opened as a normal window (not hidden in the tray)
- Optional start with Windows, with clipping already on

Quality is **Low / Medium / High** from the PC’s GPU and display. Bitrate defaults to **14 Mbps** (same as 14000 in OBS). Encoder is picked automatically: NVIDIA NVENC, AMD, Intel Quick Sync, or x264.

## Requirements

- Windows 10 or 11, 64-bit
- Internet the first time, if OBS is not installed yet
- A folder for clips

## Download

- **Finished app:** [ClipKit.exe](https://github.com/WHOMEANSWHO/ClipKit/releases/latest/download/ClipKit.exe) — latest [Release](https://github.com/WHOMEANSWHO/ClipKit/releases/latest), one file, no Python.
- **Unbuilt source:** the rest of this repo (`clipkit/`, `build.py`).

Do not download `release/ClipKit.exe` from the repo tree. That copy can sit behind the newest Release.

## How to use it

1. Download **ClipKit.exe**.
2. Double-click it. Windows may ask to allow it.
3. Pick a clips folder, clip length, bitrate, and keys if you want to change them. **Open** next to the path shows that folder.
4. Click **Apply**. ClipKit installs OBS if needed, waits until OBS is fully open, closes it, writes the ClipKit setup, then opens OBS again. FiveM can stay running.
5. Wait for the health check: OBS should be open on **ClipKit**. If you already picked a game window in OBS, it should name that game.
6. Click **Test clip** once OBS is open. It opens the clips folder — press the save-clip key in OBS, then check that a file appears.
7. Delete **ClipKit.exe**. You do not need it installed. Play, and press the save-clip key after something happens.

Windows SmartScreen may appear because the app is not signed. **More info → Run anyway**.

If OBS is missing, ClipKit installs official OBS, waits until it is running, closes it, writes the ClipKit profile, then opens OBS again.

## Keys (defaults)

| Action | Default |
| --- | --- |
| Save clip | Page Up |
| Start / stop clipping | Num − |
| Start / stop recording | Num + |
| Push to talk | Mouse 4 / Mouse 5 |

Any of these can be rebound in ClipKit. Microphone is Always on, Push to talk, or off. ClipKit writes the selected mic into OBS.

## Games

Use **borderless / windowed fullscreen** if you can. In OBS, click **Game Capture**, set Mode to **Capture specific window**, and pick your game.

FiveM clips land in `YourClipsFolder\Server name`, named like `Clip_Server_Name_19-08-26_21-00-00.mp4`. Recordings use `Recording_` instead of `Clip_`. Other games land in `YourClipsFolder\Game name`.

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

- ClipKit is a setup tool only. After Apply you can delete `ClipKit.exe`. OBS keeps the ClipKit profile, the clip sorter, and the Clip saved popup.
- ClipKit picks a real microphone (not Chat Mix / virtual cables) and writes it into Settings → Audio as Mic/Auxiliary Audio. Desktop Audio is Disabled. Push to talk is OBS source PTT, default Mouse 4 and Mouse 5.
- OBS must be fully closed while ClipKit applies settings.
- ClipKit searches common install folders, the registry, shortcuts, and other drives for OBS before it installs a new copy.
- A backup of `user.ini` is stored in `%APPDATA%\obs-studio\clipkit-backups\`.
- Last folder, keys, bitrate, and the rest of the setup are stored in `%APPDATA%\ClipKit\settings.json`.
- **Fresh OBS install** in the app wipes OBS, then downloads the newest official Windows x64 installer and applies ClipKit.
- Switch back anytime in OBS: **Profile → Untitled**.

## License

MIT. See [LICENSE](LICENSE). You can use, share, and change ClipKit.
