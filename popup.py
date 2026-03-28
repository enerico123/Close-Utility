"""
popup.py
Affiche un popup natif Windows demandant si l'utilisateur veut retirer
une application du démarrage automatique.

Doit être appelé depuis le thread principal (contrainte tkinter).
On utilise une queue pour recevoir les demandes depuis le thread watcher.
"""

import tkinter as tk
from tkinter import ttk
from queue import Queue, Empty
from typing import Callable
import threading


class PopupRequest:
    """Représente une demande d'affichage de popup."""
    def __init__(self, exe_name: str, reg_name: str):
        self.exe_name = exe_name
        self.reg_name = reg_name


class PopupManager:
    """
    Gère l'affichage des popups dans le thread principal tkinter.

    Architecture :
        - Le watcher (thread secondaire) appelle request_popup()
        - Le thread principal tkinter poll la queue et affiche les popups
        - Les callbacks on_yes / on_no sont appelés dans le thread principal

    Usage :
        manager = PopupManager(
            on_yes=lambda exe, reg: startup_manager.remove_from_startup(reg),
            on_no=lambda exe, reg: counter.add_to_ignore(exe),
        )
        manager.start_loop()   # bloquant — à appeler depuis le thread principal
    """

    def __init__(
        self,
        on_yes: Callable[[str, str], None],  # (exe_name, reg_name)
        on_no: Callable[[str, str], None],
    ):
        self.on_yes = on_yes
        self.on_no = on_no
        self._queue: Queue[PopupRequest] = Queue()
        self._root: tk.Tk | None = None
        self._popup_open = False  # Un seul popup à la fois

    # ------------------------------------------------------------------
    # API publique — thread-safe
    # ------------------------------------------------------------------

    def request_popup(self, exe_name: str, reg_name: str):
        """
        Enqueue une demande de popup. Thread-safe.
        Peut être appelé depuis n'importe quel thread.
        """
        self._queue.put(PopupRequest(exe_name, reg_name))

    def start_loop(self):
        """
        Initialise tkinter et démarre la boucle principale.
        Bloquant — à appeler depuis le thread principal.
        """
        self._root = tk.Tk()
        self._root.withdraw()  # Fenêtre principale invisible
        self._root.title("Close Utility")

        # On poll la queue toutes les 500ms
        self._poll()
        self._root.mainloop()

    def stop(self):
        if self._root:
            self._root.quit()

    # ------------------------------------------------------------------
    # Logique interne
    # ------------------------------------------------------------------

    def _poll(self):
        """Vérifie la queue et affiche un popup si nécessaire."""
        if not self._popup_open:
            try:
                req = self._queue.get_nowait()
                self._popup_open = True
                self._show_popup(req)
            except Empty:
                pass

        if self._root:
            self._root.after(500, self._poll)

    def _show_popup(self, req: PopupRequest):
        """Crée et affiche la fenêtre de popup."""
        win = tk.Toplevel(self._root)
        win.title("Close Utility")
        win.resizable(False, False)
        win.attributes("-topmost", True)   # Toujours au premier plan
        win.protocol("WM_DELETE_WINDOW", lambda: self._on_dismiss(win, req))

        # Centrer sur l'écran
        win.update_idletasks()
        w, h = 420, 200
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

        # --- Layout ---
        frame = ttk.Frame(win, padding=24)
        frame.pack(fill=tk.BOTH, expand=True)

        # Icône + titre
        title_frame = ttk.Frame(frame)
        title_frame.pack(fill=tk.X, pady=(0, 12))

        icon_label = ttk.Label(title_frame, text="🚀", font=("Segoe UI", 22))
        icon_label.pack(side=tk.LEFT, padx=(0, 10))

        title_label = ttk.Label(
            title_frame,
            text="Close Utility",
            font=("Segoe UI", 13, "bold"),
        )
        title_label.pack(side=tk.LEFT, anchor="s", pady=(0, 2))

        # Message
        msg = (
            f"Vous avez fermé {req.reg_name} plusieurs fois.\n"
            f"Voulez-vous le retirer du démarrage automatique ?"
        )
        msg_label = ttk.Label(
            frame,
            text=msg,
            font=("Segoe UI", 10),
            wraplength=370,
            justify=tk.LEFT,
        )
        msg_label.pack(fill=tk.X, pady=(0, 20))

        # Boutons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        # "Ne plus afficher" (checkbox) à gauche
        ignore_var = tk.BooleanVar(value=False)
        ignore_check = ttk.Checkbutton(
            btn_frame,
            text="Ne plus afficher pour cette app",
            variable=ignore_var,
        )
        ignore_check.pack(side=tk.LEFT)

        # Oui / Non à droite
        btn_no = ttk.Button(
            btn_frame,
            text="Non",
            width=8,
            command=lambda: self._on_no(win, req, ignore_var.get()),
        )
        btn_no.pack(side=tk.RIGHT, padx=(8, 0))

        btn_yes = ttk.Button(
            btn_frame,
            text="Oui",
            width=8,
            command=lambda: self._on_yes(win, req),
        )
        btn_yes.pack(side=tk.RIGHT)

        # Focus sur "Oui" par défaut
        btn_yes.focus_set()
        win.bind("<Return>", lambda e: self._on_yes(win, req))
        win.bind("<Escape>", lambda e: self._on_dismiss(win, req))

    def _on_yes(self, win: tk.Toplevel, req: PopupRequest):
        print(f"[Popup] Oui → retirer '{req.reg_name}' du démarrage")
        self.on_yes(req.exe_name, req.reg_name)
        self._close_popup(win)

    def _on_no(self, win: tk.Toplevel, req: PopupRequest, ignore: bool):
        if ignore:
            print(f"[Popup] Non + ignorer → '{req.exe_name}' ne sera plus demandé")
        else:
            print(f"[Popup] Non → '{req.reg_name}' conservé au démarrage")
        self.on_no(req.exe_name, req.reg_name, ignore)
        self._close_popup(win)

    def _on_dismiss(self, win: tk.Toplevel, req: PopupRequest):
        """Fermeture via la croix = même effet que Non sans cocher ignore."""
        print(f"[Popup] Fermé via croix → '{req.reg_name}' conservé")
        self.on_no(req.exe_name, req.reg_name, False)
        self._close_popup(win)

    def _close_popup(self, win: tk.Toplevel):
        win.destroy()
        self._popup_open = False


# ---------------------------------------------------------------------------
# Test rapide — python popup.py
# Affiche un popup de démo sans lancer le watcher
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    def on_yes(exe: str, reg: str):
        print(f"[Test] on_yes appelé : exe={exe}, reg={reg}")

    def on_no(exe: str, reg: str, ignore: bool):
        print(f"[Test] on_no appelé : exe={exe}, reg={reg}, ignore={ignore}")

    manager = PopupManager(on_yes=on_yes, on_no=on_no)

    # Simule une demande depuis un thread watcher après 1 seconde
    def _simulate():
        import time
        time.sleep(1)
        manager.request_popup("steam.exe", "Steam")
        time.sleep(4)
        manager.request_popup("discord.exe", "Discord")

    threading.Thread(target=_simulate, daemon=True).start()
    manager.start_loop()