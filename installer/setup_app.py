"""GeoHarvest Setup: the Windows installer.

Built into GeoHarvest-Setup.exe (plus its runtime/ folder) by tools/build.py. The
finished app travels inside it as payload.zip, so nothing is downloaded. The look
and the page flow come from HomingPigeon's installer.

Everything goes into %LOCALAPPDATA%\\Programs\\GeoHarvest, so no administrator
rights are needed. The user's data lives in %APPDATA%\\GeoHarvest and survives
updates (and uninstalls, unless the user ticks "also delete").

    GeoHarvest-Setup.exe                       install, update or repair
    ... --update --target DIR                  update in place once the app has closed, then
                                               reopen it (the app's "Update now" button)
    ... --uninstall [--target DIR]             remove (Settings > Apps, and the app's Settings)
    ... --uninstall --confirmed [--delete-data]   remove without asking (tests)
    ... --target DIR                           install somewhere else (tests: no shortcuts,
                                               nothing in Settings > Apps)
    ... /SILENT /DIR=DIR                       what GeoHarvest 0.1.1's updater sends: update
                                               without reopening the app (its script does that)

Standard library only, so Setup stays small.
"""
from __future__ import annotations

import ctypes
import math
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import zipfile
from pathlib import Path
from tkinter import messagebox

APP_NAME = "GeoHarvest"
APP_EXE = "GeoHarvest.exe"
SETUP_EXE = "GeoHarvest-Setup.exe"
UNINSTALL_DIR = "uninstall"          # Setup keeps a copy of itself here, minus the payload
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GeoHarvest"
# GeoHarvest 0.1.1 was installed with Inno Setup; installing over it replaces that entry
INNO_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F2B8C1E-4D7A-4E59-9B3C-2A1F0E8D7C64}_is1"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_BREAKAWAY_FROM_JOB = 0x01000000  # leave the browser's or Explorer's job object
LAUNCH_CONFIRM_SECONDS = 4.0

# --- Look (the app's dark theme) ----------------------------------------------
BG = "#1f2125"
PANEL = "#282b31"
CONSOLE = "#17191c"
BORDER = "#34373f"
FG = "#d0d4da"
FG_BRIGHT = "#f2f4f7"
FG_MUTED = "#8d939d"
ACCENT = "#3b86dd"
ACCENT_HOVER = "#4e94e6"
CONFIRM = "#39ad70"
CONFIRM_HOVER = "#48bc7e"
SECONDARY = "#34373f"
SECONDARY_HOVER = "#40444d"
ERROR = "#ef8a7f"


