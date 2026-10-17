"""GeoHarvest launcher."""
from __future__ import annotations

import sys
import traceback
from datetime import datetime


def report(message: str) -> None:
    """Show a message even in a windowed build, where stdout may not exist."""
    try:
        print(message)
    except Exception:
        pass
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "GeoHarvest", message)
        del app
    except Exception:
        pass


def install_crash_guard() -> None:
    """Log an unhandled error and carry on, instead of PyQt aborting the process.

    A scrape in progress keeps every lead it already saved, so losing one action
    is far better than the window vanishing.
    """
    from app import config

    def hook(kind, value, trace) -> None:
        details = "".join(traceback.format_exception(kind, value, trace))
        try:
            print(details)
        except Exception:
            pass
        try:
            config.ensure_dirs()
            with (config.LOGS_DIR / "crash.log").open("a", encoding="utf-8") as log:
                log.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---\n{details}")
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QApplication

            from app.ui.widgets.common import toast

            window = QApplication.activeWindow()
            if window is not None:
                toast(window, f"Something went wrong: {type(value).__name__}: {value}",
                      "error", 8000)
        except Exception:
            pass

    sys.excepthook = hook


def self_test(out: str) -> int:
    """GeoHarvest.exe --self-test RESULT.json: prove a build works, without a window.

    Loads every bundled library, runs one real Google Maps search and exports it to
    Excel. The build script and CI run it, because a missing hidden import only
    shows up in the packaged app.
    """
    import json
    import tempfile
    from pathlib import Path

    result: dict = {"ok": False}
    try:
        import anthropic
        from PyQt6.QtWidgets import QApplication  # noqa: F401

        from app.core import ai, credentials, enrich, exporter, geo, scraper  # noqa: F401
        from app.services import updater  # noqa: F401

        # The build leaves out the Claude SDK's optional extras: send a real request through
        # it (to a closed local port) to prove it still builds and sends one without them
        claude = anthropic.Anthropic(api_key="test", base_url="http://127.0.0.1:9", max_retries=0)
        try:
            claude.beta.messages.create(
                model="claude-opus-5-5", max_tokens=16,
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                messages=[{"role": "user", "content": "test"}])
        except anthropic.APIConnectionError:
            pass

        # The live search is reported, not required: a build server's address may be one
        # Google refuses, and that says nothing about whether the build is sound
        leads = [{"place_id": "x", "name": "Sample", "rating": 4.5}]
        try:
            client = scraper.MapsClient()
            leads = next(scraper.search(client, "dentist in Dubai, United Arab Emirates"))
            client.close()
            result["search"] = f"{len(leads)} leads"
        except Exception as error:  # noqa: BLE001
            result["search"] = f"skipped: {type(error).__name__}: {error}"
        exporter.export(leads, Path(tempfile.gettempdir()) / "geoharvest-self-test.xlsx")
        result.update(ok=True, countries=len(geo.countries()))
    except Exception as error:  # noqa: BLE001 - the point is to report it
        result["error"] = f"{type(error).__name__}: {error}"
    Path(out).write_text(json.dumps(result), encoding="utf-8")
    return 0 if result["ok"] else 1


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        return self_test(sys.argv[2])
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    if sys.platform == "win32":
        # Own taskbar identity, so it shows the GeoHarvest icon rather than Python's
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GeoHarvest.App")
        except (AttributeError, OSError):
            pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.RoundPreferFloor)
    app = QApplication(sys.argv)
    app.setApplicationName("GeoHarvest")
    app.setOrganizationName("GeoHarvest")
    # Fusion is the only style QSS can fully restyle
    app.setStyle("Fusion")

    from app import config
    from app.core import db

    config.ensure_dirs()
    install_crash_guard()
    db.init()
    from app.core import search

    search.recover_interrupted()

    for name in ("assets/icon.ico", "assets/logo-256.png"):
        path = config.resource_path(name)
        if path.exists():
            app.setWindowIcon(QIcon(str(path)))
            break

    from app.ui import theme

    theme.apply_preferences()
    app.setStyleSheet(theme.stylesheet())

    from app.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    window.check_for_update_soon()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - never fail silently
        details = traceback.format_exc()
        try:
            from app import config

            config.ensure_dirs()
            (config.LOGS_DIR / "crash.log").write_text(details, encoding="utf-8")
        except Exception:
            pass
        report(f"GeoHarvest could not start.\n\n{type(error).__name__}: {error}")
        sys.exit(1)
