"""Verifica delle scelte dell'utente: leghe, competizioni e nome del giornale.

    python test_impostazioni.py
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import main
from fantamagazine import api, auth, config, impostazioni, servizio
from fantamagazine.impostazioni import SceltaLega
from test_accesso import _cartella, _errore

COMPETIZIONI = [("1", "Campionato"), ("2", "Coppa")]


@contextlib.contextmanager
def _ambiente(**variabili):
    originali = {nome: os.environ.get(nome) for nome in variabili}
    for nome, valore in variabili.items():
        if valore is None:
            os.environ.pop(nome, None)
        else:
            os.environ[nome] = valore
    try:
        yield
    finally:
        for nome, valore in originali.items():
            if valore is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valore


class _ClientFinto:
    """Un client dell'API che conosce due competizioni e nessuna giornata disputata."""

    scaduti: set[str] = set()

    def __init__(self, token: str) -> None:
        if token.split()[-1] in self.scaduti:
            raise api.TokenScaduto("scaduto")
        self.token = token

    def calendario(self, _competizione):
        return []


@contextlib.contextmanager
def _api_finta():
    originali = (api.Client, api.competizioni_disponibili)
    api.Client = _ClientFinto
    api.competizioni_disponibili = lambda _client: list(COMPETIZIONI)
    try:
        yield
    finally:
        api.Client, api.competizioni_disponibili = originali


def _tre_leghe() -> None:
    auth.salva_leghe([
        {"alias": "a", "nome": "Lega A", "token": "eyJ.a"},
        {"alias": "b", "nome": "Lega B", "token": "eyJ.b"},
        {"alias": "c", "nome": "Lega C", "token": "eyJ.c"},
    ])


# --- Il file delle scelte ------------------------------------------------------------
def test_senza_file_tutto_attivo() -> None:
    with _cartella(), _ambiente(FANTA_TESTATA=None):
        assert impostazioni.carica() == {}
        scelta = impostazioni.scelta("qualunque")
        assert scelta == SceltaLega() and scelta.usa_competizione("12200")
        assert impostazioni.testata("lega-nuova", "Lega Nuova") == "LA GAZZETTA DI LEGA NUOVA"
    print("  ok  senza scelte salvate: leghe e competizioni attive, testata ricavata dal nome")


def test_testata_scelta_forzata_e_ricavata() -> None:
    with _cartella(), _ambiente(FANTA_TESTATA=None):
        impostazioni.salva({"a": SceltaLega(testata="La Gazzetta del Bar")})
        assert impostazioni.testata("a", "Lega A") == "La Gazzetta del Bar", "le maiuscole restano come scritte"
        assert impostazioni.testata("b", "Lega B") == "LA GAZZETTA DI LEGA B"
        with _ambiente(FANTA_TESTATA="Edizione Speciale"):
            assert impostazioni.testata("a", "Lega A") == "Edizione Speciale"
            assert impostazioni.testata("b", "Lega B") == "Edizione Speciale"
    print("  ok  testata: forzata dall'ambiente, poi scelta, poi ricavata")


def test_pulizia_della_testata() -> None:
    assert impostazioni.pulisci_testata('  Il "Corriere"\n della\tLega  ') == "Il 'Corriere' della Lega"
    assert len(impostazioni.pulisci_testata("X" * 200)) == impostazioni.MASSIMO_TESTATA
    assert impostazioni.pulisci_testata(None) == ""
    lunga = impostazioni.testata_predefinita("Una lega dal nome davvero lunghissimo e ancora più lungo")
    assert len(lunga) <= impostazioni.MASSIMO_TESTATA, lunga
    print("  ok  testata su una riga, senza virgolette doppie, al massimo 60 caratteri")


