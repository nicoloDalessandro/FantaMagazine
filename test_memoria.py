"""Verifica della vista sulla memoria: che cosa ricorda e che cosa usa la pagina.

La vista risponde a una domanda sola — la storia pesa davvero su quello che si
legge? — e una risposta sbagliata sarebbe peggio di nessuna. Qui si controlla
che ogni richiamo citi un testo che in pagina c'è davvero, nella sezione
dichiarata, e che togliendo la memoria quel testo sparisca.

    python test_memoria.py
"""

from __future__ import annotations

import contextlib
import io
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from fantamagazine import prompt, resoconto, servizio, tendenze
from fantamagazine.analysis import Formazione, Giocatore, Partita, RigaClassifica
from fantamagazine.tendenze import Memoria, StoricoGiocatore, StoricoSquadra
from test_prompt import _giornata_ricca
from test_tendenze import _storico_finto

# Classifica finta per le quattro squadre dello storico: le prime due appaiate,
# così il pezzo sulla classifica lascia fuori una squadra in crisi da citare.
PUNTI = {"Bomber United": 12, "Muro Difensivo": 12, "Media Mediocre": 1, "Sfigati FC": 0}


def _tabella(punti: dict[str, int]) -> list[RigaClassifica]:
    return [
        RigaClassifica(squadra=nome, punti=valore, giocate=4, fantapunti=300.0 - indice * 10)
        for indice, (nome, valore) in enumerate(punti.items())
    ]


def _componi(partite, tabella, giornata, memoria, seme) -> prompt.PrimaPagina:
    return prompt.componi(
        partite=partite, tabella=tabella, giornata=giornata, stagione="2026-27",
        data="15 settembre 2026", testata="LA GAZZETTA DI PROVA", memoria=memoria, seme=seme,
    )


def _giornata_della_memoria() -> tuple[list[Partita], Memoria]:
    """Una giornata in cui ogni partita ha come angolo più forte un fatto del passato.

    Senza classifica non esistono vetta né zone basse, che verrebbero prima:
    così nei trafiletti finiscono prima vittoria, prima sconfitta, primo
    pareggio, serie positiva e crisi, e nel racconto un digiuno di gol.
    """

    def formazione(nome: str, totale: float, gol: int = 0, in_campo: int = 11) -> Formazione:
        giocatori = [Giocatore(nome=f"{nome}{i}", squadra_reale="TST", voto=6.0, fantavoto=6.0)
                     for i in range(in_campo)]
        if gol:
            giocatori[0] = Giocatore(nome=f"Bomber {nome}", squadra_reale="TST", voto=7.0,
                                     fantavoto=7.0 + 3 * gol, gol=gol)
        return Formazione(squadra=nome, modulo=433, totale=totale, giocatori=giocatori)

    partite = [
        # In apertura per la formazione incompleta: Omega non segna da due giornate.
        Partita(formazione("Omega", 64.0), formazione("Sigma", 60.0, in_campo=10), "0-0"),
        Partita(formazione("Alfa", 72.0, gol=1), formazione("Beta", 66.0), "1-0"),
        Partita(formazione("Gamma", 75.0, gol=2), formazione("Delta", 69.0, gol=1), "2-1"),
        Partita(formazione("Epsilon", 74.0, gol=1), formazione("Zeta", 67.0), "1-0"),
        Partita(formazione("Eta", 79.0, gol=2), formazione("Theta", 61.0), "2-0"),
        Partita(formazione("Iota", 70.0, gol=1), formazione("Kappa", 70.5, gol=1), "1-1"),
    ]
    storia = {
        "Omega": (["V", "N", "N"], [2, 0, 0]), "Sigma": (["P", "V", "N"], [1, 2, 0]),
        "Alfa": (["P", "P", "V"], [0, 1, 1]), "Beta": (["V", "N", "P"], [2, 1, 0]),
        "Gamma": (["V", "V", "V"], [2, 2, 2]), "Delta": (["V", "V", "P"], [1, 2, 1]),
        "Epsilon": (["V", "V", "V"], [1, 1, 1]), "Zeta": (["P", "P", "P"], [1, 1, 0]),
        "Eta": (["V", "P", "V"], [2, 0, 2]), "Theta": (["P", "P", "P"], [0, 1, 0]),
        "Iota": (["V", "P", "N"], [1, 0, 1]), "Kappa": (["V", "V", "N"], [2, 1, 1]),
    }
    memoria = Memoria(
        squadre={
            nome: StoricoSquadra(nome=nome, esiti=esiti, fantapunti=[70.0] * 3, gol_fatti=gol,
                                 giornate=[1, 2, 3])
            for nome, (esiti, gol) in storia.items()
        },
        giocatori={},
        giornate=3,
        numeri_giornate=[1, 2, 3],
    )
    return partite, memoria


