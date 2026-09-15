"""Ricostruzione delle formazioni e analisi della giornata.

Due dettagli del formato API che non sono documentati e sono stati dedotti dai
dati reali (la deduzione e' verificabile: vedi `valida_totali`).

1. Senza voto (s.v.)
   Le righe con voto >= 50 e fantavoto == 100 sono sentinelle per "non ha
   giocato", non punteggi reali.

2. Vettore eventi `b`
   Sedici slot separati da ';'. Gli indici usati qui:
       0  -> ammonizione        (-0.5)
       2  -> gol segnato        (+3 ciascuno)
       3  -> gol subito         (-1 ciascuno, portiere)
       10 -> bonus              (+1)
       13 -> bonus              (+1)
       14 -> bonus              (+1)
   Gli slot 10/13/14 valgono tutti +1 e raggruppano assist e porta inviolata:
   restano indistinti perche' la corrispondenza esatta non e' ricavabile dai
   dati osservati.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Costanti di formato ----------------------------------------------------
SENTINELLA_SENZA_VOTO = 50.0
SLOT_AMMONIZIONE = 0
SLOT_GOL = 2
SLOT_GOL_SUBITO = 3
SLOT_BONUS = (10, 13, 14)

USCITO = "U"  # titolare sostituito perche' senza voto
ENTRATO = "E"  # panchinaro subentrato


@dataclass
class Giocatore:
    nome: str
    squadra_reale: str
    voto: float
    fantavoto: float
    gol: int = 0
    ammonito: bool = False
    gol_subiti: int = 0
    bonus: int = 0
    subentrato: bool = False


@dataclass
class Formazione:
    squadra: str
    modulo: int
    totale: float
    giocatori: list[Giocatore] = field(default_factory=list)

    @property
    def incompleta(self) -> bool:
        return len(self.giocatori) < 11

    @property
    def marcatori(self) -> list[Giocatore]:
        return [g for g in self.giocatori if g.gol]

    @property
    def insufficienti(self) -> list[Giocatore]:
        """Voti sotto il 5, dal peggiore."""
        return sorted((g for g in self.giocatori if g.voto < 5), key=lambda g: g.voto)


@dataclass
class Partita:
    casa: Formazione
    trasferta: Formazione
    risultato: str

    @property
    def gol_casa(self) -> int:
        return int(self.risultato.split("-")[0])

    @property
    def gol_trasferta(self) -> int:
        return int(self.risultato.split("-")[1])


@dataclass
class RigaClassifica:
    squadra: str
    punti: int = 0
    giocate: int = 0
    vinte: int = 0
    pareggiate: int = 0
    perse: int = 0
    gol_fatti: int = 0
    gol_subiti: int = 0
    fantapunti: float = 0.0

    @property
    def differenza_reti(self) -> int:
        return self.gol_fatti - self.gol_subiti


# --- Calendario -------------------------------------------------------------
def giornate_calcolate(calendario: list[dict]) -> list[dict]:
    return [g for g in calendario if g.get("calculated")]


def ultima_giornata(calendario: list[dict]) -> dict:
    """La giornata disputata piu' recente."""
    disputate = giornate_calcolate(calendario)
    if not disputate:
        raise ValueError("Nessuna giornata risulta ancora calcolata.")
    return max(disputate, key=lambda g: g["matchDay"])


def scontri_diretti(giornata: dict) -> bool:
    """Vero se ogni squadra compare in una sola partita della giornata.

    E' l'assunto su cui poggiano classifica e commenti: un campionato normale
    accoppia le squadre due a due. Formati come il Royale fanno giocare tutti
    contro tutti nella stessa giornata, e li' questi conteggi non reggono.
    """
    presenze: dict[int, int] = {}
    for partita in giornata.get("matches", []):
        for chiave in ("tIdH", "tIdA"):
            identificativo = partita.get(chiave)
            presenze[identificativo] = presenze.get(identificativo, 0) + 1
    return all(conteggio == 1 for conteggio in presenze.values())


# --- Formazioni -------------------------------------------------------------
def _senza_voto(riga: dict) -> bool:
    voto = riga.get("scr")
    return voto is None or float(voto) >= SENTINELLA_SENZA_VOTO


