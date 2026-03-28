"""
tray.py
Icône dans la zone de notification Windows (system tray).
- Clic gauche / À propos → fenêtre moderne sans barre de titre
- Clic droit → menu Quitter
"""

import pystray
from pystray import MenuItem as Item
from PIL import Image, ImageDraw
import threading
import tkinter as tk


def _create_icon_image(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 2
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(99, 74, 183, 255),
    )
    cx = size // 2
    s = size
    lightning = [
        (cx - s * 0.12, s * 0.22),
        (cx + s * 0.08, s * 0.22),
        (cx - s * 0.04, s * 0.50),
        (cx + s * 0.14, s * 0.50),
        (cx - s * 0.08, s * 0.78),
        (cx + s * 0.04, s * 0.48),
        (cx - s * 0.06, s * 0.48),
    ]
    draw.polygon(lightning, fill=(255, 255, 255, 230))
    return img


def show_about(watched: int, ignored: int):
    """Fenêtre À propos — design sombre moderne, sans barre de titre Windows."""

    win = tk.Toplevel()
    win.overrideredirect(True)       # Supprime la barre de titre native
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.0)    # Démarre invisible pour le fade-in
    win.configure(bg="#0f0d1a")

    W, H = 360, 450
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = (sw - W) // 2
    y = (sh - H) // 2
    win.geometry(f"{W}x{H}+{x}+{y}")

    # --- Drag pour déplacer la fenêtre ---
    def start_drag(e):
        win._drag_x = e.x
        win._drag_y = e.y

    def do_drag(e):
        dx = e.x - win._drag_x
        dy = e.y - win._drag_y
        nx = win.winfo_x() + dx
        ny = win.winfo_y() + dy
        win.geometry(f"+{nx}+{ny}")

    # --- Canvas principal ---
    canvas = tk.Canvas(win, width=W, height=H, bg="#0f0d1a", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    canvas.bind("<ButtonPress-1>", start_drag)
    canvas.bind("<B1-Motion>", do_drag)

    # Bordure subtile violette
    canvas.create_rectangle(0, 0, W-1, H-1, outline="#2d1f5e", width=1)

    # Ligne déco en haut
    canvas.create_rectangle(0, 0, W, 3, fill="#6342c8", outline="")

    # Accent glow (simulé avec des rectangles superposés)
    for i, alpha_color in enumerate(["#1a0f3a", "#160d33", "#120b2b"]):
        canvas.create_oval(W//2 - 60 + i*5, 30 + i*5,
                           W//2 + 60 - i*5, 150 - i*5,
                           fill=alpha_color, outline="")

    # Cercle icône
    cx, cy, r = W // 2, 90, 38
    canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#1e1545", outline="#4a32a8", width=1)
    canvas.create_text(cx, cy, text="⚡", font=("Segoe UI Emoji", 26), fill="white")

    # Titre
    canvas.create_text(W//2, 150, text="Close Utility",
                       font=("Segoe UI", 18, "bold"), fill="white")

    # Version
    canvas.create_text(W//2, 174, text="v1.0.2",
                       font=("Segoe UI", 9), fill="#5a4a8a")

    # Séparateur
    canvas.create_line(40, 196, W-40, 196, fill="#1e1545", width=1)

    # Description
    desc = "Tourne en arrière-plan et surveille\ntes apps au démarrage de Windows.\n\nFerme une app → popup pour la retirer\nautomatiquement du démarrage."
    canvas.create_text(W//2, 248, text=desc,
                       font=("Segoe UI", 10), fill="#8b7ab8",
                       justify=tk.CENTER, width=280)

    # Séparateur
    canvas.create_line(40, 298, W-40, 298, fill="#1e1545", width=1)

    # Stats cards
    card_y = 320

    # Card surveillées
    canvas.create_rectangle(30, card_y, W//2 - 10, card_y + 56,
                             fill="#14102a", outline="#2a1f52", width=1)
    canvas.create_text(W//4 + 10, card_y + 16,
                       text=str(watched), font=("Segoe UI", 18, "bold"), fill="#7c5cbf")
    canvas.create_text(W//4 + 10, card_y + 38,
                       text="surveillées", font=("Segoe UI", 8), fill="#4a3a72")

    # Card ignorées
    canvas.create_rectangle(W//2 + 10, card_y, W - 30, card_y + 56,
                             fill="#14102a", outline="#2a1f52", width=1)
    canvas.create_text(W//4 * 3 - 10, card_y + 16,
                       text=str(ignored), font=("Segoe UI", 18, "bold"), fill="#c45bab")
    canvas.create_text(W//4 * 3 - 10, card_y + 38,
                       text="ignorées", font=("Segoe UI", 8), fill="#4a3a72")

    # Bouton Fermer
    btn_y = card_y + 72
    btn = canvas.create_rectangle(80, btn_y, W-80, btn_y + 36,
                                   fill="#1e1545", outline="#3d2a8a", width=1)
    btn_txt = canvas.create_text(W//2, btn_y + 18,
                                  text="Fermer", font=("Segoe UI", 10),
                                  fill="#8b7ab8")

    def on_close(e=None):
        # Fade out
        def fade(alpha=0.95):
            if alpha <= 0:
                win.destroy()
                return
            win.attributes("-alpha", alpha)
            win.after(16, lambda: fade(alpha - 0.08))
        fade()

    def btn_hover(e):
        canvas.itemconfig(btn, fill="#2d1f5e", outline="#6342c8")
        canvas.itemconfig(btn_txt, fill="white")
        canvas.configure(cursor="hand2")

    def btn_leave(e):
        canvas.itemconfig(btn, fill="#1e1545", outline="#3d2a8a")
        canvas.itemconfig(btn_txt, fill="#8b7ab8")
        canvas.configure(cursor="")

    canvas.tag_bind(btn, "<Enter>", btn_hover)
    canvas.tag_bind(btn_txt, "<Enter>", btn_hover)
    canvas.tag_bind(btn, "<Leave>", btn_leave)
    canvas.tag_bind(btn_txt, "<Leave>", btn_leave)
    canvas.tag_bind(btn, "<Button-1>", on_close)
    canvas.tag_bind(btn_txt, "<Button-1>", on_close)

    win.bind("<Escape>", on_close)

    # Croix de fermeture custom en haut à droite
    close_x = canvas.create_text(W - 20, 16, text="✕",
                                   font=("Segoe UI", 10), fill="#3d2a6a")
    canvas.tag_bind(close_x, "<Button-1>", on_close)
    canvas.tag_bind(close_x, "<Enter>",
                    lambda e: canvas.itemconfig(close_x, fill="white"))
    canvas.tag_bind(close_x, "<Leave>",
                    lambda e: canvas.itemconfig(close_x, fill="#3d2a6a"))

    # Fade-in
    def fade_in(alpha=0.0):
        if alpha >= 0.97:
            win.attributes("-alpha", 1.0)
            return
        win.attributes("-alpha", alpha)
        win.after(16, lambda: fade_in(alpha + 0.07))

    fade_in()
    return win


class TrayIcon:
    def __init__(self, on_quit: callable, get_stats: callable):
        self.on_quit = on_quit
        self.get_stats = get_stats
        self._icon: pystray.Icon | None = None
        self._tk_root: tk.Tk | None = None
        self._about_win: tk.Toplevel | None = None

    def set_tk_root(self, root: tk.Tk):
        self._tk_root = root

    def run_in_thread(self):
        thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="CloseUtility-Tray",
        )
        thread.start()

    def _run(self):
        image = _create_icon_image()

        menu = pystray.Menu(
            Item("À propos", self._on_left_click, default=True),
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

    def _on_left_click(self, icon=None, item=None):
        if self._tk_root:
            # Si déjà ouverte, on la met au premier plan
            if self._about_win and self._about_win.winfo_exists():
                self._tk_root.after(0, lambda: self._about_win.lift())
                return
            watched, ignored = self.get_stats()
            def open_about():
                self._about_win = show_about(watched, ignored)
            self._tk_root.after(0, open_about)

    def _on_quit(self, icon: pystray.Icon, item):
        print("[Tray] Quitter demandé.")
        icon.stop()
        self.on_quit()

    def stop(self):
        if self._icon:
            self._icon.stop()