# Ogni combinazione di sezione e fatto che la pagina sa scrivere.
COMBINAZIONI = {
    ("titolo", "sconfitte"), ("titolo", "vittorie"),
    ("racconto", "sconfitte"), ("racconto", "vittorie"), ("racconto", "digiuno"),
    ("dietro_i_numeri", "sconfitte"), ("dietro_i_numeri", "vittorie"),
    ("trafiletti", "prima_vittoria"), ("trafiletti", "prima_sconfitta"),
    ("trafiletti", "primo_pareggio"), ("trafiletti", "vittorie"), ("trafiletti", "sconfitte"),
}


def _casi():
    """Pagine con e senza memoria: lo storico finto, la giornata ricca e quella della memoria."""
    storia = _storico_finto()
    for giornata in range(1, 5):
        passato = {n: p for n, p in storia.items() if n <= giornata}
        memoria = tendenze.calcola(passato)
        for seme in range(40):
            yield f"finto g{giornata} s{seme}", storia[giornata], _tabella(PUNTI), giornata, memoria, seme

    partite, memoria, posizioni, _ = _giornata_ricca()
    ordine = sorted(posizioni, key=posizioni.get)
    tabella = _tabella({nome: 30 - i for i, nome in enumerate(ordine)})
    for seme in range(40):
        yield f"ricca s{seme}", partite, tabella, 3, memoria, seme

    partite, memoria = _giornata_della_memoria()
    for seme in range(40):
        yield f"memoria s{seme}", partite, [], 3, memoria, seme


def test_ogni_richiamo_si_legge_nella_sua_sezione() -> None:
    per_sezione: dict[str, int] = {}
    combinazioni: set[tuple[str, str]] = set()
    for nome, partite, tabella, giornata, memoria, seme in _casi():
        pagina = _componi(partite, tabella, giornata, memoria, seme)
        testo = prompt.renderizza(pagina)
        for r in pagina.richiami:
            per_sezione[r.sezione] = per_sezione.get(r.sezione, 0) + 1
            combinazioni.add((r.sezione, r.tipo))
            if r.sezione == "titolo":
                assert (r.titolo, r.testo) == (pagina.titolo, pagina.sottotitolo), (nome, r)
            elif r.sezione == "racconto":
                assert not r.titolo and any(r.testo in p for p in pagina.racconto), (nome, r)
            elif r.sezione == "dietro_i_numeri":
                assert not r.titolo and r.testo in pagina.pezzo_lungo[1], (nome, r)
            elif r.sezione == "trafiletti":
                assert (r.titolo, r.testo) in pagina.trafiletti, (nome, r)
            else:
                raise AssertionError(f"{nome}: sezione sconosciuta {r.sezione}")
            assert r.testo in testo and r.titolo in testo, f"{nome}: il richiamo non è nel prompt: {r}"

    mai_provate = COMBINAZIONI - combinazioni
    assert not mai_provate, f"combinazioni mai messe alla prova: {sorted(mai_provate)}"
    assert combinazioni <= COMBINAZIONI, f"combinazioni inattese: {sorted(combinazioni - COMBINAZIONI)}"
    print(f"  ok  {sum(per_sezione.values())} richiami, ciascuno nella sua sezione, "
          f"tutte le {len(COMBINAZIONI)} combinazioni di sezione e fatto")


def test_senza_memoria_i_testi_dei_richiami_spariscono() -> None:
    """Il richiamo dice «questo c'è grazie alla memoria»: senza, non deve esserci."""
    controllati = 0
    for nome, partite, tabella, giornata, memoria, seme in _casi():
        con = _componi(partite, tabella, giornata, memoria, seme)
        senza = _componi(partite, tabella, giornata, None, seme)
        assert senza.richiami == [], f"{nome}: richiami senza memoria: {senza.richiami}"
        testo_senza = prompt.renderizza(senza)
        for r in con.richiami:
            assert r.testo not in testo_senza, f"{nome}: «{r.testo}» c'è anche senza memoria"
            controllati += 1
    assert controllati, "nessun richiamo controllato"
    print(f"  ok  {controllati} testi nati dalla memoria, spariti tutti togliendola")


