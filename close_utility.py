"""Close Utility — Détecte la fermeture répétée d'applications au démarrage
et propose de les retirer du démarrage automatique Windows.

Fonctionnement :
  - L'application tourne en arrière-plan avec une icône dans la zone de notification.
  - Elle surveille les applications configurées pour démarrer automatiquement
    (registre Windows).
  - Quand une de ces applications est fermée 3 fois, une fenêtre demande :
      « Voulez-vous retirer cette application du démarrage ? »
      Oui  → retire l'entrée du registre (démarrage Windows)
      Non  → ne plus poser la question pour cette application
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Set

# ---------------------------------------------------------------------------
# Optional Windows-only imports — guarded so unit tests run on any platform
# ---------------------------------------------------------------------------
try:
    import winreg  # type: ignore[import]

    _WINDOWS = True
except ImportError:  # pragma: no cover — non-Windows platforms
    winreg = None  # type: ignore[assignment]
    _WINDOWS = False

try:
    import psutil  # type: ignore[import]
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

try:
    import pystray  # type: ignore[import]
    from PIL import Image, ImageDraw  # type: ignore[import]

    _TRAY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TRAY_AVAILABLE = False

try:
    import tkinter as tk
    from tkinter import messagebox

    _TKINTER_AVAILABLE = True
except ImportError:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    _TKINTER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLOSE_THRESHOLD = 3  # nombre de fermetures avant d'afficher la popup

STATE_FILE = Path.home() / ".close_utility_state.json"

MONITOR_INTERVAL = 5  # secondes entre chaque vérification des processus

STARTUP_REGISTRY_KEYS = [
    (
        "HKCU",
        r"Software\Microsoft\Windows\CurrentVersion\Run",
    ),
    (
        "HKLM",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    ),
    (
        "HKLM",
        r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Run",
    ),
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State manager
# ---------------------------------------------------------------------------
class StateManager:
    """Persiste les compteurs de fermetures et les préférences utilisateur."""

    def __init__(self, state_file: Path = STATE_FILE) -> None:
        self._file = state_file
        self._data: dict = self._load()

    # ------------------------------------------------------------------
    def _load(self) -> dict:
        if self._file.exists():
            try:
                with open(self._file, encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    data.setdefault("close_counts", {})
                    data.setdefault("ignored", [])
                    return data
            except Exception as exc:  # noqa: BLE001
                logger.warning("Impossible de lire l'état persisté : %s", exc)
        return {"close_counts": {}, "ignored": []}

    def save(self) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.error("Impossible de sauvegarder l'état : %s", exc)

    # ------------------------------------------------------------------
    def get_close_count(self, exe_name: str) -> int:
        return self._data["close_counts"].get(exe_name.lower(), 0)

    def increment_close_count(self, exe_name: str) -> int:
        key = exe_name.lower()
        self._data["close_counts"][key] = self._data["close_counts"].get(key, 0) + 1
        self.save()
        return self._data["close_counts"][key]

    def reset_close_count(self, exe_name: str) -> None:
        self._data["close_counts"][exe_name.lower()] = 0
        self.save()

    def is_ignored(self, exe_name: str) -> bool:
        return exe_name.lower() in [e.lower() for e in self._data["ignored"]]

    def add_ignored(self, exe_name: str) -> None:
        key = exe_name.lower()
        if key not in [e.lower() for e in self._data["ignored"]]:
            self._data["ignored"].append(key)
        self.save()


# ---------------------------------------------------------------------------
# Startup apps reader (Windows registry)
# ---------------------------------------------------------------------------
class StartupAppsReader:
    """Lit les applications configurées pour démarrer automatiquement."""

    @staticmethod
    def _hive(hive_name: str):
        """Retourne le handle winreg correspondant au nom de ruche."""
        mapping = {
            "HKCU": winreg.HKEY_CURRENT_USER,
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
        }
        return mapping[hive_name]

    @classmethod
    def get_startup_apps(cls) -> Dict[str, dict]:
        """Retourne {exe_name_lower: app_info_dict}."""
        if not _WINDOWS or winreg is None:
            return {}

        apps: Dict[str, dict] = {}
        for hive_name, key_path in STARTUP_REGISTRY_KEYS:
            try:
                hive = cls._hive(hive_name)
                with winreg.OpenKey(hive, key_path) as key:
                    idx = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, idx)
                            exe_path = cls._extract_exe_path(value)
                            if exe_path:
                                exe_name = os.path.basename(exe_path).lower()
                                # Prefer HKCU over HKLM for the same executable
                                if exe_name not in apps:
                                    apps[exe_name] = {
                                        "display_name": name,
                                        "exe_path": exe_path,
                                        "command": value,
                                        "registry_key": key_path,
                                        "registry_hive": hive,
                                        "registry_name": name,
                                    }
                            idx += 1
                        except OSError:
                            break
            except OSError:
                pass  # Clé absente ou accès refusé
        return apps

    @staticmethod
    def _extract_exe_path(command: str) -> Optional[str]:
        """Extrait le chemin de l'exécutable d'une chaîne de commande."""
        command = command.strip()
        if not command:
            return None
        if command.startswith('"'):
            end = command.find('"', 1)
            if end > 0:
                return command[1:end]
        # For unquoted commands, try to find the end of the .exe path
        lower = command.lower()
        exe_pos = lower.find(".exe")
        if exe_pos != -1:
            return command[: exe_pos + 4]
        parts = command.split()
        if parts:
            return parts[0]
        return None

    @staticmethod
    def remove_from_startup(app_info: dict) -> bool:
        """Retire une application du registre de démarrage. Retourne True si réussi."""
        if not _WINDOWS or winreg is None:
            return False
        try:
            with winreg.OpenKey(
                app_info["registry_hive"],
                app_info["registry_key"],
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, app_info["registry_name"])
            return True
        except OSError as exc:
            logger.error("Impossible de retirer du démarrage : %s", exc)
            return False


# ---------------------------------------------------------------------------
# Process monitor
# ---------------------------------------------------------------------------
class ProcessMonitor:
    """Surveille les processus et détecte les fermetures d'applications au démarrage."""

    def __init__(
        self,
        state: StateManager,
        on_threshold_reached: Callable[[dict], None],
        interval: float = MONITOR_INTERVAL,
    ) -> None:
        self._state = state
        self._on_threshold = on_threshold_reached
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # exe_name -> set of PIDs vus lors du dernier tour
        self._prev_pids: Dict[str, Set[int]] = {}
        # exe_name -> app_info
        self._startup_apps: Dict[str, dict] = {}
        # Évite les popups en double pour la même app
        self._pending: Set[str] = set()

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="CloseUtility-Monitor")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    def _get_current_pids(self, startup_apps: Dict[str, dict]) -> Dict[str, Set[int]]:
        """Retourne {exe_name_lower: set_of_pids} pour les apps au démarrage."""
        if psutil is None:
            return {}
        current: Dict[str, Set[int]] = {}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name in startup_apps:
                    current.setdefault(name, set()).add(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return current

    def _loop(self) -> None:
        logger.info("Surveillance des processus démarrée.")
        while self._running:
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Erreur dans la boucle de surveillance : %s", exc)
            time.sleep(self._interval)
        logger.info("Surveillance des processus arrêtée.")

    def _tick(self) -> None:
        startup_apps = StartupAppsReader.get_startup_apps()
        current_pids = self._get_current_pids(startup_apps)

        # Détecte les fermetures : app qui avait des PIDs, n'en a plus
        for exe_name, prev in self._prev_pids.items():
            if not prev:
                continue
            if self._state.is_ignored(exe_name):
                continue
            if exe_name not in startup_apps:
                continue
            if exe_name in self._pending:
                continue

            now = current_pids.get(exe_name, set())
            if not now:
                count = self._state.increment_close_count(exe_name)
                logger.info(
                    "%s fermé (compteur = %d / %d)", exe_name, count, CLOSE_THRESHOLD
                )
                if count >= CLOSE_THRESHOLD:
                    self._pending.add(exe_name)
                    self._on_threshold(startup_apps[exe_name])

        self._prev_pids = current_pids

    def clear_pending(self, exe_name: str) -> None:
        """Appelé après traitement d'une popup pour autoriser une future détection."""
        self._pending.discard(exe_name.lower())


# ---------------------------------------------------------------------------
# Tray icon factory
# ---------------------------------------------------------------------------
def _build_tray_icon(on_quit: callable) -> "pystray.Icon":
    """Crée et retourne l'icône de la zone de notification."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill="#1565C0")
    # Lettre «C» stylisée
    draw.arc([12, 12, size - 12, size - 12], start=40, end=320, fill="white", width=8)

    menu = pystray.Menu(
        pystray.MenuItem("Close Utility", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", on_quit),
    )
    return pystray.Icon("close_utility", img, "Close Utility", menu)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class CloseUtilityApp:
    """Orchestre toutes les composantes de l'application."""

    def __init__(
        self,
        state: Optional[StateManager] = None,
        monitor: Optional[ProcessMonitor] = None,
    ) -> None:
        self._state = state or StateManager()
        self._popup_queue: queue.Queue[dict] = queue.Queue()
        self._running = False
        self._tray_icon: Optional["pystray.Icon"] = None

        self._monitor = monitor or ProcessMonitor(
            state=self._state,
            on_threshold_reached=self._queue_popup,
        )

        # Fenêtre Tk masquée (nécessaire pour les boîtes de dialogue)
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title("Close Utility")

    # ------------------------------------------------------------------
    def _queue_popup(self, app_info: dict) -> None:
        """Appelé depuis le thread moniteur — met la popup en file."""
        self._popup_queue.put(app_info)

    def _process_popup_queue(self) -> None:
        """Traite les popups en attente depuis le thread principal (Tk)."""
        try:
            while True:
                app_info = self._popup_queue.get_nowait()
                self._show_popup(app_info)
        except queue.Empty:
            pass
        finally:
            if self._running:
                self._root.after(200, self._process_popup_queue)

    def _show_popup(self, app_info: dict) -> None:
        """Affiche la boîte de dialogue et traite le choix de l'utilisateur."""
        exe_name = os.path.basename(app_info.get("exe_path", "")).lower() or app_info.get(
            "display_name", "?"
        ).lower()
        display = app_info.get("display_name", exe_name)

        msg = (
            f'L\'application "{display}" a été fermée {CLOSE_THRESHOLD} fois.\n\n'
            f"Voulez-vous la retirer du démarrage automatique ?"
        )
        answer = messagebox.askyesno(
            title="Close Utility",
            message=msg,
            parent=self._root,
        )

        if answer:
            ok = StartupAppsReader.remove_from_startup(app_info)
            if ok:
                messagebox.showinfo(
                    title="Close Utility",
                    message=f'"{display}" a été retiré du démarrage automatique.',
                    parent=self._root,
                )
            else:
                messagebox.showerror(
                    title="Close Utility",
                    message=(
                        f'Impossible de retirer "{display}" du démarrage automatique.\n'
                        "Essayez de relancer Close Utility en tant qu'administrateur."
                    ),
                    parent=self._root,
                )
        else:
            # L'utilisateur ne veut plus être questionné pour cette app
            self._state.add_ignored(exe_name)

        # Remet le compteur à zéro et libère l'entrée pendante
        self._state.reset_close_count(exe_name)
        self._monitor.clear_pending(exe_name)

    # ------------------------------------------------------------------
    def run(self) -> None:
        """Démarre l'application (bloque jusqu'à la fermeture)."""
        if not _WINDOWS:
            logger.error("Close Utility nécessite Windows.")
            sys.exit(1)

        self._running = True
        self._monitor.start()

        if _TRAY_AVAILABLE:
            self._tray_icon = _build_tray_icon(on_quit=self._quit)
            tray_thread = threading.Thread(
                target=self._tray_icon.run, daemon=True, name="CloseUtility-Tray"
            )
            tray_thread.start()
        else:
            logger.warning(
                "pystray / Pillow non disponible — pas d'icône dans la zone de notification."
            )

        self._root.after(200, self._process_popup_queue)
        logger.info("Close Utility démarré.")
        self._root.mainloop()

    def _quit(self, icon=None, item=None) -> None:
        """Arrête proprement l'application."""
        self._running = False
        self._monitor.stop()
        if self._tray_icon:
            self._tray_icon.stop()
        self._root.quit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    app = CloseUtilityApp()
    app.run()


if __name__ == "__main__":
    main()