def test_file_rovinato_non_blocca() -> None:
    with _cartella():
        for contenuto in ("{rotto", "[]", '{"leghe": "no"}', '{"leghe": {"a": "no", "b": {"attiva": false}}}'):
            config.IMPOSTAZIONI_FILE.write_text(contenuto, encoding="utf-8")
            scelte = impostazioni.carica()
            assert "a" not in scelte, (contenuto, scelte)
        assert scelte["b"].attiva is False
    print("  ok  file delle scelte rovinato: si riparte dalle predefinite, senza errori")


def test_salvataggio_senza_residui() -> None:
    with _cartella() as cartella:
        impostazioni.salva({"z": SceltaLega(attiva=False), "a": SceltaLega(competizioni_escluse=["2"])})
        assert list(impostazioni.carica()) == ["a", "z"]
        assert not list(cartella.glob("*.tmp"))
    print("  ok  salvataggio in un colpo solo, leghe in ordine")


# --- Le scelte dal servizio ----------------------------------------------------------
def test_salva_impostazioni_valida_e_conserva() -> None:
    with _cartella():
        _tre_leghe()
        servizio.salva_impostazioni([
            {"alias": "a", "attiva": False, "testata": '  Il "Bar"  ', "competizioni_escluse": [12, "12", "7"]},
        ])
        assert impostazioni.carica()["a"] == SceltaLega(
            attiva=False, testata="Il 'Bar'", competizioni_escluse=["12", "7"]
        ), impostazioni.carica()["a"]
        # Ripulita già nel file, non solo quando la si rilegge.
        assert '"testata": "Il \'Bar\'"' in config.IMPOSTAZIONI_FILE.read_text(encoding="utf-8")

        servizio.salva_impostazioni([{"alias": "b", "testata": "B"}])
        assert impostazioni.carica()["a"].attiva is False, "le leghe non nominate conservano le scelte"

        guasti = [
            "non un elenco",
            [{"alias": "sconosciuta"}],
            ["a"],
            [{"alias": "a", "attiva": "no"}],
            [{"alias": "a", "testata": 5}],
            [{"alias": "a", "competizioni_escluse": "12"}],
            [{"alias": "a", "competizioni_escluse": [True]}],
            # Una voce buona seguita da una sbagliata: non si salva nemmeno la prima.
            [{"alias": "a", "testata": "CAMBIATA"}, {"alias": "sconosciuta"}],
            [{"alias": "a", "testata": "CAMBIATA"}, {"alias": "b", "attiva": "no"}],
        ]
        for guasto in guasti:
            errore = _errore(lambda g=guasto: servizio.salva_impostazioni(g))
            assert (errore.codice, errore.stato_http) == ("impostazioni_non_valide", 400), guasto
        assert impostazioni.carica()["a"].testata == "Il 'Bar'", "una richiesta sbagliata non deve cambiare nulla"
    print(f"  ok  scelte ripulite e salvate; {len(guasti)} richieste sbagliate rifiutate senza effetti")


def test_redazione_mostra_solo_le_scelte() -> None:
    with _cartella(), _api_finta(), _ambiente(FANTA_TESTATA=None):
        _tre_leghe()
        impostazioni.salva({
            "a": SceltaLega(testata="Il Bar", competizioni_escluse=["2"]),
            "b": SceltaLega(attiva=False),
        })

        stati = servizio.stato_leghe()
        assert [s.alias for s in stati] == ["a", "c"], [s.alias for s in stati]
        assert [c.id for c in stati[0].competizioni] == ["1"] and stati[0].testata == "Il Bar"
        assert [c.id for c in stati[1].competizioni] == ["1", "2"]

        tutti = servizio.stato_leghe(tutte=True)
        assert [(s.alias, s.attiva) for s in tutti] == [("a", True), ("b", False), ("c", True)]
        assert [(c.id, c.attiva) for c in tutti[0].competizioni] == [("1", True), ("2", False)]

        assert servizio.competizioni("a") == [("1", "Campionato")]
        assert servizio.competizioni("a", tutte=True) == COMPETIZIONI
        impostazioni.salva({"a": SceltaLega(competizioni_escluse=["1", "2"])})
        assert _errore(lambda: servizio.competizioni("a")).codice == "nessuna_competizione"
    print("  ok  redazione e riga di comando vedono solo leghe attive e competizioni non escluse")


