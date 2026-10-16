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


def main() -> int:
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
