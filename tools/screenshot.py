"""Open the app, show each page and save a screenshot of it to docs/screenshots/.

    python tools/screenshot.py                 # every page
    python tools/screenshot.py search leads    # just these
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def main() -> None:
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    from app.core import db
    from app.ui import theme
    from app.ui.main_window import NAV_ITEMS, SETTINGS_ITEM, MainWindow

    db.init()
    theme.apply_preferences()
    app.setStyleSheet(theme.stylesheet())
    window = MainWindow()
    window.resize(1360, 860)
    window.show()

    pages = sys.argv[1:] or [item[0] for item in NAV_ITEMS + [SETTINGS_ITEM]]
    out = ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)

    def shoot(index: int = 0) -> None:
        if index >= len(pages):
            app.quit()
            return
        window.show_page(pages[index])
        QTimer.singleShot(400, lambda: (window.grab().save(str(out / f"{pages[index]}.png")),
                                        shoot(index + 1)))

    QTimer.singleShot(600, shoot)
    app.exec()


if __name__ == "__main__":
    main()
