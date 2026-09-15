"""Configurazione del progetto.

I valori possono essere sovrascritti da variabili d'ambiente (prefisso FANTA_).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Leghe ------------------------------------------------------------------
# Le leghe non sono piu' cablate: vengono scoperte dai token estratti dal
# browser. Questo alias serve solo come ripiego quando ne esiste una sola o
# quando il token arriva dall'ambiente.
LEGA_PREDEFINITA = os.getenv("FANTA_LEAGUE_ALIAS", "")

# Competizione: se vuota viene individuata automaticamente per la lega scelta.
# Ogni lega ha le proprie, quindi cablarne una sola sarebbe sbagliato.
COMPETITION_ID = os.getenv("FANTA_COMPETITION_ID", "")

# --- Testate ----------------------------------------------------------------
# Ogni lega ha il suo quotidiano. Per aggiungerne una basta una riga qui.
TESTATE = {
    "fantatana": "LA GAZZETTA DELLA TANA",
    "madonna-del-pozzo-league": "LA GAZZETTA DEL SAGRATO",
}


def testata(alias: str, nome_lega: str = "") -> str:
    """Nome del giornale per una lega.

    Senza una voce dedicata se ne deriva una dal nome della lega, così una
    lega nuova produce comunque una testata sensata invece di un segnaposto.
    """
    forzata = os.getenv("FANTA_TESTATA", "").strip()
    if forzata:
        return forzata.upper()
    if alias in TESTATE:
        return TESTATE[alias]
    return f"LA GAZZETTA DI {(nome_lega or alias).upper()}"


# --- Endpoint ---------------------------------------------------------------
API_BASE = "https://apileague.fantacalcio.it"
SITE_BASE = "https://leghe.fantacalcio.it"

# Chiave pubblica del client, inclusa in chiaro nel bundle JavaScript della SPA.
# Non e' un segreto dell'utente: identifica l'applicazione, non la persona.
APP_KEY = os.getenv("FANTA_APP_KEY", "ICiELOObd5DF5uJEATi77CRvHiiRuMU0")

# --- Token ------------------------------------------------------------------
# Mappa alias -> {nome, id, token}. Vedi auth.py e refresh_token.py.
LEGHE_FILE = Path(os.getenv("FANTA_LEGHE_FILE", ROOT / ".fanta_leghe.json"))

# Chiave dell'API di Gemini, per generare l'immagine della prima pagina.
# Anche questa resta fuori da git; in alternativa, variabile GEMINI_API_KEY.
GEMINI_KEY_FILE = Path(os.getenv("GEMINI_KEY_FILE", ROOT / ".gemini_key"))

# Dove finiscono le immagini: le bozze appena generate, che nessuno ha ancora
# deciso di tenere, e le prime pagine salvate.
BOZZE_DIR = ROOT / ".cache" / "immagini"
ARCHIVIO_DIR = Path(os.getenv("FANTA_ARCHIVIO", ROOT / "prime_pagine"))

# --- Rete -------------------------------------------------------------------
TIMEOUT = float(os.getenv("FANTA_TIMEOUT", "30"))
USER_AGENT = "FantaProject/1.0"
