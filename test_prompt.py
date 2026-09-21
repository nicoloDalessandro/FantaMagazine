"""Verifica della struttura del prompt e della lingua italiana.

Controlla le cose che a occhio sfuggono: che nessuna squadra resti fuori dalla
pagina, che non compaiano doppi punti dopo i cognomi abbreviati, e che la
testata cambi davvero da lega a lega.

    python test_prompt.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Gli output contengono accenti: senza questo, su console Windows con code page
# legacy diventano illeggibili.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from fantamagazine import prompt, tendenze
from fantamagazine.analysis import Formazione, Giocatore, Partita, RigaClassifica
from test_tendenze import _formazione, _storico_finto

SQUADRE = ["Sfigati FC", "Bomber United", "Muro Difensivo", "Media Mediocre"]


def _pagina(testata: str = "LA GAZZETTA DI PROVA") -> str:
    storia = _storico_finto()
    memoria = tendenze.calcola(storia)
    tabella = [
        RigaClassifica(squadra=nome, punti=3 * (4 - i), giocate=4, fantapunti=70.0 + i)
        for i, nome in enumerate(SQUADRE)
    ]
    return prompt.costruisci(
        partite=storia[4],
        tabella=tabella,
        giornata=4,
        stagione="2026-27",
        data="8 settembre 2026",
        testata=testata,
        memoria=memoria,
    )


def test_tutte_le_squadre_sono_citate() -> None:
    pagina = _pagina()
    mancanti = [s for s in SQUADRE if s not in pagina]
    assert not mancanti, f"squadre assenti dalla pagina: {mancanti}"
    print(f"  ok  tutte le {len(SQUADRE)} squadre compaiono in pagina")


def _lega_grande() -> tuple[list[Partita], list[str]]:
    """Cinque partite, dieci squadre: come una lega vera.

    Con sole quattro squadre il racconto le copre tutte da solo, e la garanzia
    di copertura non verrebbe messa alla prova.
    """
    nomi = [f"Squadra {chr(65 + i)}" for i in range(10)]
    partite = []
    for i in range(0, 10, 2):
        casa = Formazione(
            squadra=nomi[i],
            modulo=433,
            totale=70.0 + i,
            giocatori=[
                Giocatore(nome=f"Bomber{i}", squadra_reale="TST", voto=7.0,
                          fantavoto=10.0, gol=1),
                *[Giocatore(nome=f"Tale{i}_{j}", squadra_reale="TST", voto=6.0,
                            fantavoto=6.0) for j in range(10)],
            ],
        )
        via = Formazione(
            squadra=nomi[i + 1],
            modulo=442,
            totale=66.0 + i,
            giocatori=[
                Giocatore(nome=f"Punta{i}", squadra_reale="TST", voto=6.5,
                          fantavoto=9.5, gol=1),
                *[Giocatore(nome=f"Altro{i}_{j}", squadra_reale="TST", voto=6.0,
                            fantavoto=6.0) for j in range(10)],
            ],
        )
        partite.append(Partita(casa=casa, trasferta=via, risultato="2-1"))
    return partite, nomi


def test_copertura_con_dieci_squadre() -> None:
    """Racconto e trafiletti insieme devono nominare tutte le squadre."""
    partite, nomi = _lega_grande()
    testo = " ".join(prompt.racconto(partite, None, seme=1))
    pezzi = prompt.trafiletti(prompt.partite_minori(partite), None, {}, seme=1)
    testo += " " + " ".join(f"{a} {b}" for a, b in pezzi)
    mancanti = [n for n in nomi if n.upper() not in testo.upper()]
    assert not mancanti, f"squadre mai nominate: {mancanti}"
    print(f"  ok  tutte le {len(nomi)} squadre citate fra apertura e trafiletti")


def test_una_partita_in_apertura() -> None:
    """Il racconto copre una sola gara; le altre vanno nei trafiletti."""
    partite, _ = _lega_grande()
    assert len(prompt.racconto(partite, None, seme=1)) == 1
    minori = prompt.partite_minori(partite)
    assert len(minori) == len(partite) - 1, f"{len(minori)} partite minori"
    apertura = prompt.partita_di_apertura(partite)
    assert apertura not in minori, "la gara di apertura ricompare fra le minori"
    print(f"  ok  1 gara in apertura e {len(minori)} nei trafiletti")


def test_un_trafiletto_per_partita() -> None:
    partite, _ = _lega_grande()
    minori = prompt.partite_minori(partite)
    pezzi = prompt.trafiletti(minori, None, {}, seme=1)
    assert len(pezzi) == len(minori), f"{len(pezzi)} trafiletti per {len(minori)} gare"
    print(f"  ok  {len(pezzi)} trafiletti per {len(minori)} partite, uno a testa")


def test_angoli_tutti_diversi() -> None:
    """Il difetto segnalato: due trafiletti che dicono la stessa cosa.

    Non basta che cambino le squadre: devono cambiare le parole.
    """
    partite, _ = _lega_grande()
    minori = prompt.partite_minori(partite)
    for seme in range(40):
        _verifica_angoli_diversi(prompt.trafiletti(minori, None, {}, seme=seme), seme)
    print("  ok  su 40 semi i trafiletti hanno sempre formulazioni diverse")


def _verifica_angoli_diversi(pezzi: list[tuple[str, str]], seme: int) -> None:
    titoli = [t for t, _ in pezzi]
    assert len(titoli) == len(set(titoli)), f"seme {seme}: titoli ripetuti: {titoli}"

    # Due testi non devono condividere la stessa ossatura: si confrontano le
    # parole togliendo i nomi propri e i numeri.
    import re as _re

    def scheletro(testo: str) -> str:
        parole = [
            w.lower()
            for w in _re.findall(r"[A-Za-zÀ-ÿ]+", testo)
            if not w[0].isupper() and len(w) > 3
        ]
        return " ".join(parole)

    scheletri = [scheletro(c) for _, c in pezzi]
    duplicati = [s for s in scheletri if scheletri.count(s) > 1]
    assert not duplicati, f"seme {seme}: trafiletti con la stessa formulazione: {duplicati[:2]}"


def test_pezzo_lungo_parla_di_classifica() -> None:
    """Con tutte le partite già coperte, il pezzo lungo guarda la classifica."""
    tabella = [
        RigaClassifica(squadra=f"Squadra {chr(65 + i)}", punti=10 - i, giocate=4,
                       fantapunti=240.0 - i * 5)
        for i in range(10)
    ]
    titoletto, testo = prompt.dietro_i_numeri(tabella, None, seme=1)
    assert titoletto == "DIETRO I NUMERI", titoletto
    assert len(testo) > 120, f"troppo corto: {len(testo)}"
    # Nessuna squadra deve comparire due volte nello stesso paragrafo.
    for riga in tabella:
        assert testo.count(riga.squadra) <= 1, f"{riga.squadra} citata due volte"
    print(f"  ok  pezzo lungo sulla classifica, {len(testo)} caratteri, senza ripetizioni")


def test_layout_trafiletti() -> None:
    """Il trafiletto lungo sta sopra i tre brevi."""
    pagina = _pagina()
    assert "SQUADRA PER SQUADRA" not in pagina, "la vecchia sezione a elenco è rimasta"
    posizione_lungo = pagina.find("TRAFILETTO LUNGO")
    posizione_brevi = pagina.find("TRAFILETTI BREVI")
    assert posizione_lungo != -1 and posizione_brevi != -1
    assert posizione_lungo < posizione_brevi, "ordine sbagliato in pagina"
    print("  ok  trafiletto lungo collocato sopra i brevi")


def test_niente_squadra_reale() -> None:
    """La squadra di Serie A del giocatore non va mai nominata."""
    pagina = _pagina()
    codici = re.findall(r"\((LAZ|COM|ROM|MIL|INT|NAP|JUV|ATA|FIO|MON|UDI|SAS|TST)\)", pagina)
    assert not codici, f"codici squadra trovati: {set(codici)}"
    print("  ok  nessun codice di squadra reale accanto ai giocatori")


def test_concordanza_marcatori() -> None:
    """Un marcatore vuole il singolare, due il plurale — con qualunque seme.

    Il test non cerca formule precise: con le scelte indipendenti per seme può
    uscire una qualsiasi delle varianti, e ciascuna deve concordare.
    """
    singolari = ("ci mette la firma", "trova il gol con", "si affida alla zampata di")
    plurali = ("costruisce il bottino con", "va a bersaglio con", "lo portano")

    for seme in range(40):
        partite, _ = _lega_grande()
        partite[0].casa.giocatori[1] = Giocatore(
            nome="Secondo", squadra_reale="TST", voto=7.0, fantavoto=10.0, gol=1
        )
        frasi = prompt.racconto(partite, None, seme=seme)[0].split(". ")

        due = [f for f in frasi if "Secondo" in f]
        assert due, f"seme {seme}: la frase con due marcatori non c'è"
        assert any(m in due[0] for m in plurali), f"seme {seme}: plurale mancante: {due[0]}"
        assert not any(m in due[0] for m in singolari), f"seme {seme}: singolare con due nomi"

        uno = [f for f in frasi if "Punta0" in f and "Squadra B" in f]
        assert uno, f"seme {seme}: la frase con un marcatore non c'è"
        assert any(m in uno[0] for m in singolari), f"seme {seme}: singolare mancante: {uno[0]}"
    print("  ok  concordanza giusta per uno e due marcatori su 40 semi")


def test_niente_trafiletto_marcatori() -> None:
    pagina = _pagina()
    assert "I MARCATORI" not in pagina, "il trafiletto marcatori doveva sparire"
    print("  ok  il trafiletto dei marcatori non c'è più")


def test_ce_il_racconto() -> None:
    pagina = _pagina()
    assert "IL RACCONTO" in pagina
    paragrafi = prompt.racconto(_storico_finto()[4], tendenze.calcola(_storico_finto()))
    assert paragrafi, "nessun paragrafo generato"
    assert len(paragrafi[0]) > 180, f"racconto troppo corto: {len(paragrafi[0])} caratteri"
    print(f"  ok  racconto presente, {len(paragrafi)} paragrafi, "
          f"{len(paragrafi[0])} caratteri il principale")


def test_testata_finisce_in_pagina() -> None:
    # Le testate scelte dall'utente si provano in test_impostazioni.py: qui
    # conta che quella ricevuta finisca davvero nel prompt.
    assert "LA GAZZETTA DEL SAGRATO" in _pagina("LA GAZZETTA DEL SAGRATO")
    assert "LA GAZZETTA DELLA TANA" in _pagina("LA GAZZETTA DELLA TANA")
    print("  ok  la testata scelta finisce davvero nel prompt")


def test_niente_doppi_punti() -> None:
    """I cognomi abbreviati ('Yeboah J.') non devono generare '..'."""
    pagina = _pagina()
    doppi = re.findall(r"[A-Za-z]\.\.(?!\.)", pagina)
    assert not doppi, f"doppi punti trovati: {doppi}"
    print("  ok  nessun doppio punto dopo i cognomi abbreviati")


def test_frase_non_raddoppia_il_punto() -> None:
    assert prompt._frase("Segna Yeboah J.") == "Segna Yeboah J."
    assert prompt._frase("Segna Rossi") == "Segna Rossi."
    print("  ok  la punteggiatura viene aggiunta solo quando serve")


def test_decimali_all_italiana() -> None:
    assert prompt._n(82.5) == "82,5"
    assert prompt._n(78.0) == "78"
    pagina = _pagina()
    assert "82.5" not in pagina, "trovato un decimale col punto anglosassone"
    print("  ok  i decimali usano la virgola")


def test_elenco_italiano() -> None:
    assert prompt._elenco(["A"]) == "A"
    assert prompt._elenco(["A", "B"]) == "A e B"
    assert prompt._elenco(["A", "B", "C"]) == "A, B e C"
    print("  ok  gli elenchi si chiudono con 'e', non con la virgola")


def test_nessuna_ripetizione_fra_sezioni() -> None:
    """Chi è nel racconto non torna nei trafiletti brevi.

    Era il difetto visibile in pagina: la squadra della notizia di apertura
    ricompariva in fondo con parole diverse.
    """
    partite, nomi = _lega_grande()
    testo_racconto = " ".join(prompt.racconto(partite, None, seme=1))
    pezzi = prompt.trafiletti(prompt.partite_minori(partite), None, {}, seme=1)
    testo_trafiletti = " ".join(f"{t} {c}" for t, c in pezzi).upper()

    ripetute = [
        nome
        for nome in nomi
        if nome in testo_racconto and nome.upper() in testo_trafiletti
    ]
    assert not ripetute, f"squadre ripetute fra racconto e trafiletti: {ripetute}"
    print("  ok  nessuna squadra dell'apertura torna nei trafiletti")


def test_apertura_fuori_dai_trafiletti() -> None:
    """La gara di apertura non deve avere anche un trafiletto."""
    partite, _ = _lega_grande()
    apertura = prompt.partita_di_apertura(partite)
    pezzi = prompt.trafiletti(prompt.partite_minori(partite), None, {}, seme=1)
    testo = " ".join(f"{a} {b}" for a, b in pezzi).upper()
    # Le due squadre dell'apertura possono comparire solo in classifica,
    # mai nei trafiletti brevi.
    for formazione in (apertura.casa, apertura.trasferta):
        assert formazione.squadra.upper() not in testo, (
            f"{formazione.squadra} è in apertura ma torna nei trafiletti"
        )
    print("  ok  le squadre dell'apertura non ricompaiono nei trafiletti")


def test_ogni_partita_offre_piu_angoli() -> None:
    """Una gara deve poter essere raccontata in più modi, non in uno solo."""
    partite, _ = _lega_grande()
    angoli = prompt._angoli_partita(partite[0], None, {}, 0)
    assert len(angoli) > 1, "la partita offre un angolo solo"
    chiavi = [a[0] for a in angoli]
    assert len(chiavi) == len(set(chiavi)), "angoli duplicati nella stessa gara"
    print(f"  ok  una gara offre {len(angoli)} angoli distinti")


def test_nessun_angolo_resta_scoperto() -> None:
    """Anche con molte gare simili ciascuna trova un angolo libero."""
    partite, _ = _lega_grande()
    pezzi = prompt.trafiletti(partite, None, {}, seme=1)
    assert len(pezzi) == len(partite), (
        f"{len(pezzi)} trafiletti per {len(partite)} gare: qualcuna è rimasta senza"
    )
    print(f"  ok  tutte le {len(partite)} gare trovano un angolo libero")


def _partite(risultati: list[str]) -> list[Partita]:
    """Partite minimali con i risultati indicati, per provare la copertura."""
    fuori = []
    for indice, risultato in enumerate(risultati):
        casa = Formazione(squadra=f"Casa {indice}", modulo=433, totale=70.0 + indice,
                          giocatori=[Giocatore(nome=f"G{indice}a", squadra_reale="TST",
                                               voto=6.0, fantavoto=6.0)] * 11)
        via = Formazione(squadra=f"Via {indice}", modulo=442, totale=68.0 + indice,
                         giocatori=[Giocatore(nome=f"G{indice}b", squadra_reale="TST",
                                              voto=6.0, fantavoto=6.0)] * 11)
        fuori.append(Partita(casa=casa, trasferta=via, risultato=risultato))
    return fuori


def test_pareggi_non_restano_senza_trafiletto() -> None:
    """Il difetto visto in pagina: due pareggi e uno resta senza.

    Gli angoli dei pari erano uno solo, quindi la seconda gara pari non aveva
    piu' nulla da dire e sparival dalla pagina.
    """
    partite = _partite(["1-1", "0-0", "2-2", "3-3"])
    pezzi = prompt.trafiletti(partite, None, {}, seme=0)
    assert len(pezzi) == len(partite), (
        f"{len(pezzi)} trafiletti per {len(partite)} pareggi"
    )
    titoli = [t for t, _ in pezzi]
    assert len(titoli) == len(set(titoli)), f"titoli ripetuti: {titoli}"
    print(f"  ok  {len(pezzi)} pareggi, {len(pezzi)} trafiletti distinti")


def test_ogni_partita_ha_sempre_un_trafiletto() -> None:
    """Anche con gare identiche nessuna deve restare fuori dalla pagina."""
    for risultati in (
        ["1-0"] * 5,
        ["0-0"] * 5,
        ["2-1", "2-1", "1-1", "1-1", "0-0"],
    ):
        partite = _partite(risultati)
        pezzi = prompt.trafiletti(partite, None, {}, seme=0)
        assert len(pezzi) == len(partite), (
            f"{risultati}: {len(pezzi)} trafiletti su {len(partite)} gare"
        )
    print("  ok  nessuna gara resta senza trafiletto, nemmeno fra gare identiche")


def test_seme_stabile() -> None:
    """Lo stesso seme deve rigenerare esattamente lo stesso testo."""
    partite, _ = _lega_grande()
    a = prompt.trafiletti(prompt.partite_minori(partite), None, {}, seme=7)
    b = prompt.trafiletti(prompt.partite_minori(partite), None, {}, seme=7)
    assert a == b, "lo stesso seme produce testi diversi"
    print("  ok  stesso seme, stesso testo")


def test_seme_diverso_cambia_il_testo() -> None:
    """Semi diversi devono cambiare le formule, non i fatti."""
    partite, _ = _lega_grande()
    apertura = prompt.partita_di_apertura(partite)
    testi = {
        " ".join(prompt.racconto(partite, None, seme=s)) for s in range(6)
    }
    assert len(testi) > 1, "il seme non cambia nulla nel racconto"
    # I fatti restano gli stessi: il risultato compare in tutte le versioni.
    for testo in testi:
        assert apertura.risultato in testo, "il seme ha alterato i fatti"
    print(f"  ok  {len(testi)} formulazioni diverse a parita' di fatti")


def test_semi_producono_versioni_indipendenti() -> None:
    """Il difetto trovato usando l'interfaccia: sessanta semi, sei testi.

    Con `seme % len(opzioni)` i punti a due e tre formule si muovevano insieme,
    quindi contava solo il seme modulo 6. Qui si pretende molto più di sei
    versioni, e che nessun testo si ripeta per più di pochi semi.
    """
    from collections import Counter

    partite, _ = _lega_grande()
    versioni = Counter(" ".join(prompt.racconto(partite, None, seme=s)) for s in range(60))
    assert len(versioni) > 12, f"solo {len(versioni)} versioni su 60 semi"
    assert max(versioni.values()) <= 10, f"un testo si ripete {max(versioni.values())} volte"
    print(f"  ok  60 semi, {len(versioni)} versioni del racconto, al massimo "
          f"{max(versioni.values())} semi per versione")


def test_variante_stabile_fra_processi() -> None:
    """hash() sulle stringhe cambia a ogni avvio: la scelta non deve dipenderne."""
    import subprocess

    codice = (
        "from fantamagazine import prompt;"
        "print(prompt._variante(['alfa','beta','gamma','delta','epsilon'], 12345))"
    )
    esiti = {
        subprocess.run(
            [sys.executable, "-c", codice],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent),
            env={**__import__("os").environ, "PYTHONHASHSEED": str(salt)},
        ).stdout.strip()
        for salt in (1, 2, 3)
    }
    assert len(esiti) == 1, f"la scelta cambia fra processi: {esiti}"
    print("  ok  la stessa formula viene scelta in processi Python diversi")


def test_classifica_raccontata_senza_falsi() -> None:
    """Il pezzo sulla classifica deve dire il motivo vero dell'ordine in vetta.

    L'ordine è punti, poi differenza reti, poi fantapunti. In una lega vera era
    uscito "separate solo dai fantapunti" per due squadre appaiate in cui era
    prima quella con meno fantapunti, e "senza trovarsi in testa" per una squadra
    che in testa c'era, a pari punti. Ogni scenario qui ha il suo testo atteso,
    e in nessuno una squadra può essere nominata due volte.
    """

    def riga(nome: str, punti: int, differenza: int, fantapunti: float) -> RigaClassifica:
        return RigaClassifica(
            squadra=nome, punti=punti, giocate=3,
            gol_fatti=10 + differenza, gol_subiti=10, fantapunti=fantapunti,
        )

    scenari = {
        "pari, più fantapunti alla seconda": (
            [riga("Alfa", 6, 6, 166), riga("Beta", 6, 2, 166.5), riga("Gamma", 3, 0, 150)],
            ["soltanto la differenza reti"],
            ["dai fantapunti", "senza trovarsi in testa"],
        ),
        "pari, decide la differenza reti": (
            [riga("Alfa", 6, 6, 170), riga("Beta", 6, 2, 160), riga("Gamma", 3, 0, 150)],
            ["davanti per differenza reti"],
            ["dai fantapunti"],
        ),
        "pari, stessa differenza reti": (
            [riga("Alfa", 6, 3, 170), riga("Beta", 6, 3, 160), riga("Gamma", 3, 0, 150)],
            ["sono i fantapunti"],
            ["davanti per differenza reti"],
        ),
        "pari perfetto": (
            [riga("Alfa", 6, 3, 170), riga("Beta", 6, 3, 170), riga("Gamma", 3, 0, 150)],
            ["stessi fantapunti"],
            ["sono i fantapunti"],
        ),
        "pari, più fantapunti a una terza staccata": (
            [riga("Alfa", 6, 4, 160), riga("Beta", 6, 2, 150), riga("Gamma", 3, 0, 180)],
            ["differenza reti", "senza trovarsi in testa"],
            ["dai fantapunti", "sono i fantapunti"],
        ),
        "pari a tre, più fantapunti alla terza": (
            [riga("Alfa", 6, 4, 160), riga("Beta", 6, 3, 150), riga("Gamma", 6, 1, 180)],
            ["soltanto la differenza reti"],
            ["senza trovarsi in testa"],
        ),
        "un punto, più fantapunti alla seconda": (
            [riga("Alfa", 7, 3, 230.5), riga("Beta", 6, 2, 232.5), riga("Gamma", 3, 0, 200)],
            ["a un solo punto e ha prodotto più fantapunti"],
            ["senza trovarsi in testa"],
        ),
        "distacco largo, più fantapunti alla seconda": (
            [riga("Alfa", 9, 3, 200), riga("Beta", 6, 2, 210), riga("Gamma", 3, 0, 190)],
            ["che pure ha prodotto"],
            [],
        ),
        "distacco, più fantapunti alla prima": (
            [riga("Alfa", 9, 3, 220), riga("Beta", 6, 2, 200), riga("Gamma", 3, 0, 190)],
            ["capolista"],
            ["premia però"],
        ),
        "distacco, più fantapunti a una terza": (
            [riga("Alfa", 9, 3, 200), riga("Beta", 6, 2, 190), riga("Gamma", 3, 0, 230)],
            ["senza trovarsi in testa"],
            [],
        ),
    }

    ordine = lambda r: (-r.punti, -r.differenza_reti, -r.fantapunti)  # noqa: E731
    for nome, (tabella, attesi, vietati) in scenari.items():
        assert tabella == sorted(tabella, key=ordine), f"{nome}: tabella non ordinata"
        # Ogni seme può scegliere varianti diverse: il falso non deve comparire
        # in nessuna di esse.
        for seme in range(40):
            _, testo = prompt.dietro_i_numeri(tabella, None, seme=seme)
            for frammento in attesi:
                assert frammento in testo, f"{nome}, seme {seme}: manca «{frammento}»: {testo}"
            for frammento in vietati:
                assert frammento not in testo, (
                    f"{nome}, seme {seme}: non doveva dire «{frammento}»: {testo}"
                )
            for r in tabella:
                assert testo.count(r.squadra) <= 1, (
                    f"{nome}, seme {seme}: {r.squadra} nominata due volte: {testo}"
                )
    print(f"  ok  {len(scenari)} situazioni di classifica, 40 semi, nessuna affermazione falsa")


def _giornata_ricca() -> tuple[list[Partita], tendenze.Memoria, dict[str, int], list[str]]:
    """Partite costruite per accendere quasi tutti gli angoli.

    Vittorie di misura e dilaganti, esordi e strisce, pareggi a reti bianche e
    pieni di gol, una squadra incompleta, punteggi che iniziano per 0, 1 e 8
    (quelli che richiedono "lo" e "l'"), e una squadra il cui nome inizia per
    vocale, dove "a" seguito dal nome sarebbe un errore.
    """
    from fantamagazine.tendenze import Memoria, StoricoSquadra

    def formazione(nome: str, totale: float, gol: dict[str, int] | None = None,
                   in_campo: int = 11) -> Formazione:
        giocatori = [
            Giocatore(nome=marcatore, squadra_reale="TST", voto=7.0,
                      fantavoto=7.0 + 3 * reti, gol=reti)
            for marcatore, reti in (gol or {}).items()
        ]
        giocatori += [
            Giocatore(nome=f"{nome[:3]}{i}", squadra_reale="TST", voto=6.0, fantavoto=6.0)
            for i in range(in_campo - len(giocatori))
        ]
        return Formazione(squadra=nome, modulo=433, totale=totale, giocatori=giocatori)

    partite = [
        Partita(formazione("Alfa FC", 74.5, {"Rossi": 2}), formazione("Bravo United", 72.0), "2-1"),
        Partita(formazione("Charlie", 88.0, {"Verdi": 1}), formazione("Delta Team", 60.0), "1-0"),
        Partita(formazione("Echo", 90.0, {"Neri": 3}), formazione("Foxtrot", 58.0, in_campo=10), "8-0"),
        Partita(formazione("Golf Club", 70.0, {"Blu": 1}), formazione("Hotel", 70.0, {"Gialli": 1}), "1-1"),
        Partita(formazione("India", 60.0), formazione("Juliett", 60.0), "0-0"),
        Partita(formazione("Kilo", 76.0, {"Viola": 2}), formazione("Lima", 76.5, {"Rosa": 2}), "2-2"),
        Partita(formazione("Mike", 67.0, {"Oro": 1}), formazione("November", 66.0), "1-0"),
    ]
    esiti = {
        "Alfa FC": ["P", "V"], "Bravo United": ["V", "P"],
        "Charlie": ["V"], "Delta Team": ["P"],
        "Echo": ["V", "V", "V"], "Foxtrot": ["P", "P"],
        "Golf Club": ["V", "N"], "Hotel": ["V", "N"],
        "India": ["N"], "Juliett": ["N"],
        "Kilo": ["P", "N"], "Lima": ["V", "N"],
        "Mike": ["N", "V"], "November": ["N", "P"],
    }
    memoria = Memoria(
        squadre={nome: StoricoSquadra(nome=nome, esiti=e, fantapunti=[70.0] * len(e),
                                      gol_fatti=[1] * len(e))
                 for nome, e in esiti.items()},
        giocatori={},
        giornate=3,
    )
    ordine = ["Alfa FC", "Charlie", "Golf Club", "Echo", "Hotel", "Lima", "Kilo",
              "Mike", "India", "Juliett", "November", "Delta Team", "Foxtrot",
              "Bravo United"]
    posizioni = {nome: indice for indice, nome in enumerate(ordine, 1)}
    return partite, memoria, posizioni, list(esiti)


def test_regole_di_scrittura_in_ogni_variante() -> None:
    """Ogni formulazione possibile, per ogni angolo, rispetta le stesse regole.

    Con più varianti per angolo non basta guardare il testo di un seme: un
    errore può nascondersi in una variante che esce una volta su tre. Qui si
    generano gli angoli con quaranta semi e si controllano tutti.
    """
    partite, memoria, posizioni, _ = _giornata_ricca()
    articoli_sbagliati = re.compile(r"\b(il|sul|del|dal) (0|1|8|11)-|\bun 0-|\blo [2-79]-", re.I)
    numero_singolare = re.compile(r"\b1 (punti|fantapunti)\b")
    elisione_mancata = re.compile(r"\ba (Alfa|Echo|India)\b")
    controllati = 0

    for indice, partita in enumerate(partite):
        squadre = (partita.casa.squadra, partita.trasferta.squadra)
        for seme in range(40):
            for chiave, titoletto, testo in prompt._angoli_partita(
                partita, memoria, posizioni, indice, seme
            ):
                pezzo = f"{titoletto} {testo}"
                for squadra in squadre:
                    volte = pezzo.upper().count(squadra.upper())
                    assert volte >= 1, f"{chiave}: manca {squadra} in «{pezzo}»"
                    assert volte == 1, f"{chiave}: {squadra} nominata {volte} volte in «{pezzo}»"
                assert not testo[:1].isdigit(), f"{chiave}: il testo inizia con un numero: {testo}"
                assert not articoli_sbagliati.search(pezzo), f"{chiave}: articolo sbagliato: {pezzo}"
                assert not numero_singolare.search(pezzo), f"{chiave}: «1 punti»: {pezzo}"
                assert not elisione_mancata.search(pezzo), f"{chiave}: «a» davanti a vocale: {pezzo}"
                controllati += 1
    print(f"  ok  {controllati} formulazioni controllate: nomi, articoli, numeri, elisioni")


def test_trafiletti_cambiano_col_seme_ma_non_gli_angoli() -> None:
    """Il seme cambia le parole dei trafiletti, non la notizia che raccontano."""
    partite, memoria, posizioni, _ = _giornata_ricca()

    for indice, partita in enumerate(partite):
        chiavi = [a[0] for a in prompt._angoli_partita(partita, memoria, posizioni, indice, 0)]
        for seme in range(1, 25):
            altre = [a[0] for a in prompt._angoli_partita(partita, memoria, posizioni, indice, seme)]
            assert altre == chiavi, f"il seme {seme} ha cambiato gli angoli disponibili"

    pagine = {
        tuple(t for t, _ in prompt.trafiletti(partite, memoria, posizioni, seme))
        for seme in range(25)
    }
    assert len(pagine) > 5, f"i titoli dei trafiletti cambiano troppo poco: {len(pagine)} versioni"
    print(f"  ok  25 semi, {len(pagine)} versioni dei titoli; angoli sempre gli stessi")


def test_titoli_cambiano_col_seme() -> None:
    """Il titolo principale varia, e ogni variante dice la stessa cosa."""
    from fantamagazine.tendenze import Memoria, StoricoSquadra

    def squadra(nome: str, totale: float) -> Formazione:
        return Formazione(squadra=nome, modulo=433, totale=totale)

    storia = _storico_finto()
    crisi = tendenze.calcola(storia)
    titoli = {prompt.titolo(storia[4], crisi, s) for s in range(30)}
    assert len(titoli) > 1, "il titolo di crisi non cambia col seme"
    for principale, sottotitolo in titoli:
        assert "SFIGATI FC" in principale, principale
        assert "quarta" in sottotitolo.lower(), sottotitolo

    trasferta = [
        Partita(squadra("A", 60.0), squadra("B", 70.0), "0-1"),
        Partita(squadra("C", 61.0), squadra("D", 72.0), "0-2"),
    ]
    titoli = {prompt.titolo(trasferta, None, s) for s in range(30)}
    assert len(titoli) > 1, "il titolo sulle vittorie esterne non cambia col seme"

    serie = Memoria(
        squadre={"Corsara": StoricoSquadra(nome="Corsara", esiti=["V", "V", "V"])},
        giocatori={},
        giornate=3,
    )
    miste = [
        Partita(squadra("Corsara", 80.0), squadra("E", 60.0), "2-0"),
        Partita(squadra("F", 50.0), squadra("G", 70.0), "0-1"),
        Partita(squadra("H", 66.0), squadra("I", 66.0), "1-1"),
    ]
    titoli = {prompt.titolo(miste, serie, s) for s in range(30)}
    assert len(titoli) > 1, "il titolo sulla serie positiva non cambia col seme"
    for principale, sottotitolo in titoli:
        assert "CORSARA" in principale, principale
        assert "terza" in sottotitolo.lower(), sottotitolo

    senza_storia = {prompt.titolo(miste, None, s) for s in range(30)}
    assert len(senza_storia) > 1, "il titolo sul miglior punteggio non cambia col seme"
    for principale, _ in senza_storia:
        assert "CORSARA" in principale, principale
    print("  ok  il titolo cambia col seme e ogni variante conserva la notizia")


def test_articoli_davanti_ai_punteggi() -> None:
    casi = {
        ("2-1", ""): "il 2-1", ("1-1", ""): "l'1-1", ("0-0", ""): "lo 0-0",
        ("8-0", ""): "l'8-0", ("11-2", ""): "l'11-2", ("3-3", "su"): "sul 3-3",
        ("1-0", "su"): "sull'1-0", ("0-0", "su"): "sullo 0-0", ("1-2", "di"): "dell'1-2",
    }
    for (risultato, preposizione), atteso in casi.items():
        assert prompt._col_articolo(risultato, preposizione) == atteso, (risultato, preposizione)
    assert prompt._un_risultato("0-0") == "uno 0-0"
    assert prompt._un_risultato("2-2") == "un 2-2"
    assert prompt._punti(1) == "1 punto" and prompt._punti(0) == "0 punti"
    assert prompt._fantapunti(1) == "un fantapunto" and prompt._fantapunti(2.5) == "2,5 fantapunti"
    assert prompt._maiuscola("l'1-1 con Alfa FC") == "L'1-1 con Alfa FC"
    print("  ok  il 2-1, l'1-1, lo 0-0, sull'1-0; «1 punto», «un fantapunto»")


def test_racconto_senza_articoli_sbagliati() -> None:
    """Il racconto dei pareggi e delle goleade usava "sul" davanti a qualunque punteggio."""
    sbagliati = re.compile(r"\b(il|sul) (0|1|8|11)-", re.I)
    partite, memoria, _, _ = _giornata_ricca()
    for partita in partite:
        for seme in range(30):
            testo = " ".join(prompt.racconto([partita], memoria, seme))
            assert not sbagliati.search(testo), f"articolo sbagliato nel racconto: {testo}"
    print("  ok  nessun «sul 1-1» o «sul 0-0» nel racconto, su 30 semi")


def test_vetta_condivisa_non_contraddice_la_classifica() -> None:
    """Prima a pari punti: nessun trafiletto può dire che la vetta è sua e basta.

    Sulla pagina vera il pezzo sulla classifica diceva "dividono la vetta" e un
    trafiletto, nella stessa pagina, "la vetta è sua".
    """
    partite, memoria, posizioni, _ = _giornata_ricca()
    esclusiva = ("LA VETTA È SUA", "GUARDA TUTTI DALL'ALTO", "È PRIMA IN CLASSIFICA",
                 "VALE LA TESTA DELLA CLASSIFICA")
    condivisa = ("COABITAZIONE", "A PARI PUNTI", "NON DA SOLA")
    for seme in range(40):
        angoli = prompt._angoli_partita(partite[0], memoria, posizioni, 0, seme,
                                        vetta_condivisa=True)
        vetta = [f"{t} {x}".upper() for chiave, t, x in angoli if chiave == "vetta"]
        assert vetta, "la capolista non ha più l'angolo vetta"
        assert not any(f in vetta[0] for f in esclusiva), f"seme {seme}: {vetta[0]}"
        assert any(f in vetta[0] for f in condivisa), f"seme {seme}: vetta condivisa taciuta: {vetta[0]}"

        sola = prompt._angoli_partita(partite[0], memoria, posizioni, 0, seme)
        testo = [f"{t} {x}".upper() for chiave, t, x in sola if chiave == "vetta"][0]
        assert not any(f in testo for f in condivisa), f"seme {seme}: condivisa senza motivo: {testo}"
    print("  ok  vetta condivisa raccontata come tale, su 40 semi")


# --- La partita in apertura scelta da chi usa l'app ---------------------------------
def _tabella_semplice(nomi: list[str]) -> list[RigaClassifica]:
    return [
        RigaClassifica(squadra=nome, punti=3 * (len(nomi) - i), giocate=3, fantapunti=200.0 - i)
        for i, nome in enumerate(nomi)
    ]


def _pagina_con(partite: list[Partita], memoria=None, seme: int = 1, apertura=None, giornata: int = 3):
    nomi = [f.squadra for p in partite for f in (p.casa, p.trasferta)]
    return prompt.componi(partite, _tabella_semplice(nomi), giornata, "2026-27",
                          "21 settembre 2026", "LA PROVA", memoria, seme, apertura=apertura)


def test_partita_scelta_va_in_apertura() -> None:
    """Qualunque partita si scelga, racconto e titolo sono suoi e le altre restano coperte."""
    partite, nomi = _lega_grande()
    for gara in partite:
        pagina = _pagina_con(partite, apertura=gara, giornata=1)
        casa, fuori = gara.casa.squadra, gara.trasferta.squadra
        assert casa in pagina.racconto[0] and fuori in pagina.racconto[0], pagina.racconto[0]
        assert pagina.apertura == f"{casa} {gara.risultato} {fuori}", pagina.apertura
        assert pagina.apertura_scelta == casa, pagina.apertura_scelta
        assert casa.upper() in pagina.titolo or fuori.upper() in pagina.titolo, pagina.titolo
        assert len(pagina.trafiletti) == len(partite) - 1, f"{len(pagina.trafiletti)} trafiletti"
        testo = " ".join(pagina.racconto) + " " + " ".join(f"{a} {b}" for a, b in pagina.trafiletti)
        mancanti = [n for n in nomi if n.upper() not in testo.upper()]
        assert not mancanti, f"con {casa} in apertura restano fuori: {mancanti}"
    print(f"  ok  ognuna delle {len(partite)} partite, scelta, va in titolo e racconto; le altre nei trafiletti")


def test_senza_scelta_la_pagina_decide_da_sola() -> None:
    """Il comportamento di sempre, e i campi nuovi non finiscono nel prompt."""
    partite, _ = _lega_grande()
    pagina = _pagina_con(partite, giornata=1)
    automatica = prompt.partita_di_apertura(partite)
    assert pagina.apertura_scelta == ""
    assert pagina.apertura.startswith(automatica.casa.squadra), pagina.apertura
    assert [(v.casa, v.trasferta, v.risultato) for v in pagina.partite] == [
        (p.casa.squadra, p.trasferta.squadra, p.risultato) for p in partite
    ]
    # L'elenco delle partite e la scelta servono all'interfaccia: il prompt che
    # va al modello deve restare lo stesso, con o senza.
    prima = prompt.renderizza(pagina)
    pagina.partite, pagina.apertura_scelta = [], "Qualcuno"
    assert prompt.renderizza(pagina) == prima, "i campi dell'interfaccia sono finiti nel prompt"
    print("  ok  senza scelta decide la pagina; elenco e scelta non toccano il prompt")


def _giornate_con_una_crisi() -> dict[int, list[Partita]]:
    """Tre giornate: Beta perde sempre con Alfa, Gamma e Delta si alternano.

    Una sola striscia da titolo - la crisi di Beta, con la serie di Alfa - e una
    partita, Gamma-Delta, che con quella striscia non c'entra niente.
    """
    esiti = {1: ("1-1", 66.0, 66.5), 2: ("2-1", 72.0, 67.0), 3: ("0-1", 64.0, 71.0)}
    return {
        numero: [
            Partita(casa=_formazione("Alfa", 76.0, marcatore=f"Punta{numero}", gol=2),
                    trasferta=_formazione("Beta", 60.0), risultato="2-0"),
            Partita(casa=_formazione("Gamma", gamma), trasferta=_formazione("Delta", delta),
                    risultato=risultato),
        ]
        for numero, (risultato, gamma, delta) in esiti.items()
    }


def test_la_memoria_nel_titolo_della_partita_scelta() -> None:
    """Una striscia entra nel titolo solo se è di chi gioca la partita scelta."""
    giornate = _giornate_con_una_crisi()
    memoria = tendenze.calcola(giornate)
    partite = giornate[3]
    alfa_beta, gamma_delta = partite

    automatica = _pagina_con(partite, memoria)
    assert "BETA" in automatica.titolo, automatica.titolo

    neutra = _pagina_con(partite, memoria, apertura=gamma_delta)
    assert "GAMMA" in neutra.titolo or "DELTA" in neutra.titolo, neutra.titolo
    assert "BETA" not in neutra.titolo and "ALFA" not in neutra.titolo, neutra.titolo
    assert not [r for r in neutra.richiami if r.sezione == "titolo"], "titolo attribuito alla memoria"

    for seme in range(8):
        crisi = _pagina_con(partite, memoria, seme=seme, apertura=alfa_beta)
        # Alfa è in serie e Beta in crisi: vale la stessa precedenza del titolo
        # automatico, prima la crisi.
        assert "BETA" in crisi.titolo, crisi.titolo
        tracce = [r for r in crisi.richiami if r.sezione == "titolo"]
        assert [(r.tipo, r.squadra, r.valore) for r in tracce] == [("sconfitte", "Beta", 3)], tracce
        assert tracce[0].titolo == crisi.titolo and tracce[0].testo == crisi.sottotitolo
    print("  ok  la striscia di chi gioca finisce nel titolo, con la sua traccia; quella di altri no")


def test_titoli_della_partita_per_ogni_esito() -> None:
    """Pareggio, dominio, vittoria sul filo, in casa, in trasferta: sempre più di una formula."""
    def squadra(nome: str, totale: float) -> Formazione:
        return Formazione(squadra=nome, modulo=433, totale=totale)

    casi = {
        "pareggio": Partita(squadra("Pari Uno", 68.0), squadra("Pari Due", 67.0), "1-1"),
        "dominio": Partita(squadra("Forte", 85.0), squadra("Debole", 62.0), "3-0"),
        "sul filo": Partita(squadra("Vince Poco", 68.0), squadra("Perde Poco", 66.0), "1-0"),
        "in casa": Partita(squadra("Padroni", 74.0), squadra("Ospiti", 66.0), "2-1"),
        "in trasferta": Partita(squadra("Casalinghi", 63.0), squadra("Corsari", 72.0), "0-2"),
        "zero a zero": Partita(squadra("Muro A", 60.0), squadra("Muro B", 61.0), "0-0"),
    }
    # "un 1-0" è giusto; sbagliati sono "il 1-0", "sul 0-0", "un 0-0" e i doppi punti.
    sbagliati = re.compile(r"\b(il|sul) (0|1|8|11)-|\bun 0-|\.\.", re.I)
    for nome, gara in casi.items():
        titoli = set()
        for seme in range(12):
            principale, sottotitolo = prompt._titolo_partita(gara, None, seme)
            titoli.add(principale)
            squadre = (gara.casa.squadra.upper(), gara.trasferta.squadra.upper())
            assert any(s in principale for s in squadre), f"{nome}: {principale}"
            assert principale == principale.upper(), f"{nome}: titolo non in maiuscolo"
            assert sottotitolo and sottotitolo[0].isupper(), f"{nome}: {sottotitolo!r}"
            assert not sbagliati.search(sottotitolo), f"{nome}: {sottotitolo}"
        # "Scrivila diversamente" riprova finché il titolo cambia: con una
        # formula sola girerebbe a vuoto.
        assert len(titoli) > 1, f"{nome}: un solo titolo su 12 semi"
    print(f"  ok  {len(casi)} esiti, ciascuno con più formule e punteggi con l'articolo giusto")


def test_trova_partita_da_una_delle_due_squadre() -> None:
    partite, _ = _lega_grande()
    terza = partite[2]
    assert prompt.trova_partita(partite, terza.casa.squadra) is terza
    assert prompt.trova_partita(partite, terza.trasferta.squadra) is terza
    assert prompt.trova_partita(partite, f"  {terza.trasferta.squadra.upper()} ") is terza
    assert prompt.trova_partita(partite, "Nessuno FC") is None
    assert prompt.trova_partita(partite, "   ") is None
    print("  ok  la partita si trova da casa o trasferta, senza badare a maiuscole e spazi")


def test_partita_di_un_altra_giornata_rifiutata() -> None:
    partite, _ = _lega_grande()
    estranea, _ = _lega_grande()  # stesse squadre, ma oggetti di un'altra giornata
    try:
        _pagina_con(partite, apertura=estranea[0], giornata=1)
    except ValueError:
        print("  ok  una partita che non è della giornata viene rifiutata")
        return
    raise AssertionError("una partita estranea è finita in apertura")


def test_generazione_con_partita_scelta() -> None:
    """Dal servizio: la squadra si trova, e una squadra inesistente elenca le partite vere."""
    from datetime import date

    from fantamagazine import auth, servizio
    from test_accesso import _cartella, _errore
    from test_listone import _cache, _servizio_finto

    with _cartella(), _cache(), _servizio_finto():
        auth.salva_leghe([{"alias": "mia-lega", "nome": "Mia Lega", "token": "eyJ.finto"}])
        risultato = servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16), apertura=" ospiti fc ")
        assert risultato.pagina.apertura_scelta == "Casa FC", risultato.pagina.apertura_scelta
        assert "CASA FC" in risultato.pagina.titolo or "OSPITI FC" in risultato.pagina.titolo

        errore = _errore(lambda: servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16),
                                                 apertura="Nessuno"))
        assert errore.codice == "partita_sconosciuta" and errore.stato_http == 404, errore.codice
        assert "Casa FC - Ospiti FC" in errore.messaggio, errore.messaggio
    print("  ok  il servizio trova la partita dalla squadra, e se non c'è elenca quelle giocate")


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
