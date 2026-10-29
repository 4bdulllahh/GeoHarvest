"""Build the Windows release: dist/GeoHarvest-vX.Y.Z-windows.zip with GeoHarvest's own installer.

    pip install -r requirements-dev.txt
    python tools/build.py

1. The app: a PyInstaller one-folder build (dist/GeoHarvest). It starts in about a
   second because nothing is unpacked at launch, and antivirus tools flag it far
   less than one-file builds. It is self-tested at the end.
2. The installer: installer/setup_app.py (Tkinter, HomingPigeon's look) built the same
   way into dist/GeoHarvest-Setup, carrying the app as payload.zip. Its DLLs sit in a
   runtime/ folder beside GeoHarvest-Setup.exe, so the zip has to be extracted first:
   HomingPigeon found a one-file Setup gets flagged by Defender as a trojan.
3. The zip: GeoHarvest-Setup.exe, runtime/ and READ ME FIRST.txt. The app's updater
   looks for GeoHarvest-Setup.exe in it.
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
           "numpy", "pandas", "PIL", "lxml", "cryptography",
           # extras the anthropic SDK can use but GeoHarvest's calls never touch (Bedrock/Vertex
           # auth, its CLI's pretty printing, async backends); the SDK still works without them
           "pygments", "rich", "click", "google", "setuptools", "pkg_resources", "requests",
           "urllib3", "markdown_it", "mdurl", "pyasn1", "pyasn1_modules", "rsa", "cachetools",
           "boto3", "botocore", "aiohttp", "aiodns", "aiohappyeyeballs", "aiosignal", "frozenlist",
           "multidict", "yarl", "propcache", "attr", "attrs", "trio", "brotli", "brotlicffi", "h2",
           "hpack", "hyperframe", "websockets"]
# Qt files a widgets-only app never loads (it needs PNG, ICO and SVG images only)
QT = "PyQt6/Qt6/"
DROP = [QT + "bin/opengl32sw.dll", QT + "bin/Qt6Pdf.dll", QT + "bin/Qt6Network.dll", QT + "translations",
        QT + "plugins/generic", QT + "plugins/styles", QT + "plugins/platforms/qminimal.dll",
        QT + "plugins/platforms/qoffscreen.dll"] + [
        QT + f"plugins/imageformats/q{name}.dll"
        for name in ("pdf", "gif", "icns", "jpeg", "tga", "tiff", "wbmp", "webp")]
# Parts of Setup's own Python/Tk it never uses: HTTPS (PowerShell does it), OpenSSL hashes
# (hashlib falls back to its built-in SHA-256), time zones, translations, demos
SETUP_EXCLUDE = ["PyQt6", "numpy", "PIL", "httpx", "openpyxl", "anthropic", "ssl", "_ssl",
                 "_hashlib", "unicodedata", "decimal", "_decimal", "bz2", "_bz2",
                 "email", "http", "xml", "pydoc", "unittest", "asyncio", "multiprocessing"]
SETUP_DROP = ["_tcl_data/tzdata", "_tcl_data/msgs", "_tk_data/msgs", "_tk_data/images",
              "_tk_data/demos"]


def tag() -> str:
    """'v0.1.0 beta' -> 'v0.1.0-beta'."""
    return re.sub(r"\s+", "-", config.APP_VERSION.strip())


def build_app() -> Path:
    shutil.rmtree(DIST / "GeoHarvest", ignore_errors=True)
    command = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "run.py"), "--noconfirm", "--clean", "--windowed",
        "--name", "GeoHarvest", "--icon", str(ROOT / "assets" / "icon.ico"),
        "--distpath", str(DIST), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
        "--add-data", f"{ROOT / 'app' / 'data'};app/data",
        "--add-data", f"{ROOT / 'app' / 'i18n' / 'locales'};app/i18n/locales",
        "--add-data", f"{ROOT / 'assets'};assets",
        "--hidden-import", "app.ui.pages.search", "--hidden-import", "app.ui.pages.leads",
        "--hidden-import", "app.ui.pages.history", "--hidden-import", "app.ui.pages.smart",
        "--hidden-import", "app.ui.pages.settings", "--hidden-import", "app.ui.pages.guide",
    ]
    for module in EXCLUDE:
        command += ["--exclude-module", module]
    subprocess.run(command, cwd=ROOT, check=True)

    folder = DIST / "GeoHarvest"
    for name in DROP:
        path = folder / "_internal" / name
        shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
    add_legal_files(folder)  # installed with the app
    return folder


def bundled_distributions() -> dict:
    """requirements.txt and everything it pulls in, as installed here: what the app ships."""
    from importlib import metadata

    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    todo = [Requirement(line.split("#")[0].strip()) for line in
            (ROOT / "requirements.txt").read_text("utf-8").splitlines() if line.split("#")[0].strip()]
    found: dict = {}
    while todo:
        wanted = todo.pop()
        name = canonicalize_name(wanted.name)
        if name in found:
            continue
        try:
            found[name] = dist = metadata.distribution(wanted.name)
        except metadata.PackageNotFoundError:
            continue  # an optional dependency for another platform or Python
        for text in dist.requires or []:
            child = Requirement(text)
            if child.marker is None or any(child.marker.evaluate({"extra": extra})
                                           for extra in (wanted.extras or {""})):
                todo.append(child)
    return found


def add_legal_files(folder: Path) -> None:
    """LICENSE, THIRD-PARTY-NOTICES.md and every bundled library's own license in licenses/.

    PyQt6 is GPL v3, so the Windows download has to carry the license texts with it.
    """
    shutil.copy2(ROOT / "LICENSE", folder / "LICENSE.txt")
    shutil.copy2(ROOT / "THIRD-PARTY-NOTICES.md", folder / "THIRD-PARTY-NOTICES.md")
    licenses = folder / "licenses"
    shutil.rmtree(licenses, ignore_errors=True)
    (licenses / "python").mkdir(parents=True)
    # Python's license also covers what it bundles: OpenSSL, SQLite, Tcl/Tk, libffi, zlib...
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "python" / "LICENSE.txt")
    for name, dist in sorted(bundled_distributions().items()):
        target = licenses / name
        target.mkdir()
        files = [f for f in dist.files or [] if any(word in f.name.upper() for word in
                                                     ("LICENSE", "LICENCE", "COPYING", "NOTICE"))]
        for file in files:
            shutil.copy2(dist.locate_file(file), target / file.name)
        if not files:  # some packages only state their license in their metadata
            meta = dist.metadata
            (target / "LICENSE.txt").write_text(
                f"{meta['Name']} {meta['Version']}\nLicense: "
                f"{meta.get('License-Expression') or meta.get('License') or 'see the project'}\n"
                f"Project: {meta.get('Home-page') or meta.get('Project-URL') or ''}\n", "utf-8")


def build_setup(app_folder: Path) -> Path:
    """dist/GeoHarvest-Setup: the installer, carrying the app as payload.zip."""
    data = ROOT / "build" / "setup-data"  # also where setup_app.py looks when run from source
    shutil.rmtree(data, ignore_errors=True)
    (data / "assets").mkdir(parents=True)
    for name in ("icon.ico", "logo-96.png", "logo-128.png", "logo-160.png"):
        shutil.copy2(ROOT / "assets" / name, data / "assets" / name)
    (data / "version.txt").write_text(config.APP_VERSION, encoding="utf-8")
    with zipfile.ZipFile(data / "payload.zip", "w", zipfile.ZIP_LZMA) as payload:  # smallest
        for path in sorted(app_folder.rglob("*")):
            if path.is_file():
                payload.write(path, path.relative_to(app_folder))

    shutil.rmtree(DIST / "GeoHarvest-Setup", ignore_errors=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", str(ROOT / "installer" / "setup_app.py"),
        "--name", "GeoHarvest-Setup", "--onedir", "--contents-directory", "runtime", "--noupx",
        "--windowed", "--clean", "--noconfirm", "--icon", str(ROOT / "assets" / "icon.ico"),
        "--add-data", f"{data};.",
        "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "setup-work"),
        "--specpath", str(ROOT / "build"),
        # Setup needs only the standard library and Tk
        *[arg for module in SETUP_EXCLUDE for arg in ("--exclude-module", module)],
    ], cwd=ROOT, check=True)
    runtime = DIST / "GeoHarvest-Setup" / "runtime"
    for name in SETUP_DROP:
        shutil.rmtree(runtime / name, ignore_errors=True)
    return DIST / "GeoHarvest-Setup"


def main() -> Path:
    folder = build_app()
    setup = build_setup(folder)

    archive = DIST / f"GeoHarvest-{tag()}-windows.zip"
    archive.unlink(missing_ok=True)
    readme = (ROOT / "installer" / "READ ME FIRST.txt").read_text("utf-8")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(setup.rglob("*")):
            if path.is_file():  # payload.zip is compressed already
                bundle.write(path, path.relative_to(setup), zipfile.ZIP_STORED
                             if path.name == "payload.zip" else zipfile.ZIP_DEFLATED)
        bundle.writestr("READ ME FIRST.txt", readme.replace("\n", "\r\n"))
        # The license texts, readable without installing
        legal = [folder / "LICENSE.txt", folder / "THIRD-PARTY-NOTICES.md",
                 *sorted(p for p in (folder / "licenses").rglob("*") if p.is_file())]
        for path in legal:
            bundle.write(path, path.relative_to(folder))
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
