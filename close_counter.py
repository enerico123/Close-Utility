"""
close_counter.py
Surveille les process en cours via psutil et détecte leurs fermetures.
Maintient un compteur par exe — déclenche un callback quand le seuil est atteint.
"""

import psutil
import time
from collections import defaultdict
from typing import Callable


# Exes trop génériques pour être trackés de façon fiable
AMBIGUOUS_EXES = {
    "update.exe",
    "install.exe",
    "setup.exe",
    "helper.exe",
    "launcher.exe",
    "service.exe",
    "host.exe",
    "agent.exe",
}

CLOSE_THRESHOLD = 1  # Nombre de fermetures avant de déclencher le popup


class CloseCounter:
    """
    Surveille les process qui sont dans le registre de démarrage.
    Quand un process suivi se ferme N fois, appelle on_threshold_reached.

    Usage :
        counter = CloseCounter(
            startup_exes={"discord.exe", "steam.exe", ...},
            on_threshold_reached=lambda exe, reg_name: ...,
            ignore_list={"steam.exe"},   # exes déjà ignorés par l'utilisateur
        )
        counter.run()   # boucle bloquante — lancer dans un thread
    """

    def __init__(
        self,
        startup_exes: dict[str, str],           # {exe_name: registry_entry_name}
        on_threshold_reached: Callable[[str, str], None],  # (exe_name, reg_name)
        ignore_list: set[str] | None = None,
        poll_interval: float = 2.0,
        threshold: int = CLOSE_THRESHOLD,
    ):
        self.startup_exes = startup_exes
        self.on_threshold_reached = on_threshold_reached
        self.ignore_list: set[str] = ignore_list or set()
        self.poll_interval = poll_interval
        self.threshold = threshold

        # {exe_name: set of pids actuellement vivants}
        self._live_pids: dict[str, set[int]] = defaultdict(set)
        # {exe_name: nombre de fermetures détectées}
        self._close_counts: dict[str, int] = defaultdict(int)
        # exes pour lesquels le popup a déjà été affiché (évite les doublons)
        self._triggered: set[str] = set()

        self._running = False

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def run(self):
        """Boucle de surveillance — bloquante, à lancer dans un thread."""
        self._running = True
        print("[CloseCounter] Démarrage de la surveillance.")

        # Snapshot initial — on considère tout ce qui tourne déjà comme "connu"
        self._live_pids = self._snapshot_live_pids()

        while self._running:
            time.sleep(self.poll_interval)
            self._tick()

    def stop(self):
        self._running = False
        print("[CloseCounter] Arrêt de la surveillance.")

    # ------------------------------------------------------------------
    # Logique interne
    # ------------------------------------------------------------------

    def _snapshot_live_pids(self) -> dict[str, set[int]]:
        """
        Retourne {exe_name: {pids}} pour tous les process suivis actuellement actifs.
        On ne snapshote que les exes présents dans startup_exes.
        """
        live: dict[str, set[int]] = defaultdict(set)
        tracked = set(self.startup_exes.keys()) - AMBIGUOUS_EXES - self.ignore_list

        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    name = proc.info["name"].lower()
                    if name in tracked:
                        live[name].add(proc.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            print(f"[CloseCounter] Erreur snapshot : {e}")

        return live

    def _tick(self):
        """
        Compare le snapshot précédent avec l'état actuel.
        Pour chaque pid disparu → incrémente le compteur de l'exe.
        """
        new_snapshot = self._snapshot_live_pids()

        for exe_name, old_pids in self._live_pids.items():
            new_pids = new_snapshot.get(exe_name, set())
            closed_pids = old_pids - new_pids  # pids qui existaient et n'existent plus

            if closed_pids:
                self._close_counts[exe_name] += len(closed_pids)
                count = self._close_counts[exe_name]
                reg_name = self.startup_exes.get(exe_name, exe_name)
                print(
                    f"[CloseCounter] {exe_name} fermé "
                    f"({len(closed_pids)} instance(s)) — total : {count}/{self.threshold}"
                )

                if count >= self.threshold and exe_name not in self._triggered:
                    self._triggered.add(exe_name)
                    print(f"[CloseCounter] Seuil atteint pour '{exe_name}' → popup")
                    self.on_threshold_reached(exe_name, reg_name)

        self._live_pids = new_snapshot

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def update_startup_exes(self, startup_exes: dict[str, str]):
        """Met à jour la liste des exes surveillés (ex: après modif du registre)."""
        self.startup_exes = startup_exes

    def add_to_ignore(self, exe_name: str):
        """Ajoute un exe à la liste d'ignorés (choix 'Non + ne plus afficher')."""
        self.ignore_list.add(exe_name.lower())
        # On reset son compteur pour éviter un re-trigger fantôme
        self._close_counts.pop(exe_name.lower(), None)
        self._triggered.discard(exe_name.lower())

    def reset_counter(self, exe_name: str):
        """Remet le compteur à zéro pour un exe donné."""
        self._close_counts.pop(exe_name.lower(), None)
        self._triggered.discard(exe_name.lower())

    def get_counts(self) -> dict[str, int]:
        """Retourne une copie des compteurs actuels — utile pour debug."""
        return dict(self._close_counts)


# ---------------------------------------------------------------------------
# Test rapide — python close_counter.py
# Ferme une app qui est dans ton registre de démarrage pour voir le log.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from startup_manager import get_startup_executables

    startup = get_startup_executables()
    print(f"[Test] {len(startup)} apps surveillées : {list(startup.keys())}\n")

    def on_trigger(exe_name: str, reg_name: str):
        print(f"\n>>> POPUP : Voulez-vous retirer '{reg_name}' ({exe_name}) du démarrage ? <<<\n")

    counter = CloseCounter(
        startup_exes=startup,
        on_threshold_reached=on_trigger,
        threshold=CLOSE_THRESHOLD,
    )

    try:
        counter.run()
    except KeyboardInterrupt:
        counter.stop()
        print("\nCounts finaux :", counter.get_counts())