"""Finding, downloading and installing a newer release from GitHub.

The app asks GitHub for the latest release when it opens. If there is a newer
one, the user is offered "Update now" or "Update later". Updating now:

  1. downloads that release's GeoHarvest-vX.Y.Z-windows.zip (the same file people
     download by hand) and checks it against the SHA-256 GitHub publishes,
  2. unpacks the installer inside it to a temporary folder, then
  3. starts a small script and closes the app. The script waits for the app to
     go, runs the installer silently over the current install and opens the app again.

The user's searches, leads and settings live in %APPDATA%/GeoHarvest and are
never part of an update.

Nothing here touches Qt, so it can run on a worker thread and be tested alone.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from app import config

API_URL = config.REPO_URL.replace("https://github.com/", "https://api.github.com/repos/")
ASSET_PATTERN = re.compile(r"^GeoHarvest-v[\w.\-]+-windows\.zip$")
EXE_NAME = "GeoHarvest.exe"
SETUP_PATTERN = "GeoHarvest-Setup*.exe"
WORK_DIR = Path(tempfile.gettempdir()) / f"{config.APP_NAME}-update"
CHUNK = 256 * 1024


@dataclass
class Release:
    tag: str             # "v0.2.0"
    page_url: str        # the release page on GitHub
    zip_url: str = ""    # empty while GitHub is still attaching the build
    zip_size: int = 0
    sha256: str = ""
    notes: str = ""


class UpdateCancelled(Exception):
    pass


def version_tuple(text: str) -> tuple[int, ...]:
    """'v0.1.0 beta' -> (0, 1, 0, 0); a final release sorts after its betas: (0, 1, 0, 1)."""
    numbers = [int(n) for n in re.findall(r"\d+", text.split("beta")[0])[:3]]
    numbers += [0] * (3 - len(numbers))
    return (*numbers, 0 if "beta" in text.lower() else 1)


def is_newer(candidate: str, current: str) -> bool:
    return version_tuple(candidate) > version_tuple(current)


# --- checking ---------------------------------------------------------------
def parse_release(data: dict) -> Release:
    release = Release(tag=str(data.get("tag_name") or ""),
                      page_url=str(data.get("html_url") or f"{config.REPO_URL}/releases"),
                      notes=str(data.get("body") or ""))
    for asset in data.get("assets") or []:
        if ASSET_PATTERN.match(str(asset.get("name") or "")):
            release.zip_url = str(asset.get("browser_download_url") or "")
            release.zip_size = int(asset.get("size") or 0)
            digest = str(asset.get("digest") or "")
            if digest.startswith("sha256:"):
                release.sha256 = digest.split(":", 1)[1].lower()
            break
    return release


def latest_release() -> Release | None:
    """The newest published release, or None when GitHub can't be reached."""
    try:
        reply = httpx.get(f"{API_URL}/releases/latest", timeout=15,
                          headers={"User-Agent": config.APP_NAME,
                                   "Accept": "application/vnd.github+json"})
        reply.raise_for_status()
        release = parse_release(reply.json())
    except Exception:  # noqa: BLE001 - offline, rate limited, no releases yet
        return None
    return release if release.tag else None


def available_update() -> Release | None:
    """The latest release if it is newer than this copy, otherwise None."""
    shutil.rmtree(WORK_DIR, ignore_errors=True)  # whatever an earlier update left behind
    release = latest_release()
    if release and is_newer(release.tag, config.APP_VERSION):
        return release
    return None


def app_folder() -> Path:
    return Path(sys.executable).resolve().parent


def can_update_itself(release: Release | None = None) -> bool:
    """True for the packaged Windows app with a release zip to fetch.

    Running from source (a developer) gets the download page instead.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    if not os.access(app_folder(), os.W_OK):
        return False
    return release is None or bool(release.zip_url)


# --- downloading ------------------------------------------------------------
def download(release: Release, progress: Callable[[int, int], None] | None = None,
             cancelled: Callable[[], bool] | None = None) -> Path:
    """Fetch the release zip, check it, unpack it. Returns the installer inside."""
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    archive = WORK_DIR / "update.zip"
    digest = hashlib.sha256()
    received = 0
    with httpx.stream("GET", release.zip_url, follow_redirects=True, timeout=60,
                      headers={"User-Agent": config.APP_NAME}) as reply, open(archive, "wb") as out:
        reply.raise_for_status()
        total = int(reply.headers.get("content-length") or release.zip_size or 0)
        for chunk in reply.iter_bytes(CHUNK):
            if cancelled and cancelled():
                raise UpdateCancelled()
            out.write(chunk)
            digest.update(chunk)
            received += len(chunk)
            if progress:
                progress(received, total)

    if release.sha256 and digest.hexdigest() != release.sha256:
        raise OSError("the download was damaged on the way. Please try again")

    staged = WORK_DIR / "files"
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (staged / member.filename).resolve()
            if staged.resolve() not in target.parents:
                continue  # never write outside the work folder
            if member.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, open(target, "wb") as out:
                shutil.copyfileobj(source, out)
    archive.unlink(missing_ok=True)

    found = next(staged.rglob(SETUP_PATTERN), None)
    if found is None:
        raise OSError("the download didn't contain the GeoHarvest installer")
    return found


# --- installing -------------------------------------------------------------
def after_exit_script(pid: int, then: str) -> str:
    """A batch file that waits for this process (pid) to exit, then runs ``then``."""
    return (
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul && '
        "(timeout /t 1 /nobreak >nul & goto wait)\r\n" + then
    )


def install_script(setup: Path, target: Path, pid: int) -> str:
    """Runs the installer once this process (pid) has exited, then reopens the app."""
    return after_exit_script(pid, (
        # /SILENT shows only a progress bar; /DIR keeps the app where it is now
        f'start "" /wait "{setup}" /SILENT /SUPPRESSMSGBOXES /NORESTART /DIR="{target}"\r\n'
        f'start "" "{target / EXE_NAME}"\r\n'))


def uninstaller() -> Path | None:
    """The installed app's uninstaller; None when running from source or a loose folder."""
    path = app_folder() / "unins000.exe"
    return path if getattr(sys, "frozen", False) and path.is_file() else None


def start_uninstall() -> None:
    """Run the uninstaller once the app has closed (it can't remove a running exe).
    /SILENT skips its "are you sure" (the app asked) but still asks about the user's data."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    _run_script("uninstall.bat",
                after_exit_script(os.getpid(), f'start "" "{uninstaller()}" /SILENT\r\n'))


def start_install(setup: Path) -> None:
    """Hand over to the install script. The caller then closes the app."""
    _run_script("install.bat", install_script(setup, app_folder(), os.getpid()))


def _run_script(name: str, text: str) -> None:
    """Start a batch file in the background, detached so it outlives the app."""
    script = WORK_DIR / name
    script.write_text(text, encoding="utf-8")
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS \
        | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(["cmd", "/c", str(script)], cwd=str(WORK_DIR), close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags)