# =============================================================================
# Paths and facts about this computer
# =============================================================================
def bundle_dir() -> Path:
    """payload.zip, version.txt and the logo: inside Setup, or build/setup-data from source."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent / "build" / "setup-data"


def payload() -> Path:
    return bundle_dir() / "payload.zip"


def default_install_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Programs" / APP_NAME


def data_dir() -> Path:
    roaming = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(roaming) / APP_NAME


def read_version(folder: Path) -> str | None:
    try:
        return (folder / "version.txt").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def child_env() -> dict[str, str]:
    """Tell a PyInstaller-built child (the app) to set itself up from scratch, not from ours."""
    return {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}


def human_mb(n: float) -> str:
    return f"{n / 1_048_576:.0f} MB"


def powershell(script: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)


def running_app_pids(install_dir: Path) -> list[int]:
    """Process ids of GeoHarvest windows started from this install folder."""
    folder = str(install_dir).replace("'", "''")
    try:
        out = powershell(f"Get-Process GeoHarvest -ErrorAction SilentlyContinue | "
                         f"Where-Object {{ $_.Path -like '{folder}\\*' }} | ForEach-Object {{ $_.Id }}")
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [int(line) for line in out.stdout.split() if line.strip().isdigit()]


def special_folder(name: str) -> Path:
    """'Desktop', 'Programs' (the Start menu) or 'Startup', following OneDrive redirection."""
    try:
        out = powershell(f"(New-Object -ComObject WScript.Shell).SpecialFolders('{name}')")
        if out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    if name == "Desktop":
        return Path.home() / "Desktop"
    programs = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return programs / "Startup" if name == "Startup" else programs


def make_shortcut(link: Path, install_dir: Path) -> None:
    def q(value: object) -> str:
        return str(value).replace("'", "''")

    link.parent.mkdir(parents=True, exist_ok=True)
    result = powershell(
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{q(link)}'); "
        f"$s.TargetPath = '{q(install_dir / APP_EXE)}'; "
        f"$s.WorkingDirectory = '{q(install_dir)}'; "
        f"$s.IconLocation = '{q(install_dir / APP_EXE)},0'; "
        "$s.Description = 'Find business leads on Google Maps'; "
        "$s.Save()", timeout=60)
    if result.returncode != 0 or not link.exists():
        raise OSError((result.stderr or "the shortcut could not be saved").strip()[:300])


def start_app(install_dir: Path) -> subprocess.Popen:
    """Open the app, outside any job object that would close it along with Setup."""
    base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    last: OSError | None = None
    for flags in (base | CREATE_BREAKAWAY_FROM_JOB, base):
        try:
            return subprocess.Popen([str(install_dir / APP_EXE)], cwd=install_dir, env=child_env(),
                                    close_fds=True, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=flags)
        except OSError as error:
            last = error  # breakaway is not allowed in this job; try without it
    raise last or OSError("the app could not be started")


# =============================================================================
# The work, run on a background thread
# =============================================================================
class Cancelled(Exception):
    pass


class StepFailed(Exception):
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


INSTALL_STEPS = [
    ("close", "Check GeoHarvest is closed", 5),
    ("copy", "Copy GeoHarvest's files", 80),
    ("check", "Make sure everything is in place", 5),
    ("finish", "Finish up", 10),
]

UNINSTALL_STEPS = [
    ("close", "Check GeoHarvest is closed", 10),
    ("shortcuts", "Remove shortcuts", 10),
    ("files", "Delete the program files", 70),
    ("register", "Remove it from Settings > Apps", 10),
]


class Job:
    """Base for install/uninstall: reports to the window through a queue."""

    steps: list[tuple[str, str, int]] = []
    wait_seconds = 20

    def __init__(self, events: queue.Queue, install_dir: Path):
        self.events = events
        self.install_dir = install_dir
        self.cancel_event = threading.Event()
        self.log_path = Path(tempfile.gettempdir()) / f"{APP_NAME}-setup-log.txt"
        self._log_file = open(self.log_path, "w", encoding="utf-8")
        self._total_weight = sum(w for _, _, w in self.steps)
        self._done_weight = 0
        self._current_weight = 0

    def log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        for line in text.rstrip().splitlines() or [""]:
            self._log_file.write(f"{stamp}  {line}\n")
            self.events.put(("log", line))
        self._log_file.flush()

    def progress(self, fraction: float, detail: str = "") -> None:
        fraction = max(0.0, min(1.0, fraction))
        overall = (self._done_weight + self._current_weight * fraction) / self._total_weight
        self.events.put(("progress", overall, detail))

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            for index, (key, title, weight) in enumerate(self.steps):
                self.check_cancel()
                self._current_weight = weight
                self.events.put(("step", index, "running", ""))
                self.log("")
                self.log(f"== {title} ==")
                self.progress(0)
                summary = getattr(self, f"step_{key}")() or "Done"
                self._done_weight += weight
                self.progress(0)
                self.events.put(("step", index, "done", summary))
            self.events.put(("finished",))
        except Cancelled:
            self.log("Stopped because Cancel was pressed.")
            self.events.put(("cancelled",))
        except StepFailed as error:
            self.log(f"PROBLEM: {error}")
            self.events.put(("failed", str(error), error.hint))
        except Exception as error:  # noqa: BLE001 - always tell the user
            import traceback

            self.log(traceback.format_exc())
            self.events.put(("failed", f"Something unexpected went wrong: {error}",
                             "Click Try again. If it keeps happening, report it on GitHub with the "
                             "log file."))
        finally:
            self._log_file.close()

    def step_close(self) -> str:
        """The app closes itself after starting an update or uninstall; give it time."""
        for attempt in range(self.wait_seconds):
            if not running_app_pids(self.install_dir):
                return "Closed"
            if attempt == 0:
                self.log("Waiting for GeoHarvest to close...")
                self.progress(0, "Waiting for GeoHarvest to close...")
            self.check_cancel()
            time.sleep(1)
        raise StepFailed("GeoHarvest is still open.", "Close GeoHarvest, then click Try again.")


class InstallJob(Job):
    steps = INSTALL_STEPS

    def __init__(self, events: queue.Queue, install_dir: Path, register: bool,
                 wait_seconds: int = 20):
        super().__init__(events, install_dir)
        self.register = register
        self.wait_seconds = wait_seconds
        self.desktop = self.start_menu = self.startup = None

    def step_close(self) -> str:
        self.log(f"Installing to: {self.install_dir}")
        try:
            free = shutil.disk_usage(self.install_dir.anchor or "C:\\").free
            self.log(f"Free disk space: {human_mb(free)}")
            if free < 250 * 1_048_576:
                raise StepFailed("There isn't enough free disk space.",
                                 "GeoHarvest needs about 150 MB. Free up some space, then click "
                                 "Try again.")
        except OSError:
            pass
        return super().step_close()

    def step_copy(self) -> str:
        self.install_dir.mkdir(parents=True, exist_ok=True)
        old = self.install_dir / "_internal"
        if old.exists():
            self.log("Removing the previous version's files.")
            shutil.rmtree(old, ignore_errors=True)
        with zipfile.ZipFile(payload()) as archive:
            members = archive.infolist()
            self.log(f"Unpacking {len(members)} files")
            for index, member in enumerate(members):
                if index % 25 == 0:
                    self.check_cancel()
                    self.progress(index / len(members), f"{index} of {len(members)} files")
                try:
                    archive.extract(member, self.install_dir)
                except PermissionError:
                    raise StepFailed(f"Windows wouldn't let Setup replace {member.filename}.",
                                     "Close GeoHarvest if it is open, then click Try again.") from None
        shutil.copy2(bundle_dir() / "version.txt", self.install_dir / "version.txt")
        return f"{len(members)} files"

    def step_check(self) -> str:
        exe = self.install_dir / APP_EXE
        if not exe.is_file() or not (self.install_dir / "_internal").is_dir():
            raise StepFailed("Some of GeoHarvest's files are missing after copying.",
                             "Your antivirus may have removed them. Click Try again.")
        self.log(f"Found {exe}")
        return "All good"

    def step_finish(self) -> str:
        # A copy of Setup (without the payload) stays behind as the uninstaller
        target = self.install_dir / UNINSTALL_DIR
        if getattr(sys, "frozen", False):
            source = Path(sys.executable).resolve().parent
            if source != target.resolve():
                self.log("Saving the uninstaller.")
                shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("payload.zip"))
        for leftover in ("unins000.exe", "unins000.dat"):  # from the 0.1.1 installer
            (self.install_dir / leftover).unlink(missing_ok=True)
        self.progress(0.3)

        if self.register:
            self.desktop = special_folder("Desktop")
            self.start_menu = special_folder("Programs")
            self.startup = special_folder("Startup")
            self.progress(0.6)
            self.log("Adding GeoHarvest to Settings > Apps, so it can be removed like any other app.")
            import winreg

            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, INNO_KEY)
            except OSError:
                pass
            size_kb = sum(f.stat().st_size for f in self.install_dir.rglob("*") if f.is_file()) // 1024
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
                values = {
                    "DisplayName": APP_NAME,
                    "DisplayVersion": read_version(self.install_dir) or "",
                    "Publisher": APP_NAME,
                    "DisplayIcon": str(self.install_dir / APP_EXE),
                    "InstallLocation": str(self.install_dir),
                    "URLInfoAbout": "https://github.com/4bdulllahh/GeoHarvest",
                    "UninstallString": f'"{target / SETUP_EXE}" --uninstall',
                }
                for name, value in values.items():
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
                winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        self.progress(1.0)
        return "Done"


class UninstallJob(Job):
    steps = UNINSTALL_STEPS

    def __init__(self, events: queue.Queue, install_dir: Path, delete_data: bool, register: bool):
        super().__init__(events, install_dir)
        self.delete_data = delete_data
        self.register = register  # False for test installs elsewhere: leave real shortcuts alone

    def step_shortcuts(self) -> str:
        if not self.register:
            return "Skipped (test install)"
        removed = 0
        for name in ("Desktop", "Programs", "Startup"):
            link = special_folder(name) / f"{APP_NAME}.lnk"
            if link.exists():
                self.log(f"Deleting {link}")
                link.unlink()
                removed += 1
        return f"{removed} removed"

    def step_files(self) -> str:
        targets = [self.install_dir]
        if self.delete_data:
            targets.append(data_dir())
        # This uninstaller runs from inside the install folder; its own files are locked
        # until it closes, so they are removed right after the window closes.
        own = Path(sys.executable).resolve().parent
        for target in (t.resolve() for t in targets):
            if not target.exists():
                continue
            files = [p for p in target.rglob("*") if p.is_file() and own not in p.parents]
            self.log(f"Deleting {target} ({len(files)} files)")
            for index, path in enumerate(files):
                if index % 50 == 0:
                    self.check_cancel()
                    self.progress(index / max(len(files), 1), f"{index} of {len(files)} files")
                try:
                    path.unlink()
                except OSError as error:
                    self.log(f"  could not delete {path}: {error}")
            if own.is_relative_to(target):
                self.log("The last few files are removed as soon as this window closes.")
            else:
                shutil.rmtree(target, ignore_errors=True)
        if not self.delete_data:
            self.log(f"Your searches, leads and settings were kept in {data_dir()}")
        return "Deleted"

    def step_register(self) -> str:
        if not self.register:
            return "Skipped (test install)"
        import winreg

        for key in (REGISTRY_KEY, INNO_KEY):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
                self.log("Removed from Settings > Apps.")
            except OSError:
                pass
        return "Done"


# =============================================================================
# The window
# =============================================================================
class Button(tk.Label):
    """A flat button that matches the app (tk.Button can't be styled on Windows)."""

    def __init__(self, master, text: str, command, kind: str = "secondary", **kwargs):
        colours = {"primary": (ACCENT, ACCENT_HOVER), "confirm": (CONFIRM, CONFIRM_HOVER),
                   "secondary": (SECONDARY, SECONDARY_HOVER)}[kind]
        self._normal, self._hover = colours
        self._command = command
        self._enabled = True
        super().__init__(master, text=text, bg=self._normal, fg=FG_BRIGHT, cursor="hand2",
                         padx=22, pady=9, **kwargs)
        self.bind("<Enter>", lambda _e: self._enabled and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._normal if self._enabled else SECONDARY))
        self.bind("<Button-1>", lambda _e: self.invoke())

    def invoke(self) -> None:
        if self._enabled:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(bg=self._normal if enabled else SECONDARY, fg=FG_BRIGHT if enabled else FG_MUTED,
                       cursor="hand2" if enabled else "arrow")


