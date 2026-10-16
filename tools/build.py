"""Build the Windows release: dist/GeoHarvest-vX.Y.Z-windows.zip with GeoHarvest.exe inside.

    pip install -r requirements-dev.txt
    python tools/build.py

PyInstaller one-folder build: the exe starts in about a second because nothing
is unpacked at launch, and antivirus tools flag it far less than one-file builds.
The zip holds a single GeoHarvest/ folder; the auto-updater expects that layout.
"""
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

    archive = DIST / f"GeoHarvest-{tag()}-windows.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                bundle.write(path, Path("GeoHarvest") / path.relative_to(folder))
    size = archive.stat().st_size / 1_048_576
    print(f"Built {archive.name} ({size:.0f} MB)")

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
