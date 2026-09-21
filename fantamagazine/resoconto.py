"""Il resoconto della memoria: che cosa ricorda e che cosa ne è finito in pagina.

La memoria (`tendenze.py`) calcola serie e ricorrenze; la pagina (`prompt.py`)
ne usa una parte e annota dove, con i `Richiamo`. Qui le due cose si incontrano
in una forma che si può guardare: per verificare che la storia pesi davvero su
quello che si legge, e per capire perché una notizia che la memoria conosce è
rimasta fuori.

Qui non si decide nulla della pagina. Le regole in `REGOLE` descrivono il
motore con le sue stesse soglie, così un cambio di soglia non le rende false.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .prompt import SOGLIA_TITOLO, PrimaPagina
from .tendenze import (
    SOGLIA_DIGIUNO,
    SOGLIA_GOL_CONSECUTIVI,
    SOGLIA_STRISCIA,
    Memoria,
    StoricoSquadra,
)

# Dove può entrare la memoria, sezione per sezione.
REGOLE = (
    (
        "Titolo",
        f"la crisi più lunga, da almeno {SOGLIA_TITOLO} sconfitte di fila; se non c'è, "
        f"la serie positiva più lunga, da almeno {SOGLIA_TITOLO} vittorie. "
        "Altrimenti il titolo racconta la giornata. Se la partita in apertura l'hai "
        "scelta tu, contano solo le serie delle sue due squadre, e senza serie il "
        "titolo racconta quella partita.",
    ),
    (
        "Il racconto",
        "una frase per ciascuna squadra della partita di apertura: la serie di "
        f"sconfitte o di vittorie, da {SOGLIA_STRISCIA} in su, oppure il digiuno di gol, "
        f"da {SOGLIA_DIGIUNO} giornate. Le prime volte qui non entrano.",
    ),
    (
        "Dietro i numeri",
        f"una serie da {SOGLIA_STRISCIA} in su, prima le positive e poi le crisi, della "
        "prima squadra che il pezzo non ha già nominato.",
    ),
    (
        "Trafiletti",
        "prima vittoria, prima sconfitta e primo pareggio della stagione, e le serie da "
        f"{SOGLIA_STRISCIA} in su. Ogni partita ha un solo trafiletto e ogni angolo "
        "compare una volta: se la gara offre qualcosa di più forte, come una formazione "
        "incompleta, la vetta o uno 0-0, la memoria resta fuori.",
    ),
    (
        "Giocatori",
        "la memoria ne conta gol, voti e serie, ma la pagina per ora non li racconta.",
    ),
)

# L'ordine di forza delle notizie: le serie prima delle prime volte.
_FORZA = {
    "sconfitte": 0,
    "vittorie": 0,
    "digiuno": 1,
    "prima_vittoria": 2,
    "prima_sconfitta": 2,
    "primo_pareggio": 2,
    "gol_di_fila": 3,
}

_PRIME_VOLTE = {"V": "prima_vittoria", "P": "prima_sconfitta", "N": "primo_pareggio"}


@dataclass
class Notizia:
    """Un fatto che la memoria conosce e che può diventare una notizia."""

    tipo: str
    soggetto: str  # la squadra, o il giocatore
    squadra: str  # la squadra di fantacalcio: per una squadra, lei stessa
    valore: int
    fatto: str  # "3 sconfitte di fila"
    raccontabile: bool  # la pagina sa scriverla?
    sezioni: list[str] = field(default_factory=list)  # dove è finita in pagina


@dataclass
class SchedaSquadra:
    nome: str
    posizione: int | None
    giornate: list[int]
    esiti: list[str]
    fantapunti: list[float]
    gol_fatti: list[int]
    serie: list[str]  # "3 sconfitte di fila", "senza gol da 2 giornate"
    media_fantapunti: float
    miglior_prestazione: float
    peggior_prestazione: float
    incomplete: int


@dataclass
class SchedaGiocatore:
    nome: str
    squadra: str
    presenze: int
    gol: int
    striscia_gol: int
    media_voto: float
    insufficienze: int
    ammonizioni: int


@dataclass
class Resoconto:
    giornate: list[int]
    sintesi: str
    notizie: list[Notizia]
    squadre: list[SchedaSquadra]
    giocatori: list[SchedaGiocatore]
    regole: list[tuple[str, str]]


def descrivi(tipo: str, valore: int) -> str:
    """Il fatto in parole: «3 sconfitte di fila», «prima vittoria stagionale»."""
    return {
        "sconfitte": f"{valore} sconfitte di fila",
        "vittorie": f"{valore} vittorie di fila",
        "digiuno": f"senza gol da {valore} giornate",
        "prima_vittoria": "prima vittoria stagionale",
        "prima_sconfitta": "prima sconfitta stagionale",
        "primo_pareggio": "primo pareggio stagionale",
        "gol_di_fila": f"in gol da {valore} presenze di fila",
    }.get(tipo, tipo)


def notizie(memoria: Memoria) -> list[Notizia]:
    """Le notizie che la memoria conosce, dalla più forte.

    Sono i fatti che la pagina sa raccontare — serie di vittorie e di
    sconfitte, digiuni di gol, prime volte della stagione — più le serie di gol
    dei giocatori, che la memoria calcola ma la pagina non usa. Una prima volta
    all'esordio non conta: dietro non c'è nessuna giornata passata.
    """
    elenco: list[Notizia] = []

    def aggiungi(tipo: str, soggetto: str, squadra: str, valore: int) -> None:
        elenco.append(
            Notizia(
                tipo=tipo,
                soggetto=soggetto,
                squadra=squadra,
                valore=valore,
                fatto=descrivi(tipo, valore),
                raccontabile=tipo != "gol_di_fila",
            )
        )

    for scheda in memoria.squadre.values():
        if scheda.striscia_sconfitte >= SOGLIA_STRISCIA:
            aggiungi("sconfitte", scheda.nome, scheda.nome, scheda.striscia_sconfitte)
        if scheda.striscia_vittorie >= SOGLIA_STRISCIA:
            aggiungi("vittorie", scheda.nome, scheda.nome, scheda.striscia_vittorie)
        if scheda.digiuno_gol >= SOGLIA_DIGIUNO:
            aggiungi("digiuno", scheda.nome, scheda.nome, scheda.digiuno_gol)
        if len(scheda.esiti) > 1 and scheda.esiti.count(scheda.esiti[-1]) == 1:
            aggiungi(_PRIME_VOLTE[scheda.esiti[-1]], scheda.nome, scheda.nome, 1)

    for giocatore in memoria.giocatori.values():
        if giocatore.striscia_gol >= SOGLIA_GOL_CONSECUTIVI:
            aggiungi("gol_di_fila", giocatore.nome, giocatore.squadra, giocatore.striscia_gol)

    return sorted(elenco, key=lambda n: (_FORZA[n.tipo], -n.valore))


def _serie(scheda: StoricoSquadra) -> list[str]:
    """La serie in corso e l'eventuale digiuno di gol, in parole."""
    fatti = []
    if scheda.striscia_vittorie >= SOGLIA_STRISCIA:
        fatti.append(descrivi("vittorie", scheda.striscia_vittorie))
    elif scheda.striscia_sconfitte >= SOGLIA_STRISCIA:
        fatti.append(descrivi("sconfitte", scheda.striscia_sconfitte))
    elif scheda.imbattuta_da >= SOGLIA_STRISCIA:
        fatti.append(f"imbattuta da {scheda.imbattuta_da} giornate")
    elif scheda.senza_vittorie_da >= SOGLIA_STRISCIA:
        fatti.append(f"senza vittorie da {scheda.senza_vittorie_da} giornate")
    if scheda.digiuno_gol >= SOGLIA_DIGIUNO:
        fatti.append(descrivi("digiuno", scheda.digiuno_gol))
    return fatti


