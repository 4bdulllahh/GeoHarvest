"""Render assets/logo.svg to the PNG sizes and the Windows .ico the app uses.

Run after changing the logo:  python tools/make_icons.py
"""
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZES = [96, 128, 160, 192, 256]


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return image


def main() -> None:
    QGuiApplication([])
    renderer = QSvgRenderer(str(ASSETS / "logo.svg"))
    for size in SIZES:
        render(renderer, size).save(str(ASSETS / f"logo-{size}.png"))
    render(renderer, 512).save(str(ASSETS / "logo-512.png"))
    Image.open(ASSETS / "logo-512.png").save(
        ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                    (256, 256)])
    (ASSETS / "logo-512.png").unlink()


if __name__ == "__main__":
    main()
