"""
startup_manager.py
Lecture et modification de la clé de démarrage Windows.
Cible : HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
Pas besoin de droits admin — scope utilisateur courant uniquement.
"""

import winreg
import re
import sys
from pathlib import Path


STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _parse_exe_from_value(value: str) -> str:
    """
    Extrait le nom de l'executable final depuis une valeur de registre.

    Gère les cas :
      - "C:\\path with spaces\\app.exe" --args
      - C:\\path\\without\\quotes\\app.exe --args
      - "C:\\...\\Update.exe" --processStart Discord.exe   ← launcher pattern

    Returns:
        Nom de l'exe en minuscules, ex: "discord.exe"
        Retourne "" si non parsable.
    """
    value = value.strip()

    # Cas --processStart : le vrai process est l'argument qui suit
    match = re.search(r'--processStart\s+(\S+\.exe)', value, re.IGNORECASE)
    if match:
        return match.group(1).lower()

    # Chemin entre guillemets
    match = re.match(r'"([^"]+\.exe)"', value, re.IGNORECASE)
    if match:
        return Path(match.group(1)).name.lower()

    # Chemin sans guillemets
    tokens = value.split()
    for i, token in enumerate(tokens):
        if token.lower().endswith('.exe'):
            candidate = ' '.join(tokens[:i + 1])
            return Path(candidate).name.lower()

    return ""


def get_startup_entries() -> dict[str, str]:
    """
    Retourne toutes les entrées de démarrage de l'utilisateur courant.

    Returns:
        dict {nom_entrée: valeur_brute_registre}
    """
    entries = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_READ) as key:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                    entries[name] = value
                    index += 1
                except OSError:
                    break
    except OSError as e:
        print(f"[StartupManager] Impossible d'ouvrir la clé registre : {e}")

    return entries


def get_startup_executables() -> dict[str, str]:
    """
    Retourne un mapping {nom_exe_normalisé: nom_entrée_registre}.
    ex: {"discord.exe": "Discord", "steam.exe": "Steam"}
    """
    entries = get_startup_entries()
    result = {}

    for name, path in entries.items():
        exe = _parse_exe_from_value(path)
        if exe:
            result[exe] = name
        else:
            print(f"[StartupManager] Warning — impossible de parser l'exe pour '{name}' : {path!r}")

    return result


def add_to_startup(entry_name: str, cmd: str) -> bool:
    """
    Ajoute une entrée au démarrage automatique.

    Args:
        entry_name: nom de l'entrée registre, ex: "CloseUtility"
        cmd:        commande complète, ex: '"C:\\...\\pythonw.exe" "C:\\...\\main.py"'

    Returns:
        True si ajouté avec succès, False sinon.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, entry_name, 0, winreg.REG_SZ, cmd)
            print(f"[StartupManager] '{entry_name}' ajouté au démarrage.")
            return True
    except OSError as e:
        print(f"[StartupManager] Erreur lors de l'ajout de '{entry_name}' : {e}")
        return False


def register_self() -> bool:
    """
    Ajoute Close Utility lui-même au démarrage Windows.
    Utilise pythonw.exe pour tourner sans fenêtre console.

    Returns:
        True si déjà présent ou ajouté avec succès.
    """
    entry_name = "CloseUtility"

    # Déjà présent ?
    if entry_name in get_startup_entries():
        print("[StartupManager] Close Utility est déjà dans le démarrage.")
        return True

    # pythonw.exe = Python sans fenêtre console noire au démarrage
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)  # fallback

    script_path = Path(__file__).parent.resolve() / "main.py"
    cmd = f'"{pythonw}" "{script_path}"'

    print(f"[StartupManager] Enregistrement : {cmd}")
    return add_to_startup(entry_name, cmd)


def remove_from_startup(entry_name: str) -> bool:
    """
    Supprime une entrée du démarrage automatique.

    Args:
        entry_name: le nom de l'entrée registre, ex: "Discord", "Steam"

    Returns:
        True si supprimé avec succès, False sinon.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, entry_name)
            print(f"[StartupManager] '{entry_name}' retiré du démarrage.")
            return True
    except FileNotFoundError:
        print(f"[StartupManager] '{entry_name}' introuvable dans le registre.")
        return False
    except OSError as e:
        print(f"[StartupManager] Erreur lors de la suppression de '{entry_name}' : {e}")
        return False


def is_in_startup(exe_name: str) -> bool:
    """
    Vérifie si un executable est dans les entrées de démarrage.

    Args:
        exe_name: nom de l'exe normalisé en minuscules, ex: "discord.exe"
    """
    return exe_name.lower() in get_startup_executables()


# ---------------------------------------------------------------------------
# Test rapide — python startup_manager.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Entrées de démarrage (HKCU) ===")
    entries = get_startup_entries()
    if not entries:
        print("  (aucune entrée trouvée)")
    for name, path in entries.items():
        print(f"  [{name}]  →  {path}")

    print("\n=== Mapping exe → nom registre ===")
    for exe, reg_name in get_startup_executables().items():
        print(f"  {exe}  →  {reg_name}")