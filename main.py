"""
main.py
Point d'entrée de Close Utility.

Démarre le watcher dans un thread secondaire et la boucle tkinter
dans le thread principal (contrainte tkinter sur Windows).

Lancement :
    python main.py
"""

import threading
import sys
import json
import os
from pathlib import Path

from startup_manager import get_startup_executables, remove_from_startup, register_self
from close_counter import CloseCounter
from popup import PopupManager
from tray import TrayIcon
from splash import show_splash
import tkinter as tk


# ---------------------------------------------------------------------------
# Persistance de la liste d'ignorés
# ---------------------------------------------------------------------------

IGNORE_FILE = Path(__file__).parent / "ignore_list.json"


def load_ignore_list() -> set[str]:
    if IGNORE_FILE.exists():
        try:
            content = IGNORE_FILE.read_text(encoding="utf-8").strip()
            if not content:
                return set()
            data = json.loads(content)
            return set(data)
        except Exception as e:
            print(f"[Main] Erreur lecture ignore_list.json : {e}")
    return set()


def save_ignore_list(ignore_list: set[str]):
    try:
        IGNORE_FILE.write_text(
            json.dumps(sorted(ignore_list), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[Main] Erreur sauvegarde ignore_list.json : {e}")


# ---------------------------------------------------------------------------
# App principale
# ---------------------------------------------------------------------------

class CloseUtility:
    def __init__(self):
        self.ignore_list = load_ignore_list()
        self.startup_exes = get_startup_executables()

        print(f"[Main] {len(self.startup_exes)} apps surveillées.")
        print(f"[Main] {len(self.ignore_list)} apps ignorées : {self.ignore_list or 'aucune'}")

        # Auto-enregistrement au démarrage Windows
        register_self()

        # Icône system tray
        self.tray = TrayIcon(
            on_quit=self._on_quit_requested,
            get_stats=lambda: (len(self.startup_exes), len(self.ignore_list)),
        )

        self.popup_manager = PopupManager(
            on_yes=self._on_yes,
            on_no=self._on_no,
        )

        self.counter = CloseCounter(
            startup_exes=self.startup_exes,
            on_threshold_reached=self._on_threshold,
            ignore_list=self.ignore_list,
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_threshold(self, exe_name: str, reg_name: str):
        """Appelé par le watcher quand une app a été fermée 3 fois."""
        self.popup_manager.request_popup(exe_name, reg_name)

    def _on_yes(self, exe_name: str, reg_name: str):
        """L'utilisateur veut retirer l'app du démarrage."""
        success = remove_from_startup(reg_name)
        if success:
            # Refresh du mapping registre — l'entrée n'existe plus
            self.startup_exes = get_startup_executables()
            self.counter.update_startup_exes(self.startup_exes)
            print(f"[Main] '{reg_name}' retiré du démarrage avec succès.")
        else:
            print(f"[Main] Échec suppression de '{reg_name}'.")

    def _on_no(self, exe_name: str, reg_name: str, ignore: bool):
        """L'utilisateur ne veut pas retirer l'app — éventuellement l'ignorer."""
        if ignore:
            self.ignore_list.add(exe_name)
            self.counter.add_to_ignore(exe_name)
            save_ignore_list(self.ignore_list)
            print(f"[Main] '{exe_name}' ajouté à la liste d'ignorés.")
        else:
            # Pas d'ignore — on reset le compteur pour pouvoir re-demander plus tard
            self.counter.reset_counter(exe_name)
            print(f"[Main] Compteur de '{exe_name}' remis à zéro.")

    def _on_quit_requested(self):
        """Appelé depuis le menu Quitter de la system tray."""
        print("[Main] Arrêt de Close Utility.")
        self.counter.stop()
        if self.popup_manager._root:
            self.popup_manager._root.quit()

    # ------------------------------------------------------------------
    # Démarrage
    # ------------------------------------------------------------------

    def run(self):
        show_splash()
        self.tray.run_in_thread()
        print("[Main] Icône system tray active.")

        # Thread watcher — tourne en daemon (s'arrête avec le process principal)
        watcher_thread = threading.Thread(
            target=self.counter.run,
            daemon=True,
            name="CloseUtility-Watcher",
        )
        watcher_thread.start()
        print("[Main] Watcher démarré. Close Utility est actif.")

        # Donne la ref tkinter au tray une fois la boucle prête
        self.popup_manager._root = tk.Tk()
        self.popup_manager._root.withdraw()
        self.tray.set_tk_root(self.popup_manager._root)
        self.popup_manager._poll()

        # Boucle tkinter — bloquante, dans le thread principal
        try:
            self.popup_manager._root.mainloop()
        except KeyboardInterrupt:
            print("\n[Main] Arrêt demandé.")
            self.counter.stop()
            sys.exit(0)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = CloseUtility()
    app.run()