def test_impostazioni_per_la_pagina() -> None:
    with _cartella(), _api_finta(), _ambiente(FANTA_TESTATA=None):
        _tre_leghe()
        impostazioni.salva({"a": SceltaLega(testata="Il Bar", competizioni_escluse=["2"])})
        _ClientFinto.scaduti = {"eyJ.c"}
        try:
            voci = {voce.alias: voce for voce in servizio.impostazioni_leghe()}
        finally:
            _ClientFinto.scaduti = set()

        a = voci["a"]
        assert (a.attiva, a.testata, a.testata_predefinita) == (True, "Il Bar", "LA GAZZETTA DI LEGA A")
        assert [(c.id, c.attiva) for c in a.competizioni] == [("1", True), ("2", False)]
        assert a.competizioni_escluse == ["2"]
        assert voci["b"].testata == "" and all(c.attiva for c in voci["b"].competizioni)
        assert voci["c"].codice_errore == "token_scaduto" and voci["c"].competizioni == []
    print("  ok  la pagina riceve ogni lega con scelte, testata suggerita ed eventuale errore")


# --- La riga di comando --------------------------------------------------------------
def _esegui(*argomenti: str) -> tuple[int, str]:
    originale = sys.argv
    sys.argv = ["main.py", *argomenti]
    errori = io.StringIO()
    try:
        with contextlib.redirect_stderr(errori), contextlib.redirect_stdout(io.StringIO()):
            return main.main(), errori.getvalue()
    finally:
        sys.argv = originale


def test_menu_con_le_sole_leghe_attive() -> None:
    offerte = []

    def chiedi(voci, _domanda):
        offerte.append([alias for alias, _ in voci])
        return voci[0][0]

    def ferma(*_a, **_k):
        raise servizio.ErroreServizio("fermo qui", "nessuna_giornata")

    with _cartella():
        _tre_leghe()
        impostazioni.salva({"b": SceltaLega(attiva=False)})
        originali = (main._chiedi, servizio.competizioni, servizio.genera)
        main._chiedi, servizio.genera = chiedi, ferma
        servizio.competizioni = lambda alias, tutte=False: [("1", "Campionato")]
        try:
            uscita, _ = _esegui()
            assert uscita == 1 and offerte[0] == ["a", "c"], offerte

            impostazioni.salva({alias: SceltaLega(attiva=False) for alias in "abc"})
            uscita, testo = _esegui()
            assert uscita == 1 and "escluso tutte le tue leghe" in testo, testo
        finally:
            main._chiedi, servizio.competizioni, servizio.genera = originali
    print("  ok  il menu propone solo le leghe attive, e spiega quando non ce n'è nessuna")


def test_imposta_testata_da_riga_di_comando() -> None:
    with _cartella(), _ambiente(FANTA_TESTATA=None):
        _tre_leghe()
        impostazioni.salva({"a": SceltaLega(competizioni_escluse=["2"])})
        uscita, testo = _esegui("--imposta-testata", "a", "La Voce del Bar")
        assert uscita == 0 and "La Voce del Bar" in testo, testo
        assert impostazioni.carica()["a"] == SceltaLega(testata="La Voce del Bar", competizioni_escluse=["2"])

        uscita, _ = _esegui("--imposta-testata", "a", "")
        assert uscita == 0 and impostazioni.testata("a", "Lega A") == "LA GAZZETTA DI LEGA A"

        uscita, testo = _esegui("--imposta-testata", "inesistente", "X")
        assert uscita == 2 and "inesistente" in testo, (uscita, testo)
    print("  ok  --imposta-testata salva, torna alla predefinita, rifiuta leghe sconosciute")


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
