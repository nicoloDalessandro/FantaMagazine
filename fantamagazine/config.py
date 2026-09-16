"""Configurazione del progetto.

I valori possono essere sovrascritti da variabili d'ambiente (prefisso FANTA_).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from . import __version__

# Vero quando l'app gira come eseguibile costruito con PyInstaller.
CONGELATO = bool(getattr(sys, "frozen", False))

# Le risorse in sola lettura - le pagine e i fogli di stile della redazione -
# viaggiano dentro il pacchetto, che PyInstaller scompatta dove decide lui.
RISORSE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _cartella_dati() -> Path:
    """Dove finiscono token, scelte, chiave e cache.

    Da sorgente e' la cartella del progetto, come e' sempre stato. Nell'eseguibile
    e' la cartella dell'.exe: tutto resta insieme allo ZIP appena estratto, e per
    disfarsene basta cancellare quella cartella. Se pero' l'app e' stata messa
    dove Windows non lascia scrivere (Programmi, per dire), i dati andrebbero
    persi a ogni avvio: in quel caso si ripiega sui dati locali dell'utente.
    """
    if not CONGELATO:
        return Path(__file__).resolve().parent.parent

    accanto = Path(sys.executable).resolve().parent
    try:
        with tempfile.TemporaryFile(dir=accanto):
            return accanto
    except OSError:
        pass

    riserva = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "FantaMagazine"
    riserva.mkdir(parents=True, exist_ok=True)
    return riserva


ROOT = _cartella_dati()

# --- Leghe ------------------------------------------------------------------
# Le leghe non sono cablate: arrivano con l'accesso dell'utente. Questo alias
# serve solo come ripiego quando il token arriva dall'ambiente.
LEGA_PREDEFINITA = os.getenv("FANTA_LEAGUE_ALIAS", "")

# Competizione: se vuota viene individuata automaticamente per la lega scelta.
# Ogni lega ha le proprie, quindi cablarne una sola sarebbe sbagliato.
COMPETITION_ID = os.getenv("FANTA_COMPETITION_ID", "")

# --- Endpoint ---------------------------------------------------------------
API_BASE = "https://apileague.fantacalcio.it"
SITE_BASE = "https://leghe.fantacalcio.it"

# Accesso e profilo, gli stessi che usa il sito: la risposta contiene l'utente e
# tutte le sue leghe, ciascuna col proprio token.
URL_ACCESSO = f"{API_BASE}/onboarding/v1/login"
URL_PROFILO = f"{API_BASE}/onboarding/v2/profile/{{id_utente}}"

# Chiave pubblica del client, inclusa in chiaro nel bundle JavaScript della SPA.
# Non e' un segreto dell'utente: identifica l'applicazione, non la persona.
APP_KEY = os.getenv("FANTA_APP_KEY", "ICiELOObd5DF5uJEATi77CRvHiiRuMU0")

# --- Token e scelte ---------------------------------------------------------
# Mappa alias -> {nome, id, token}. Vedi auth.py.
LEGHE_FILE = Path(os.getenv("FANTA_LEGHE_FILE", ROOT / ".fanta_leghe.json"))

# L'utente che ha fatto l'accesso, con il suo token: serve ad aggiornare
# l'elenco delle leghe senza chiedere di nuovo la password. Mai la password.
UTENTE_FILE = Path(os.getenv("FANTA_UTENTE_FILE", ROOT / ".fanta_utente.json"))

# Leghe e competizioni scelte, e il nome del giornale di ciascuna lega.
IMPOSTAZIONI_FILE = Path(os.getenv("FANTA_IMPOSTAZIONI_FILE", ROOT / ".fanta_impostazioni.json"))

# Chiave dell'API di Gemini, per generare l'immagine della prima pagina.
# Anche questa resta fuori da git; in alternativa, variabile GEMINI_API_KEY.
GEMINI_KEY_FILE = Path(os.getenv("GEMINI_KEY_FILE", ROOT / ".gemini_key"))

# Dove finiscono le immagini: le bozze appena generate, che nessuno ha ancora
# deciso di tenere, e le prime pagine salvate.
BOZZE_DIR = ROOT / ".cache" / "immagini"
ARCHIVIO_DIR = Path(os.getenv("FANTA_ARCHIVIO", ROOT / "prime_pagine"))

# --- Rete -------------------------------------------------------------------
TIMEOUT = float(os.getenv("FANTA_TIMEOUT", "30"))
USER_AGENT = f"FantaMagazine/{__version__}"
