"""Verifica della cache del listone: senza rete e senza account.

Il listone è la risposta più pesante dell'API e cambia di rado, quindi viene
tenuto da parte. Qui si controlla che venga riletto invece di riscaricarlo, che
si aggiorni quando glielo si chiede, e soprattutto che si riscarichi da solo
quando in campo compare un giocatore che non conosce: altrimenti in pagina
finirebbe un codice al posto del nome.

    python test_listone.py
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from fantamagazine import api, auth, listone, servizio
from fantamagazine.analysis import Formazione, Giocatore, Partita
from test_accesso import _cartella, _errore

ROSA = [
    {"id": 1, "name": "Radunovic", "stnme": "CAG"},
    {"id": 2, "name": "Yeboah J.", "stnme": "GEN"},
]
ARRIVATO = {"id": 999, "name": "Colpo Di Mercato", "stnme": "NAP"}


class ClientFinto:
    """Un client che conta quante volte gli viene chiesto il listone."""

    listone_chiesto = 0
    con_arrivato = False

    def __init__(self, token: str = "eyJ.finto") -> None:
        self.token = token

    def giocatori(self):
        ClientFinto.listone_chiesto += 1
        return [*ROSA, ARRIVATO] if ClientFinto.con_arrivato else list(ROSA)

    def squadre(self):
        return [{"id": 1, "n": "Casa FC"}, {"id": 2, "n": "Ospiti FC"}]

    def calendario(self, _competizione):
        return [{
            "matchDay": 1, "championshipMatchDay": 1, "calculated": True,
            "matches": [{"tIdH": 1, "tIdA": 2, "result": "1-0",
                         "standingPtH": 3, "standingPtA": 0, "ptH": 70.0, "ptA": 60.0}],
        }]


@contextlib.contextmanager
def _cache():
    originale = listone.CACHE
    ClientFinto.listone_chiesto, ClientFinto.con_arrivato = 0, False
    with tempfile.TemporaryDirectory() as cartella:
        listone.CACHE = Path(cartella) / "listone"
        try:
            yield listone.CACHE
        finally:
            listone.CACHE = originale


# --- La cache -----------------------------------------------------------------------
def test_scaricato_una_volta_e_riletto() -> None:
    with _cache() as cartella:
        client = ClientFinto()
        primo = listone.carica(client, "mia-lega")
        assert primo == {1: ("Radunovic", "CAG"), 2: ("Yeboah J.", "GEN")}, primo
        assert (cartella / "mia-lega.json").exists() and not list(cartella.glob("*.tmp"))

        secondo = listone.carica(client, "mia-lega")
        assert secondo == primo, "i codici devono tornare numeri, non stringhe"
        assert ClientFinto.listone_chiesto == 1, "il secondo caricamento non doveva chiamare l'API"

        listone.carica(client, "mia-lega", usa_cache=False)
        assert ClientFinto.listone_chiesto == 2, "senza cache deve riscaricare"
        assert listone.aggiornato("mia-lega").startswith("20"), listone.aggiornato("mia-lega")
    print("  ok  listone scaricato una volta, poi riletto dal disco; senza cache si riscarica")


def test_una_cache_per_lega() -> None:
    with _cache() as cartella:
        client = ClientFinto()
        listone.carica(client, "mia-lega")
        listone.carica(client, "altra/lega")  # niente sottocartelle da un alias
        assert ClientFinto.listone_chiesto == 2
        assert sorted(p.name for p in cartella.glob("*.json")) == ["altra-lega.json", "mia-lega.json"]
    print("  ok  un file per lega, e un alias strano non diventa un percorso")


def test_file_rovinato_si_riscarica() -> None:
    with _cache() as cartella:
        client = ClientFinto()
        listone.carica(client, "mia-lega")
        guasti = ("{rotto", "{}", '{"giocatori": {"x": ["a", "b"]}}')
        for contenuto in guasti:
            (cartella / "mia-lega.json").write_text(contenuto, encoding="utf-8")
            prima = ClientFinto.listone_chiesto
            assert listone.carica(client, "mia-lega")[1] == ("Radunovic", "CAG")
            assert ClientFinto.listone_chiesto == prima + 1, contenuto
    print(f"  ok  {len(guasti)} listoni salvati illeggibili: riscaricati, senza errori")


def test_svuota() -> None:
    with _cache() as cartella:
        client = ClientFinto()
        listone.carica(client, "una")
        listone.carica(client, "due")
        assert listone.svuota("una") == 1 and (cartella / "due.json").exists()
        assert listone.svuota() == 1 and not list(cartella.glob("*.json"))
        assert listone.svuota() == 0, "svuotare due volte non è un errore"
    print("  ok  il listone si cancella per una lega o per tutte")


def test_riconosce_i_codici_sconosciuti() -> None:
    def partita(nome: str) -> Partita:
        casa = Formazione(squadra="Casa FC", modulo=433, totale=70.0, giocatori=[
            Giocatore(nome=nome, squadra_reale="?", voto=6.0, fantavoto=6.0),
        ])
        return Partita(casa=casa, trasferta=Formazione(squadra="Ospiti FC", modulo=433, totale=60.0),
                       risultato="1-0")

    assert listone.codici_sconosciuti({1: [partita("Radunovic")]}) == set()
    assert listone.codici_sconosciuti({1: [partita("Radunovic")], 2: [partita("#999")]}) == {999}
    assert listone.codici_sconosciuti({1: [partita("#Strano")]}) == set()
    print("  ok  un nome che comincia con # è il codice di un giocatore sconosciuto")


# --- Dentro la generazione ------------------------------------------------------------
@contextlib.contextmanager
def _servizio_finto():
    """Client e storico finti: la generazione gira senza rete, sul listone del test."""
    originali = (api.Client, api.competizioni_disponibili, servizio.storico.carica_storico)
    api.Client = ClientFinto
    api.competizioni_disponibili = lambda _client: [("1", "Campionato")]

    def storico_finto(_client, _competizione, _calendario, nomi_squadre, nomi_giocatori, **_opzioni):
        # In campo c'è l'arrivato dal mercato solo dopo il mercato. Come fa
        # analysis, un codice che il listone non conosce diventa "#codice".
        codice = 999 if ClientFinto.con_arrivato else 1
        nome, squadra = nomi_giocatori.get(codice, (f"#{codice}", "?"))
        casa = Formazione(squadra=nomi_squadre[1], modulo=433, totale=70.0, giocatori=[
            Giocatore(nome=nome, squadra_reale=squadra, voto=7.0, fantavoto=10.0, gol=1),
        ])
        trasferta = Formazione(squadra=nomi_squadre[2], modulo=433, totale=60.0, giocatori=[
            Giocatore(nome=nomi_giocatori[1][0], squadra_reale="CAG", voto=6.0, fantavoto=6.0),
        ])
        return {1: [Partita(casa=casa, trasferta=trasferta, risultato="1-0")]}

    servizio.storico.carica_storico = storico_finto
    try:
        yield
    finally:
        api.Client, api.competizioni_disponibili, servizio.storico.carica_storico = originali


def test_la_generazione_usa_la_cache() -> None:
    with _cartella(), _cache(), _servizio_finto():
        auth.salva_leghe([{"alias": "mia-lega", "nome": "Mia Lega", "token": "eyJ.finto"}])
        for _ in range(3):
            servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16))
        assert ClientFinto.listone_chiesto == 1, f"{ClientFinto.listone_chiesto} listoni per tre pagine"
    print("  ok  tre generazioni di fila, un solo listone scaricato")


def test_giocatore_nuovo_riscarica_il_listone() -> None:
    """Chi arriva dal mercato non è nel listone salvato: in pagina non deve finire col codice."""
    with _cartella(), _cache(), _servizio_finto():
        auth.salva_leghe([{"alias": "mia-lega", "nome": "Mia Lega", "token": "eyJ.finto"}])
        servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16))
        assert ClientFinto.listone_chiesto == 1

        ClientFinto.con_arrivato = True  # il mercato porta il giocatore 999
        risultato = servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16))
        assert ClientFinto.listone_chiesto == 2, "il listone doveva essere riscaricato"
        assert "Colpo Di Mercato" in risultato.prompt and "#999" not in risultato.prompt

        risultato = servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16))
        assert ClientFinto.listone_chiesto == 2, "ora è in cache: niente nuove chiamate"
        assert "#999" not in risultato.prompt
    print("  ok  giocatore sconosciuto: listone riscaricato una volta sola, nome giusto in pagina")


def test_codice_senza_nome_non_fa_riscaricare_ogni_volta() -> None:
    """Un ceduto all'estero non torna nel listone: cercarlo a ogni pagina sarebbe inutile."""
    with _cartella(), _cache(), _servizio_finto():
        auth.salva_leghe([{"alias": "mia-lega", "nome": "Mia Lega", "token": "eyJ.finto"}])
        ClientFinto.con_arrivato = True  # in campo c'è il 999...
        originale = ClientFinto.giocatori

        def senza_arrivato(self):
            ClientFinto.listone_chiesto += 1
            return list(ROSA)  # ...ma il listone non lo conosce, nemmeno fresco

        ClientFinto.giocatori = senza_arrivato
        try:
            risultato = servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16))
            assert ClientFinto.listone_chiesto == 2, "prima volta: scaricato e riscaricato"
            assert "#999" in risultato.prompt, "senza nome resta il codice, ed è giusto vederlo"
            assert listone.irrisolti("mia-lega") == {999}

            servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16))
            servizio.genera("mia-lega", "1", oggi=date(2026, 9, 16))
            assert ClientFinto.listone_chiesto == 2, "ora è annotato: niente altre chiamate"
        finally:
            ClientFinto.giocatori = originale
    print("  ok  un codice senza nome viene annotato: il listone non si riscarica più per lui")


def test_aggiorna_listone_dal_servizio() -> None:
    with _cartella(), _cache(), _servizio_finto():
        auth.salva_leghe([{"alias": "mia-lega", "nome": "Mia Lega", "token": "eyJ.finto"}])
        assert servizio.aggiorna_listone("mia-lega") == 2
        ClientFinto.con_arrivato = True
        assert servizio.aggiorna_listone("mia-lega") == 3, "deve riscaricare, non rileggere"
        assert listone.carica(ClientFinto(), "mia-lega")[999][0] == "Colpo Di Mercato"
        assert _errore(lambda: servizio.aggiorna_listone("inesistente")).codice == "lega_sconosciuta"
    print("  ok  «Aggiorna il listone» riscarica sempre e conta i giocatori")


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
