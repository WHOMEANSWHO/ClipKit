"""ClipKit window — detect the PC, pick a preset, apply OBS clipping setup."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .hardware import Hardware, detect, load_cached_hardware, obs_is_running
from .health import probe, reveal_in_explorer
from .install_obs import (
    find_obs_exe,
    fresh_install_obs,
    install_obs,
    launch_obs_clipkit,
    obs_exe_present,
    obs_is_installed,
    prepare_obs_then_close,
    reveal_obs_window,
)
from .keys import DEFAULT_BINDS, Hotkey, UserBinds, from_tk, mouse_button_held
from .obs import PROFILE_NAME, apply_setup, default_output_dir
from .paths import icon_file, mark_file
from .presets import (
    CLIP_LENGTHS,
    DEFAULT_BITRATE,
    FPS_CHOICES,
    PRESET_ORDER,
    RECORD_BITRATES,
    Preset,
    all_presets,
    recommend_id,
)
from .settings import binds_from_settings, load_settings, save_settings, settings_from_app

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
        self.after(120, self._poll_mouse)

    def _poll_mouse(self) -> None:
        if not self._listening:
            return
        held = mouse_button_held()
        if held is not None:
            self.hotkey = held
            self._stop()
            return
        self.after(30, self._poll_mouse)

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
        self._set_app_icon()
        self._hw: Hardware | None = None
        self._presets: dict[str, Preset] = {}
        self._preset_id = tk.StringVar(value="medium")
        self._output = tk.StringVar(value=str(default_output_dir()))
        self._clip_seconds = tk.IntVar(value=300)
        self._fps = tk.IntVar(value=60)
        self._bitrate = tk.IntVar(value=DEFAULT_BITRATE)
        self._just_installed = False
        self._capture = tk.StringVar(value="window")
        self._start_with_windows = tk.BooleanVar(value=True)
        self._enable_recording = tk.BooleanVar(value=True)
        self._status = tk.StringVar(value="Detecting your PC…")
        self._busy = False
        self._chip_groups: list[tuple[dict, tk.Variable]] = []
        self._quality_chips: dict = {}
        self._saved = load_settings()
        self._settings_restored = False
        self._health_tries = 0
        self._health_expect_replay = True
        self._health_apply_result: dict | None = None
        self._obs_present: bool | None = None
        self._poll_n = 0
        self._detect_gen = 0
        self._build_style()
        self._build()
        if self._saved:
            self._restore_settings()
            self._settings_restored = True
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        cached = load_cached_hardware()
        if cached is not None:
            self._apply_hardware(cached, status_ready=False)
            self._status.set("Checking hardware…")
        self.after(50, self.refresh_hardware)
        self.after(2500, self._poll_obs)

    def _set_app_icon(self) -> None:
        ico = icon_file()
        if ico is not None:
            try:
                self.iconbitmap(str(ico))
            except tk.TclError:
                pass
        mark = mark_file()
        if mark is None:
            return
        try:
            self._app_icon = tk.PhotoImage(file=str(mark))
            self.iconphoto(True, self._app_icon)
        except tk.TclError:
            self._app_icon = None

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
        mark = mark_file()
        if mark is not None:
            try:
                self._header_mark = tk.PhotoImage(file=str(mark))
                tk.Label(brand, image=self._header_mark, bg=PANEL, bd=0).pack(
                    side="left", padx=(0, 12)
                )
            except tk.TclError:
                mark = None
        if mark is None:
            tk.Label(
                brand,
                text="CK",
                bg=PRIMARY_BTN,
                fg=PRIMARY,
                font=(UI, 11, "bold"),
                padx=9,
                pady=7,
            ).pack(side="left", padx=(0, 12))
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
            text="OBS is open. Apply will restart OBS. FiveM and other games can stay running.",
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
        self.test_btn = tk.Button(
            bar,
            text="Test clip",
            command=self.test_clip,
            bg=SURFACE,
            fg=TEXT,
            activebackground=RAISED,
            activeforeground=PRIMARY,
            disabledforeground=MUTED,
            relief="flat",
            bd=0,
            padx=20,
            pady=12,
            font=(UI, 11, "bold"),
            cursor="hand2",
        )
        self.test_btn.pack(side="right", padx=(0, 10))

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

        def _on_mousewheel(event) -> None:
            try:
                x, y = canvas.winfo_pointerxy()
                left = canvas.winfo_rootx()
                top = canvas.winfo_rooty()
                if left <= x <= left + canvas.winfo_width() and top <= y <= top + canvas.winfo_height():
                    canvas.yview_scroll(int(-event.delta / 120), "units")
            except tk.TclError:
                pass

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
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
            (("window", "This game"), ("any", "Any fullscreen")),
            None,
        )
        tk.Label(
            choices,
            text="This game: in OBS, click Game Capture and pick the window yourself. Any fullscreen grabs whatever is in front.",
            bg=PANEL,
            fg=MUTED,
            font=(MONO, 8),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))
        tk.Label(
            choices,
            text="Game audio on track 1, mic on track 2. ClipKit picks your microphone. Mute and push-to-talk stay in Windows / Discord.",
            bg=PANEL,
            fg=MUTED,
            font=(MONO, 8),
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 16))

        save = self._card(left, "Clips folder", "OBS saves here, then the sorter puts FiveM clips in a server folder.")
        path_row = tk.Frame(save, bg=PANEL)
        path_row.pack(fill="x", padx=20, pady=(4, 16))
        self._path_entry = ttk.Entry(path_row, textvariable=self._output, style="Dark.TEntry")
        self._path_entry.pack(side="left", fill="x", expand=True, ipady=6)
        ttk.Button(path_row, text="Open", style="Ghost.TButton", command=self._open_clips_folder).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(path_row, text="Browse", style="Ghost.TButton", command=self._browse).pack(side="left", padx=(8, 0))

        binds = self._card(right, "Keybinds", "Click a keycap, then press the key or mouse button.")
        self.save_bind = self._bind_row(binds, "Save clip", DEFAULT_BINDS.save)
        self.replay_bind = self._bind_row(binds, "Clipping on / off", DEFAULT_BINDS.replay_toggle)
        self.record_bind = self._bind_row(binds, "Recording on / off", DEFAULT_BINDS.record_toggle)
        self._record_row = self.record_bind.master

        options = self._card(right, "Extras", "Leave these on unless you know you want them off.")
        self._check(options, "Start OBS with Windows", self._start_with_windows)
        self._check(
            options,
            "Full recording setup (same quality as clips)",
            self._enable_recording,
            self._sync_record_bind,
        )
        tk.Frame(options, bg=PANEL, height=10).pack()

        fresh = self._card(
            right,
            "Fresh OBS install",
            "Use this if OBS is the wrong version, desktop audio keeps coming back, or the setup is a mess.",
        )
        tk.Label(
            fresh,
            text="Removes OBS and its settings, then installs the newest official OBS and applies ClipKit. Clip videos stay.",
            bg=PANEL,
            fg=MUTED,
            font=(UI, 9),
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 12))
        self.fresh_btn = tk.Button(
            fresh,
            text="Remove OBS and install latest",
            command=self.fresh_install,
            bg=RAISED,
            fg=TEXT,
            activebackground=BRIGHT,
            activeforeground=PRIMARY,
            disabledforeground=MUTED,
            relief="flat",
            bd=0,
            padx=16,
            pady=10,
            font=(UI, 10, "bold"),
            cursor="hand2",
        )
        self.fresh_btn.pack(anchor="w", padx=20, pady=(0, 16))

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

    def _current_binds(self) -> UserBinds:
        saved = binds_from_settings(self._saved)
        return UserBinds(
            save=self.save_bind.hotkey,
            replay_toggle=self.replay_bind.hotkey,
            record_toggle=self.record_bind.hotkey,
            mic_device_id=saved.mic_device_id,
            mic_device_name=saved.mic_device_name,
        )

    def _sync_record_bind(self) -> None:
        state = "normal" if self._enable_recording.get() else "disabled"
        self.record_bind.configure(state=state)

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
        self._detect_gen += 1
        gen = self._detect_gen
        threading.Thread(target=self._detect_hardware_bg, args=(gen,), daemon=True).start()

    def _detect_hardware_bg(self, gen: int) -> None:
        try:
            hw = detect()
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda e=exc, g=gen: self._hardware_failed(e, g))
            return
        self.after(0, lambda h=hw, g=gen: self._hardware_ready(h, g))

    def _hardware_failed(self, exc: Exception, gen: int) -> None:
        if gen != self._detect_gen:
            return
        self._status.set(f"Hardware scan failed: {exc}")
        self.specs_label.configure(text="Could not read PC specs. You can still pick a preset.")
        if self._hw is None:
            self._apply_hardware(Hardware(), status_ready=True)

    def _hardware_ready(self, hw: Hardware, gen: int) -> None:
        if gen != self._detect_gen:
            return
        self._apply_hardware(hw, status_ready=True)
        if not hw.obs_installed:
            threading.Thread(target=self._deep_find_obs, args=(gen,), daemon=True).start()

    def _deep_find_obs(self, gen: int) -> None:
        found = find_obs_exe(deep=True) is not None
        self.after(0, lambda f=found, g=gen: self._deep_find_done(f, g))

    def _deep_find_done(self, found: bool, gen: int) -> None:
        if gen != self._detect_gen or self._busy:
            return
        self._sync_obs_presence(found, update_status=True)

    def _apply_hardware(self, hw: Hardware, *, status_ready: bool = True) -> None:
        self._hw = hw
        self._presets = all_presets(
            hw,
            replay_seconds=int(self._clip_seconds.get()),
            fps=int(self._fps.get()),
            bitrate_kbps=int(self._bitrate.get()),
        )
        recommended = recommend_id(hw)
        if not self._settings_restored:
            self._preset_id.set(recommended)
            self._settings_restored = True
        for store, variable in self._chip_groups:
            self._refresh_chips(store, variable)
        vram = f"{hw.vram_gb:g} GB" if hw.vram_gb else "Unknown"
        self._pill_gpu.configure(text=hw.gpu_name or "Unknown")
        self._pill_cpu.configure(text=hw.cpu_name or "Unknown")
        self._pill_ram.configure(text=f"{hw.ram_gb:g} GB  •  {vram}")
        self.specs_label.configure(
            text=f"{hw.display_label}  ·  Recommended quality: {recommended.title()}"
        )
        notes = list(hw.notes)
        self._set_obs_warning(hw.obs_running)
        if hw.obs_running:
            notes.insert(0, "Apply restarts OBS. You can keep FiveM open.")
        self.notes_label.configure(text="\n".join(notes))
        self._sync_preset_copy()
        self._sync_obs_presence(hw.obs_installed, update_status=status_ready)

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

    def _sync_obs_presence(self, installed: bool | None = None, *, update_status: bool = False) -> None:
        if installed is None:
            installed = obs_exe_present()
        if self._hw:
            self._hw.obs_installed = installed
            if not installed:
                self._hw.obs_exe = None
        changed = self._obs_present is not installed
        self._obs_present = installed
        if installed:
            self._pill_obs.configure(text="Installed", fg=GREEN)
            if not self._busy:
                self.apply_btn.configure(text="Apply to OBS")
            if update_status or (changed and not self._busy):
                self._status.set("Ready. Pick your options, then Apply.")
            return
        self._pill_obs.configure(text="Will install", fg=AMBER)
        if not self._busy:
            self.apply_btn.configure(text="Install OBS and set up")
        if update_status or (changed and not self._busy):
            self._status.set("OBS is missing. Apply will download the official installer, then configure it.")

    def _poll_obs(self) -> None:
        if not self._busy:
            try:
                self._set_obs_warning(obs_is_running())
                self._poll_n += 1
                if not self._obs_present or self._poll_n % 4 == 0:
                    self._sync_obs_presence()
            except Exception:
                pass
        self.after(2500, self._poll_obs)

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(title="Folder for clips")
        if chosen:
            self._output.set(chosen)

    def _open_clips_folder(self) -> None:
        folder = self._output.get().strip()
        if not folder:
            messagebox.showerror("Clips folder", "Pick a folder where clips should be saved.")
            return
        try:
            reveal_in_explorer(Path(folder))
        except OSError as exc:
            messagebox.showerror("Clips folder", f"Could not open that folder.\n\n{exc}")

    def test_clip(self) -> None:
        if self._busy:
            return
        folder = self._output.get().strip()
        if not folder:
            messagebox.showerror("Clips folder", "Pick a folder where clips should be saved.")
            return
        if not obs_is_running():
            messagebox.showerror(
                "OBS is not open",
                "Open OBS on the ClipKit profile first (Apply if you have not), then click Test clip.",
            )
            return
        try:
            reveal_in_explorer(Path(folder))
        except OSError as exc:
            messagebox.showerror("Clips folder", f"Could not open that folder.\n\n{exc}")
            return
        save_label = self.save_bind.hotkey.label
        self._status.set(f"Clips folder opened. Press {save_label} in OBS to save a clip.")
        messagebox.showinfo(
            "Test clip",
            f"OBS is open. Press {save_label} in OBS to save the replay buffer, then check this folder.",
        )

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self._busy = busy
        self.apply_btn.configure(state="disabled" if busy else "normal", bg=RAISED if busy else PRIMARY_BTN)
        if getattr(self, "test_btn", None):
            self.test_btn.configure(state="disabled" if busy else "normal")
        if getattr(self, "fresh_btn", None):
            self.fresh_btn.configure(state="disabled" if busy else "normal")
        if message:
            self._status.set(message)

    def apply(self) -> None:
        if self._busy:
            return
        folder = self._output.get().strip()
        if not folder:
            messagebox.showerror("Clips folder", "Pick a folder where clips should be saved.")
            return
        installing = not obs_is_installed()
        if installing:
            if not messagebox.askyesno(
                "Install OBS Studio?",
                "OBS Studio is not on this PC.\n\n"
                "ClipKit will install OBS, wait until it is running, close it, "
                "write the ClipKit setup, then open OBS again.\n\n"
                "FiveM can stay open.\n\n"
                "Windows will ask for permission — click Yes. Keep ClipKit open.\n\nContinue?",
            ):
                return
            self._set_busy(True, "Installing OBS Studio…")
        else:
            self._set_busy(True, "Opening OBS… FiveM can stay running.")
        threading.Thread(target=self._prepare_obs_then_apply, args=(installing,), daemon=True).start()

    def _prepare_obs_then_apply(self, installing: bool) -> None:
        def status(message: str) -> None:
            self.after(0, lambda m=message: self._status.set(m))

        try:
            if installing or not obs_is_installed():
                install_obs(status)
            prepare_obs_then_close(status)
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._install_failed(exc))
            return
        self.after(0, lambda: self._do_apply_ready(fresh=installing))

    def _do_apply_ready(self, fresh: bool = False) -> None:
        if fresh:
            self._start_with_windows.set(True)
            self._enable_recording.set(True)
        self._sync_obs_presence(True, update_status=False)
        self._do_apply()

    def fresh_install(self) -> None:
        if self._busy:
            return
        folder = self._output.get().strip()
        if not folder:
            messagebox.showerror("Clips folder", "Pick a folder where clips should be saved.")
            return
        if not messagebox.askyesno(
            "Fresh OBS install?",
            "This closes OBS and deletes it from this PC, including OBS profiles and scenes.\n\n"
            "Your clip videos and ClipKit options stay.\n\n"
            "ClipKit then downloads the newest official OBS, installs it, and sets up clipping.\n\n"
            "Windows will ask for permission — click Yes. Keep ClipKit open.\n\nContinue?",
        ):
            return
        self._set_busy(True, "Removing OBS…")
        threading.Thread(target=self._fresh_install_then_apply, daemon=True).start()

    def _fresh_install_then_apply(self) -> None:
        def status(message: str) -> None:
            self.after(0, lambda m=message: self._status.set(m))

        try:
            fresh_install_obs(status)
            prepare_obs_then_close(status)
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._install_failed(exc))
            return
        self.after(0, lambda: self._do_apply_ready(fresh=True))

    def _install_failed(self, exc: Exception) -> None:
        self._set_busy(False, "OBS install did not finish.")
        traceback.print_exc()
        messagebox.showerror("Could not install OBS", str(exc))

    def _persist_settings(self) -> None:
        try:
            save_settings(
                settings_from_app(
                    output=self._output.get().strip(),
                    preset=self._preset_id.get(),
                    clip_seconds=int(self._clip_seconds.get()),
                    fps=int(self._fps.get()),
                    bitrate=int(self._bitrate.get()),
                    capture=self._capture.get(),
                    binds=self._current_binds(),
                    start_with_windows=self._start_with_windows.get(),
                    enable_recording=self._enable_recording.get(),
                )
            )
        except OSError:
            pass

    def _restore_settings(self) -> None:
        data = self._saved
        if not data:
            return
        output = str(data.get("output") or "").strip()
        if output:
            self._output.set(output)
        if data.get("preset") in PRESET_ORDER:
            self._preset_id.set(str(data["preset"]))
        seconds = data.get("clip_seconds")
        if seconds in {length for length, _label in CLIP_LENGTHS}:
            self._clip_seconds.set(int(seconds))
        fps = data.get("fps")
        if fps in FPS_CHOICES:
            self._fps.set(int(fps))
        allowed_bitrate = {kbps for kbps, _label in RECORD_BITRATES}
        bitrate = data.get("bitrate")
        if bitrate in allowed_bitrate:
            self._bitrate.set(int(bitrate))
        if data.get("capture") == "any":
            self._capture.set("any")
        elif data.get("capture") in {"window", "hotkey"}:
            self._capture.set("window")
        binds = binds_from_settings(data)
        self.save_bind.set_hotkey(binds.save)
        self.replay_bind.set_hotkey(binds.replay_toggle)
        self.record_bind.set_hotkey(binds.record_toggle)
        extras = (
            ("start_with_windows", self._start_with_windows),
            ("enable_recording", self._enable_recording),
        )
        for key, variable in extras:
            if key in data:
                variable.set(bool(data[key]))
        self._on_choices_changed()
        self._sync_record_bind()
        for store, variable in self._chip_groups:
            self._refresh_chips(store, variable)

    def _on_close(self) -> None:
        if self._settings_restored:
            self._persist_settings()
        self._app_icon = None
        self.destroy()
        from .paths import leave_extract_dir

        leave_extract_dir()

    def _health_verdict(self, info: dict) -> tuple[str, bool]:
        game = str(info.get("game") or "").strip()
        if game:
            hooked = game
        elif self._capture.get() == "any":
            hooked = "any fullscreen game"
        else:
            hooked = "none yet — pick the window in OBS Game Capture"
        lines = [
            f"OBS: {info['obs']}",
            f"Profile: {info['profile']}",
            f"Replay buffer: {info['replay']}",
            f"Game Capture: {hooked}",
        ]
        ok = bool(info.get("ok"))
        if ok:
            lines.append("")
            lines.append("OBS is open on the ClipKit profile.")
        elif info["obs"] != "open":
            lines.append("")
            lines.append("OBS did not stay open. Open OBS yourself — it should be on the ClipKit profile.")
        elif info["profile"] != PROFILE_NAME:
            lines.append("")
            lines.append("OBS opened, but not on the ClipKit profile. Pick Profile → ClipKit.")
        return "\n".join(lines), ok

    def _poll_health(self) -> None:
        if not self.winfo_exists():
            return
        info = probe()
        reveal_obs_window()
        self._health_tries += 1
        if not info.get("ok") and self._health_tries < 40:
            self.after(500, self._poll_health)
            return
        result = self._health_apply_result or {}
        self._set_busy(False)
        self._show_apply_result(result, info)

    def _show_apply_result(self, result: dict, info: dict) -> None:
        preset = self._presets.get(self._preset_id.get())
        seconds = int(result.get("clip_seconds") or self._clip_seconds.get())
        length = f"{seconds} seconds" if seconds < 60 else f"{seconds // 60} minutes"
        bitrate = int(result.get("bitrate_kbps") or (preset.bitrate_kbps if preset else self._bitrate.get()))
        health_text, ok = self._health_verdict(info)
        if ok:
            self._status.set(
                f"OBS is on ClipKit with clipping on. Press {result.get('save_hotkey', 'Save')} to save the last {length}."
            )
        elif info["obs"] == "open":
            self._status.set("OBS opened. Check the health check — clipping may still be starting.")
        else:
            self._status.set(
                f"Done. Open OBS, then press {result.get('save_hotkey', 'Save')} to save the last {length}."
            )
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
                    "Is it working?",
                    health_text,
                    "",
                    f"OBS profile: {PROFILE_NAME}",
                    f"Quality: {result.get('quality', self._preset_id.get())}",
                    f"Bitrate: {bitrate} kbps",
                    f"Clip length: last {length} at {result.get('fps', self._fps.get())} fps",
                    f"Capture: {result.get('capture', self._capture.get())}",
                    f"Clips save to: {result.get('output_dir', self._output.get())}",
                    f"Game Capture: {info.get('game') or 'none yet — pick the window in OBS Game Capture'}",
                    f"Save clip: {result.get('save_hotkey', '')}",
                    f"Start/stop clipping: {result.get('clip_toggle', '')}",
                    f"Start/stop recording: {result.get('record_toggle', '')}",
                    f"Mic: {result.get('mic', '')}",
                    f"Audio: {result.get('audio', 'game + mic')}",
                    startup_line,
                    "",
                    "In OBS, click Game Capture and choose your game window. Run OBS as administrator if the preview stays black or game audio is missing.",
                    "",
                    "You can delete ClipKit.exe now. OBS keeps the ClipKit profile.",
                ]
            ),
        )

    def _do_apply(self) -> None:
        self._on_choices_changed()
        preset = self._presets.get(self._preset_id.get())
        if preset is None:
            self._set_busy(False)
            messagebox.showerror("ClipKit", "Pick a preset first.")
            return
        try:
            result = apply_setup(
                preset,
                Path(self._output.get()),
                binds=self._current_binds(),
                capture=self._capture.get(),
                enable_recording=self._enable_recording.get(),
                start_with_windows=self._start_with_windows.get(),
            )
        except Exception as exc:  # noqa: BLE001
            self._set_busy(False)
            traceback.print_exc()
            messagebox.showerror("ClipKit could not apply settings", str(exc))
            return
        self._just_installed = False
        if result.get("mic_device_id"):
            self._saved = dict(self._saved or {})
            self._saved["mic_device_id"] = result["mic_device_id"]
            self._saved["mic_device_name"] = str(result.get("mic") or "")
        self._persist_settings()
        launched = launch_obs_clipkit()
        self._health_apply_result = result
        self._health_expect_replay = True
        self._health_tries = 0
        if launched:
            self._set_busy(True, "Checking OBS… is the ClipKit profile open?")
            self.after(500, self._poll_health)
            return
        info = probe()
        self._set_busy(False)
        self._show_apply_result(result, info)


def run() -> None:
    from .paths import is_frozen, leave_extract_dir
    from .startup import migrate_legacy_obs_startup
    from .windows_app import cleanup_legacy_windows_app

    leave_extract_dir()
    if is_frozen():
        cleanup_legacy_windows_app()
    migrate_legacy_obs_startup()
    app = ClipKitApp()
    app.mainloop()
    leave_extract_dir()
