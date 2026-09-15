"""Conservazione dei token: uno per lega, più quello dell'utente.

L'API di Leghe Fantacalcio usa un JWT **per lega**: non esiste un token che le
apra tutte. L'accesso (`accesso.py`) li restituisce insieme, e qui vengono
conservati come mappa alias -> lega. Il token dell'utente, a parte, permette di
ritrovare le leghe nuove senza chiedere di nuovo la password.

La password non passa mai di qui: su disco finiscono solo i token.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import config
from .accesso import Utente


class TokenMancante(RuntimeError):
    """Sollevata quando non si trova un token utilizzabile."""


@dataclass
class Lega:
    alias: str
    nome: str
    token: str
    id: int | None = None

    @property
    def url(self) -> str:
        return f"{config.SITE_BASE}/{self.alias}"


def _normalizza(token: str) -> str:
    """Garantisce il prefisso Bearer una sola volta."""
    token = token.strip().strip('"')
    if not token.lower().startswith("bearer "):
        token = f"Bearer {token}"
    return token


def _scrivi_privato(percorso: Path, contenuto: dict) -> None:
    """Scrive un file di token: prima in un file temporaneo, poi al suo posto.

    Così un'interruzione a metà non lascia un file troncato, e i permessi
    ristretti valgono fin dal primo byte dove il sistema li rispetta.
    """
    temporaneo = percorso.with_name(percorso.name + ".tmp")
    temporaneo.write_text(json.dumps(contenuto, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(temporaneo, 0o600)
    except OSError:
        # Su Windows chmod e' in gran parte inefficace: non e' un errore fatale.
        pass
    os.replace(temporaneo, percorso)


def carica_leghe() -> dict[str, Lega]:
    """Tutte le leghe con un token disponibile, indicizzate per alias."""
    leghe: dict[str, Lega] = {}

    if config.LEGHE_FILE.exists():
        try:
            grezzo = json.loads(config.LEGHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as errore:
            raise TokenMancante(
                f"{config.LEGHE_FILE} illeggibile ({errore}).\n"
                "Rifai l'accesso con:  python main.py --accedi"
            ) from errore

        for alias, voce in grezzo.items():
            leghe[alias] = Lega(
                alias=alias,
                nome=voce.get("nome", alias),
                token=_normalizza(voce["token"]),
                id=voce.get("id"),
            )

    # Un token passato dall'ambiente ha sempre la precedenza: utile in CI.
    da_ambiente = os.getenv("FANTA_TOKEN", "").strip()
    if da_ambiente:
        alias = os.getenv("FANTA_LEAGUE_ALIAS", config.LEGA_PREDEFINITA)
        leghe[alias] = Lega(
            alias=alias,
            nome=leghe.get(alias).nome if alias in leghe else alias,
            token=_normalizza(da_ambiente),
            id=leghe[alias].id if alias in leghe else None,
        )

    return leghe


def salva_leghe(leghe: list[dict]) -> None:
    """Scrive la mappa delle leghe su disco."""
    _scrivi_privato(
        config.LEGHE_FILE,
        {
            voce["alias"]: {
                "nome": voce.get("nome") or voce["alias"],
                "id": voce.get("id"),
                "token": voce["token"],
            }
            for voce in leghe
            if voce.get("token")
        },
    )


def salva_utente(utente: Utente) -> None:
    """Conserva l'utente e il suo token, per aggiornare le leghe senza password."""
    _scrivi_privato(
        config.UTENTE_FILE,
        {
            "id": utente.id,
            "username": utente.username,
            "jwt": utente.jwt,
            "token_auth": utente.token_auth,
        },
    )


def carica_utente() -> Utente | None:
    """L'utente dell'ultimo accesso, se c'è ed è leggibile."""
    if not config.UTENTE_FILE.exists():
        return None
    try:
        dati = json.loads(config.UTENTE_FILE.read_text(encoding="utf-8"))
        return Utente(
            id=int(dati["id"]),
            username=str(dati.get("username") or ""),
            jwt=str(dati["jwt"]),
            token_auth=str(dati.get("token_auth") or ""),
        )
    except (OSError, ValueError, KeyError, TypeError):
        # Un file rovinato equivale a nessun accesso: si rientra con la password.
        return None


def _rimuovi(percorso: Path) -> None:
    try:
        percorso.unlink()
    except FileNotFoundError:
        pass


def dimentica_utente() -> None:
    """Toglie solo l'utente: i token delle leghe restano utilizzabili."""
    _rimuovi(config.UTENTE_FILE)


def cancella_sessione() -> None:
    """Dimentica utente e token. Le scelte su leghe e testate restano."""
    _rimuovi(config.UTENTE_FILE)
    _rimuovi(config.LEGHE_FILE)


def scegli_lega(alias: str | None = None) -> Lega:
    """Restituisce la lega richiesta, o l'unica disponibile."""
    leghe = carica_leghe()
    if not leghe:
        raise TokenMancante(
            "Nessun token trovato.\n"
            f"  Atteso in {config.LEGHE_FILE}\n"
            "  Per generarlo accedi con:  python main.py --accedi"
        )

    if alias:
        if alias not in leghe:
            disponibili = ", ".join(sorted(leghe)) or "nessuna"
            raise TokenMancante(
                f"Lega '{alias}' senza token.\n"
                f"  Disponibili: {disponibili}\n"
                "  Se ne manca una, rifai l'accesso:  python main.py --accedi"
            )
        return leghe[alias]

    if len(leghe) == 1:
        return next(iter(leghe.values()))

    raise TokenMancante(
        "Piu' leghe disponibili: indica quale con --lega, oppure scegli dal menu."
    )


def intestazioni(token: str) -> dict[str, str]:
    """Header completi per una richiesta all'API."""
    return {
        "accept": "application/json",
        "Content-Type": "application/json",
        "app_key": config.APP_KEY,
        "Authorization": _normalizza(token),
        "User-Agent": config.USER_AGENT,
    }