def test_ogni_richiamo_ha_la_sua_notizia() -> None:
    """Notizie e richiami usano le stesse soglie: nessun richiamo resta orfano."""
    for nome, partite, tabella, giornata, memoria, seme in _casi():
        pagina = _componi(partite, tabella, giornata, memoria, seme)
        vista = resoconto.componi(memoria, pagina)
        for r in pagina.richiami:
            notizia = [n for n in vista.notizie if (n.tipo, n.soggetto) == (r.tipo, r.squadra)]
            assert len(notizia) == 1, f"{nome}: richiamo senza notizia: {r}"
            assert r.sezione in notizia[0].sezioni, f"{nome}: notizia non segnata in {r.sezione}"
            assert notizia[0].valore == r.valore, f"{nome}: valori diversi: {notizia[0]} / {r}"
        for n in vista.notizie:
            if n.sezioni:
                assert any((r.tipo, r.squadra) == (n.tipo, n.soggetto) for r in pagina.richiami), n
    print("  ok  ogni richiamo ha la sua notizia, e ogni notizia in pagina il suo richiamo")


def test_prima_giornata_niente_passato() -> None:
    """All'esordio la memoria esiste ma non ha nulla di passato da offrire.

    I trafiletti raccontano comunque "prima vittoria", "falsa partenza" e
    "parte con un pari": sono angoli nati dalla memoria, ma dietro non c'è
    nessuna giornata passata, quindi non devono lasciare richiami. Senza
    classifica quegli angoli diventano i più forti e finiscono davvero in
    pagina, altrimenti la prova non li metterebbe alla prova.
    """
    partite, _ = _giornata_della_memoria()
    esordio = Memoria(giornate=1, numeri_giornate=[1])
    for p in partite:
        for squadra, fatti, subiti in ((p.casa.squadra, p.gol_casa, p.gol_trasferta),
                                       (p.trasferta.squadra, p.gol_trasferta, p.gol_casa)):
            esito = "V" if fatti > subiti else "P" if fatti < subiti else "N"
            esordio.squadre[squadra] = StoricoSquadra(
                nome=squadra, esiti=[esito], fantapunti=[70.0], gol_fatti=[fatti], giornate=[1]
            )

    storia = _storico_finto()
    casi = [(partite, [], esordio), (storia[1], [], tendenze.calcola({1: storia[1]})),
            (storia[1], _tabella(PUNTI), tendenze.calcola({1: storia[1]}))]
    titoletti = set()
    for gare, tabella, memoria in casi:
        for seme in range(20):
            pagina = _componi(gare, tabella, 1, memoria, seme)
            assert pagina.richiami == [], f"seme {seme}: richiami alla prima giornata: {pagina.richiami}"
            titoletti.update(t for t, _ in pagina.trafiletti)
        vista = resoconto.componi(memoria, pagina)
        assert vista.notizie == [], vista.notizie
        assert "prima giornata" in vista.sintesi, vista.sintesi

    # Gli angoli dell'esordio devono essere usciti davvero, o la prova è vuota.
    uscite = " ".join(titoletti)
    for traccia in (("PARTE COL PIEDE GIUSTO", "BUONA LA PRIMA", "C'È"),
                    ("FALSA PARTENZA", "PARTE IN SALITA", "SI ARRENDE"),
                    ("PARTE CON UN PARI", "PRIMO PUNTO")):
        assert any(t in uscite for t in traccia), f"angolo d'esordio mai uscito: {traccia}"
    print("  ok  prima giornata: angoli d'esordio in pagina, ma nessun richiamo e nessuna notizia")


