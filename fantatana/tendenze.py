"""Memoria storica: strisce, ricorrenze e costanti di rendimento.

Serve a dare ai commenti una profondita' che la singola giornata non ha. Una
sconfitta e' un fatto; la quarta sconfitta di fila e' una storia.

Tutto viene calcolato sulle giornate disputate in ordine crescente: le strisce
sono sempre "correnti", cioe' terminano all'ultima giornata disponibile.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .analysis import Partita

# Sotto queste soglie una striscia non e' una notizia.
SOGLIA_STRISCIA = 2
SOGLIA_DIGIUNO = 2
SOGLIA_GOL_CONSECUTIVI = 2


@dataclass
class StoricoSquadra:
    nome: str
    esiti: list[str] = field(default_factory=list)  # 'V', 'N', 'P' in ordine
    fantapunti: list[float] = field(default_factory=list)
    gol_fatti: list[int] = field(default_factory=list)
    incomplete: int = 0
    # Il numero di ogni giornata giocata, allineato agli esiti: una squadra che
    # salta un turno non deve far scivolare i risultati sulla giornata sbagliata.
    giornate: list[int] = field(default_factory=list)

    # -- strisce correnti ---------------------------------------------------
    @property
    def striscia_sconfitte(self) -> int:
        return _coda(self.esiti, {"P"})

    @property
    def striscia_vittorie(self) -> int:
        return _coda(self.esiti, {"V"})

    @property
    def imbattuta_da(self) -> int:
        return _coda(self.esiti, {"V", "N"})

    @property
    def senza_vittorie_da(self) -> int:
        return _coda(self.esiti, {"P", "N"})

    @property
    def digiuno_gol(self) -> int:
        """Giornate consecutive chiuse senza segnare."""
        conta = 0
        for gol in reversed(self.gol_fatti):
            if gol:
                break
            conta += 1
        return conta

    # -- rendimento ---------------------------------------------------------
    @property
    def media_fantapunti(self) -> float:
        return sum(self.fantapunti) / len(self.fantapunti) if self.fantapunti else 0.0

    @property
    def miglior_prestazione(self) -> float:
        return max(self.fantapunti, default=0.0)

    @property
    def peggior_prestazione(self) -> float:
        return min(self.fantapunti, default=0.0)


@dataclass
class StoricoGiocatore:
    nome: str
    squadra_reale: str
    # La squadra di fantacalcio dell'ultima presenza: in una lega è quella che
    # conta, e a differenza della squadra di Serie A si può mostrare.
    squadra: str = ""
    presenze: int = 0
    gol: int = 0
    ammonizioni: int = 0
    insufficienze: int = 0
    voti: list[float] = field(default_factory=list)
    gol_per_presenza: list[int] = field(default_factory=list)

    @property
    def striscia_gol(self) -> int:
        """Presenze consecutive andate a segno, dall'ultima all'indietro."""
        conta = 0
        for gol in reversed(self.gol_per_presenza):
            if not gol:
                break
            conta += 1
        return conta

    @property
    def media_voto(self) -> float:
        return sum(self.voti) / len(self.voti) if self.voti else 0.0


@dataclass
class Memoria:
    squadre: dict[str, StoricoSquadra] = field(default_factory=dict)
    giocatori: dict[str, StoricoGiocatore] = field(default_factory=dict)
    giornate: int = 0
    numeri_giornate: list[int] = field(default_factory=list)

    @property
    def abbastanza_storia(self) -> bool:
        """Sotto le due giornate non esistono strisce degne del nome."""
        return self.giornate >= SOGLIA_STRISCIA

    def capocannoniere(self) -> StoricoGiocatore | None:
        marcatori = [g for g in self.giocatori.values() if g.gol]
        return max(marcatori, key=lambda g: (g.gol, g.media_voto), default=None)

    def in_striscia_gol(self) -> list[StoricoGiocatore]:
        """Chi sta segnando con continuita', dal piu' costante."""
        return sorted(
            (g for g in self.giocatori.values() if g.striscia_gol >= SOGLIA_GOL_CONSECUTIVI),
            key=lambda g: (-g.striscia_gol, -g.gol),
        )

    def in_crisi(self) -> list[StoricoSquadra]:
        return sorted(
            (s for s in self.squadre.values() if s.striscia_sconfitte >= SOGLIA_STRISCIA),
            key=lambda s: -s.striscia_sconfitte,
        )

    def in_serie_positiva(self) -> list[StoricoSquadra]:
        return sorted(
            (s for s in self.squadre.values() if s.striscia_vittorie >= SOGLIA_STRISCIA),
            key=lambda s: -s.striscia_vittorie,
        )

    def a_secco(self) -> list[StoricoSquadra]:
        return sorted(
            (s for s in self.squadre.values() if s.digiuno_gol >= SOGLIA_DIGIUNO),
            key=lambda s: -s.digiuno_gol,
        )


def _coda(esiti: list[str], ammessi: set[str]) -> int:
    """Lunghezza della coda finale composta solo da esiti ammessi."""
    conta = 0
    for esito in reversed(esiti):
        if esito not in ammessi:
            break
        conta += 1
    return conta


def calcola(storico: dict[int, list[Partita]]) -> Memoria:
    """Costruisce la memoria a partire dalle giornate disputate."""
    memoria = Memoria(giornate=len(storico), numeri_giornate=sorted(storico))
    squadre: dict[str, StoricoSquadra] = {}
    giocatori: dict[str, StoricoGiocatore] = defaultdict(
        lambda: StoricoGiocatore(nome="", squadra_reale="")
    )

    for numero in sorted(storico):
        for partita in storico[numero]:
            lati = (
                (partita.casa, partita.gol_casa, partita.gol_trasferta),
                (partita.trasferta, partita.gol_trasferta, partita.gol_casa),
            )
            for formazione, fatti, subiti in lati:
                riga = squadre.setdefault(
                    formazione.squadra, StoricoSquadra(nome=formazione.squadra)
                )
                riga.esiti.append("V" if fatti > subiti else "P" if fatti < subiti else "N")
                riga.fantapunti.append(formazione.totale)
                riga.gol_fatti.append(fatti)
                riga.giornate.append(numero)
                if formazione.incompleta:
                    riga.incomplete += 1

                for g in formazione.giocatori:
                    scheda = giocatori[g.nome]
                    scheda.nome = g.nome
                    scheda.squadra_reale = g.squadra_reale
                    scheda.squadra = formazione.squadra
                    scheda.presenze += 1
                    scheda.gol += g.gol
                    scheda.ammonizioni += int(g.ammonito)
                    scheda.voti.append(g.voto)
                    scheda.gol_per_presenza.append(g.gol)
                    if g.voto < 5:
                        scheda.insufficienze += 1

    memoria.squadre = squadre
    memoria.giocatori = dict(giocatori)
    return memoria