def _numeri(scheda: StoricoSquadra, giornate: list[int]) -> list[int]:
    """Il numero di giornata di ogni esito.

    Una memoria costruita a mano può non averli: si assume allora che la
    squadra abbia giocato le ultime giornate, purché i conti tornino.
    """
    if len(scheda.giornate) == len(scheda.esiti):
        return list(scheda.giornate)
    if len(giornate) >= len(scheda.esiti):
        return giornate[len(giornate) - len(scheda.esiti):]
    return list(range(1, len(scheda.esiti) + 1))


def _sintesi(giornate: list[int], elenco: list[Notizia]) -> str:
    if len(giornate) <= 1:
        return (
            "È la prima giornata in memoria: non ci sono partite passate da raccontare, "
            "quindi la pagina parla solo di questa."
        )
    arco = f"La memoria copre {len(giornate)} giornate, dalla {giornate[0]} alla {giornate[-1]}."
    if not elenco:
        return f"{arco} Nessuna serie in corso e nessuna prima volta: la pagina racconta solo la giornata."

    totale = len(elenco)
    entrate = sum(1 for n in elenco if n.sezioni)
    conosce = "Conosce una notizia" if totale == 1 else f"Conosce {totale} notizie"
    if entrate == 0:
        frase = f"{conosce}, ma {'non è entrata' if totale == 1 else 'nessuna è entrata'} in pagina."
        if not any(n.raccontabile for n in elenco):
            frase += (
                " È la serie di un giocatore, che la pagina per ora non racconta."
                if totale == 1
                else " Sono tutte serie di giocatori, che la pagina per ora non racconta."
            )
    elif totale == 1:
        frase = f"{conosce}, ed è entrata in pagina."
    elif entrate == 1:
        frase = f"{conosce}: una è entrata in pagina."
    else:
        frase = f"{conosce}: {entrate} sono entrate in pagina."
    return f"{arco} {frase}"


