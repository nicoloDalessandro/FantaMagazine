"""Verifica dell'integrazione con Gemini, senza rete e senza spendere.

Ogni chiamata all'API viene sostituita con una risposta simulata costruita sullo
schema ufficiale (documento di discovery di generativelanguage v1beta). Si
controllano la richiesta inviata, la lettura della risposta, la traduzione
degli errori, le bozze e l'archivio, e che la chiave non compaia mai in un
messaggio.

    python test_gemini.py
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import requests

from fantamagazine import config, gemini, servizio

CHIAVE_FINTA = "CHIAVE-DI-PROVA-segretissima-123"


class _Risposta:
    """Il minimo di requests.Response che il client usa."""

    def __init__(self, stato: int, corpo: dict | str) -> None:
        self.status_code = stato
        self._corpo = corpo
        self.text = corpo if isinstance(corpo, str) else json.dumps(corpo)

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self):
        if isinstance(self._corpo, str):
            raise ValueError("non JSON")
        return self._corpo


def _parte_immagine(contenuto: bytes, pensiero: bool = False) -> dict:
    parte = {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(contenuto).decode()}}
    if pensiero:
        parte["thought"] = True
    return parte


def _successo(*parti: dict) -> _Risposta:
    return _Risposta(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": list(parti)}}]})


@contextlib.contextmanager
def _ambiente(risposte: list, chiave: str = CHIAVE_FINTA):
    """Chiave finta e richieste di rete simulate, registrate per il controllo."""
    inviate: list[dict] = []
    coda = list(risposte)

    def finto_post(url, headers=None, json=None, timeout=None):
        inviate.append({"url": url, "headers": headers, "json": json})
        risposta = coda.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        return risposta

    originale_post = gemini.requests.post
    originale_env = os.environ.get("GEMINI_API_KEY")
    gemini.requests.post = finto_post
    os.environ["GEMINI_API_KEY"] = chiave
    try:
        yield inviate
    finally:
        gemini.requests.post = originale_post
        if originale_env is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = originale_env


def _errore(funzione) -> gemini.ErroreGemini:
    try:
        funzione()
    except gemini.ErroreGemini as errore:
        return errore
    raise AssertionError("doveva sollevare ErroreGemini")


# --- La richiesta -----------------------------------------------------------------------
def test_richiesta_nel_formato_giusto() -> None:
    with _ambiente([_successo(_parte_immagine(b"png"))]) as inviate:
        gemini.genera("Prima pagina di prova")
    richiesta = inviate[0]
    assert richiesta["url"].endswith("/models/gemini-3-pro-image:generateContent"), richiesta["url"]
    assert richiesta["headers"]["x-goog-api-key"] == CHIAVE_FINTA
    configurazione = richiesta["json"]["generationConfig"]
    assert configurazione["imageConfig"] == {"aspectRatio": "9:16", "imageSize": "2K"}, configurazione
    assert configurazione["responseModalities"] == ["IMAGE"], configurazione
    assert richiesta["json"]["contents"][0]["parts"][0]["text"] == "Prima pagina di prova"
    print("  ok  richiesta: Nano Banana Pro, 9:16, 2K, sola immagine, chiave nell'header")


def test_risoluzione_4k() -> None:
    with _ambiente([_successo(_parte_immagine(b"png"))]) as inviate:
        immagine = gemini.genera("prova", dimensione="4K")
    assert inviate[0]["json"]["generationConfig"]["imageConfig"]["imageSize"] == "4K"
    assert immagine.dimensione == "4K"
    print("  ok  la risoluzione scelta arriva nella richiesta")


def test_risoluzione_non_valida_non_chiama_la_rete() -> None:
    with _ambiente([]) as inviate:
        errore = _errore(lambda: gemini.genera("prova", dimensione="8K"))
    assert errore.codice == "richiesta_non_valida"
    assert not inviate, "con una risoluzione non valida non si doveva chiamare Gemini"
    print("  ok  risoluzione non valida respinta prima di spendere")


def test_ripiego_se_la_sola_immagine_non_e_accettata() -> None:
    rifiuto = _Risposta(400, {"error": {"message": "Model does not support the requested response modalities: image", "status": "INVALID_ARGUMENT"}})
    with _ambiente([rifiuto, _successo(_parte_immagine(b"ok"))]) as inviate:
        immagine = gemini.genera("prova")
    assert [r["json"]["generationConfig"]["responseModalities"] for r in inviate] == [["IMAGE"], ["TEXT", "IMAGE"]]
    assert immagine.dati == b"ok"
    print("  ok  se la sola immagine viene rifiutata si riprova con testo e immagine")


# --- La risposta --------------------------------------------------------------------------
def test_bozze_intermedie_scartate() -> None:
    """Il modello genera immagini di prova marcate thought: vale solo la finale."""
    with _ambiente([_successo(
        _parte_immagine(b"prima bozza", pensiero=True),
        _parte_immagine(b"seconda bozza", pensiero=True),
        _parte_immagine(b"immagine finale"),
    )]):
        immagine = gemini.genera("prova")
    assert immagine.dati == b"immagine finale", immagine.dati
    assert immagine.mime == "image/png" and immagine.estensione == "png"

    # Con la finale in fondo la prova passerebbe anche senza scartare nulla:
    # una bozza dopo l'immagine vera smaschera un codice che non le distingue.
    with _ambiente([_successo(
        _parte_immagine(b"immagine finale"),
        _parte_immagine(b"bozza tardiva", pensiero=True),
    )]):
        immagine = gemini.genera("prova")
    assert immagine.dati == b"immagine finale", immagine.dati
    print("  ok  le bozze intermedie del modello vengono scartate, in qualunque ordine")


def test_prompt_bloccato() -> None:
    bloccata = _Risposta(200, {"promptFeedback": {"blockReason": "SAFETY"}})
    with _ambiente([bloccata]):
        errore = _errore(lambda: gemini.genera("prova"))
    assert errore.codice == "bloccata", errore.codice
    print("  ok  prompt bloccato dal filtro: codice 'bloccata'")


def test_immagine_rifiutata() -> None:
    rifiutata = _Risposta(200, {"candidates": [{"finishReason": "IMAGE_SAFETY", "finishMessage": "contenuto non consentito", "content": {"parts": []}}]})
    with _ambiente([rifiutata]):
        errore = _errore(lambda: gemini.genera("prova"))
    assert errore.codice == "bloccata" and "IMAGE_SAFETY" in errore.messaggio, errore.messaggio
    print("  ok  immagine rifiutata dal filtro: codice 'bloccata' con il motivo")


def test_risposta_senza_immagine() -> None:
    solo_testo = _Risposta(200, {"candidates": [{"finishReason": "NO_IMAGE", "content": {"parts": [{"text": "Non posso disegnarlo."}]}}]})
    with _ambiente([solo_testo]):
        errore = _errore(lambda: gemini.genera("prova"))
    assert errore.codice == "nessuna_immagine", errore.codice
    assert "Non posso disegnarlo" in errore.messaggio
    print("  ok  risposta senza immagine: codice 'nessuna_immagine' con la spiegazione del modello")


# --- Gli errori ---------------------------------------------------------------------------
def test_errori_http_tradotti() -> None:
    casi = [
        (_Risposta(400, {"error": {"message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}), "chiave_non_valida"),
        (_Risposta(429, {"error": {"message": "You exceeded your current quota", "status": "RESOURCE_EXHAUSTED"}}), "quota"),
        (_Risposta(403, {"error": {"message": "Permission denied", "status": "PERMISSION_DENIED"}}), "permesso"),
        (_Risposta(404, {"error": {"message": "models/x is not found", "status": "NOT_FOUND"}}), "modello_non_disponibile"),
        (_Risposta(503, "Service Unavailable"), "servizio"),
        (requests.Timeout(), "tempo_scaduto"),
        (requests.ConnectionError(), "rete"),
    ]
    for risposta, atteso in casi:
        with _ambiente([risposta]):
            errore = _errore(lambda: gemini.genera("prova"))
        assert errore.codice == atteso, (atteso, errore.codice)
    print(f"  ok  {len(casi)} errori tradotti in codici e messaggi comprensibili")


def test_la_chiave_non_compare_mai() -> None:
    """Nessun messaggio d'errore deve contenere la chiave, qualunque cosa succeda."""
    risposte = [
        _Risposta(400, {"error": {"message": "API key not valid", "details": [{"reason": "API_KEY_INVALID"}]}}),
        _Risposta(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}),
        _Risposta(500, "errore interno"),
        requests.Timeout(),
        _Risposta(200, {"candidates": [{"finishReason": "NO_IMAGE", "content": {"parts": []}}]}),
    ]
    for risposta in risposte:
        with _ambiente([risposta]):
            errore = _errore(lambda: gemini.genera("prova"))
        assert CHIAVE_FINTA not in errore.messaggio and CHIAVE_FINTA not in str(errore)
    print("  ok  la chiave non compare in nessun messaggio d'errore")


