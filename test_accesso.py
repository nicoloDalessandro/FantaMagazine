"""Verifica dell'accesso con username e password, senza rete e senza account.

L'accesso vero non si può provare qui: servirebbe la password di qualcuno. Si
prova tutto il resto, con risposte che hanno la forma di quelle reali: la
richiesta che parte, la lettura della risposta, gli errori, e soprattutto che
la password non resti da nessuna parte.

    python test_accesso.py
"""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import requests

from fantamagazine import accesso, auth, browser, config, servizio

PASSWORD = " Pa$$w0rd segreta con spazi "
JWT_UTENTE = "eyJ.utente." + "u" * 40
JWT_LEGA_A = "eyJ.lega-a." + "a" * 40
JWT_LEGA_B = "eyJ.lega-b." + "b" * 40
TOKEN_AUTH = "x" * 128


def _profilo(**modifiche) -> dict:
    """Una risposta con la forma di quella reale del profilo, e valori finti."""
    corpo = {
        "state_auth": 1532864904128,
        "token_auth": TOKEN_AUTH,
        "sendbird_token": "s" * 40,
        "utente": {"id": 4242, "username": "mario.rossi", "email": "mario@example.com", "confermato": 1},
        "leghe": [
            {"visibile": True, "ordine": 2, "admin": 0, "id": 11, "id_squadra": 5, "tipo_lega": 0,
             "tipo_gioco": 1, "nome": "Lega del Bar", "alias": "lega-del-bar", "jwt": JWT_LEGA_B,
             "token": "t" * 128},
            {"visibile": False, "ordine": 1, "admin": 1, "id": 10, "nome": "Amici di Sempre",
             "alias": "amici-di-sempre", "jwt": JWT_LEGA_A, "token": "t" * 128},
            {"visibile": True, "ordine": 3, "id": 12, "nome": "Senza token", "alias": "senza-token"},
        ],
        "acquisti": [],
        "message_ids": [],
        "jwt": JWT_UTENTE,
    }
    corpo.update(modifiche)
    return corpo


class _Risposta:
    def __init__(self, stato: int, corpo=None) -> None:
        self.status_code = stato
        self._corpo = corpo
        self.ok = 200 <= stato < 300

    def json(self):
        if self._corpo is None:
            raise ValueError("non è JSON")
        return self._corpo


@contextlib.contextmanager
def _rete(*risposte):
    """Sostituisce requests.request: registra le chiamate e dà le risposte in ordine."""
    chiamate: list[dict] = []
    coda = list(risposte)
    originale = accesso.requests.request

    def finta(metodo, url, **opzioni):
        chiamate.append({"metodo": metodo, "url": url, **opzioni})
        esito = coda.pop(0)
        if isinstance(esito, Exception):
            raise esito
        return esito

    accesso.requests.request = finta
    try:
        yield chiamate
    finally:
        accesso.requests.request = originale


@contextlib.contextmanager
def _cartella():
    """Token e scelte in una cartella temporanea: le prove non toccano i file veri."""
    nomi = ("LEGHE_FILE", "UTENTE_FILE", "IMPOSTAZIONI_FILE")
    originali = {nome: getattr(config, nome) for nome in nomi}
    with tempfile.TemporaryDirectory() as cartella:
        for nome in nomi:
            setattr(config, nome, Path(cartella) / f".{nome.lower()}.json")
        try:
            yield Path(cartella)
        finally:
            for nome, valore in originali.items():
                setattr(config, nome, valore)


def _errore(funzione):
    try:
        funzione()
    except (accesso.ErroreAccesso, servizio.ErroreServizio) as errore:
        return errore
    raise AssertionError("doveva sollevare un errore")


# --- La risposta --------------------------------------------------------------------
def test_risposta_letta_come_il_sito() -> None:
    utente, leghe = accesso.interpreta(_profilo())
    assert (utente.id, utente.username, utente.jwt, utente.token_auth) == (
        4242, "mario.rossi", JWT_UTENTE, TOKEN_AUTH,
    ), utente
    assert [lega.alias for lega in leghe] == ["amici-di-sempre", "lega-del-bar"], leghe
    assert leghe[0].token == JWT_LEGA_A, "il token di lega è il jwt, non il vecchio token da 128 caratteri"
    assert (leghe[0].visibile, leghe[1].visibile) == (False, True)
    print("  ok  risposta letta come fa il sito: ordine, jwt di lega, leghe senza token scartate")


def test_forme_alternative_della_risposta() -> None:
    """Il sito accetta i dati sotto `data` e le leghe come dizionario: anche qui."""
    corpo = _profilo()
    corpo["leghe"] = {str(voce["id"]): voce for voce in corpo["leghe"]}
    utente, leghe = accesso.interpreta({"data": corpo})
    assert utente.id == 4242 and len(leghe) == 2, (utente, leghe)

    for guasto in ({}, {"utente": {"id": 1}}, {"jwt": "x"}, {"id": "abc", "jwt": "x"}, [], "testo"):
        errore = _errore(lambda g=guasto: accesso.interpreta(g))
        assert errore.codice == "risposta", (guasto, errore.codice)
    print("  ok  dati sotto «data», leghe come dizionario; risposte monche rifiutate")


