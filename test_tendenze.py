"""Verifica della memoria storica su dati sintetici.

Serve perche' a inizio stagione esiste una sola giornata reale: le strisce non
possono manifestarsi e la funzionalita' resterebbe non verificabile fino a
ottobre. Qui si costruiscono quattro giornate finte con andamenti noti e si
controlla che il motore li riconosca.

    python test_tendenze.py
"""

from __future__ import annotations

import sys

# Gli output contengono accenti: senza questo, su console Windows con code page
# legacy diventano illeggibili.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from fantatana import prompt, tendenze
from fantatana.analysis import Formazione, Giocatore, Partita

SQUADRE = ["Sfigati FC", "Bomber United", "Muro Difensivo", "Media Mediocre"]


def _giocatore(nome: str, voto: float, gol: int = 0) -> Giocatore:
    return Giocatore(
        nome=nome,
        squadra_reale="TST",
        voto=voto,
        fantavoto=voto + 3 * gol,
        gol=gol,
    )


def _formazione(squadra: str, totale: float, marcatore: str | None = None, gol: int = 1,
                incompleta: bool = False) -> Formazione:
    rosa = [_giocatore(f"{squadra[:3]}{i}", 6.0) for i in range(10 if incompleta else 11)]
    if marcatore:
        rosa[0] = _giocatore(marcatore, 7.0, gol)
    return Formazione(squadra=squadra, modulo=433, totale=totale, giocatori=rosa)


def _storico_finto() -> dict[int, list[Partita]]:
    """Quattro giornate con andamenti deliberati.

    - Sfigati FC perde sempre e non segna mai
    - Rossi (Bomber United) va a segno a ogni giornata
    - Muro Difensivo vince sempre
    """
    giornate: dict[int, list[Partita]] = {}
    for numero in range(1, 5):
        giornate[numero] = [
            Partita(
                casa=_formazione("Sfigati FC", 55.0 + numero),
                trasferta=_formazione("Bomber United", 78.0, marcatore="Rossi"),
                risultato="0-3",
            ),
            Partita(
                casa=_formazione("Muro Difensivo", 74.0, marcatore="Bianchi"),
                trasferta=_formazione("Media Mediocre", 66.0),
                risultato="2-1",
            ),
        ]
    return giornate


def test_striscia_sconfitte() -> None:
    memoria = tendenze.calcola(_storico_finto())
    crisi = memoria.in_crisi()
    assert crisi, "nessuna squadra in crisi rilevata"
    assert crisi[0].nome == "Sfigati FC", crisi[0].nome
    assert crisi[0].striscia_sconfitte == 4, crisi[0].striscia_sconfitte
    print(f"  ok  crisi rilevata: {crisi[0].nome}, {crisi[0].striscia_sconfitte} sconfitte")


def test_digiuno_gol() -> None:
    memoria = tendenze.calcola(_storico_finto())
    secche = memoria.a_secco()
    assert secche, "nessun digiuno rilevato"
    assert secche[0].nome == "Sfigati FC", secche[0].nome
    assert secche[0].digiuno_gol == 4, secche[0].digiuno_gol
    print(f"  ok  digiuno rilevato: {secche[0].nome}, {secche[0].digiuno_gol} giornate")


def test_striscia_gol_giocatore() -> None:
    memoria = tendenze.calcola(_storico_finto())
    in_gol = memoria.in_striscia_gol()
    nomi = [g.nome for g in in_gol]
    assert "Rossi" in nomi, nomi
    rossi = next(g for g in in_gol if g.nome == "Rossi")
    assert rossi.striscia_gol == 4, rossi.striscia_gol
    assert rossi.gol == 4, rossi.gol
    print(f"  ok  striscia gol: {rossi.nome}, {rossi.striscia_gol} presenze, {rossi.gol} gol")


def test_capocannoniere() -> None:
    memoria = tendenze.calcola(_storico_finto())
    bomber = memoria.capocannoniere()
    assert bomber is not None
    assert bomber.nome == "Rossi", bomber.nome
    print(f"  ok  capocannoniere: {bomber.nome} con {bomber.gol} gol")


def test_serie_positiva() -> None:
    memoria = tendenze.calcola(_storico_finto())
    serie = memoria.in_serie_positiva()
    nomi = [s.nome for s in serie]
    assert "Muro Difensivo" in nomi, nomi
    print(f"  ok  serie positiva: {serie[0].nome}, {serie[0].striscia_vittorie} vittorie")


def test_storia_insufficiente() -> None:
    """Con una sola giornata nessuna striscia deve scattare."""
    singola = {1: _storico_finto()[1]}
    memoria = tendenze.calcola(singola)
    assert not memoria.abbastanza_storia
    assert not memoria.in_crisi()
    assert not memoria.in_striscia_gol()
    print("  ok  con 1 giornata nessuna striscia viene inventata")


def test_trafiletti_usano_la_memoria() -> None:
    storia = _storico_finto()
    memoria = tendenze.calcola(storia)
    minori = prompt.partite_minori(storia[4])
    testi = prompt.trafiletti(minori, memoria, {}, seme=4)
    assert testi, "nessun trafiletto generato"
    titoli = [t for t, _ in testi]
    assert len(titoli) == len(set(titoli)), "titoli ripetuti"
    print(f"  ok  trafiletti con memoria ({len(testi)}):")
    for titoletto, testo in testi:
        print(f'        "{titoletto}" - {testo}')


def test_titolo_usa_la_memoria() -> None:
    storia = _storico_finto()
    memoria = tendenze.calcola(storia)
    principale, sottotitolo = prompt.titolo(storia[4], memoria)
    assert "SFIGATI FC" in principale, principale
    assert "quarta" in sottotitolo.lower(), sottotitolo
    print(f'  ok  titolo: "{principale}" / "{sottotitolo}"')


def test_confronto_senza_memoria() -> None:
    """Senza memoria i trafiletti perdono gli angoli storici."""
    storia = _storico_finto()
    minori = prompt.partite_minori(storia[4])
    con = prompt.trafiletti(minori, tendenze.calcola(storia), {}, seme=4)
    senza = prompt.trafiletti(minori, None, {}, seme=4)
    assert con != senza, "la memoria non sta cambiando nulla"
    print("  ok  la memoria cambia effettivamente l'esito")
    print(f"        senza memoria: {senza[0][0]}")
    print(f"        con memoria:   {con[0][0]}")


def main() -> int:
    prove = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    falliti = 0
    for prova in prove:
        try:
            prova()
        except AssertionError as errore:
            falliti += 1
            print(f"  FALLITO  {prova.__name__}: {errore}")
    print(f"\n{len(prove) - falliti}/{len(prove)} prove superate")
    return 1 if falliti else 0


if __name__ == "__main__":
    raise SystemExit(main())