def test_chiave_mancante() -> None:
    originale_file = config.GEMINI_KEY_FILE
    with tempfile.TemporaryDirectory() as cartella, _ambiente([], chiave=""):
        config.GEMINI_KEY_FILE = Path(cartella) / "inesistente"
        try:
            errore = _errore(lambda: gemini.genera("prova"))
            assert gemini.chiave_presente() is False
        finally:
            config.GEMINI_KEY_FILE = originale_file
    assert errore.codice == "chiave_mancante", errore.codice
    print("  ok  senza chiave: messaggio che dice dove metterla")


# --- Bozze e archivio -----------------------------------------------------------------------
@contextlib.contextmanager
def _cartelle_temporanee():
    originali = (config.BOZZE_DIR, config.ARCHIVIO_DIR)
    with tempfile.TemporaryDirectory() as cartella:
        config.BOZZE_DIR = Path(cartella) / "bozze"
        config.ARCHIVIO_DIR = Path(cartella) / "archivio"
        try:
            yield config.BOZZE_DIR, config.ARCHIVIO_DIR
        finally:
            config.BOZZE_DIR, config.ARCHIVIO_DIR = originali


def test_bozza_conservata_anche_senza_salvare() -> None:
    """Un'immagine costa: resta su disco anche se nessuno preme Salva."""
    with _cartelle_temporanee() as (bozze, archivio), _ambiente([_successo(_parte_immagine(b"PNG!"))]):
        bozza = servizio.genera_immagine("prova", lega="fantatana", giornata=3, seme=7)
        assert bozza.percorso.read_bytes() == b"PNG!"
        assert bozza.percorso.parent == bozze
        assert not archivio.exists() or not any(archivio.iterdir()), "non doveva finire in archivio"
        assert bozza.nome_file.startswith("fantatana_giornata-03_seme-7_"), bozza.nome_file
        assert bozza.nome_file.endswith(".png")
        ritrovata = servizio.bozza(bozza.id)
        assert ritrovata.nome_file == bozza.nome_file and ritrovata.costo_stimato == 0.134
    print("  ok  la bozza resta su disco con un nome che dice lega, giornata e seme")


