"""Il listone dei giocatori, scaricato una volta e tenuto da parte.

È la risposta più pesante dell'API — quasi 400 KB a esecuzione — e serve solo a
tradurre il codice di un giocatore nel suo nome. I giocatori di una lega
cambiano di rado, quindi qui si conserva la sola mappa dei nomi: 17 KB invece
di 400, riletti dal disco senza chiamare nessuno.

Tre vie d'uscita, perché una rosa può comunque cambiare:

- il pulsante «Aggiorna il listone» della redazione, e `--rigenera-listone`;
- `--no-cache`, che come per le giornate ignora quanto c'è senza cancellarlo;
- il ricarico automatico: se in una formazione compare un giocatore che il
  listone salvato non conosce, viene riscaricato da solo. È il caso di chi
  arriva dal mercato, e senza questo controllo finirebbe in pagina col suo
  codice al posto del nome.

Un codice può restare sconosciuto anche a listone fresco: succede a chi è stato
ceduto all'estero e compare solo nelle giornate vecchie. Quei codici vengono
annotati, così non fanno riscaricare il listone a ogni generazione.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import config
from .analysis import Partita

CACHE = Path(config.ROOT) / ".cache" / "listone"

# Nome e squadra di Serie A per ogni codice giocatore.
Nomi = dict[int, tuple[str, str]]


def _percorso(alias: str) -> Path:
    """Un file per lega: il listone si chiede con il token di quella lega."""
    pulito = "".join(c if c.isalnum() or c in "-_" else "-" for c in (alias or "lega"))
    return CACHE / f"{pulito}.json"


def _leggi(percorso: Path) -> Nomi | None:
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
        voci = dati["giocatori"]
        # Le chiavi JSON sono stringhe: i codici tornano numeri, come li usa l'API.
        return {int(codice): (str(nome), str(squadra)) for codice, (nome, squadra) in voci.items()}
    except (OSError, ValueError, KeyError, TypeError):
        # Un file rovinato o di un formato vecchio vale come nessuna cache.
        return None


def _scrivi(percorso: Path, nomi: Nomi, irrisolti_: set[int] | None = None) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    contenuto = {
        "aggiornato": datetime.now().isoformat(timespec="seconds"),
        "irrisolti": sorted(irrisolti_ or ()),
        "giocatori": {str(codice): [nome, squadra] for codice, (nome, squadra) in nomi.items()},
    }
    temporaneo = percorso.with_name(percorso.name + ".tmp")
    temporaneo.write_text(json.dumps(contenuto, ensure_ascii=False), encoding="utf-8")
    temporaneo.replace(percorso)


def aggiornato(alias: str) -> str:
    """Quando è stato scaricato l'ultima volta, se c'è."""
    try:
        return str(json.loads(_percorso(alias).read_text(encoding="utf-8")).get("aggiornato", ""))
    except (OSError, ValueError, AttributeError):
        return ""


def carica(client, alias: str, usa_cache: bool = True, su_log=None) -> Nomi:
    """La mappa codice -> (nome, squadra di Serie A), dal disco o dall'API."""
    log = su_log or (lambda _messaggio: None)
    percorso = _percorso(alias)

    if usa_cache:
        nomi = _leggi(percorso)
        if nomi:
            log(f"listone: {len(nomi)} giocatori dalla cache ({aggiornato(alias)})")
            return nomi

    nomi = {g["id"]: (g["name"], g.get("stnme", "")) for g in client.giocatori()}
    _scrivi(percorso, nomi)
    log(f"listone: {len(nomi)} giocatori scaricati")
    return nomi


def codici_sconosciuti(storico: dict[int, list[Partita]]) -> set[int]:
    """I codici che il listone non conosce: in pagina sarebbero un numero al posto del nome."""
    codici = set()
    for partite in storico.values():
        for partita in partite:
            for formazione in (partita.casa, partita.trasferta):
                for giocatore in formazione.giocatori:
                    if giocatore.nome.startswith("#") and giocatore.nome[1:].isdigit():
                        codici.add(int(giocatore.nome[1:]))
    return codici


def irrisolti(alias: str) -> set[int]:
    """I codici che nemmeno un listone appena scaricato conosceva."""
    try:
        dati = json.loads(_percorso(alias).read_text(encoding="utf-8"))
        return {int(c) for c in dati.get("irrisolti", [])}
    except (OSError, ValueError, AttributeError, TypeError):
        return set()


def segna_irrisolti(alias: str, codici: set[int]) -> None:
    """Annota i codici senza nome, così non si riscarica il listone per loro ogni volta."""
    percorso = _percorso(alias)
    nomi = _leggi(percorso)
    if nomi is None:
        return
    _scrivi(percorso, nomi, irrisolti(alias) | set(codici))


def svuota(alias: str | None = None) -> int:
    """Cancella il listone salvato, di una lega o di tutte. Restituisce quanti file."""
    if not CACHE.exists():
        return 0
    file = [_percorso(alias)] if alias else list(CACHE.glob("*.json"))
    rimossi = 0
    for percorso in file:
        try:
            percorso.unlink()
            rimossi += 1
        except FileNotFoundError:
            pass
    return rimossi