# --- La richiesta -------------------------------------------------------------------
def test_richiesta_di_accesso() -> None:
    with _rete(_Risposta(200, _profilo())) as chiamate:
        _, leghe = accesso.accedi("  mario.rossi  ", PASSWORD)
    [chiamata] = chiamate
    assert chiamata["metodo"] == "POST", chiamata["metodo"]
    assert chiamata["url"] == "https://apileague.fantacalcio.it/onboarding/v1/login", chiamata["url"]
    assert chiamata["json"] == {"username": "mario.rossi", "password": PASSWORD}, (
        "lo username si ripulisce, la password va inviata intatta"
    )
    assert chiamata["headers"]["app_key"] == config.APP_KEY
    assert "Authorization" not in chiamata["headers"]
    assert chiamata["timeout"] == config.TIMEOUT and len(leghe) == 2
    assert chiamata["allow_redirects"] is False, "la password non deve seguire un reindirizzamento"
    print("  ok  POST /onboarding/v1/login con app_key, username ripulito, password intatta, niente redirect")


def test_accesso_senza_dati_non_parte() -> None:
    with _rete() as chiamate:
        for utente, password in (("", PASSWORD), ("mario", ""), ("   ", "x"), (None, None)):
            errore = _errore(lambda u=utente, p=password: accesso.accedi(u, p))
            assert errore.codice == "credenziali", errore.codice
    assert not chiamate, "senza username o password non deve partire nessuna richiesta"
    print("  ok  senza username o password nessuna richiesta")


def test_errori_di_accesso() -> None:
    casi = [
        (_Risposta(401, {"Code": "ATH018", "Message": "Username o password non validi"}), "credenziali"),
        (_Risposta(400, {"error_msgs": [{"code": "ATH006"}]}), "credenziali"),
        (_Risposta(401), "credenziali"),
        (_Risposta(200, {"success": False, "error": {"code": "ATH018"}}), "credenziali"),
        (_Risposta(403, {"code": "ATH017"}), "applicazione"),
        (_Risposta(502), "servizio"),
        (_Risposta(503, {"code": "Auth01"}), "servizio"),
        (_Risposta(418, {"code": "XYZ"}), "risposta"),
        (_Risposta(302), "risposta"),
        (requests.Timeout("lento"), "rete"),
        (requests.ConnectionError("irraggiungibile"), "rete"),
    ]
    for risposta, atteso in casi:
        with _rete(risposta):
            errore = _errore(lambda: accesso.accedi("mario", PASSWORD))
        assert errore.codice == atteso, (risposta, errore.codice)
        assert PASSWORD.strip() not in f"{errore} {errore.messaggio}", "la password è finita nel messaggio"
        # L'eccezione di requests porta con sé la richiesta, e con essa il corpo.
        assert errore.__cause__ is None and (errore.__context__ is None or errore.__suppress_context__)
    print(f"  ok  {len(casi)} esiti tradotti in codici, senza password e senza la richiesta originale")


def test_profilo_senza_password() -> None:
    vecchio = accesso.Utente(id=4242, username="mario.rossi", jwt=JWT_UTENTE, token_auth="vecchio")
    ridotto = _profilo(utente={"id": 4242})
    ridotto.pop("token_auth")
    with _rete(_Risposta(200, ridotto)) as chiamate:
        nuovo, leghe = accesso.profilo(vecchio)
    [chiamata] = chiamate
    assert chiamata["metodo"] == "GET" and "json" not in chiamata
    assert chiamata["url"] == "https://apileague.fantacalcio.it/onboarding/v2/profile/4242", chiamata["url"]
    assert chiamata["headers"]["Authorization"] == f"Bearer {JWT_UTENTE}"
    assert (nuovo.username, nuovo.token_auth, len(leghe)) == ("mario.rossi", "vecchio", 2)

    for risposta in (_Risposta(401, {"code": "ATH004"}), _Risposta(401), _Risposta(400, {"Code": "ATH011"})):
        with _rete(risposta):
            assert _errore(lambda: accesso.profilo(vecchio)).codice == "sessione_scaduta"
    print("  ok  profilo con il token dell'utente; accesso scaduto riconosciuto")


def test_token_fuori_dalle_rappresentazioni() -> None:
    """Un oggetto finito in un log o in una traccia non deve portarsi dietro i token."""
    utente, leghe = accesso.interpreta(_profilo())
    testo = repr(utente) + repr(leghe)
    for segreto in (JWT_UTENTE, JWT_LEGA_A, TOKEN_AUTH):
        assert segreto not in testo, f"token nella rappresentazione: {testo[:120]}"
    print("  ok  repr di utente e leghe senza token")