def test_salvataggio_in_archivio() -> None:
    with _cartelle_temporanee() as (_, archivio), _ambiente([
        _successo(_parte_immagine(b"uno")), _successo(_parte_immagine(b"due")),
    ]):
        prima = servizio.genera_immagine("prova", lega="fantatana", giornata=3, seme=7)
        seconda = servizio.genera_immagine("prova", lega="fantatana", giornata=3, seme=7)
        # Stesso secondo, stesso nome: la seconda non deve sovrascrivere la prima.
        seconda_meta = servizio._meta(seconda.id)
        dati = json.loads(seconda_meta.read_text(encoding="utf-8"))
        dati["nome_file"] = prima.nome_file
        seconda_meta.write_text(json.dumps(dati), encoding="utf-8")

        percorso = servizio.salva_immagine(prima.id)
        di_nuovo = servizio.salva_immagine(prima.id)
        altro = servizio.salva_immagine(seconda.id)

        assert percorso.parent == archivio and percorso.read_bytes() == b"uno"
        assert di_nuovo == percorso, "salvare due volte non deve duplicare"
        assert altro != percorso and altro.read_bytes() == b"due", "un omonimo non deve sovrascrivere"
        assert len(list(archivio.iterdir())) == 2
    print("  ok  archivio: niente duplicati, niente sovrascritture")


