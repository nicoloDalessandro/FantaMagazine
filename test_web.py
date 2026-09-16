"""Verifica dell'interfaccia web, senza rete e senza Chrome.

Il livello di servizio viene sostituito con risposte finte: qui si controlla ciò
che appartiene all'app web — le difese, la validazione dei parametri, la
traduzione degli errori, il fatto che i token non escano mai dal server.

    python test_web.py
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import app as applicazione
from fantamagazine import auth, browser, prompt, servizio

RADICE = Path(__file__).resolve().parent


@contextlib.contextmanager
def _sostituisci(modulo, **funzioni):
    """Sostituisce temporaneamente attributi di un modulo."""
    originali = {nome: getattr(modulo, nome) for nome in funzioni}
    for nome, funzione in funzioni.items():
        setattr(modulo, nome, funzione)
    try:
        yield
    finally:
        for nome, funzione in originali.items():
            setattr(modulo, nome, funzione)


def _client():
    return applicazione.crea_app().test_client()


def _pagina_finta() -> prompt.PrimaPagina:
    return prompt.PrimaPagina(
        testata="LA GAZZETTA DI PROVA",
        stagione="2026-27",
        giornata=3,
        data="15 settembre 2026",
        seme=3,
        titolo="TITOLO",
        sottotitolo="Sottotitolo",
        apertura="A 1-0 B",
        racconto=["Paragrafo."],
        risultati=["A 1-0 B"],
        classifica=[prompt.VoceClassifica(1, "A", 3, 70.5)],
        pezzo_lungo=("DIETRO I NUMERI", "Testo."),
        trafiletti=[("TITOLETTO", "Testo breve.")],
    )


# --- Pagina e intestazioni ----------------------------------------------------------
def test_la_pagina_si_apre() -> None:
    risposta = _client().get("/")
    assert risposta.status_code == 200, risposta.status_code
    html = risposta.get_data(as_text=True)
    assert "app.js" in html and "app.css" in html
    print("  ok  la pagina principale si apre con i suoi file")


def test_intestazioni_di_sicurezza() -> None:
    risposta = _client().get("/")
    csp = risposta.headers.get("Content-Security-Policy", "")
    assert "script-src 'self'" in csp, csp
    assert "frame-ancestors 'none'" in csp, csp
    assert risposta.headers.get("X-Content-Type-Options") == "nosniff"
    print("  ok  CSP e intestazioni di sicurezza presenti")


def test_mai_in_debug() -> None:
    """Il debugger di Werkzeug consentirebbe di eseguire codice dal browser."""
    assert applicazione.crea_app().debug is False
    sorgente = (RADICE / "app.py").read_text(encoding="utf-8")
    assert "debug=True" not in sorgente, "app.py non deve mai avviarsi in debug"
    print("  ok  l'app non parte mai in modalità debug")


def test_ascolta_solo_in_locale() -> None:
    assert applicazione.INDIRIZZO == "127.0.0.1", applicazione.INDIRIZZO
    print("  ok  il server ascolta solo su 127.0.0.1")


# --- Difese -----------------------------------------------------------------------
def test_host_estraneo_rifiutato() -> None:
    """Difesa dal DNS rebinding: un dominio che risolve a 127.0.0.1 non passa."""
    risposta = _client().get("/api/leghe", headers={"Host": "attaccante.example"})
    assert risposta.status_code == 403, risposta.status_code
    assert risposta.get_json()["codice"] == "host_non_ammesso"
    print("  ok  host estraneo rifiutato (DNS rebinding)")


def test_post_senza_json_rifiutata() -> None:
    """Un form di un sito esterno arriverebbe così: va respinto."""
    risposta = _client().post("/api/cache", data="rimossi=1")
    assert risposta.status_code == 415, risposta.status_code
    print("  ok  POST non JSON rifiutata (niente CSRF da form)")


def test_origine_esterna_rifiutata() -> None:
    risposta = _client().post(
        "/api/cache", json={}, headers={"Origin": "https://attaccante.example"}
    )
    assert risposta.status_code == 403, risposta.status_code
    assert risposta.get_json()["codice"] == "origine_esterna"
    print("  ok  POST da origine esterna rifiutata")


def test_origine_locale_ammessa() -> None:
    with _sostituisci(servizio, svuota_cache=lambda: 4):
        risposta = _client().post(
            "/api/cache", json={}, headers={"Origin": "http://127.0.0.1:8765"}
        )
    assert risposta.status_code == 200, risposta.status_code
    assert risposta.get_json() == {"rimossi": 4}
    print("  ok  POST dalla pagina locale ammessa")


def test_nessun_innerhtml_nel_javascript() -> None:
    """I nomi delle squadre sono input non fidato: devono entrare solo come testo."""
    sorgente = (RADICE / "web" / "static" / "app.js").read_text(encoding="utf-8")
    vietati = [v for v in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")
               if v in sorgente]
    assert not vietati, f"app.js usa API che interpretano HTML: {vietati}"
    print("  ok  il JavaScript non inserisce mai HTML dai dati")


# --- API --------------------------------------------------------------------------
def test_leghe_serializzate() -> None:
    finte = [
        servizio.StatoLega(
            alias="tana",
            nome="Tana",
            testata="LA GAZZETTA DELLA TANA",
            competizioni=[
                servizio.StatoCompetizione(
                    id="1", nome="Campionato", giornate_totali=38,
                    giornate_calcolate=[1, 2, 3], supportata=True,
                )
            ],
        )
    ]
    with _sostituisci(servizio, stato_leghe=lambda: finte):
        dati = _client().get("/api/leghe").get_json()
    competizione = dati[0]["competizioni"][0]
    assert competizione["ultima"] == 3, competizione
    assert competizione["supportata"] is True
    assert "token" not in str(dati).lower(), "l'elenco leghe contiene token"
    print("  ok  elenco leghe serializzato, senza token")


def test_genera_richiede_i_parametri() -> None:
    risposta = _client().post("/api/genera", json={"competizione": "1"})
    assert risposta.status_code == 400
    assert "lega" in risposta.get_json()["errore"]
    print("  ok  genera senza lega: 400 con messaggio chiaro")


def test_genera_valida_i_numeri() -> None:
    for campo, valore in (("giornata", "tre"), ("seme", True), ("seme", "4x")):
        corpo = {"lega": "tana", "competizione": "1", campo: valore}
        chiamate = []
        with _sostituisci(servizio, genera=lambda *a, **k: chiamate.append(k)):
            risposta = _client().post("/api/genera", json=corpo)
        assert risposta.status_code == 400, (campo, valore, risposta.status_code)
        assert not chiamate, "il servizio non doveva essere chiamato"
    print("  ok  giornata e seme non numerici rifiutati prima di chiamare il servizio")


def test_genera_passa_i_parametri() -> None:
    ricevuti = {}

    def finto(alias, competizione, **opzioni):
        ricevuti.update(alias=alias, competizione=competizione, **opzioni)
        return servizio.Risultato(
            prompt="PROMPT", pagina=_pagina_finta(), lega=alias, nome_lega="Tana",
            competizione=competizione, nome_competizione="Campionato", avvisi=["attenzione"],
        )

    with _sostituisci(servizio, genera=finto):
        risposta = _client().post(
            "/api/genera",
            json={"lega": "tana", "competizione": 12200, "giornata": "2", "varia": True},
        )
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    dati = risposta.get_json()
    assert ricevuti == {
        "alias": "tana", "competizione": "12200", "giornata": 2,
        "seme": None, "varia": True, "usa_cache": True,
    }, ricevuti
    assert dati["prompt"] == "PROMPT"
    assert dati["pagina"]["classifica"][0]["fantapunti"] == 70.5
    assert dati["pagina"]["trafiletti"] == [["TITOLETTO", "Testo breve."]]
    assert dati["avvisi"] == ["attenzione"]
    print("  ok  genera converte i parametri e restituisce pagina e prompt")


def test_genera_restituisce_la_memoria() -> None:
    """La scheda Memoria vive di questi dati: resoconto e richiami devono arrivare interi."""
    from fantamagazine import resoconto, tendenze
    from fantamagazine.analysis import RigaClassifica
    from test_tendenze import _storico_finto

    storia = _storico_finto()
    memoria = tendenze.calcola(storia)
    tabella = [
        RigaClassifica(squadra=nome, punti=punti, giocate=4, fantapunti=300.0 - i * 10)
        for i, (nome, punti) in enumerate(
            (("Bomber United", 12), ("Muro Difensivo", 12), ("Media Mediocre", 1), ("Sfigati FC", 0))
        )
    ]
    pagina = prompt.componi(storia[4], tabella, 4, "2026-27", "15 settembre 2026",
                            "LA GAZZETTA DI PROVA", memoria)
    finto = servizio.Risultato(
        prompt=prompt.renderizza(pagina), pagina=pagina, lega="tana", nome_lega="Tana",
        competizione="1", nome_competizione="Campionato", memoria=resoconto.componi(memoria, pagina),
    )
    with _sostituisci(servizio, genera=lambda *_a, **_k: finto):
        risposta = _client().post("/api/genera", json={"lega": "tana", "competizione": "1"})
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    dati = risposta.get_json()

    assert dati["memoria"]["sintesi"] == finto.memoria.sintesi
    assert len(dati["pagina"]["richiami"]) == len(pagina.richiami) > 0
    assert set(dati["pagina"]["richiami"][0]) == {"sezione", "tipo", "squadra", "valore", "titolo", "testo"}
    assert set(dati["memoria"]["notizie"][0]) == {
        "tipo", "soggetto", "squadra", "valore", "fatto", "raccontabile", "sezioni",
    }
    for scheda in dati["memoria"]["squadre"]:
        assert len(scheda["giornate"]) == len(scheda["esiti"]) == len(scheda["fantapunti"]), scheda
    assert dati["memoria"]["regole"][0][0] == "Titolo"
    assert "token" not in risposta.get_data(as_text=True).lower()
    print(f"  ok  genera restituisce la memoria: {len(dati['memoria']['notizie'])} notizie, "
          f"{len(dati['pagina']['richiami'])} richiami")


def test_errori_del_servizio_tradotti() -> None:
    casi = {
        "token_scaduto": 401,
        "giornata_non_disponibile": 404,
        "formato_non_supportato": 422,
        "rete": 503,
    }
    for codice, stato_atteso in casi.items():
        def fallisce(*_a, _codice=codice, **_k):
            raise servizio.ErroreServizio(f"messaggio {_codice}", _codice)

        with _sostituisci(servizio, genera=fallisce):
            risposta = _client().post("/api/genera", json={"lega": "t", "competizione": "1"})
        assert risposta.status_code == stato_atteso, (codice, risposta.status_code)
        assert risposta.get_json() == {"errore": f"messaggio {codice}", "codice": codice}
    print(f"  ok  {len(casi)} errori del servizio tradotti con stato e codice")


def test_errore_imprevisto_senza_dettagli() -> None:
    """Al browser un messaggio generico; lo stack resta nel terminale."""
    def esplode(*_a, **_k):
        raise RuntimeError("C:\\percorso\\segreto token=abc")

    # Il registro viene zittito solo per non sporcare l'output delle prove.
    with _sostituisci(servizio, genera=esplode):
        applicazione.registro.disabled = True
        try:
            risposta = _client().post("/api/genera", json={"lega": "t", "competizione": "1"})
        finally:
            applicazione.registro.disabled = False
    assert risposta.status_code == 500
    corpo = risposta.get_data(as_text=True)
    assert "segreto" not in corpo and "token=abc" not in corpo, corpo
    assert risposta.get_json()["codice"] == "interno"
    print("  ok  errore imprevisto: 500 generico, nessun dettaglio al browser")


def test_metodo_sbagliato_non_e_un_guasto() -> None:
    """Il gestore generico non deve trasformare un 405 in un 500."""
    risposta = _client().get("/api/genera")
    assert risposta.status_code == 405, risposta.status_code
    assert risposta.get_json()["codice"] == "http"
    print("  ok  metodo non ammesso resta un 405")


# --- Token ------------------------------------------------------------------------
def test_rinnovo_non_restituisce_token() -> None:
    salvate = []
    lette = [
        {"alias": "tana", "nome": "Tana", "id": 1, "token": "eyJ-segreto-1"},
        {"alias": "sagrato", "nome": "Sagrato", "id": 2, "token": "eyJ-segreto-2"},
    ]
    with _sostituisci(browser, leggi_leghe=lambda: lette), \
         _sostituisci(auth, salva_leghe=lambda voci: salvate.extend(voci), dimentica_utente=lambda: None):
        risposta = _client().post("/api/token", json={})
    assert risposta.status_code == 200, risposta.status_code
    corpo = risposta.get_data(as_text=True)
    assert "segreto" not in corpo, "i token sono finiti nella risposta"
    assert risposta.get_json()["leghe"] == [
        {"alias": "sagrato", "nome": "Sagrato"},
        {"alias": "tana", "nome": "Tana"},
    ]
    assert len(salvate) == 2, "i token non sono stati salvati"
    print("  ok  rinnovo: token salvati su disco, mai restituiti al browser")


def test_rinnovo_senza_browser() -> None:
    def assente():
        raise browser.ErroreBrowser("browser-harness non è installato")

    with _sostituisci(browser, leggi_leghe=assente):
        risposta = _client().post("/api/token", json={})
    assert risposta.status_code == 503, risposta.status_code
    assert risposta.get_json()["codice"] == "browser"
    print("  ok  browser assente: 503 con codice 'browser'")


def test_interpretazione_uscita_browser() -> None:
    uscita = (
        "[browser-harness] update available\n"
        + browser.MARCATORE
        + '[{"alias":"tana","nome":"Tana","token":"x"},{"alias":"","token":"y"},{"nome":"senza"}]\n'
    )
    leghe = browser.interpreta_uscita(uscita)
    assert [l["alias"] for l in leghe] == ["tana"], leghe
    assert browser.interpreta_uscita("niente di utile") == []
    assert browser.interpreta_uscita(browser.MARCATORE + "{rotto") == []
    print("  ok  uscita del browser interpretata, voci incomplete scartate")


# --- Accesso e scelte -------------------------------------------------------------------
PASSWORD = "Segreta-Web 123"


def test_account_senza_segreti() -> None:
    from fantamagazine import accesso
    from test_accesso import _cartella

    with _cartella():
        vuoto = _client().get("/api/account").get_json()
        assert vuoto == {"collegato": False, "username": None, "aggiornabile": False, "leghe": 0}, vuoto

        auth.salva_leghe([{"alias": "tana", "nome": "Tana", "token": "eyJ-lega-segreto"}])
        auth.salva_utente(accesso.Utente(id=7, username="mario", jwt="eyJ-utente-segreto", token_auth="auth-segreto"))
        risposta = _client().get("/api/account")
    corpo = risposta.get_data(as_text=True)
    assert risposta.get_json() == {"collegato": True, "username": "mario", "aggiornabile": True, "leghe": 1}
    assert "segreto" not in corpo, "un token è finito nella risposta"
    print("  ok  /api/account dice chi è entrato e con quante leghe, mai un token")


def test_accesso_valida_prima_di_chiamare() -> None:
    chiamate = []
    guasti = [
        {"utente": "mario"},
        {"password": PASSWORD},
        {"utente": "  ", "password": PASSWORD},
        {"utente": "mario", "password": ""},
        {"utente": ["mario"], "password": PASSWORD},
        {"utente": "mario", "password": 12345},
        {"utente": "m" * 201, "password": PASSWORD},
        {"utente": "mario", "password": "p" * 201},
    ]
    with _sostituisci(servizio, accedi=lambda *a: chiamate.append(a)):
        for corpo in guasti:
            risposta = _client().post("/api/accesso", json=corpo)
            assert risposta.status_code == 400, (corpo, risposta.status_code)
            assert PASSWORD not in risposta.get_data(as_text=True)
        elenco = _client().post("/api/accesso", json=["mario", PASSWORD])
        assert elenco.status_code == 400, f"un corpo che non è un oggetto: {elenco.status_code}"
        esterna = _client().post(
            "/api/accesso", json={"utente": "mario", "password": PASSWORD},
            headers={"Origin": "https://attaccante.example"},
        )
        da_form = _client().post("/api/accesso", data={"utente": "mario", "password": PASSWORD})
    assert esterna.status_code == 403 and da_form.status_code == 415, (esterna.status_code, da_form.status_code)
    assert not chiamate, "con una richiesta non valida l'accesso non doveva partire"
    print(f"  ok  {len(guasti)} richieste di accesso non valide, da un altro sito o da un form: nessun tentativo")


def test_accesso_riuscito_e_fallito() -> None:
    ricevuti = []

    def riuscito(utente, password):
        ricevuti.append((utente, password))
        return [{"alias": "tana", "nome": "Tana"}]

    account = servizio.Account(collegato=True, username="mario", aggiornabile=True, leghe=1)
    with _sostituisci(servizio, accedi=riuscito, stato_account=lambda: account):
        risposta = _client().post("/api/accesso", json={"utente": "mario", "password": f" {PASSWORD} "})
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    assert ricevuti == [("mario", f" {PASSWORD} ")], "la password va passata intatta, spazi compresi"
    assert risposta.get_json() == {
        "leghe": [{"alias": "tana", "nome": "Tana"}],
        "account": {"collegato": True, "username": "mario", "aggiornabile": True, "leghe": 1},
    }
    assert PASSWORD not in risposta.get_data(as_text=True)

    def sbagliata(*_a):
        raise servizio.ErroreServizio("Username o password non validi.", "accesso_credenziali")

    with _sostituisci(servizio, accedi=sbagliata):
        risposta = _client().post("/api/accesso", json={"utente": "mario", "password": PASSWORD})
    assert risposta.status_code == 401
    assert risposta.get_json() == {"errore": "Username o password non validi.", "codice": "accesso_credenziali"}
    print("  ok  accesso riuscito: leghe e account; sbagliato: 401 con codice; la password non torna mai")


def test_scelte_esci_e_aggiorna_dal_web() -> None:
    salvate, uscite = [], []
    voce = servizio.ImpostazioneLega(
        alias="tana", nome="Tana", attiva=True, testata="", testata_predefinita="LA GAZZETTA DI TANA",
        competizioni=[servizio.ImpostazioneCompetizione("1", "Campionato", True)],
    )
    account = servizio.Account(collegato=False, username=None, aggiornabile=False, leghe=0)
    with _sostituisci(
        servizio,
        impostazioni_leghe=lambda: [voce],
        salva_impostazioni=lambda voci: salvate.append(voci),
        esci=lambda: uscite.append(True),
        aggiorna_leghe=lambda: [{"alias": "tana", "nome": "Tana"}],
        stato_account=lambda: account,
    ):
        elenco = _client().get("/api/impostazioni").get_json()
        salva = _client().post("/api/impostazioni", json={"leghe": [{"alias": "tana", "attiva": False}]})
        esci = _client().post("/api/esci", json={})
        aggiorna = _client().post("/api/leghe/aggiorna", json={})
        esci_da_form = _client().post("/api/esci", data="x=1")
    assert elenco[0]["competizioni"] == [{"id": "1", "nome": "Campionato", "attiva": True}], elenco
    assert elenco[0]["testata_predefinita"] == "LA GAZZETTA DI TANA"
    assert salva.status_code == 200 and salvate == [[{"alias": "tana", "attiva": False}]], salvate
    assert esci.status_code == 200 and esci.get_json()["collegato"] is False and uscite == [True]
    assert aggiorna.get_json()["leghe"] == [{"alias": "tana", "nome": "Tana"}]
    assert esci_da_form.status_code == 415 and uscite == [True], "uscire da un form esterno non deve funzionare"

    def rifiuta(_voci):
        raise servizio.ErroreServizio("Una delle leghe indicate non è fra le tue.", "impostazioni_non_valide")

    with _sostituisci(servizio, salva_impostazioni=rifiuta):
        risposta = _client().post("/api/impostazioni", json={"leghe": [{"alias": "altrui"}]})
    assert risposta.status_code == 400 and risposta.get_json()["codice"] == "impostazioni_non_valide"
    print("  ok  scelte lette e salvate, uscita e aggiornamento dal web; errori con il loro codice")


def test_listone_aggiornato_dal_web() -> None:
    chiamate = []
    with _sostituisci(servizio, aggiorna_listone=lambda alias: chiamate.append(alias) or 595):
        senza_lega = _client().post("/api/listone", json={})
        elenco = _client().post("/api/listone", json=["tana"])
        riuscito = _client().post("/api/listone", json={"lega": "tana"})
        da_form = _client().post("/api/listone", data="lega=tana")
    assert senza_lega.status_code == 400 and elenco.status_code == 400
    assert da_form.status_code == 415
    assert riuscito.status_code == 200 and riuscito.get_json() == {"giocatori": 595}
    assert chiamate == ["tana"], chiamate
    print("  ok  «Aggiorna il listone» dal web: una lega per volta, niente richieste storte")


# --- Codici di uscita -----------------------------------------------------------------
def test_codici_di_uscita_cli() -> None:
    assert servizio.ErroreServizio("", "token_scaduto").uscita == 2
    assert servizio.ErroreServizio("", "lega_sconosciuta").uscita == 2
    assert servizio.ErroreServizio("", "accesso_credenziali").uscita == 2
    assert servizio.ErroreServizio("", "nessuna_giornata").uscita == 1
    print("  ok  codici di uscita della riga di comando invariati")


# --- Immagini con Gemini -----------------------------------------------------------------
def _bozza_finta(cartella: Path) -> servizio.Bozza:
    percorso = cartella / ("a" * 32 + ".png")
    percorso.write_bytes(b"\x89PNG finta")
    return servizio.Bozza(
        id="a" * 32, percorso=percorso, mime="image/png",
        nome_file="fantatana_giornata-03_seme-7_2026-09-15_21-00-00.png",
        modello="gemini-3-pro-image", proporzioni="9:16", dimensione="2K",
        secondi=31.5, costo_stimato=0.134,
    )


def test_stato_gemini_senza_chiave_in_chiaro() -> None:
    import os

    precedente = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "CHIAVE-CHE-NON-DEVE-USCIRE"
    try:
        corpo = _client().get("/api/gemini").get_data(as_text=True)
    finally:
        if precedente is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = precedente
    assert "CHIAVE-CHE-NON-DEVE-USCIRE" not in corpo, "la chiave è finita nella risposta"
    import json as _json
    dati = _json.loads(corpo)
    assert dati["disponibile"] is True and dati["proporzioni"] == "9:16", dati
    assert dati["dimensione_predefinita"] in dati["dimensioni"]
    print("  ok  /api/gemini dice se la chiave c'è, non quale sia")


def test_immagine_valida_i_parametri() -> None:
    chiamate = []
    with _sostituisci(servizio, genera_immagine=lambda *a, **k: chiamate.append(k)):
        senza_prompt = _client().post("/api/immagine", json={"lega": "tana"})
        risoluzione = _client().post("/api/immagine", json={"prompt": "x", "dimensione": "8K"})
        giornata = _client().post("/api/immagine", json={"prompt": "x", "giornata": "tre"})
    assert senza_prompt.status_code == 400 and "prompt" in senza_prompt.get_json()["errore"]
    assert risoluzione.status_code == 400, risoluzione.status_code
    assert giornata.status_code == 400, giornata.status_code
    assert not chiamate, "con parametri non validi Gemini non doveva essere chiamato"
    print("  ok  /api/immagine respinge parametri non validi prima di spendere")


def test_immagine_generata() -> None:
    import tempfile

    ricevuti = {}
    with tempfile.TemporaryDirectory() as cartella:
        bozza = _bozza_finta(Path(cartella))

        def finta(prompt, **opzioni):
            ricevuti.update(prompt=prompt, **opzioni)
            return bozza

        with _sostituisci(servizio, genera_immagine=finta):
            risposta = _client().post(
                "/api/immagine",
                json={"prompt": "PROMPT", "lega": "fantatana", "giornata": 3, "seme": 7, "dimensione": "4K"},
            )
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    dati = risposta.get_json()
    assert ricevuti == {"prompt": "PROMPT", "lega": "fantatana", "giornata": 3, "seme": 7, "dimensione": "4K"}, ricevuti
    assert dati["url"] == f"/immagini/{'a' * 32}" and dati["url_scarica"].endswith("?scarica=1")
    assert "percorso" not in dati, "il percorso sul disco non serve al browser"
    print("  ok  /api/immagine passa prompt e scelte al servizio e restituisce gli indirizzi")


def test_file_immagine_e_scaricamento() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as cartella:
        bozza = _bozza_finta(Path(cartella))
        with _sostituisci(servizio, bozza=lambda _id: bozza):
            vista = _client().get(f"/immagini/{'a' * 32}")
            scaricata = _client().get(f"/immagini/{'a' * 32}?scarica=1")
        assert vista.status_code == 200 and vista.mimetype == "image/png"
        assert vista.data == b"\x89PNG finta"
        assert "attachment" not in vista.headers.get("Content-Disposition", "")
        disposizione = scaricata.headers.get("Content-Disposition", "")
        assert "attachment" in disposizione and bozza.nome_file in disposizione, disposizione
        vista.close()
        scaricata.close()
    print("  ok  l'immagine si vede nella pagina e si scarica col suo nome")


def test_file_immagine_con_identificativo_malevolo() -> None:
    for malevolo in ("..%2F..%2F.gemini_key", "nonesiste", "a" * 31):
        risposta = _client().get(f"/immagini/{malevolo}")
        assert risposta.status_code == 404, (malevolo, risposta.status_code)
    print("  ok  identificativi malevoli: 404, nessun file servito")


def test_salvataggio_da_web() -> None:
    with _sostituisci(servizio, salva_immagine=lambda _id: Path("C:/archivio/prima.png")):
        risposta = _client().post(f"/api/immagine/{'a' * 32}/salva", json={})
    assert risposta.status_code == 200, risposta.status_code
    assert risposta.get_json()["nome_file"] == "prima.png"
    print("  ok  salvataggio in archivio dal web")


def test_quota_esaurita_da_web() -> None:
    def rifiuta(*_a, **_k):
        raise servizio.ErroreServizio("serve la fatturazione", "gemini_quota")

    with _sostituisci(servizio, genera_immagine=rifiuta):
        risposta = _client().post("/api/immagine", json={"prompt": "x"})
    assert risposta.status_code == 429, risposta.status_code
    assert risposta.get_json() == {"errore": "serve la fatturazione", "codice": "gemini_quota"}
    print("  ok  quota esaurita: HTTP 429 con codice e messaggio per la pagina")


def test_pagina_inesistente_e_un_404() -> None:
    """Il gestore dei 404 era rotto fin dall'inizio: ogni pagina inesistente dava 500."""
    risposta = _client().get("/pagina-che-non-esiste")
    assert risposta.status_code == 404, risposta.status_code
    assert risposta.get_json() == {"errore": "Pagina inesistente.", "codice": "non_trovato"}
    print("  ok  una pagina inesistente è un 404 in JSON, non un errore interno")


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
