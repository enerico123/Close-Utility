"""
startup_manager.py
Lecture et modification de la clé de démarrage Windows.
Cible : HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
Pas besoin de droits admin — scope utilisateur courant uniquement.
"""

import winreg
import re
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
    # ex: Update.exe --processStart Discord.exe
    match = re.search(r'--processStart\s+(\S+\.exe)', value, re.IGNORECASE)
    if match:
        return match.group(1).lower()

    # Chemin entre guillemets : "C:\path with spaces\app.exe" args...
    match = re.match(r'"([^"]+\.exe)"', value, re.IGNORECASE)
    if match:
        return Path(match.group(1)).name.lower()

    # Chemin sans guillemets : on cherche le premier token finissant par .exe
    # en recollant depuis le début pour gérer les espaces dans le chemin
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
        ex: {"Discord": '"C:\\...\\Update.exe" --processStart Discord.exe'}
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
    Utile pour faire le lien entre un process psutil et une entrée registre.

    ex: {"discord.exe": "Discord", "steam.exe": "Steam"}

    Note : si un exe n'est pas parsable il est ignoré avec un warning.
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


def remove_from_startup(entry_name: str) -> bool:
    """
    Supprime une entrée du démarrage automatique.

    Args:
        entry_name: le nom de l'entrée registre (pas le nom de l'exe)
                    ex: "Discord", "Steam"

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
    mapping = get_startup_executables()
    for exe, reg_name in mapping.items():
        print(f"  {exe}  →  {reg_name}")