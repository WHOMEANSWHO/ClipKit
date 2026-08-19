# ClipKit

One-click OBS clipping setup for Discord communities. It looks at the PC, picks a **Low / Medium / High** preset, turns on Replay Buffer, and installs the game clip sorter so FiveM (and other games) land in named folders.

If OBS is not installed, ClipKit downloads the **official** OBS Studio installer and sets it up.

## What it sets up

- Quality: **Low / Medium / High** (one is marked recommended for their PC)
- Recording bitrate: **8 / 10 / 12 / 14 / 20 / 25 Mbps** (default **14 Mbps**, same as 14000 in OBS)
- Clip length: **30 seconds / 1 minute / 2 minutes / 5 minutes**
- FPS: **30 or 60**
- Capture: **this game** (press a key to switch) or **any fullscreen game**
- Mic: **Push to talk** on Mouse 3 and Mouse 4 by default (or always on / off). Noise suppression is turned on.
- Audio: **game on track 1**, **mic on track 2**. Discord and desktop sound are left out.
- Default keys: **Num +** start/stop recording, **Num −** start/stop clipping, **Page Up** save clip, **F7** switch game (any key can be bound)
- Starts **OBS with Windows**, hidden in the tray, with **Replay Buffer already running**
- Windows notification and/or on-screen popup for **Clip** or **Recording**, with the date/time and FiveM server (notification works over fullscreen exclusive)
- Files named like `Clip_Felicity_Roleplay_18-08-26_23-59-12.mp4`
- OBS Studio itself, if it is missing
- A separate OBS profile named **ClipKit**. Apply switches OBS onto that profile automatically (Untitled is left alone)
- Encoder from the GPU it finds: NVIDIA NVENC, AMD, Intel Quick Sync, or x264
- `obs_game_clip_sorter.lua` so clips go into `FiveM\Felicity Roleplay`, `Fortnite`, and so on
- A helper that starts Replay Buffer when OBS opens and **beeps when a clip saves**
- A Windows Startup shortcut for OBS (tray, clipping already on)

## For Discord members

They do **not** need Python. Zip and share the built `dist\ClipKit` folder.

1. Unzip the folder.
2. Double-click **ClipKit.exe**.
3. Pick a clips folder, keybinds, and Low / Medium / High.
4. Click **Install OBS and set up** (or **Apply to OBS** if they already have it).
5. Play, press the save-clip key after something happens. OBS can sit in the tray.

Windows may show SmartScreen the first time (unsigned app). More info → Run anyway.

If OBS is missing, ClipKit downloads the official installer, then sets up clipping, folders, keys, audio, and the replay buffer automatically. OBS then starts in the tray.

FiveM works in **borderless / windowed fullscreen**. Click **Switch game** in ClipKit and press whatever key you want, then press that key while in the game (default is F7). If the preview is black, run OBS as administrator.

The sorter then moves files under the save location they chose: FiveM into `FiveM\Server`, other games into their own folder.

## For you (development)

```text
python clipkit.py
python clipkit.py --detect
python build.py
```

`--detect` prints GPU / RAM / recommended preset without writing anything. `build.py` makes `dist\ClipKit\ClipKit.exe` (PyInstaller, one-folder). That is what you send to Discord.

## After apply

OBS must be **fully closed** (also the tray icon) while ClipKit writes files. A timestamped backup of `user.ini` is stored in `%APPDATA%\obs-studio\clipkit-backups\`.

Switch back anytime: OBS → Profile → Untitled.
