"""Storico delle giornate, con cache su disco.

Il calendario arriva in una chiamata sola, ma le formazioni no: sono cinque
richieste per giornata. A fine stagione sarebbero quasi duecento richieste a
ogni esecuzione, per dati che non cambiano piu'.

Una giornata gia' calcolata e' immutabile in pratica, quindi viene salvata su
disco e riletta. L'unica eccezione sono le rettifiche di un amministratore:
per quelle esiste `svuota_cache()` e l'opzione --rigenera-cache.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import analysis, config
from .analysis import Partita

CACHE = Path(config.ROOT) / ".cache" / "giornate"


def _percorso(competizione: str | int, giornata: int, casa: int, trasferta: int) -> Path:
    return CACHE / f"{competizione}_{giornata:02d}_{casa}_{trasferta}.json"


def svuota_cache() -> int:
    """Cancella la cache. Restituisce quanti file sono stati rimossi."""
    if not CACHE.exists():
        return 0
    rimossi = 0
    for file in CACHE.glob("*.json"):
        file.unlink()
        rimossi += 1
    return rimossi


def _formazioni_cachate(
    client,
    competizione: str | int,
    giornata: dict,
    incontro: dict,
    usa_cache: bool,
) -> dict:
    percorso = _percorso(
        competizione, giornata["matchDay"], incontro["tIdH"], incontro["tIdA"]
    )

    if usa_cache and percorso.exists():
        try:
            return json.loads(percorso.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Cache corrotta: la si ignora e si riscarica.
            pass

    dati = client.formazioni(
        competizione,
        giornata["matchDay"],
        giornata["championshipMatchDay"],
        incontro["tIdH"],
        incontro["tIdA"],
    )
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(dati), encoding="utf-8")
    return dati


def partite_di_giornata(
    client,
    competizione: str | int,
    giornata: dict,
    nomi_squadre: dict[int, str],
    nomi_giocatori: dict[int, tuple[str, str]],
    usa_cache: bool = True,
    su_avviso=None,
) -> list[Partita]:
    """Le cinque partite di una giornata, gia' ricostruite e validate."""
    partite: list[Partita] = []

    for incontro in giornata["matches"]:
        dati = _formazioni_cachate(client, competizione, giornata, incontro, usa_cache)

        casa = analysis.formazione_effettiva(
            dati["home"], nomi_squadre[incontro["tIdH"]], nomi_giocatori
        )
        trasferta = analysis.formazione_effettiva(
            dati["away"], nomi_squadre[incontro["tIdA"]], nomi_giocatori
        )

        if su_avviso:
            for lato, formazione in ((dati["home"], casa), (dati["away"], trasferta)):
                if not analysis.valida_totali(lato, formazione):
                    su_avviso(f"totale non riconciliato: {formazione.squadra}")

        partite.append(Partita(casa=casa, trasferta=trasferta, risultato=dati["res"]))

    return partite


def carica_storico(
    client,
    competizione: str | int,
    calendario: list[dict],
    nomi_squadre: dict[int, str],
    nomi_giocatori: dict[int, tuple[str, str]],
    usa_cache: bool = True,
    su_avviso=None,
    su_progresso=None,
) -> dict[int, list[Partita]]:
    """Tutte le giornate disputate, in ordine, indicizzate per numero."""
    storico: dict[int, list[Partita]] = {}

    for giornata in sorted(analysis.giornate_calcolate(calendario), key=lambda g: g["matchDay"]):
        numero = giornata["matchDay"]
        if su_progresso:
            su_progresso(numero)
        storico[numero] = partite_di_giornata(
            client,
            competizione,
            giornata,
            nomi_squadre,
            nomi_giocatori,
            usa_cache=usa_cache,
            su_avviso=su_avviso,
        )

    return storico
