"""Gestione dei token, una per lega.

L'API di Leghe Fantacalcio usa un JWT **per lega**: non esiste un token che le
apra tutte. Il browser li tiene tutti insieme, quindi `refresh_token.py` li
estrae in blocco e qui vengono conservati come mappa alias -> lega.

Nessuna password viene mai letta, richiesta o salvata da questo progetto.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from . import config


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


def carica_leghe() -> dict[str, Lega]:
    """Tutte le leghe con un token disponibile, indicizzate per alias."""
    leghe: dict[str, Lega] = {}

    if config.LEGHE_FILE.exists():
        try:
            grezzo = json.loads(config.LEGHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as errore:
            raise TokenMancante(
                f"{config.LEGHE_FILE} illeggibile ({errore}).\n"
                "Rigeneralo con:  python refresh_token.py"
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
    contenuto = {
        voce["alias"]: {
            "nome": voce.get("nome") or voce["alias"],
            "id": voce.get("id"),
            "token": voce["token"],
        }
        for voce in leghe
        if voce.get("token")
    }
    config.LEGHE_FILE.write_text(
        json.dumps(contenuto, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    try:
        os.chmod(config.LEGHE_FILE, 0o600)
    except OSError:
        # Su Windows chmod e' in gran parte inefficace: non e' un errore fatale.
        pass


def scegli_lega(alias: str | None = None) -> Lega:
    """Restituisce la lega richiesta, o l'unica disponibile."""
    leghe = carica_leghe()
    if not leghe:
        raise TokenMancante(
            "Nessun token trovato.\n"
            f"  Atteso in {config.LEGHE_FILE}\n"
            "  Per generarlo: apri Chrome, accedi a leghe.fantacalcio.it, poi esegui\n"
            "      python refresh_token.py"
        )

    if alias:
        if alias not in leghe:
            disponibili = ", ".join(sorted(leghe)) or "nessuna"
            raise TokenMancante(
                f"Lega '{alias}' senza token.\n"
                f"  Disponibili: {disponibili}\n"
                "  Se ne manca una, rilancia:  python refresh_token.py"
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
