# Close Utility (FULL IA)

> Marre de fermer une app et d'oublier de la retirer du démarrage Windows ? Close Utility s'en charge automatiquement.

## Comment ça marche

Close Utility tourne silencieusement en arrière-plan et surveille les applications qui se lancent au démarrage de Windows. Quand tu fermes la même app 3 fois, il te propose de la retirer du démarrage automatiquement.

```
Tu fermes Discord 3 fois
        ↓
┌─────────────────────────────────────────────┐
│  🚀 Close Utility                           │
│                                             │
│  Vous avez fermé Discord plusieurs fois.    │
│  Voulez-vous le retirer du démarrage ?      │
│                                             │
│  ☐ Ne plus afficher pour cette app          │
│                              [Oui]  [Non]   │
└─────────────────────────────────────────────┘
```

- **Oui** → l'app est retirée du registre de démarrage Windows
- **Non** → le compteur repart à zéro, il re-demandera dans 3 fermetures
- **Non + coché** → l'app est ignorée définitivement, plus jamais de popup

## Installation

### Prérequis

- Python 3.10+
- Windows 10 ou 11

### Setup

```bash
git clone https://github.com/ton-user/Close-Utility.git
cd Close-Utility
pip install psutil pystray pillow
python main.py
```

Close Utility s'ajoute automatiquement au démarrage de Windows dès le premier lancement. Il apparaît dans la zone de notification (icône violette en bas à droite).

## Structure du projet

```
Close-Utility/
├── main.py              # Point d'entrée — relie tous les modules
├── startup_manager.py   # Lecture et modification du registre Windows
├── close_counter.py     # Surveillance des process et comptage des fermetures
├── popup.py             # Interface utilisateur (popup tkinter)
├── tray.py              # Icône system tray
└── ignore_list.json     # Apps ignorées (généré automatiquement, non commité)
```

## Utilisation

Lance `main.py` une première fois pour l'installer. Ensuite il se lance tout seul au démarrage de Windows — tu n'as plus rien à faire.

Pour quitter : clic droit sur l'icône dans la zone de notification → **Quitter**.

Pour désinstaller du démarrage : Gestionnaire des tâches → onglet Démarrage → CloseUtility → Désactiver.

## Ce que Close Utility surveille

Uniquement les applications présentes dans la clé de registre `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` — c'est-à-dire exactement ce que tu vois dans le Gestionnaire des tâches → onglet Démarrage. Pas de droits administrateur requis.

## Dépendances

| Package | Utilisation |
|---------|-------------|
| `psutil` | Surveillance des process en temps réel |
| `pystray` | Icône dans la zone de notification |
| `pillow` | Génération de l'icône en mémoire |
| `winreg` | Lecture/écriture du registre Windows (stdlib) |
| `tkinter` | Interface du popup (stdlib) |