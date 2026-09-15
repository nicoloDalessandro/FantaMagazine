"""Client HTTP per l'API di Leghe Fantacalcio.

Il sito e' una SPA: le pagine sono gusci vuoti e i dati arrivano tutti da
apileague.fantacalcio.it. Qui non si usa nessun browser.
"""

from __future__ import annotations

from typing import Any

import requests

from . import auth, config


class ApiError(RuntimeError):
    pass


class TokenScaduto(ApiError):
    pass


class Client:
    """Client legato a una singola lega: il token ne determina l'ambito."""

    def __init__(self, token: str) -> None:
        self._sessione = requests.Session()
        self._sessione.headers.update(auth.intestazioni(token))

    # -- primitive ----------------------------------------------------------
    def _get(self, path: str, **params: Any) -> Any:
        url = f"{config.API_BASE}{path}"
        risposta = self._sessione.get(url, params=params or None, timeout=config.TIMEOUT)

        if risposta.status_code in (401, 403):
            raise TokenScaduto(
                f"L'API ha risposto {risposta.status_code} su {path}.\n"
                "Il token e' scaduto o appartiene a un'altra lega.\n"
                "Rigeneralo con:  python refresh_token.py"
            )
        if not risposta.ok:
            raise ApiError(f"{risposta.status_code} su {path}: {risposta.text[:200]}")

        return risposta.json()

    # -- risorse ------------------------------------------------------------
    def competizioni(self) -> Any:
        return self._get("/onboarding/v1/league/competitions")

    def squadre(self) -> list[dict]:
        """Squadre della lega: id -> nome, girone, allenatore."""
        dati = self._get("/onboarding/v1/league/teams", page=1)
        return dati.get("data", []) if isinstance(dati, dict) else list(dati)

    def giocatori(self) -> list[dict]:
        """Listone completo (~600 KB): serve per mappare pid -> nome."""
        dati = self._get("/onboarding/v1/league/players")
        return dati.get("players", []) if isinstance(dati, dict) else list(dati)

    def calendario(self, competizione: str | int) -> list[dict]:
        """Tutte le giornate, con risultati e punti assegnati."""
        return self._get(f"/onboarding/v1/league/competition/calendar/{competizione}")

    def formazioni(
        self,
        competizione: str | int,
        giornata: int,
        giornata_serie_a: int,
        id_casa: int,
        id_trasferta: int,
    ) -> dict:
        """Formazioni e voti di una singola partita.

        L'ordine dei parametri nel path e' significativo e non documentato:
        /gaming/v1/teamLineup/{competizione}/{giornata}/{giornataSerieA}/{casa}/{trasferta}
        """
        return self._get(
            f"/gaming/v1/teamLineup/{competizione}/{giornata}/"
            f"{giornata_serie_a}/{id_casa}/{id_trasferta}"
        )


def _voci_competizioni(dati) -> list[dict]:
    """Appiattisce le forme possibili della risposta in una lista di dizionari."""
    if isinstance(dati, dict):
        for chiave in ("data", "competitions", "items"):
            if isinstance(dati.get(chiave), list):
                return [v for v in dati[chiave] if isinstance(v, dict)]
        return [dati] if dati.get("id") else []
    if isinstance(dati, list):
        return [v for v in dati if isinstance(v, dict)]
    return []


def competizioni_disponibili(client: Client) -> list[tuple[str, str]]:
    """(id, nome) delle competizioni della lega."""
    voci = _voci_competizioni(client.competizioni())
    trovate = []
    for voce in voci:
        identificativo = voce.get("id") or voce.get("competitionId")
        if identificativo:
            nome = voce.get("name") or voce.get("descr") or f"competizione {identificativo}"
            trovate.append((str(identificativo), str(nome)))
    return trovate


def competizione_attiva(client: Client) -> str:
    """Id della competizione da analizzare.

    Ogni lega ha le proprie competizioni, quindi va risolta lega per lega. Un
    valore in FANTA_COMPETITION_ID ha comunque la precedenza.
    """
    if config.COMPETITION_ID:
        return str(config.COMPETITION_ID)

    trovate = competizioni_disponibili(client)
    if trovate:
        return trovate[0][0]

    raise ApiError(
        "Nessuna competizione trovata per questa lega: "
        "imposta FANTA_COMPETITION_ID per forzarla."
    )