class StepRow(tk.Frame):
    def __init__(self, master, title: str, fonts, scale: float):
        super().__init__(master, bg=PANEL)
        size = int(18 * scale)
        self.size = size
        self.icon = tk.Canvas(self, width=size, height=size, bg=PANEL, highlightthickness=0)
        self.icon.pack(side="left", padx=(0, int(10 * scale)))
        self.title = tk.Label(self, text=title, bg=PANEL, fg=FG_MUTED, font=fonts["body"], anchor="w")
        self.title.pack(side="left")
        self.detail = tk.Label(self, text="", bg=PANEL, fg=FG_MUTED, font=fonts["small"], anchor="e")
        self.detail.pack(side="right")
        self.state = "pending"
        self.angle = 0
        self.draw()

    def set(self, state: str, detail: str = "") -> None:
        self.state = state
        self.title.configure(fg={"pending": FG_MUTED, "running": FG_BRIGHT}.get(state, FG))
        self.detail.configure(text=detail, fg=ERROR if state == "failed" else FG_MUTED)
        self.draw()

    def draw(self) -> None:
        c, s = self.icon, self.size
        c.delete("all")
        pad = 2
        width = max(2, s // 9)
        if self.state == "pending":
            c.create_oval(pad, pad, s - pad, s - pad, outline=BORDER, width=width)
        elif self.state == "running":
            c.create_oval(pad, pad, s - pad, s - pad, outline=BORDER, width=width)
            c.create_arc(pad, pad, s - pad, s - pad, start=self.angle, extent=110, style="arc",
                         outline=ACCENT, width=width)
        elif self.state == "done":
            c.create_oval(pad, pad, s - pad, s - pad, fill=CONFIRM, outline=CONFIRM)
            c.create_line(s * 0.28, s * 0.52, s * 0.44, s * 0.68, s * 0.73, s * 0.34,
                          fill="white", width=width, capstyle="round", joinstyle="round")
        elif self.state == "failed":
            c.create_oval(pad, pad, s - pad, s - pad, fill="#c0493f", outline="#c0493f")
            c.create_line(s * 0.34, s * 0.34, s * 0.66, s * 0.66, fill="white", width=width, capstyle="round")
            c.create_line(s * 0.66, s * 0.34, s * 0.34, s * 0.66, fill="white", width=width, capstyle="round")

    def spin(self) -> None:
        if self.state == "running":
            self.angle = (self.angle - 18) % 360
            self.draw()


class SetupWindow:
    def __init__(self, uninstall: bool, install_dir: Path, register: bool, confirmed: bool = False,
                 delete_data: bool = False, auto_update: bool = False, reopen: bool = True):
        self.uninstall = uninstall
        self.auto_update = auto_update  # started by the app's "Update now": no questions
        self.reopen = reopen            # False when an older app's script reopens it instead
        self.install_dir = install_dir
        self.register = register
        self.confirmed = confirmed
        self.preset_delete_data = delete_data
        self.events: queue.Queue = queue.Queue()
        self.job: Job | None = None
        self.busy = False
        self.uninstalled = False
        self.new_version = read_version(bundle_dir()) or ""
        installed = (install_dir / APP_EXE).exists()
        self.old_version = (read_version(install_dir) or "an older version") if installed else None

        self.root = tk.Tk()
        self.scale = self.root.winfo_fpixels("1i") / 96
        self.root.title(f"{APP_NAME} Setup" if not uninstall else f"Remove {APP_NAME}")
        self.root.configure(bg=BG)
        width = int(760 * self.scale)
        height = min(int(720 * self.scale), self.root.winfo_screenheight() - int(80 * self.scale))
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 3
        self.root.geometry(f"{width}x{height}+{x}+{max(y, 0)}")
        self.root.minsize(int(620 * self.scale), int(540 * self.scale))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Return>", lambda _e: self.primary and self.primary.invoke())

        assets = bundle_dir() / "assets"
        try:
            self.root.iconbitmap(str(assets / "icon.ico"))
        except tk.TclError:
            pass

        self.fonts = {
            "title": tkfont.Font(family="Segoe UI Semibold", size=17),
            "heading": tkfont.Font(family="Segoe UI Semibold", size=12),
            "body": tkfont.Font(family="Segoe UI", size=10),
            "bold": tkfont.Font(family="Segoe UI Semibold", size=10),
            "small": tkfont.Font(family="Segoe UI", size=9),
            "mono": tkfont.Font(family="Consolas", size=9),
        }
        self.root.option_add("*Font", self.fonts["body"])

        self._build_frame(assets)
        self.primary: Button | None = None
        self.bob_phase = 0.0
        self.bob_speed = 0.09
        self._animate()
        self._poll()

        if auto_update:
            self.root.after(300, self.start_auto_update)
        elif uninstall and confirmed:
            self.root.after(300, self.start_uninstall)
        elif uninstall:
            self.page_confirm_uninstall()
        else:
            self.page_welcome()

    # -- frame -----------------------------------------------------------------
    def _build_frame(self, assets: Path) -> None:
        s = self.scale
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=int(28 * s), pady=(int(20 * s), int(8 * s)))

        sizes = [96, 128, 160, 192, 256]
        best = min(sizes, key=lambda n: abs(n - 104 * s))
        try:
            self.logo = tk.PhotoImage(file=str(assets / f"logo-{best}.png"))
        except tk.TclError:
            self.logo = None
        box = best if self.logo else int(96 * s)
        self.bob_room = int(8 * s)
        self.logo_canvas = tk.Canvas(header, width=box, height=box + self.bob_room * 2, bg=BG,
                                     highlightthickness=0)
        self.logo_canvas.pack(side="left")
        if self.logo:
            self.logo_item = self.logo_canvas.create_image(box // 2, box // 2 + self.bob_room,
                                                           image=self.logo)
        self.shadow_item = self.logo_canvas.create_oval(0, 0, 0, 0, fill="#2a2c32", outline="")
        self.logo_canvas.tag_lower(self.shadow_item)
        self.logo_box = box

        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left", padx=(int(18 * s), 0), fill="x", expand=True)
        self.title_label = tk.Label(titles, text="", bg=BG, fg=FG_BRIGHT, font=self.fonts["title"],
                                    anchor="w", justify="left")
        self.title_label.pack(anchor="w")
        self.subtitle_label = tk.Label(titles, text="", bg=BG, fg=FG_MUTED, font=self.fonts["body"],
                                       anchor="w", justify="left")
        self.subtitle_label.pack(anchor="w", pady=(int(2 * s), 0))
        titles.bind("<Configure>", lambda e: self.subtitle_label.configure(wraplength=e.width))

        # Footer first (at the bottom) so its buttons can never be pushed out of view
        self.footer = tk.Frame(self.root, bg=BG)
        self.footer.pack(side="bottom", fill="x", padx=int(28 * s), pady=int(18 * s))
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=int(28 * s))

    def _clear(self) -> None:
        for widget in list(self.body.winfo_children()) + list(self.footer.winfo_children()):
            widget.destroy()
        # The worker keeps posting events for a moment after a page is torn down
        self.primary = None
        self.detail = None
        self.log_text = None
        self.percent = None
        self.bar = None
        self.rows = []

    def _heading(self, title: str, subtitle: str) -> None:
        self.title_label.configure(text=title)
        self.subtitle_label.configure(text=subtitle)

    def _card(self) -> tuple[tk.Frame, tk.Frame]:
        s = self.scale
        outer = tk.Frame(self.body, bg=BORDER)
        inner = tk.Frame(outer, bg=PANEL, padx=int(18 * s), pady=int(14 * s))
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return outer, inner

    def _status(self, text: str) -> None:
        label = getattr(self, "detail", None)
        try:
            if label is not None:
                label.configure(text=text)
                self.root.update_idletasks()
        except tk.TclError:
            self.detail = None

    def _footer_note(self, text: str) -> None:
        tk.Label(self.footer, text=text, bg=BG, fg=FG_MUTED, font=self.fonts["small"]).pack(side="left")

    def _button(self, text: str, command, kind: str = "secondary", primary: bool = False) -> Button:
        button = Button(self.footer, text, command, kind, font=self.fonts["bold"])
        button.pack(side="right", padx=(int(10 * self.scale), 0))
        if primary:
            self.primary = button
        return button

    def _checkbox(self, parent, variable: tk.BooleanVar, label: str, hint: str = "") -> None:
        s = self.scale
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=int(5 * s))
        tk.Checkbutton(row, text=label, variable=variable, bg=PANEL, fg=FG_BRIGHT, activebackground=PANEL,
                       activeforeground=FG_BRIGHT, selectcolor=CONSOLE, font=self.fonts["bold"],
                       anchor="w", cursor="hand2", highlightthickness=0, bd=0).pack(anchor="w")
        if hint:
            tk.Label(row, text=hint, bg=PANEL, fg=FG_MUTED, font=self.fonts["small"], anchor="w").pack(
                anchor="w", padx=(int(26 * s), 0))

    def _animate(self) -> None:
        """The logo bobs gently, and a bit faster while work is happening."""
        self.bob_phase += self.bob_speed
        if self.logo:
            offset = math.sin(self.bob_phase) * self.bob_room * 0.8
            centre = self.logo_box // 2
            self.logo_canvas.coords(self.logo_item, centre, centre + self.bob_room + offset)
            spread = self.logo_box * (0.30 - 0.03 * math.sin(self.bob_phase))
            bottom = self.logo_box + self.bob_room * 2 - 2
            self.logo_canvas.coords(self.shadow_item, centre - spread, bottom - self.bob_room * 0.7,
                                    centre + spread, bottom)
        for row in getattr(self, "rows", []):
            try:
                row.spin()
            except tk.TclError:
                pass
        self.root.after(33, self._animate)

    # -- pages: install ----------------------------------------------------------
    def page_welcome(self) -> None:
        self._clear()
        s = self.scale
        try:
            with zipfile.ZipFile(payload()) as archive:
                size = sum(member.file_size for member in archive.infolist())
        except OSError:
            size = 150 * 1_048_576
        if self.old_version:
            same = self.old_version == self.new_version
            title = f"Repair {APP_NAME} {self.new_version}" if same else \
                f"Update {APP_NAME} to {self.new_version}"
            subtitle = ("GeoHarvest is already installed. This puts every file back as it should be."
                        if same else f"You have {self.old_version}. Your searches, leads and "
                                     f"settings are kept.")
            action = "Repair" if same else "Update"
        else:
            title = f"Install {APP_NAME} {self.new_version}"
            subtitle = "Find business leads on Google Maps. Setup takes less than a minute."
            action = "Install"
        self._heading(title, subtitle)

        outer, card = self._card()
        outer.pack(fill="x", pady=(int(8 * s), 0))
        tk.Label(card, text="What Setup will do", bg=PANEL, fg=FG_BRIGHT, font=self.fonts["heading"],
                 anchor="w").pack(anchor="w", pady=(0, int(8 * s)))
        points = [
            ("Put GeoHarvest in one folder", str(self.install_dir)),
            ("Add it to Settings > Apps",
             "So you can remove it like any other app. You choose the shortcuts at the end."),
            ("Keep your data separate",
             f"Searches, leads and settings stay on this computer in {data_dir()}, so updates "
             f"never touch them. No account, no sign-in."),
        ]
        for heading, text in points:
            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x", pady=int(5 * s))
            tk.Label(row, text="•", bg=PANEL, fg=ACCENT, font=self.fonts["heading"]).pack(side="left", anchor="n")
            col = tk.Frame(row, bg=PANEL)
            col.pack(side="left", fill="x", expand=True, padx=(int(8 * s), 0))
            tk.Label(col, text=heading, bg=PANEL, fg=FG, font=self.fonts["bold"], anchor="w").pack(anchor="w")
            detail = tk.Label(col, text=text, bg=PANEL, fg=FG_MUTED, font=self.fonts["small"], anchor="w",
                              justify="left")
            detail.pack(anchor="w", fill="x")
            col.bind("<Configure>", lambda e, d=detail: d.configure(wraplength=e.width))

        tk.Label(self.body, text=f"No administrator password needed. Needs about {human_mb(size)} "
                                 f"of free space.",
                 bg=BG, fg=FG_MUTED, font=self.fonts["small"], anchor="w").pack(anchor="w", pady=(int(14 * s), 0))

        self._footer_note(f"{self.new_version}  ·  Free beta")
        self._button(action, self.start_install, "confirm", primary=True)
        self._button("Cancel", self.root.destroy)

    def start_install(self) -> None:
        if self.old_version and running_app_pids(self.install_dir):
            if not messagebox.askokcancel(f"{APP_NAME} is open",
                                          "GeoHarvest is open right now.\n\nClose it (everything you "
                                          "found is saved), then click OK to continue.", parent=self.root):
                return
        self.page_progress(InstallJob(self.events, self.install_dir, self.register, wait_seconds=5),
                           f"Installing {APP_NAME}", "This takes less than a minute. You can watch "
                                                     "every step below.")

    def start_auto_update(self) -> None:
        """Update straight away, as soon as the app that asked for it has closed."""
        self.page_progress(InstallJob(self.events, self.install_dir, self.register, wait_seconds=60),
                           f"Updating {APP_NAME} to {self.new_version}",
                           "GeoHarvest opens again by itself when this is done. Your searches, "
                           "leads and settings are kept.")

    def page_progress(self, job: Job, title: str, subtitle: str) -> None:
        self._clear()
        s = self.scale
        self._heading(title, subtitle)
        self.job = job
        self.busy = True
        self.bob_speed = 0.22

        outer, card = self._card()
        outer.pack(fill="x", pady=(int(4 * s), 0))
        self.rows = []
        for _key, step_title, _w in job.steps:
            row = StepRow(card, step_title, self.fonts, s)
            row.pack(fill="x", pady=int(3 * s))
            self.rows.append(row)

        bar_row = tk.Frame(self.body, bg=BG)
        bar_row.pack(fill="x", pady=(int(14 * s), int(2 * s)))
        self.bar_height = int(10 * s)
        self.bar = tk.Canvas(bar_row, height=self.bar_height + 2, bg=BG, highlightthickness=0)
        self.bar.pack(side="left", fill="x", expand=True)
        self.percent = tk.Label(bar_row, text="0%", bg=BG, fg=FG_BRIGHT, font=self.fonts["bold"],
                                width=5, anchor="e")
        self.percent.pack(side="right")
        self.bar_fraction = 0.0
        self.bar.bind("<Configure>", lambda _e: self._draw_bar())
        self.detail = tk.Label(self.body, text="", bg=BG, fg=FG_MUTED, font=self.fonts["small"], anchor="w")
        self.detail.pack(fill="x")

        tk.Label(self.body, text="Activity log", bg=BG, fg=FG, font=self.fonts["bold"],
                 anchor="w").pack(anchor="w", pady=(int(10 * s), int(4 * s)))
        log_frame = tk.Frame(self.body, bg=BORDER)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, bg=CONSOLE, fg="#aab1bb", font=self.fonts["mono"], relief="flat",
                                wrap="word", padx=int(10 * s), pady=int(8 * s), height=10,
                                insertbackground=CONSOLE, highlightthickness=0, borderwidth=0)
        self.log_text.configure(state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=1, pady=1)
        self.log_text.tag_configure("heading", foreground=FG_BRIGHT)
        self.log_text.tag_configure("problem", foreground=ERROR)
        self.log_follow = True
        for sequence in ("<MouseWheel>", "<Prior>", "<Next>", "<Up>", "<Down>", "<Home>", "<End>",
                         "<B1-Motion>"):
            self.log_text.bind(sequence, self._log_scrolled, add="+")

        self._button("Cancel", self.on_close)
        threading.Thread(target=job.run, daemon=True).start()

    def _draw_bar(self) -> None:
        if getattr(self, "bar", None) is None:
            return
        width = self.bar.winfo_width()
        h = self.bar_height
        y = h // 2 + 1
        self.bar.delete("all")
        self.bar.create_line(h // 2, y, width - h // 2, y, fill=PANEL, width=h, capstyle="round")
        if self.bar_fraction > 0:
            end = h // 2 + (width - h) * self.bar_fraction
            self.bar.create_line(h // 2, y, max(end, h // 2 + 1), y, fill=ACCENT, width=h, capstyle="round")

    def _log_scrolled(self, _event=None) -> None:
        """Follow the newest line unless the user has scrolled up to read something."""
        def check() -> None:
            try:
                if self.log_text is not None:
                    self.log_follow = self.log_text.yview()[1] > 0.999
            except tk.TclError:
                pass

        self.root.after_idle(check)

    def _append_log(self, line: str) -> None:
        if getattr(self, "log_text", None) is None:
            return
        self.log_text.configure(state="normal")
        tag = "heading" if line.startswith("== ") else "problem" if line.startswith("PROBLEM") else ""
        self.log_text.insert("end", line + "\n", tag)
        self.log_text.configure(state="disabled")
        if self.log_follow:
            self.log_text.yview_moveto(1.0)

    def _poll(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._append_log(event[1])
                elif kind == "progress":
                    self.bar_fraction = event[1]
                    if self.percent is not None:
                        self._draw_bar()
                        self.percent.configure(text=f"{int(event[1] * 100)}%")
                    self._status(event[2])
                elif kind == "step":
                    _, index, state, detail = event
                    if index < len(self.rows):
                        self.rows[index].set(state, detail)
                elif kind in ("finished", "failed", "cancelled"):
                    self.busy = False
                    self.bob_speed = 0.09
                    if kind == "failed":
                        self.show_failure(event[1], event[2])
                    elif kind == "cancelled":
                        self.show_cancelled()
                    elif self.uninstall:
                        self.page_uninstalled()
                    elif self.auto_update:
                        self.finish_auto_update()
                    else:
                        self.page_done()
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def show_failure(self, message: str, hint: str) -> None:
        for row in self.rows:
            if row.state == "running":
                row.set("failed", "Didn't finish")
        self._heading("Removal didn't finish" if self.uninstall else "Setup didn't finish",
                      f"{message} {hint}".strip())
        self.subtitle_label.configure(fg=ERROR)
        self._status("Nothing is broken, and your searches and leads are safe.")
        for widget in self.footer.winfo_children():
            widget.destroy()
        self._button("Try again", self.retry, "primary", primary=True)
        self._button("Open log file", lambda: os.startfile(self.job.log_path))  # noqa: S606
        self._button("Close", self.root.destroy)

    def show_cancelled(self) -> None:
        for row in self.rows:
            if row.state == "running":
                row.set("failed", "Cancelled")
        self._heading("Cancelled", "Nothing is broken. Run Setup again whenever you like.")
        for widget in self.footer.winfo_children():
            widget.destroy()
        self._button("Close", self.root.destroy, "primary", primary=True)

    def retry(self) -> None:
        self.subtitle_label.configure(fg=FG_MUTED)
        if self.uninstall:
            self.start_uninstall()
        else:
            self.start_install()

    def page_done(self) -> None:
        self._clear()
        s = self.scale
        verb = "updated" if self.old_version and self.old_version != self.new_version else "installed"
        self._heading(f"{APP_NAME} is {verb}!", "Everything is copied, checked and ready to go.")

        outer, card = self._card()
        outer.pack(fill="x", pady=(int(8 * s), 0))
        tk.Label(card, text="Before you finish", bg=PANEL, fg=FG_BRIGHT, font=self.fonts["heading"],
                 anchor="w").pack(anchor="w", pady=(0, int(8 * s)))
        self.want_start = tk.BooleanVar(value=True)
        self.want_desktop = tk.BooleanVar(value=True)
        self.want_startup = tk.BooleanVar(value=False)
        self.want_launch = tk.BooleanVar(value=True)
        if self.register:
            self._checkbox(card, self.want_start, "Add GeoHarvest to the Start menu",
                           "Find it by pressing the Windows key and typing GeoHarvest.")
            self._checkbox(card, self.want_desktop, "Put a shortcut on the Desktop",
                           "Double-click it to open the app.")
            self._checkbox(card, self.want_startup, "Open GeoHarvest when Windows starts",
                           "Handy if you search for leads every day. You can change this later "
                           "by running Setup again.")
        self._checkbox(card, self.want_launch, "Open GeoHarvest now")

        where = tk.Label(self.body, text=f"Installed in {self.install_dir}\n"
                                         f"Your searches, leads and settings are stored in {data_dir()}",
                         bg=BG, fg=FG_MUTED, font=self.fonts["small"], justify="left", anchor="w")
        where.pack(anchor="w", fill="x", pady=(int(14 * s), 0))
        where.bind("<Configure>", lambda e: where.configure(wraplength=e.width))
        self.detail = tk.Label(self.body, text="", bg=BG, fg=FG_MUTED, font=self.fonts["small"], anchor="w")
        self.detail.pack(fill="x", pady=(int(8 * s), 0))

        self._footer_note(f"{self.new_version}  ·  Thanks for trying the beta!")
        self._button("Finish", self.finish, "confirm", primary=True)

    def finish(self) -> None:
        """Make or remove the shortcuts, open the app, and close Setup no matter what."""
        problems: list[str] = []
        try:
            if self.primary is not None:
                self.primary.set_enabled(False)
            job = self.job
            if self.register:
                for wanted, folder in ((self.want_start.get(), job.start_menu),
                                       (self.want_desktop.get(), job.desktop),
                                       (self.want_startup.get(), job.startup)):
                    link = folder / f"{APP_NAME}.lnk"
                    try:
                        if wanted:
                            make_shortcut(link, self.install_dir)
                        else:
                            link.unlink(missing_ok=True)  # e.g. start-up switched off on a repair
                    except (OSError, subprocess.TimeoutExpired) as error:
                        problems.append(f"{folder}: {error}")
            if self.want_launch.get():
                problems.extend(self._launch_app())
            if problems:
                self._reveal()
                messagebox.showwarning(APP_NAME, "Almost done, but:\n\n" + "\n".join(problems),
                                       parent=self.root)
        except Exception as error:  # noqa: BLE001 - Setup still has to close
            print(f"Problem finishing up: {type(error).__name__}: {error}")
        finally:
            self.root.destroy()

    def finish_auto_update(self) -> None:
        """Reopen the app and close Setup; the shortcuts from the first install still work."""
        self._heading(f"{APP_NAME} is updated!", f"Opening {APP_NAME} {self.new_version}...")
        try:
            problems = self._launch_app() if self.reopen else []
            if problems:
                self._reveal()
                messagebox.showwarning(APP_NAME, "The update is installed, but:\n\n" + "\n".join(problems),
                                       parent=self.root)
        except Exception as error:  # noqa: BLE001 - Setup still has to close
            print(f"Problem finishing up: {type(error).__name__}: {error}")
        finally:
            self.root.destroy()

    def _reveal(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass

    def _launch_app(self) -> list[str]:
        """Open the app, and wait long enough to know it really stayed open."""
        self._status(f"Opening {APP_NAME}...")
        try:
            process = start_app(self.install_dir)
        except OSError as error:
            return [f"Couldn't open the app: {error}"]
        try:
            self.root.withdraw()  # hidden, not gone: a failed launch brings it back to say so
        except tk.TclError:
            pass
        deadline = time.monotonic() + LAUNCH_CONFIRM_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is None:
                self.root.update()
                time.sleep(0.1)
                continue
            return [f"{APP_NAME} closed again right after opening. Try opening it from the Start "
                    f"menu. If it still won't start, report it on GitHub with {self.job.log_path}."]
        return []

    # -- pages: uninstall --------------------------------------------------------
    def page_confirm_uninstall(self) -> None:
        self._clear()
        s = self.scale
        self._heading(f"Remove {APP_NAME}?", "This removes the app and its shortcuts.")
        outer, card = self._card()
        outer.pack(fill="x", pady=(int(8 * s), 0))
        tk.Label(card, text="Your information", bg=PANEL, fg=FG_BRIGHT, font=self.fonts["heading"],
                 anchor="w").pack(anchor="w", pady=(0, int(6 * s)))
        info = tk.Label(card, bg=PANEL, fg=FG_MUTED, font=self.fonts["small"], justify="left", anchor="w",
                        text="Your searches, leads, exported files, settings and AI key are kept "
                             "unless you tick the box below, so reinstalling later brings "
                             f"everything back.\n{data_dir()}")
        info.pack(anchor="w", fill="x")
        card.bind("<Configure>", lambda e: info.configure(wraplength=e.width - int(40 * s)))
        self.want_delete_data = tk.BooleanVar(value=False)
        self._checkbox(card, self.want_delete_data, "Also delete my searches, leads and settings")
        self._button("Remove", self.start_uninstall, "primary", primary=True)
        self._button("Cancel", self.root.destroy)

    def start_uninstall(self) -> None:
        if self.confirmed:
            delete_data = self.preset_delete_data
        else:
            delete_data = self.want_delete_data.get() if hasattr(self, "want_delete_data") else False
        if delete_data and not self.confirmed and not messagebox.askyesno(
                APP_NAME, "Permanently delete your searches, leads and settings too?\n\n"
                          "This can't be undone.", icon="warning", parent=self.root):
            return
        self.page_progress(UninstallJob(self.events, self.install_dir, delete_data, self.register),
                           f"Removing {APP_NAME}", "This only takes a moment.")

    def page_uninstalled(self) -> None:
        self.uninstalled = True
        self._clear()
        self._heading(f"{APP_NAME} has been removed", "Thanks for trying it. You can reinstall any "
                                                      "time from the GitHub Releases page.")
        if not self.job.delete_data and data_dir().exists():
            outer, card = self._card()
            outer.pack(fill="x", pady=(int(8 * self.scale), 0))
            tk.Label(card, text="Your information was kept", bg=PANEL, fg=FG_BRIGHT,
                     font=self.fonts["heading"], anchor="w").pack(anchor="w")
            tk.Label(card, text="Reinstall later and your searches, leads and settings will be "
                                f"there.\nThey're stored in {data_dir()}",
                     bg=PANEL, fg=FG_MUTED, font=self.fonts["small"], justify="left", anchor="w").pack(
                anchor="w", pady=(int(4 * self.scale), 0))
        self._button("Close", self.root.destroy, "primary", primary=True)
        if self.confirmed:
            self.root.after(1500, self.root.destroy)

    # -- closing -------------------------------------------------------------------
    def on_close(self) -> None:
        if self.busy and self.job:
            if messagebox.askyesno("Cancel?", "Stop now? Nothing will be broken, and you can run "
                                              "Setup again later.", parent=self.root):
                self._status("Stopping...")
                self.job.cancel()
            return
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


# =============================================================================
# Entry point
# =============================================================================
def remove_folder_after_exit(folder: Path) -> None:
    """Delete what's left of the install folder once this process (which runs from it) closes.

    A hidden PowerShell waits for this exact process to end. Never DETACHED_PROCESS here:
    it makes Windows ignore CREATE_NO_WINDOW and gives the child a visible console.
    """
    path = str(folder).replace("'", "''")
    script = (
        f"Wait-Process -Id {os.getpid()} -Timeout 120 -ErrorAction SilentlyContinue; "
        f"for ($i = 0; $i -lt 20 -and (Test-Path -LiteralPath '{path}'); $i++) {{ "
        f"Remove-Item -LiteralPath '{path}' -Recurse -Force -ErrorAction SilentlyContinue; "
        f"Start-Sleep -Milliseconds 500 }}"
    )
    command = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
               "-Command", script]
    for flags in (NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB, NO_WINDOW):
        try:
            subprocess.Popen(command, creationflags=flags, close_fds=True, cwd=tempfile.gettempdir(),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return
        except OSError:
            continue  # breakaway is not allowed in this job; try without it


def main() -> int:
    args = sys.argv[1:]
    upper = [a.upper() for a in args]
    uninstall = "--uninstall" in args
    legacy = "/SILENT" in upper  # GeoHarvest 0.1.1's updater, written for the Inno installer
    install_dir = default_install_dir()
    if "--target" in args:
        install_dir = Path(args[args.index("--target") + 1])
    elif legacy:
        install_dir = Path(next((a[5:].strip('"') for a in args if a.upper().startswith("/DIR=")),
                                str(install_dir)))
    elif uninstall and getattr(sys, "frozen", False):
        # The uninstaller lives in <install folder>\uninstall
        here = Path(sys.executable).resolve().parent
        if here.name.lower() == UNINSTALL_DIR and (here.parent / APP_EXE).exists():
            install_dir = here.parent
    install_dir = install_dir.resolve()
    # Shortcuts and Settings > Apps only for the real install, never for a test folder
    register = legacy or os.path.normcase(install_dir) == os.path.normcase(default_install_dir().resolve())

    if sys.platform != "win32":
        print("GeoHarvest Setup is for Windows.")
        return 1
    if getattr(sys, "frozen", False):
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on high-DPI screens
    except (AttributeError, OSError):
        pass

    if not uninstall and not payload().exists():
        tk.Tk().withdraw()  # no empty window behind the message
        messagebox.showerror(f"{APP_NAME} Setup",
                             "Setup can't find GeoHarvest's files.\n\nExtract the whole zip first "
                             "(right-click it, Extract All), then run GeoHarvest-Setup.exe from the "
                             "extracted folder.")
        return 1

    window = SetupWindow(uninstall, install_dir, register, confirmed="--confirmed" in args,
                         delete_data="--delete-data" in args,
                         auto_update=("--update" in args or legacy) and not uninstall,
                         reopen=not legacy)
    window.run()

    if uninstall and window.uninstalled and install_dir.exists():
        os.chdir(tempfile.gettempdir())
        remove_folder_after_exit(install_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
