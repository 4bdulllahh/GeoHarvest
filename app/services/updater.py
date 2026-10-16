"""Finding, downloading and installing a newer release from GitHub.

The app asks GitHub for the latest release when it opens. If there is a newer
one, the user is offered "Update now" or "Update later". Updating now:

  1. downloads that release's GeoHarvest-vX.Y.Z-windows.zip (the same file people
     download by hand) and checks it against the SHA-256 GitHub publishes,
  2. unpacks it (GeoHarvest-Setup.exe and its runtime folder) to a temporary folder, then
  3. starts Setup in update mode and closes the app. Setup waits for the app to
     go, shows its progress window while it updates, and opens the app again.
     No script and no console window: users don't expect a black box to appear.

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
SETUP_EXE = "GeoHarvest-Setup.exe"
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
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
    """'v0.1.0 beta' -> (0, 1, 0). Only the numbers count: release tags are written both
    with and without "beta" ("v0.1.1" for the app's "v0.1.1 beta"), so the label can't."""
    numbers = [int(n) for n in re.findall(r"\d+", text)[:3]]
    return (*numbers, *[0] * (3 - len(numbers)))


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

    found = next(staged.rglob(SETUP_EXE), None)
    if found is None:
        raise OSError("the download didn't contain the GeoHarvest installer")
    return found


# --- installing -------------------------------------------------------------
def update_command(setup: Path, target: Path) -> list[str]:
    """Setup waits for the app to close, updates it in place, then reopens it."""
    return [str(setup), "--update", "--target", str(target)]


def start_install(setup: Path) -> None:
    """Hand over to Setup. The caller then closes the app."""
    _launch(update_command(setup, app_folder()))


def uninstaller() -> Path | None:
    """The installed app's uninstaller (Setup keeps a copy of itself in the app folder);
    None when running from source or a loose folder."""
    path = app_folder() / "uninstall" / SETUP_EXE
    return path if getattr(sys, "frozen", False) and path.is_file() else None


def start_uninstall(delete_data: bool) -> None:
    """Run the uninstaller (the app already asked); it waits for the app to close."""
    _launch([str(uninstaller()), "--uninstall", "--confirmed"]
            + (["--delete-data"] if delete_data else []))


def _launch(command: list[str]) -> None:
    """Start Setup (a windowed program, so no console appears) so that it outlives the app."""
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}  # Setup is a PyInstaller app too
    base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    last: OSError | None = None
    for flags in (base | CREATE_BREAKAWAY_FROM_JOB, base):
        try:
            subprocess.Popen(command, cwd=str(Path(command[0]).parent), env=env, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=flags)
            return
        except OSError as error:
            last = error  # breakaway is not allowed in this job; try without it
    raise last or OSError("Setup could not be started")
