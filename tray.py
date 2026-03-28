"""
tray.py
Icône dans la zone de notification Windows (system tray).
Fournit un menu contextuel pour quitter Close Utility proprement.

Doit tourner dans son propre thread — pystray a sa propre boucle.
"""

import pystray
from pystray import MenuItem as Item
from PIL import Image, ImageDraw
import threading


def _create_icon_image(size: int = 64) -> Image.Image:
    """
    Génère une icône simple en mémoire — un cercle violet avec un éclair.
    Pas besoin de fichier .ico externe.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fond cercle violet
    margin = 2
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(99, 74, 183, 255),   # violet — même teinte que le diagramme
    )

    # Éclair blanc simplifié (polygone)
    cx = size // 2
    s = size
    lightning = [
        (cx - s * 0.12, s * 0.22),   # haut gauche
        (cx + s * 0.08, s * 0.22),   # haut droite
        (cx - s * 0.04, s * 0.50),   # milieu gauche
        (cx + s * 0.14, s * 0.50),   # milieu droite
        (cx - s * 0.08, s * 0.78),   # bas gauche
        (cx + s * 0.04, s * 0.48),   # retour milieu
        (cx - s * 0.06, s * 0.48),   # retour milieu gauche
    ]
    draw.polygon(lightning, fill=(255, 255, 255, 230))

    return img


class TrayIcon:
    """
    Gère l'icône dans la zone de notification.

    Usage :
        tray = TrayIcon(on_quit=lambda: app.stop())
        tray.run_in_thread()   # non bloquant
    """

    def __init__(self, on_quit: callable):
        self.on_quit = on_quit
        self._icon: pystray.Icon | None = None

    def run_in_thread(self):
        """Lance la system tray dans un thread daemon."""
        thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="CloseUtility-Tray",
        )
        thread.start()

    def _run(self):
        image = _create_icon_image()

        menu = pystray.Menu(
            Item("Close Utility — actif", None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Quitter", self._on_quit),
        )

        self._icon = pystray.Icon(
            name="CloseUtility",
            icon=image,
            title="Close Utility",
            menu=menu,
        )

        self._icon.run()

    def _on_quit(self, icon: pystray.Icon, item):
        print("[Tray] Quitter demandé.")
        icon.stop()
        self.on_quit()

    def stop(self):
        if self._icon:
            self._icon.stop()