def test_il_caso_noto() -> None:
    """Quattro giornate: Sfigati FC perde sempre, Muro Difensivo vince sempre, Rossi segna sempre."""
    storia = _storico_finto()
    memoria = tendenze.calcola(storia)
    pagina = _componi(storia[4], _tabella(PUNTI), 4, memoria, 4)
    vista = resoconto.componi(memoria, pagina)

    titolo = [r for r in pagina.richiami if r.sezione == "titolo"]
    assert titolo and (titolo[0].squadra, titolo[0].tipo, titolo[0].valore) == ("Sfigati FC", "sconfitte", 4)

    notizie = {(n.soggetto, n.tipo): n for n in vista.notizie}
    assert "titolo" in notizie[("Sfigati FC", "sconfitte")].sezioni
    assert notizie[("Sfigati FC", "digiuno")].fatto == "senza gol da 4 giornate"
    rossi = notizie[("Rossi", "gol_di_fila")]
    assert (rossi.squadra, rossi.valore, rossi.raccontabile, rossi.sezioni) == ("Bomber United", 4, False, [])
    # Sette notizie: due crisi, due serie positive, un digiuno, due bomber in serie.
    # In pagina la crisi di Sfigati FC (titolo), quella di Media Mediocre e la
    # serie di Muro Difensivo (racconto); Bomber United è raccontata dalla vetta.
    assert vista.sintesi.endswith("Conosce 7 notizie: 3 sono entrate in pagina."), vista.sintesi
    assert notizie[("Bomber United", "vittorie")].sezioni == []

    sfigati = next(s for s in vista.squadre if s.nome == "Sfigati FC")
    assert (sfigati.giornate, sfigati.esiti, sfigati.posizione) == ([1, 2, 3, 4], ["P"] * 4, 4)
    assert sfigati.serie == ["4 sconfitte di fila", "senza gol da 4 giornate"], sfigati.serie
    assert [s.nome for s in vista.squadre] == list(PUNTI), "le squadre non seguono la classifica"
    assert vista.giocatori[0].nome in {"Rossi", "Bianchi"} and vista.giocatori[0].gol == 4
    print(f"  ok  caso noto: {vista.sintesi}")


def test_serie_in_parole() -> None:
    casi = {
        ("V", "V"): ["2 vittorie di fila"],
        ("P", "P", "P"): ["3 sconfitte di fila"],
        ("V", "N"): ["imbattuta da 2 giornate"],
        ("P", "N"): ["senza vittorie da 2 giornate"],
        ("N", "V"): ["imbattuta da 2 giornate"],
        ("V", "P"): [],
    }
    for esiti, attese in casi.items():
        scheda = StoricoSquadra(nome="Prova", esiti=list(esiti), gol_fatti=[1] * len(esiti))
        assert resoconto._serie(scheda) == attese, (esiti, resoconto._serie(scheda))
    print(f"  ok  {len(casi)} andamenti descritti in parole")


def test_giornate_non_consecutive() -> None:
    """I numeri di giornata vengono dallo storico, non dalla posizione nell'elenco."""
    storia = _storico_finto()
    memoria = tendenze.calcola({3: storia[1], 5: storia[2]})
    assert memoria.numeri_giornate == [3, 5]
    assert memoria.squadre["Sfigati FC"].giornate == [3, 5]
    pagina = _componi(storia[2], _tabella(PUNTI), 5, memoria, 5)
    vista = resoconto.componi(memoria, pagina)
    assert vista.giornate == [3, 5] and "dalla 3 alla 5" in vista.sintesi, vista.sintesi
    assert all(s.giornate == [3, 5] for s in vista.squadre)
    print("  ok  giornate 3 e 5: numeri giusti in memoria e nel resoconto")


def test_memoria_costruita_a_mano() -> None:
    """Senza numeri di giornata si assumono le ultime, senza sfasare gli esiti."""
    memoria = Memoria(
        squadre={
            "Lunga": StoricoSquadra(nome="Lunga", esiti=["V", "V", "V"]),
            "Corta": StoricoSquadra(nome="Corta", esiti=["P"]),
        },
        giocatori={"Solo": StoricoGiocatore(nome="Solo", squadra_reale="TST")},
        giornate=3,
    )
    pagina = prompt.PrimaPagina(
        testata="T", stagione="2026-27", giornata=3, data="", seme=3, titolo="", sottotitolo="",
        apertura="", racconto=[], risultati=[], classifica=[], pezzo_lungo=("", ""), trafiletti=[],
    )
    vista = resoconto.componi(memoria, pagina)
    schede = {s.nome: s for s in vista.squadre}
    assert schede["Lunga"].giornate == [1, 2, 3] and schede["Corta"].giornate == [3], schede
    assert all(s.posizione is None for s in vista.squadre)
    print("  ok  memoria senza numeri di giornata: esiti allineati alle ultime giornate")