def test_identificativi_non_sono_percorsi() -> None:
    """Un identificativo non deve mai permettere di uscire dalla cartella delle bozze.

    Non basta che i percorsi strani falliscano perché il file non c'è: qui un
    file valido esiste davvero fuori dalla cartella, raggiungibile risalendo con
    "..", e deve restare irraggiungibile.
    """
    with _cartelle_temporanee() as (bozze, _):
        bozze.mkdir(parents=True, exist_ok=True)
        fuori = bozze.parent
        (fuori / "segreto.png").write_bytes(b"dati riservati")
        # Un'immagine omonima anche dentro le bozze: così la seconda difesa (il file
        # si cerca solo per nome nella cartella) non basta, e resta da provare la
        # prima, cioè che dei metadati fuori dalla cartella non vengano mai letti.
        (bozze / "segreto.png").write_bytes(b"esca")
        (fuori / "segreto.json").write_text(json.dumps({
            "id": "segreto", "percorso": "segreto.png", "mime": "image/png",
            "nome_file": "segreto.png", "modello": "x", "proporzioni": "9:16",
            "dimensione": "2K", "secondi": 1.0, "costo_stimato": 0.0,
        }), encoding="utf-8")

        for malevolo in ("../segreto", r"..\segreto", "../../.gemini_key", "ABC", "0" * 31, "g" * 32, ""):
            try:
                servizio.bozza(malevolo)
            except servizio.ErroreServizio as errore:
                assert errore.codice == "immagine_inesistente", errore.codice
            else:
                raise AssertionError(f"l'identificativo «{malevolo}» ha raggiunto un file fuori dalle bozze")
    print("  ok  nessun identificativo raggiunge file fuori dalla cartella delle bozze")


def test_errori_gemini_diventano_errori_del_servizio() -> None:
    with _cartelle_temporanee(), _ambiente([_Risposta(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})]):
        try:
            servizio.genera_immagine("prova")
        except servizio.ErroreServizio as errore:
            assert errore.codice == "gemini_quota" and errore.stato_http == 429, (errore.codice, errore.stato_http)
            assert errore.uscita == 1
        else:
            raise AssertionError("doveva fallire")
    print("  ok  quota esaurita: codice 'gemini_quota', HTTP 429")


def test_messaggi_di_quota_brevi_e_distinti() -> None:
    """Il messaggio grezzo di Google è un muro di metriche: a chi legge serve il caso."""
    gratuito = _Risposta(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": (
        "You exceeded your current quota, please check your plan and billing details.\n"
        "* Quota exceeded for metric: generativelanguage.googleapis.com/"
        "generate_content_free_tier_requests, limit: 0, model: gemini-3-pro-image\n"
        "Please retry in 9.07s."
    )}})
    limite = _Risposta(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": (
        "Resource has been exhausted (e.g. check quota). Please retry in 41.2s."
    )}})

    with _ambiente([gratuito]):
        errore = _errore(lambda: gemini.genera("prova"))
    assert errore.codice == "quota" and "piano gratuito" in errore.messaggio, errore.messaggio
    assert "Quota exceeded for metric" not in errore.messaggio and "\n" not in errore.messaggio

    with _ambiente([limite]):
        errore = _errore(lambda: gemini.genera("prova"))
    assert errore.codice == "quota" and "41 secondi" in errore.messaggio, errore.messaggio
    assert "piano gratuito" not in errore.messaggio
    print("  ok  quota: piano gratuito e limite raggiunto hanno messaggi brevi e diversi")


# --- I modelli --------------------------------------------------------------------------
def test_ogni_modello_ha_prezzo_e_taglie() -> None:
    identificativi = [scheda.id for scheda in gemini.MODELLI]
    assert len(identificativi) == len(set(identificativi)), identificativi
    for scheda in gemini.MODELLI:
        assert scheda.dimensioni, scheda.id
        assert set(scheda.costi) == set(scheda.dimensioni), f"{scheda.id}: prezzi e taglie diversi"
        assert all(costo > 0 for costo in scheda.costi.values()), scheda.costi
        assert scheda.nome and scheda.nota, scheda.id
        assert gemini.costo(scheda.id, scheda.dimensioni[0]) == scheda.costi[scheda.dimensioni[0]]
    assert gemini.modello(gemini.MODELLO_PREDEFINITO).id == gemini.MODELLO_PREDEFINITO
    # Un modello mai visto si accetta lo stesso: prezzo sconosciuto, nessun blocco.
    nuovo = gemini.modello("gemini-9-image")
    assert nuovo.id == "gemini-9-image" and nuovo.costi == {}
    assert gemini.costo("gemini-9-image", "1K") is None
    print(f"  ok  {len(gemini.MODELLI)} modelli con prezzo e taglie coerenti, più quelli futuri")