def _giocatore(riga: dict, nomi: dict[int, tuple[str, str]], subentrato: bool) -> Giocatore:
    slot = [int(x) for x in riga["b"].split(";")]
    nome, squadra = nomi.get(riga["pid"], (f"#{riga['pid']}", "?"))
    return Giocatore(
        nome=nome,
        squadra_reale=squadra,
        voto=float(riga["scr"]),
        fantavoto=float(riga["cscr"]),
        gol=slot[SLOT_GOL],
        ammonito=bool(slot[SLOT_AMMONIZIONE]),
        gol_subiti=slot[SLOT_GOL_SUBITO],
        bonus=sum(slot[i] for i in SLOT_BONUS),
        subentrato=subentrato,
    )


def formazione_effettiva(lato: dict, nome_squadra: str, nomi: dict) -> Formazione:
    """Solo i giocatori che hanno realmente concorso al punteggio.

    Titolari con voto, piu' i panchinari effettivamente subentrati. I panchinari
    rimasti fuori hanno comunque un voto nel JSON: includerli falserebbe tutto.

    `starts` e `bench` possono essere None quando una squadra non ha schierato
    nulla: in quel caso la formazione resta vuota invece di far esplodere tutto.
    """
    titolari = lato.get("starts") or []
    panchina = lato.get("bench") or []

    giocatori = [
        _giocatore(r, nomi, subentrato=False)
        for r in titolari
        if r.get("ptype") != USCITO and not _senza_voto(r)
    ]
    giocatori += [
        _giocatore(r, nomi, subentrato=True)
        for r in panchina
        if r.get("ptype") == ENTRATO and not _senza_voto(r)
    ]
    return Formazione(
        squadra=nome_squadra,
        modulo=lato.get("mdl") or 0,
        totale=float(lato.get("tot") or 0.0),
        giocatori=giocatori,
    )


def modificatori(lato: dict) -> float:
    """Somma dei bonus di squadra (modificatore difesa, ecc.)."""
    grezzo = lato.get("tbon") or ""
    return sum(float(x) for x in grezzo.split(";") if x.strip())


def valida_totali(lato: dict, formazione: Formazione) -> bool:
    """Verifica che la ricostruzione riproduca il totale ufficiale.

    E' il controllo che rende affidabile tutto il resto: se qui torna, la
    selezione dei giocatori in campo e' quella giusta.
    """
    calcolato = sum(g.fantavoto for g in formazione.giocatori) + modificatori(lato)
    return abs(calcolato - formazione.totale) < 0.01


# --- Classifica -------------------------------------------------------------
def classifica(calendario: list[dict], nomi_squadre: dict[int, str]) -> list[RigaClassifica]:
    """Classifica cumulativa su tutte le giornate disputate.

    Una classifica e' per definizione progressiva: anche analizzando solo
    l'ultima giornata, qui si sommano tutte quelle calcolate.
    """
    righe = {tid: RigaClassifica(squadra=nome) for tid, nome in nomi_squadre.items()}

    for giornata in giornate_calcolate(calendario):
        for partita in giornata.get("matches", []):
            gol_casa, gol_trasferta = (int(v) for v in partita["result"].split("-"))
            lati = (
                (partita["tIdH"], gol_casa, gol_trasferta, partita["standingPtH"], partita["ptH"]),
                (partita["tIdA"], gol_trasferta, gol_casa, partita["standingPtA"], partita["ptA"]),
            )
            for tid, fatti, subiti, punti, fantapunti in lati:
                riga = righe.get(tid)
                if riga is None:
                    continue
                riga.giocate += 1
                riga.punti += int(punti)
                riga.gol_fatti += fatti
                riga.gol_subiti += subiti
                riga.fantapunti += float(fantapunti)
                if fatti > subiti:
                    riga.vinte += 1
                elif fatti < subiti:
                    riga.perse += 1
                else:
                    riga.pareggiate += 1

    ordinata = sorted(
        righe.values(),
        key=lambda r: (-r.punti, -r.differenza_reti, -r.fantapunti),
    )
    return [r for r in ordinata if r.giocate]