def test_sintesi_al_singolare_e_al_plurale() -> None:
    def notizia(raccontabile: bool = True, sezioni: list[str] | None = None) -> resoconto.Notizia:
        return resoconto.Notizia("vittorie", "A", "A", 2, "2 vittorie di fila", raccontabile, sezioni or [])

    casi = [
        ([notizia(sezioni=["titolo"])], "Conosce una notizia, ed è entrata in pagina."),
        ([notizia(sezioni=["titolo"]), notizia()], "Conosce 2 notizie: una è entrata in pagina."),
        ([notizia(sezioni=["titolo"])] * 3, "Conosce 3 notizie: 3 sono entrate in pagina."),
        ([notizia(), notizia()], "Conosce 2 notizie, ma nessuna è entrata in pagina."),
        ([notizia(raccontabile=False)], "ma non è entrata in pagina. È la serie di un giocatore"),
        ([notizia(raccontabile=False)] * 2, "Sono tutte serie di giocatori"),
        ([], "Nessuna serie in corso e nessuna prima volta"),
    ]
    for elenco, atteso in casi:
        frase = resoconto._sintesi([1, 2, 3], elenco)
        assert atteso in frase, (atteso, frase)
    assert "giocatori" not in resoconto._sintesi([1, 2], [notizia(), notizia(raccontabile=False)])
    print(f"  ok  {len(casi)} sintesi con accordi giusti")


def test_regole_usano_le_soglie_del_motore() -> None:
    """Le regole descrivono il motore: se la soglia del titolo cambia, cambiano anche loro."""
    regole = dict(resoconto.REGOLE)
    assert f"almeno {prompt.SOGLIA_TITOLO} sconfitte" in regole["Titolo"]
    assert f"da {tendenze.SOGLIA_STRISCIA} in su" in regole["Il racconto"]
    assert f"da {tendenze.SOGLIA_DIGIUNO} giornate" in regole["Il racconto"]
    assert f"da {tendenze.SOGLIA_STRISCIA} in su" in regole["Trafiletti"]

    # E la soglia scritta è quella vera: una crisi appena sotto non va nel titolo.
    for lunghezza, nel_titolo in ((prompt.SOGLIA_TITOLO - 1, False), (prompt.SOGLIA_TITOLO, True)):
        memoria = Memoria(
            squadre={"Crisi": StoricoSquadra(nome="Crisi", esiti=["P"] * lunghezza)},
            giocatori={}, giornate=lunghezza,
        )
        richiami: list[prompt.Richiamo] = []
        prompt._titolo_completo(_storico_finto()[1], memoria, 0, richiami)
        assert bool(richiami) is nel_titolo, (lunghezza, richiami)
    print(f"  ok  regole scritte con le soglie vere (titolo da {prompt.SOGLIA_TITOLO})")


def test_riga_di_comando_mostra_la_memoria() -> None:
    import main

    storia = _storico_finto()
    memoria = tendenze.calcola(storia)
    pagina = _componi(storia[4], _tabella(PUNTI), 4, memoria, 4)
    risultato = servizio.Risultato(
        prompt=prompt.renderizza(pagina), pagina=pagina, lega="prova", nome_lega="Prova",
        competizione="1", nome_competizione="Campionato",
        memoria=resoconto.componi(memoria, pagina),
    )
    uscita, errori = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(uscita), contextlib.redirect_stderr(errori):
        main._stampa_memoria(risultato)
    testo = errori.getvalue()
    assert uscita.getvalue() == "", "la memoria non deve sporcare stdout, dove va il prompt"
    for atteso in ("MEMORIA", "In pagina grazie alla memoria", "perché Sfigati FC: 4 sconfitte di fila",
                   "non usata  Rossi (Bomber United): in gol da 4 presenze di fila",
                   "P P P P", "Regole: dove può entrare la memoria"):
        assert atteso in testo, f"manca «{atteso}» in:\n{testo}"
    print("  ok  --memoria scrive il resoconto su stderr e lascia stdout al prompt")


def main_test() -> int:
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
    raise SystemExit(main_test())