def test_ogni_modello_chiede_quello_che_sa_fare() -> None:
    """Nano Banana non accetta la taglia: chiedergliela sarebbe un errore dell'API."""
    for scheda in gemini.MODELLI:
        taglia = scheda.dimensioni[-1]
        with _ambiente([_successo(_parte_immagine(b"png"))]) as inviate:
            immagine = gemini.genera("prova", dimensione=taglia, modello_scelto=scheda.id)
        configurazione = inviate[0]["json"]["generationConfig"]["imageConfig"]
        assert f"models/{scheda.id}:generateContent" in inviate[0]["url"], inviate[0]["url"]
        assert configurazione["aspectRatio"] == "9:16"
        assert ("imageSize" in configurazione) is scheda.sceglie_taglia, (scheda.id, configurazione)
        assert immagine.modello == scheda.id and immagine.dimensione == taglia

        # Una taglia che quel modello non fa non parte nemmeno.
        with _ambiente([]) as nessuna:
            errore = _errore(lambda s=scheda: gemini.genera("prova", "8K", modello_scelto=s.id))
        assert errore.codice == "richiesta_non_valida" and scheda.nome in errore.messaggio
        assert not nessuna, "una taglia impossibile non deve diventare una richiesta"
    print("  ok  ogni modello riceve solo le taglie che sa fare, e il suo indirizzo")


# --- La chiave e le impostazioni ---------------------------------------------------------
def test_chiave_salvata_e_rimossa() -> None:
    with _cartelle_temporanee() as (cartella, _archivio):
        originale = config.GEMINI_KEY_FILE
        config.GEMINI_KEY_FILE = cartella.parent / ".gemini_key"
        ambiente = os.environ.pop("GEMINI_API_KEY", None)
        try:
            servizio.salva_chiave_gemini("  AIzaSy-chiave-di-prova-1234567890  ")
            assert config.GEMINI_KEY_FILE.read_text(encoding="utf-8") == "AIzaSy-chiave-di-prova-1234567890"
            assert gemini.chiave_presente() is True
            stato = servizio.stato_gemini()
            assert "AIzaSy" not in json.dumps(stato), "la chiave è finita nello stato"
            assert stato["disponibile"] is True and stato["chiave_da_ambiente"] is False

            for storta in ("corta", "con spazi in mezzo qui dentro", "a" * 300, "", "chiave;rm -rf /"):
                errore = None
                try:
                    servizio.salva_chiave_gemini(storta)
                except servizio.ErroreServizio as esito:
                    errore = esito
                assert errore and errore.codice == "gemini_chiave_non_valida", storta
                assert config.GEMINI_KEY_FILE.read_text(encoding="utf-8").startswith("AIzaSy")

            servizio.rimuovi_chiave_gemini()
            assert not config.GEMINI_KEY_FILE.exists() and gemini.chiave_presente() is False
            servizio.rimuovi_chiave_gemini()  # due volte non è un errore
        finally:
            config.GEMINI_KEY_FILE = originale
            if ambiente is not None:
                os.environ["GEMINI_API_KEY"] = ambiente
    print("  ok  chiave salvata e cancellata; le chiavi storte vengono rifiutate senza scrivere")


def test_impostazioni_immagine_guidano_la_generazione() -> None:
    from fantamagazine import impostazioni

    with _cartelle_temporanee() as (cartella, _archivio):
        originale = config.IMPOSTAZIONI_FILE
        config.IMPOSTAZIONI_FILE = cartella.parent / ".fanta_impostazioni.json"
        ambiente = os.environ.pop("GEMINI_MODELLO", None)
        try:
            servizio.salva_impostazioni_immagine("gemini-3.1-flash-lite-image", "1K")
            assert impostazioni.modello_immagine() == "gemini-3.1-flash-lite-image"
            assert impostazioni.dimensione_immagine() == "1K"

            for modello, dimensione in (("inventato", "1K"), ("gemini-3.1-flash-lite-image", "4K")):
                errore = None
                try:
                    servizio.salva_impostazioni_immagine(modello, dimensione)
                except servizio.ErroreServizio as esito:
                    errore = esito
                assert errore and errore.codice == "impostazioni_non_valide", (modello, dimensione)
            assert impostazioni.modello_immagine() == "gemini-3.1-flash-lite-image", "scelta cambiata"

            # Senza indicazioni, la generazione usa quanto scelto qui.
            with _ambiente([_successo(_parte_immagine(b"png"))]) as inviate:
                bozza = servizio.genera_immagine("prova")
            assert "gemini-3.1-flash-lite-image" in inviate[0]["url"], inviate[0]["url"]
            assert (bozza.dimensione, bozza.costo_stimato) == ("1K", 0.0336), bozza
        finally:
            config.IMPOSTAZIONI_FILE = originale
            if ambiente is not None:
                os.environ["GEMINI_MODELLO"] = ambiente
    print("  ok  modello e taglia scelti valgono per la generazione, e le scelte storte si rifiutano")


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