def componi(memoria: Memoria, pagina: PrimaPagina) -> Resoconto:
    """Il resoconto della memoria usata per comporre questa pagina."""
    giornate = memoria.numeri_giornate or list(range(1, memoria.giornate + 1))

    elenco = notizie(memoria)
    for notizia in elenco:
        notizia.sezioni = list(
            dict.fromkeys(
                r.sezione
                for r in pagina.richiami
                if r.tipo == notizia.tipo and r.squadra == notizia.soggetto
            )
        )

    posizioni = {voce.squadra: voce.posizione for voce in pagina.classifica}
    squadre = [
        SchedaSquadra(
            nome=s.nome,
            posizione=posizioni.get(s.nome),
            giornate=_numeri(s, giornate),
            esiti=list(s.esiti),
            fantapunti=list(s.fantapunti),
            gol_fatti=list(s.gol_fatti),
            serie=_serie(s),
            media_fantapunti=round(s.media_fantapunti, 1),
            miglior_prestazione=s.miglior_prestazione,
            peggior_prestazione=s.peggior_prestazione,
            incomplete=s.incomplete,
        )
        for s in memoria.squadre.values()
    ]
    squadre.sort(key=lambda s: (s.posizione is None, s.posizione or 0, s.nome))

    giocatori = sorted(
        (
            SchedaGiocatore(
                nome=g.nome,
                squadra=g.squadra,
                presenze=g.presenze,
                gol=g.gol,
                striscia_gol=g.striscia_gol,
                media_voto=round(g.media_voto, 2),
                insufficienze=g.insufficienze,
                ammonizioni=g.ammonizioni,
            )
            for g in memoria.giocatori.values()
        ),
        key=lambda g: (-g.gol, -g.striscia_gol, -g.media_voto, g.nome),
    )

    return Resoconto(
        giornate=giornate,
        sintesi=_sintesi(giornate, elenco),
        notizie=elenco,
        squadre=squadre,
        giocatori=giocatori,
        regole=list(REGOLE),
    )
