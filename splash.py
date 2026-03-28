"""
splash.py
Petit écran de démarrage affiché 2.5 secondes au lancement.
Disparaît tout seul et laisse place à l'icône system tray.
"""

import tkinter as tk
from tkinter import ttk


def show_splash(duration_ms: int = 2500):
    """
    Affiche un splash screen pendant duration_ms millisecondes.
    Bloquant — à appeler avant de démarrer la boucle principale.
    """
    root = tk.Tk()
    root.overrideredirect(True)   # Pas de barre de titre
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.95)
    root.configure(bg="#1e1b2e")

    # Dimensions et centrage
    w, h = 340, 160
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Contenu
    frame = tk.Frame(root, bg="#1e1b2e", padx=30, pady=20)
    frame.pack(fill=tk.BOTH, expand=True)

    icon_label = tk.Label(
        frame,
        text="🚀",
        font=("Segoe UI", 32),
        bg="#1e1b2e",
        fg="white",
    )
    icon_label.pack()

    title_label = tk.Label(
        frame,
        text="Close Utility",
        font=("Segoe UI", 16, "bold"),
        bg="#1e1b2e",
        fg="white",
    )
    title_label.pack(pady=(6, 2))

    sub_label = tk.Label(
        frame,
        text="Démarrage en arrière-plan...",
        font=("Segoe UI", 9),
        bg="#1e1b2e",
        fg="#9d8ec7",
    )
    sub_label.pack()

    # Fermeture automatique
    root.after(duration_ms, root.destroy)
    root.mainloop()