# --- Il servizio --------------------------------------------------------------------
def test_accesso_salva_i_token_mai_la_password() -> None:
    with _cartella() as cartella, _rete(_Risposta(200, _profilo())):
        leghe = servizio.accedi("mario.rossi", PASSWORD)
        assert leghe == [
            {"alias": "amici-di-sempre", "nome": "Amici di Sempre"},
            {"alias": "lega-del-bar", "nome": "Lega del Bar"},
        ], leghe
        su_disco = "".join(p.read_text(encoding="utf-8") for p in cartella.iterdir())
        assert PASSWORD.strip() not in su_disco and "password" not in su_disco.lower()
        assert not list(cartella.glob("*.tmp")), "file temporanei rimasti"
        assert auth.carica_leghe()["lega-del-bar"].token == f"Bearer {JWT_LEGA_B}"
        assert auth.carica_utente().jwt == JWT_UTENTE
        stato = servizio.stato_account()
        assert (stato.collegato, stato.username, stato.aggiornabile, stato.leghe) == (
            True, "mario.rossi", True, 2,
        ), stato
    print("  ok  su disco i token delle leghe e dell'utente, nessuna traccia della password")


def test_accesso_fallito_non_tocca_nulla() -> None:
    with _cartella():
        auth.salva_leghe([{"alias": "vecchia", "nome": "Vecchia", "token": "eyJ.vecchio"}])
        prima = config.LEGHE_FILE.read_text(encoding="utf-8")

        with _rete(_Risposta(401, {"Code": "ATH018"})):
            errore = _errore(lambda: servizio.accedi("mario", PASSWORD))
        assert (errore.codice, errore.stato_http, errore.uscita) == ("accesso_credenziali", 401, 2), errore.codice

        with _rete(_Risposta(200, _profilo(leghe=[]))):
            assert _errore(lambda: servizio.accedi("mario", PASSWORD)).codice == "nessuna_lega"

        assert config.LEGHE_FILE.read_text(encoding="utf-8") == prima
        assert not config.UTENTE_FILE.exists()
    print("  ok  credenziali sbagliate o nessuna lega: i token di prima restano intatti")


def test_aggiorna_leghe_con_il_token_dell_utente() -> None:
    with _cartella():
        assert _errore(servizio.aggiorna_leghe).codice == "accesso_mancante"
        with _rete(_Risposta(200, _profilo())):
            servizio.accedi("mario.rossi", PASSWORD)

        con_nuova = _profilo()
        con_nuova["leghe"].append({"id": 13, "nome": "Lega Nuova", "alias": "lega-nuova", "jwt": "eyJ.nuova"})
        with _rete(_Risposta(200, con_nuova)) as chiamate:
            leghe = servizio.aggiorna_leghe()
        assert "lega-nuova" in [voce["alias"] for voce in leghe] and "lega-nuova" in auth.carica_leghe()
        assert chiamate[0]["headers"]["Authorization"] == f"Bearer {JWT_UTENTE}"

        with _rete(_Risposta(401, {"code": "ATH004"})):
            assert _errore(servizio.aggiorna_leghe).codice == "accesso_sessione_scaduta"
    print("  ok  le leghe nuove arrivano senza password; accesso scaduto segnalato")


def test_uscire_cancella_utente_e_token() -> None:
    with _cartella():
        with _rete(_Risposta(200, _profilo())):
            servizio.accedi("mario.rossi", PASSWORD)
        config.IMPOSTAZIONI_FILE.write_text('{"leghe": {}}', encoding="utf-8")
        servizio.esci()
        assert not config.LEGHE_FILE.exists() and not config.UTENTE_FILE.exists()
        assert config.IMPOSTAZIONI_FILE.exists(), "le scelte restano per il prossimo accesso"
        assert servizio.stato_account().collegato is False
        servizio.esci()
    print("  ok  uscire cancella utente e token, lascia le scelte; due volte non è un errore")


def test_file_utente_rovinato() -> None:
    with _cartella():
        for contenuto in ("{rotto", '{"id": "x", "jwt": "y"}', '{"username": "senza id"}'):
            config.UTENTE_FILE.write_text(contenuto, encoding="utf-8")
            assert auth.carica_utente() is None, contenuto
    print("  ok  un file utente rovinato vale come nessun accesso")


def test_accesso_da_chrome_dimentica_l_utente() -> None:
    """I token copiati da Chrome possono essere di un altro account: l'utente di prima si dimentica."""
    with _cartella():
        with _rete(_Risposta(200, _profilo())):
            servizio.accedi("mario.rossi", PASSWORD)
        originale = browser.leggi_leghe
        browser.leggi_leghe = lambda: [{"alias": "da-chrome", "nome": "Da Chrome", "token": "eyJ.chrome"}]
        try:
            servizio.rinnova_token()
        finally:
            browser.leggi_leghe = originale
        assert auth.carica_utente() is None and list(auth.carica_leghe()) == ["da-chrome"]
        assert servizio.stato_account().aggiornabile is False
    print("  ok  accesso da Chrome: token nuovi, utente precedente dimenticato")


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
