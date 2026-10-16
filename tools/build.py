"""Build the Windows release: dist/GeoHarvest-vX.Y.Z-windows.zip with the installer inside.

    pip install -r requirements-dev.txt
    winget install JRSoftware.InnoSetup      (once; builds the installer)
    python tools/build.py

PyInstaller one-folder build: the exe starts in about a second because nothing
is unpacked at launch, and antivirus tools flag it far less than one-file builds.
Inno Setup (installer/GeoHarvest.iss) wraps that folder in GeoHarvest-Setup-<tag>.exe,
the only file in the zip; the auto-updater looks for it there.
"""
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402

DIST = ROOT / "dist"
# Big parts of Qt and Python that GeoHarvest never uses
EXCLUDE = ["tkinter", "unittest", "pydoc", "test", "PyQt6.QtQml", "PyQt6.QtQuick",
           "PyQt6.QtWebEngineCore", "PyQt6.QtMultimedia", "PyQt6.QtNetwork", "PyQt6.QtOpenGL",
           "PyQt6.QtPdf", "PyQt6.QtBluetooth", "PyQt6.QtPositioning", "PyQt6.QtSql",
           "PyQt6.QtTest", "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.Qt3DCore",
           # optional extras other libraries try to import (openpyxl: PIL, lxml; and
           # cryptography is only the off-Windows fallback in credentials.py)
           "numpy", "pandas", "PIL", "lxml", "cryptography"]
# Qt files a widgets-only app never loads
DROP = ["PyQt6/Qt6/bin/opengl32sw.dll", "PyQt6/Qt6/bin/Qt6Pdf.dll",
        "PyQt6/Qt6/plugins/imageformats/qpdf.dll", "PyQt6/Qt6/translations"]


def iscc() -> str:
    """Inno Setup's compiler: on PATH, or where its installer puts it."""
    places = [shutil.which("ISCC"),
              Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Inno Setup 6/ISCC.exe",
              Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe",
              Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6/ISCC.exe"]
    for place in places:
        if place and Path(place).is_file():
            return str(place)
    sys.exit("Inno Setup is not installed: winget install JRSoftware.InnoSetup")


def tag() -> str:
    """'v0.1.0 beta' -> 'v0.1.0-beta'."""
    return re.sub(r"\s+", "-", config.APP_VERSION.strip())


def main() -> Path:
    shutil.rmtree(DIST / "GeoHarvest", ignore_errors=True)
    command = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "run.py"), "--noconfirm", "--clean", "--windowed",
        "--name", "GeoHarvest", "--icon", str(ROOT / "assets" / "icon.ico"),
        "--distpath", str(DIST), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
        "--add-data", f"{ROOT / 'app' / 'data'};app/data",
        "--add-data", f"{ROOT / 'assets'};assets",
        "--hidden-import", "app.ui.pages.search", "--hidden-import", "app.ui.pages.leads",
        "--hidden-import", "app.ui.pages.history", "--hidden-import", "app.ui.pages.smart",
        "--hidden-import", "app.ui.pages.settings",
    ]
    for module in EXCLUDE:
        command += ["--exclude-module", module]
    subprocess.run(command, cwd=ROOT, check=True)

    folder = DIST / "GeoHarvest"
    for name in DROP:
        path = folder / "_internal" / name
        shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)

    version = ".".join(re.findall(r"\d+", config.APP_VERSION)[:3])
    subprocess.run([iscc(), "/Q", f"/DAppVersion={version}", f"/DTag={tag()}",
                    f"/DSourceDir={folder}", f"/DOutputDir={ROOT / 'build'}",
                    f"/DIconFile={ROOT / 'assets' / 'icon.ico'}",
                    str(ROOT / "installer" / "GeoHarvest.iss")], check=True)
    setup = ROOT / "build" / f"GeoHarvest-Setup-{tag()}.exe"

    archive = DIST / f"GeoHarvest-{tag()}-windows.zip"
    archive.unlink(missing_ok=True)
    # Stored, not deflated: the installer is already compressed
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as bundle:
        bundle.write(setup, setup.name)
    size = archive.stat().st_size / 1_048_576
    print(f"Built {archive.name} ({size:.0f} MB) with {setup.name}")

    report = ROOT / "build" / "self-test.json"
    report.unlink(missing_ok=True)
    subprocess.run([str(folder / "GeoHarvest.exe"), "--self-test", str(report)], timeout=120)
    outcome = report.read_text("utf-8") if report.exists() else "no report written"
    print("Self-test:", outcome)
    if '"ok": true' not in outcome:
        sys.exit("The packaged app failed its self-test.")
    return archive


if __name__ == "__main__":
    main()
