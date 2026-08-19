"""ClipKit window — detect the PC, pick a preset, apply OBS clipping setup."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .hardware import Hardware, detect, obs_is_running
from .install_obs import find_obs_exe, install_obs, launch_obs_clipkit, obs_is_installed
from .keys import DEFAULT_BINDS, Hotkey, UserBinds, from_tk
from .obs import apply_setup, default_output_dir
from .presets import (
    DEFAULT_BITRATE,
    FPS_CHOICES,
    PRESET_ORDER,
    RECORD_BITRATES,
    Preset,
    all_presets,
    recommend_id,
)

BG = "#0b1326"
PANEL = "#171f33"
SURFACE = "#131b2e"
RAISED = "#222a3d"
BRIGHT = "#31394d"
BORDER = "#464555"
TEXT = "#dae2fd"
MUTED = "#c7c4d8"
PRIMARY = "#c3c0ff"
PRIMARY_BTN = "#4f46e5"
ON_PRIMARY = "#1d00a5"
BLURPLE = PRIMARY_BTN
BLURPLE_DIM = "#3323cc"
GREEN = "#4edea3"
AMBER = "#ffb95f"
KEY_BG = "#31394d"
UI = "Segoe UI"
MONO = "Cascadia Mono"


class KeybindButton(tk.Button):
    def __init__(self, parent: tk.Misc, initial: Hotkey, *, on_change=None) -> None:
        super().__init__(
            parent,
            text=initial.label,
            command=self._listen,
            bg=KEY_BG,
            fg=TEXT,
            activebackground=PRIMARY,
            activeforeground=ON_PRIMARY,
            disabledforeground=MUTED,
            relief="raised",
            bd=1,
            padx=12,
            pady=4,
            font=(MONO, 10),
            cursor="hand2",
            highlightthickness=0,
        )
        self.hotkey = initial
        self._on_change = on_change
        self._listening = False

    def _listen(self) -> None:
        if self._listening:
            return
        self._listening = True
        self.configure(text="Press a key…", bg=PRIMARY, fg=ON_PRIMARY, relief="flat")
        self.bind_all("<KeyPress>", self._on_key)
        self.bind_all("<ButtonPress-2>", self._on_mouse)
        self.bind_all("<ButtonPress-3>", self._on_mouse)
        self.bind_all("<ButtonPress-4>", self._on_mouse)
        self.bind_all("<ButtonPress-5>", self._on_mouse)
        self.focus_set()

    def _stop(self) -> None:
        self.unbind_all("<KeyPress>")
        self.unbind_all("<ButtonPress-2>")
        self.unbind_all("<ButtonPress-3>")
        self.unbind_all("<ButtonPress-4>")
        self.unbind_all("<ButtonPress-5>")
        self._listening = False
        self.configure(text=self.hotkey.label, bg=KEY_BG, fg=TEXT, relief="raised")
        if self._on_change:
            self._on_change()

    def _on_key(self, event) -> None:
        if str(event.keysym).lower() == "escape":
            self._stop()
            return
        mapped = from_tk(event)
        if mapped is None:
            return
        self.hotkey = mapped
        self._stop()

    def _on_mouse(self, event) -> None:
        mapped = from_tk(event)
        if mapped is None:
            return
        self.hotkey = mapped
        self._stop()

    def set_hotkey(self, hotkey: Hotkey) -> None:
        self.hotkey = hotkey
        if not self._listening:
            self.configure(text=hotkey.label)


class ClipKitApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"ClipKit {__version__}")
        self.geometry("1120x860")
        self.minsize(960, 740)
        self.configure(bg=BG)
        self._hw: Hardware | None = None
        self._presets: dict[str, Preset] = {}
        self._preset_id = tk.StringVar(value="medium")
        self._output = tk.StringVar(value=str(default_output_dir()))
        self._clip_seconds = tk.IntVar(value=300)
        self._fps = tk.IntVar(value=60)
        self._bitrate = tk.IntVar(value=DEFAULT_BITRATE)
        self._just_installed = False
        self._capture = tk.StringVar(value="hotkey")
        self._mic_mode = tk.StringVar(value="ptt")
        self._install_sorter = tk.BooleanVar(value=True)
        self._install_autostart = tk.BooleanVar(value=True)
        self._start_with_windows = tk.BooleanVar(value=True)
        self._enable_recording = tk.BooleanVar(value=True)
        self._show_notifications = tk.BooleanVar(value=True)
        self._show_popup = tk.BooleanVar(value=True)
        self._status = tk.StringVar(value="Detecting your PC…")
        self._busy = False
        self._chip_groups: list[tuple[dict, tk.Variable]] = []
        self._quality_chips: dict = {}
        self._build_style()
        self._build()
        self.after(100, self.refresh_hardware)
        self.after(1500, self._poll_obs)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=RAISED)
        style.configure("TFrame", background=BG)
        style.configure("TScrollbar", background=RAISED, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)
        style.configure("Dark.TEntry", fieldbackground=SURFACE, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER)
        style.map("Dark.TEntry", fieldbackground=[("focus", SURFACE)], bordercolor=[("focus", PRIMARY)])
        style.configure(
            "Ghost.TButton",
            font=(UI, 10),
            padding=(16, 8),
            background=SURFACE,
            foreground=TEXT,
            bordercolor=BORDER,
        )
        style.map("Ghost.TButton", background=[("active", RAISED)], foreground=[("active", PRIMARY)])

    def _card(self, parent: tk.Misc, title: str, subtitle: str = "") -> tk.Frame:
        shell = tk.Frame(parent, bg=BG)
        shell.pack(fill="both", expand=True, pady=(0, 12))
        border = tk.Frame(shell, bg=BORDER)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Frame(inner, bg=PRIMARY_BTN, height=2).pack(fill="x")
        content = tk.Frame(inner, bg=PANEL)
        content.pack(fill="both", expand=True)
        head = tk.Frame(content, bg=PANEL)
        head.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(head, text=title, bg=PANEL, fg=TEXT, font=(UI, 16, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(
                head, text=subtitle, bg=PANEL, fg=MUTED, font=(UI, 10), wraplength=520, justify="left"
            ).pack(anchor="w", pady=(4, 0))
        return content

    def _refresh_chips(self, store: dict, variable: tk.Variable) -> None:
        current = variable.get()
        for value, (btn, _label) in store.items():
            if value == current:
                btn.configure(bg=PRIMARY, fg=ON_PRIMARY)
            else:
                btn.configure(bg=SURFACE, fg=MUTED)

    def _chips(
        self,
        parent: tk.Misc,
        title: str,
        variable: tk.Variable,
        options: list | tuple,
        command=None,
    ) -> dict:
        wrap = tk.Frame(parent, bg=PANEL)
        wrap.pack(fill="x", padx=20, pady=(4, 12))
        tk.Label(
            wrap, text=title.upper(), bg=PANEL, fg=MUTED, font=(UI, 8, "bold")
        ).pack(anchor="w")
        track = tk.Frame(wrap, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        track.pack(fill="x", pady=(8, 0))
        row = tk.Frame(track, bg=SURFACE)
        row.pack(fill="x", padx=4, pady=4)
        store: dict = {}

        def pick(value) -> None:
            variable.set(value)
            self._refresh_chips(store, variable)
            if command:
                command()

        for value, label in options:
            btn = tk.Label(
                row,
                text=label,
                bg=SURFACE,
                fg=MUTED,
                padx=14,
                pady=8,
                font=(UI, 10),
                cursor="hand2",
            )
            btn.pack(side="left", padx=2, fill="x", expand=True)
            btn.bind("<Button-1>", lambda _e, v=value: pick(v))
            store[value] = (btn, label)
        self._chip_groups.append((store, variable))
        self._refresh_chips(store, variable)
        if title == "Quality":
            self._quality_chips = store
        return store

    def _bind_row(self, parent: tk.Misc, label: str, initial: Hotkey) -> KeybindButton:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=16, pady=2)
        tk.Label(row, text=label, bg=PANEL, fg=MUTED, font=(UI, 10), anchor="w").pack(
            side="left", fill="x", expand=True
        )
        button = KeybindButton(row, initial, on_change=self._sync_preset_copy)
        button.pack(side="right")
        return button

    def _check(self, parent: tk.Misc, text: str, variable: tk.BooleanVar, command=None) -> None:
        tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=command,
            bg=PANEL,
            fg=MUTED,
            activebackground=PANEL,
            activeforeground=TEXT,
            selectcolor=SURFACE,
            highlightthickness=0,
            bd=0,
            font=(UI, 10),
            anchor="w",
            padx=4,
            pady=4,
        ).pack(anchor="w", padx=16, fill="x")

    def _build(self) -> None:
        header = tk.Frame(self, bg=PANEL)
        header.pack(fill="x")
        tk.Frame(header, bg=BORDER, height=1).pack(fill="x", side="bottom")
        bar = tk.Frame(header, bg=PANEL)
        bar.pack(fill="x", padx=28, pady=14)
        brand = tk.Frame(bar, bg=PANEL)
        brand.pack(side="left")
        mark = tk.Label(
            brand,
            text="CK",
            bg=PRIMARY_BTN,
            fg=PRIMARY,
            font=(UI, 11, "bold"),
            padx=9,
            pady=7,
        )
        mark.pack(side="left", padx=(0, 12))
        titles = tk.Frame(brand, bg=PANEL)
        titles.pack(side="left")
        tk.Label(titles, text="ClipKit", bg=PANEL, fg=TEXT, font=(UI, 20, "bold")).pack(anchor="w")
        tk.Label(
            titles, text="OBS CLIP SETUP", bg=PANEL, fg=PRIMARY, font=(UI, 8, "bold")
        ).pack(anchor="w")
        right_meta = tk.Frame(bar, bg=PANEL)
        right_meta.pack(side="right")
        tk.Label(right_meta, text="SYSTEM READY", bg=PANEL, fg=GREEN, font=(UI, 8, "bold")).pack(anchor="e")
        tk.Label(right_meta, text=f"v{__version__}", bg=PANEL, fg=MUTED, font=(MONO, 9)).pack(anchor="e")

        self.warn_bar = tk.Frame(self, bg="#3d2a12")
        self.warn_label = tk.Label(
            self.warn_bar,
            text="OBS is open. Close it (including the tray icon) before you apply.",
            bg="#3d2a12",
            fg=AMBER,
            font=("Segoe UI Semibold", 9),
            pady=8,
        )
        self.warn_label.pack()

        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", side="bottom")
        tk.Frame(footer, bg=BORDER, height=1).pack(fill="x")
        bar = tk.Frame(footer, bg=BG)
        bar.pack(fill="x", padx=28, pady=16)
        status_wrap = tk.Frame(bar, bg=BG)
        status_wrap.pack(side="left", fill="x", expand=True)
        self._status_dot = tk.Label(status_wrap, text="●", bg=BG, fg=GREEN, font=(UI, 9))
        self._status_dot.pack(side="left", padx=(0, 8))
        tk.Label(
            status_wrap, textvariable=self._status, bg=BG, fg=MUTED, font=(MONO, 9), wraplength=680, justify="left"
        ).pack(side="left", fill="x", expand=True)
        self.apply_btn = tk.Button(
            bar,
            text="Apply to OBS",
            command=self.apply,
            bg=PRIMARY_BTN,
            fg=PRIMARY,
            activebackground=BLURPLE_DIM,
            activeforeground=PRIMARY,
            disabledforeground=MUTED,
            relief="flat",
            bd=0,
            padx=28,
            pady=12,
            font=(UI, 13, "bold"),
            cursor="hand2",
        )
        self.apply_btn.pack(side="right")

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=28, pady=(16, 0))
        self._main_shell = shell
        canvas = tk.Canvas(shell, bg=BG, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=BG)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        def _stretch(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        canvas.bind("<Configure>", _stretch)
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"))
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._canvas = canvas

        specs = self._card(body, "Hardware")
        pills = tk.Frame(specs, bg=PANEL)
        pills.pack(fill="x", padx=20, pady=(0, 12))
        self._pill_gpu = self._make_pill(pills, "GPU", "Scanning…")
        self._pill_cpu = self._make_pill(pills, "CPU", "…")
        self._pill_ram = self._make_pill(pills, "Memory / VRAM", "…")
        self._pill_obs = self._make_pill(pills, "OBS", "…", accent=True)
        self.specs_label = tk.Label(specs, text="", bg=PANEL, fg=MUTED, font=(UI, 9), wraplength=1000, justify="left")
        self.specs_label.pack(anchor="w", padx=20, pady=(0, 4))
        self.notes_label = tk.Label(specs, text="", bg=PANEL, fg=AMBER, font=(UI, 9), wraplength=1000, justify="left")
        self.notes_label.pack(anchor="w", padx=20, pady=(0, 16))

        columns = tk.Frame(body, bg=BG)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=1, uniform="cols")
        columns.columnconfigure(1, weight=1, uniform="cols")
        left = tk.Frame(columns, bg=BG)
        right = tk.Frame(columns, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        choices = self._card(left, "Clip setup", "Tuned for this PC. Change anything you want.")
        self._chips(
            choices,
            "Quality",
            self._preset_id,
            [(pid, pid.title()) for pid in PRESET_ORDER],
            self._on_choices_changed,
        )
        self.preset_copy = tk.Label(
            choices, text="", bg=PANEL, fg=PRIMARY, font=(MONO, 9), wraplength=520, justify="left"
        )
        self.preset_copy.pack(anchor="w", padx=20, pady=(0, 4))
        self._chips(
            choices,
            "Clip length",
            self._clip_seconds,
            ((30, "30s"), (60, "1m"), (120, "2m"), (300, "5m")),
            self._on_choices_changed,
        )
        self._chips(
            choices,
            "FPS",
            self._fps,
            [(fps, f"{fps} fps") for fps in FPS_CHOICES],
            self._on_choices_changed,
        )
        self._chips(
            choices,
            "Bitrate",
            self._bitrate,
            RECORD_BITRATES,
            self._on_choices_changed,
        )
        self._chips(
            choices,
            "Capture",
            self._capture,
            (("hotkey", "This game"), ("any", "Any fullscreen")),
            self._sync_hook_bind,
        )
        self._chips(
            choices,
            "Microphone",
            self._mic_mode,
            (("open", "Always on"), ("ptt", "PTT"), ("off", "Mic off")),
            self._sync_ptt,
        )
        tk.Label(
            choices,
            text="Game audio only. Mic is a separate track.",
            bg=PANEL,
            fg=MUTED,
            font=(MONO, 8),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 16))

        save = self._card(left, "Clips folder", "FiveM → FiveM\\Server name. Other games get their own folder.")
        path_row = tk.Frame(save, bg=PANEL)
        path_row.pack(fill="x", padx=20, pady=(4, 16))
        self._path_entry = ttk.Entry(path_row, textvariable=self._output, style="Dark.TEntry")
        self._path_entry.pack(side="left", fill="x", expand=True, ipady=6)
        ttk.Button(path_row, text="Browse", style="Ghost.TButton", command=self._browse).pack(side="left", padx=(8, 0))

        binds = self._card(right, "Keybinds", "Click a keycap, then press the key or mouse button.")
        self.save_bind = self._bind_row(binds, "Save clip", DEFAULT_BINDS.save)
        self.replay_bind = self._bind_row(binds, "Clipping on / off", DEFAULT_BINDS.replay_toggle)
        self.record_bind = self._bind_row(binds, "Recording on / off", DEFAULT_BINDS.record_toggle)
        self._record_row = self.record_bind.master
        self.hook_block = tk.Frame(binds, bg=PANEL)
        self.hook_block.pack(fill="x", after=self._record_row)
        self.hook_bind = self._bind_row(self.hook_block, "Switch game", DEFAULT_BINDS.hook_game)
        tk.Label(
            self.hook_block,
            text="Press this in-game so clips follow that title.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))
        self.ptt_keys = tk.Frame(binds, bg=PANEL)
        self.ptt_keys.pack(fill="x")
        ptt_defaults = DEFAULT_BINDS.ptt_keys()
        self.ptt_bind = self._bind_row(self.ptt_keys, "Talk (hold)", ptt_defaults[0])
        self.ptt_bind2 = self._bind_row(self.ptt_keys, "Talk (2nd button)", ptt_defaults[1])
        tk.Label(
            self.ptt_keys,
            text="Only used for Push to talk. Side mouse buttons are fine.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        options = self._card(right, "Extras", "Leave these on unless you know you want them off.")
        self._check(options, "Sort clips into game / FiveM server folders", self._install_sorter)
        self._check(options, "Start replay buffer when OBS opens", self._install_autostart)
        self._check(options, "Start OBS with Windows", self._start_with_windows)
        self._check(
            options,
            "Full recording setup (same quality as clips)",
            self._enable_recording,
            self._sync_record_bind,
        )
        self._check(
            options,
            "Windows notification when a clip saves (works in fullscreen)",
            self._show_notifications,
        )
        self._check(
            options,
            "On-screen popup on the main monitor when a clip saves",
            self._show_popup,
        )
        tk.Frame(options, bg=PANEL, height=10).pack()

        self._sync_ptt()
        self._sync_hook_bind()
        self._sync_record_bind()

    def _make_pill(self, parent: tk.Misc, title: str, value: str, *, accent: bool = False) -> tk.Label:
        bg = "#0d2a22" if accent else SURFACE
        box = tk.Frame(parent, bg=bg, highlightbackground=BORDER, highlightthickness=1)
        box.pack(side="left", padx=(0, 8), pady=2, fill="x", expand=True)
        tk.Label(box, text=title.upper(), bg=bg, fg=GREEN if accent else MUTED, font=(UI, 7, "bold")).pack(
            anchor="w", padx=12, pady=(8, 0)
        )
        value_lbl = tk.Label(
            box, text=value, bg=bg, fg=TEXT, font=(MONO, 9), wraplength=200, justify="left"
        )
        value_lbl.pack(anchor="w", padx=12, pady=(2, 8))
        return value_lbl

    def _sync_ptt(self) -> None:
        if self._mic_mode.get() != "ptt":
            self.ptt_keys.pack_forget()
            return
        if str(self.hook_block.winfo_manager()):
            self.ptt_keys.pack(fill="x", after=self.hook_block)
        else:
            self.ptt_keys.pack(fill="x", after=self._record_row)

    def _current_binds(self) -> UserBinds:
        return UserBinds(
            save=self.save_bind.hotkey,
            replay_toggle=self.replay_bind.hotkey,
            record_toggle=self.record_bind.hotkey,
            hook_game=self.hook_bind.hotkey,
            mic_mode=self._mic_mode.get(),
            ptt=[self.ptt_bind.hotkey, self.ptt_bind2.hotkey],
        )

    def _sync_record_bind(self) -> None:
        state = "normal" if self._enable_recording.get() else "disabled"
        self.record_bind.configure(state=state)

    def _sync_hook_bind(self) -> None:
        if self._capture.get() == "any":
            self.hook_block.pack_forget()
        else:
            self.hook_block.pack(fill="x", after=self._record_row)
        self._sync_ptt()

    def _on_choices_changed(self) -> None:
        if not self._hw:
            return
        self._presets = all_presets(
            self._hw,
            replay_seconds=int(self._clip_seconds.get()),
            fps=int(self._fps.get()),
            bitrate_kbps=int(self._bitrate.get()),
        )
        self._sync_preset_copy()

    def refresh_hardware(self) -> None:
        try:
            self._hw = detect()
        except Exception as exc:  # noqa: BLE001
            self._status.set(f"Hardware scan failed: {exc}")
            self.specs_label.configure(text="Could not read PC specs. You can still pick a preset.")
            self._hw = Hardware()
        hw = self._hw
        self._presets = all_presets(
            hw,
            replay_seconds=int(self._clip_seconds.get()),
            fps=int(self._fps.get()),
            bitrate_kbps=int(self._bitrate.get()),
        )
        recommended = recommend_id(hw)
        self._preset_id.set(recommended)
        for store, variable in self._chip_groups:
            self._refresh_chips(store, variable)
        vram = f"{hw.vram_gb:g} GB" if hw.vram_gb else "Unknown"
        self._pill_gpu.configure(text=hw.gpu_name or "Unknown")
        self._pill_cpu.configure(text=hw.cpu_name or "Unknown")
        self._pill_ram.configure(text=f"{hw.ram_gb:g} GB  •  {vram}")
        if hw.obs_installed:
            self._pill_obs.configure(text="Installed", fg=GREEN)
        else:
            self._pill_obs.configure(text="Will install", fg=AMBER)
        self.specs_label.configure(
            text=f"{hw.display_label}  ·  Recommended quality: {recommended.title()}"
        )
        notes = list(hw.notes)
        self._set_obs_warning(hw.obs_running)
        if hw.obs_running:
            notes.insert(0, "Close OBS completely before applying.")
        self.notes_label.configure(text="\n".join(notes))
        self._sync_preset_copy()
        if hw.obs_installed:
            self.apply_btn.configure(text="Apply to OBS")
            self._status.set("Ready. Pick your options, then Apply.")
        else:
            self.apply_btn.configure(text="Install OBS and set up")
            self._status.set("OBS is missing. Apply will download the official installer, then configure it.")

    def _sync_preset_copy(self) -> None:
        preset = self._presets.get(self._preset_id.get())
        if not preset:
            return
        rec = recommend_id(self._hw) if self._hw else ""
        tag = "  ·  recommended" if preset.id == rec else ""
        seconds = preset.replay_seconds
        length = f"{seconds} sec" if seconds < 60 else f"{seconds // 60} min"
        save = getattr(self, "save_bind", None)
        save_label = save.hotkey.label if save else "F9"
        mbps = preset.bitrate_kbps / 1000
        bitrate = f"{mbps:g} Mbps" if mbps == int(mbps) else f"{preset.bitrate_kbps} kbps"
        self.preset_copy.configure(
            text=(
                f"{preset.output_width}×{preset.output_height}  •  {preset.fps} fps  •  "
                f"{bitrate}  •  {preset.encoder_label}  •  last {length}  •  Save {save_label}{tag}"
            )
        )
        for value, (btn, label) in getattr(self, "_quality_chips", {}).items():
            btn.configure(text=f"{label}  •  Best" if value == rec else label)
        for store, variable in self._chip_groups:
            if variable is self._preset_id:
                self._refresh_chips(store, variable)

    def _set_obs_warning(self, running: bool) -> None:
        if self._hw:
            self._hw.obs_running = running
        shown = bool(self.warn_bar.winfo_manager())
        if running and not shown:
            self.warn_bar.pack(fill="x", before=self._main_shell)
        elif not running and shown:
            self.warn_bar.pack_forget()

    def _poll_obs(self) -> None:
        if not self._busy:
            try:
                self._set_obs_warning(obs_is_running())
            except Exception:
                pass
        self.after(1500, self._poll_obs)

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(title="Folder for clips")
        if chosen:
            self._output.set(chosen)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self._busy = busy
        self.apply_btn.configure(state="disabled" if busy else "normal", bg=RAISED if busy else PRIMARY_BTN)
        if message:
            self._status.set(message)

    def apply(self) -> None:
        if self._busy:
            return
        folder = self._output.get().strip()
        if not folder:
            messagebox.showerror("Clips folder", "Pick a folder where clips should be saved.")
            return
        if self._hw and self._hw.obs_running:
            messagebox.showerror(
                "OBS is still open",
                "Close OBS Studio completely (check the system tray), then click Apply again.",
            )
            return
        if not obs_is_installed():
            if not messagebox.askyesno(
                "Install OBS Studio?",
                "OBS Studio is not on this PC.\n\n"
                "ClipKit will install OBS, then set up everything else automatically:\n"
                "clips folder, keys, game audio, mic, replay buffer, and Windows start.\n\n"
                "Windows may ask for permission.\n\nContinue?",
            ):
                return
            self._set_busy(True, "Installing OBS Studio…")
            threading.Thread(target=self._install_then_apply, daemon=True).start()
            return
        self._do_apply()

    def _install_then_apply(self) -> None:
        def status(message: str) -> None:
            self.after(0, lambda m=message: self._status.set(m))

        try:
            install_obs(status)
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._install_failed(exc))
            return
        self.after(0, self._after_obs_installed)

    def _install_failed(self, exc: Exception) -> None:
        self._set_busy(False, "OBS install did not finish.")
        traceback.print_exc()
        messagebox.showerror("Could not install OBS", str(exc))

    def _after_obs_installed(self) -> None:
        if find_obs_exe() is None:
            self._set_busy(False, "OBS install finished, but the app was not found.")
            messagebox.showerror(
                "OBS not found",
                "The installer ran, but obs64.exe was not found. Open OBS from the Start menu once, then run ClipKit again.",
            )
            return
        self._install_sorter.set(True)
        self._install_autostart.set(True)
        self._start_with_windows.set(True)
        self._enable_recording.set(True)
        self._show_notifications.set(True)
        self._show_popup.set(True)
        self._just_installed = True
        self._set_busy(False)
        self.refresh_hardware()
        self._do_apply()

    def _do_apply(self) -> None:
        self._on_choices_changed()
        preset = self._presets.get(self._preset_id.get())
        if preset is None:
            messagebox.showerror("ClipKit", "Pick a preset first.")
            return
        try:
            result = apply_setup(
                preset,
                Path(self._output.get()),
                install_sorter=self._install_sorter.get(),
                install_autostart=self._install_autostart.get(),
                binds=self._current_binds(),
                capture=self._capture.get(),
                enable_recording=self._enable_recording.get(),
                show_notifications=self._show_notifications.get(),
                show_popup=self._show_popup.get(),
                start_with_windows=self._start_with_windows.get(),
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            messagebox.showerror("ClipKit could not apply settings", str(exc))
            return
        seconds = int(result["clip_seconds"])
        length = f"{seconds} seconds" if seconds < 60 else f"{seconds // 60} minutes"
        bitrate = int(result.get("bitrate_kbps") or preset.bitrate_kbps)
        self._just_installed = False
        launched = launch_obs_clipkit()
        if launched:
            self._status.set(
                f"OBS opened on ClipKit. Press {result['save_hotkey']} to save the last {length}."
            )
            next_step = "OBS opened on the ClipKit profile, with clipping already on."
        else:
            self._status.set(
                f"Done. Open OBS, then press {result['save_hotkey']} to save the last {length}."
            )
            next_step = "Open OBS, or wait until Windows login. Clipping starts by itself."
        if result.get("windows_startup"):
            startup_line = "OBS starts with Windows"
        elif self._start_with_windows.get():
            startup_line = "OBS Windows start: OBS was not found, skipped"
        else:
            startup_line = "OBS Windows start: off"
        messagebox.showinfo(
            "ClipKit is set up",
            "\n".join(
                [
                    f"OBS profile: ClipKit",
                    f"Quality: {result['quality']}",
                    f"Bitrate: {bitrate} kbps",
                    f"Clip length: last {length} at {result['fps']} fps",
                    f"Capture: {result['capture']}",
                    f"Clips save to: {result['output_dir']}",
                    f"Save clip: {result['save_hotkey']}",
                    f"Start/stop clipping: {result['clip_toggle']}",
                    f"Start/stop recording: {result['record_toggle']}",
                    f"Mic: {result['mic']}",
                    f"Audio: {result.get('audio', 'game + mic')}",
                    "Windows notification: on" if result.get("notifications") else "Windows notification: off",
                    "On-screen popup: on" if result.get("popup") else "On-screen popup: off",
                    startup_line,
                    "",
                    next_step,
                    "FiveM: press the switch-game key in-game. Run OBS as administrator if the preview stays black or game audio is missing.",
                ]
            ),
        )


def run() -> None:
    from .notifications import register_toast_app
    from .startup import install_clipkit_launcher_shortcuts, migrate_legacy_obs_startup

    install_clipkit_launcher_shortcuts()
    migrate_legacy_obs_startup()
    register_toast_app()
    app = ClipKitApp()
    app.mainloop()
