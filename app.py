"""Interfaccia web locale: la redazione della Gazzetta.

    python app.py                 # avvia e apre il browser
    python app.py --porta 9000    # su un'altra porta
    python app.py --no-browser    # senza aprire il browser

Il server ascolta solo su 127.0.0.1: è raggiungibile da questo computer e da
nessun altro. Riceve la tua password per l'accesso e conserva i token delle tue
leghe, quindi non va mai esposto in rete né avviato in modalità debug (il
debugger di Werkzeug permette di eseguire codice arbitrario dal browser).
"""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from fantamagazine import gemini, servizio

RADICE = Path(__file__).resolve().parent
INDIRIZZO = "127.0.0.1"
PORTA_PREDEFINITA = 8765

registro = logging.getLogger("redazione")


def crea_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(RADICE / "web" / "templates"),
        static_folder=str(RADICE / "web" / "static"),
    )
    app.json.ensure_ascii = False  # accenti leggibili nelle risposte
    app.json.sort_keys = False

    # --- Difese ---------------------------------------------------------------
    # Anche un server locale può essere raggiunto da una pagina web qualunque
    # aperta nel browser. Due controlli bastano a chiudere le strade:
    #   - Host: blocca il DNS rebinding, in cui un dominio esterno viene fatto
    #     risolvere a 127.0.0.1 per aggirare la same-origin policy;
    #   - JSON obbligatorio sulle POST: una richiesta cross-origin con quel
    #     content type richiede un preflight CORS, che qui non viene mai
    #     autorizzato, quindi il browser la blocca prima di inviarla.
    host_ammessi = {INDIRIZZO, "localhost"}

    @app.before_request
    def proteggi():
        nome_host = (request.host or "").rsplit(":", 1)[0]
        if nome_host not in host_ammessi:
            return _errore("Richiesta rifiutata: host non ammesso.", "host_non_ammesso", 403)

        if request.method == "POST":
            origine = request.headers.get("Origin")
            if origine and origine.split("://", 1)[-1].rsplit(":", 1)[0] not in host_ammessi:
                return _errore("Richiesta rifiutata: origine esterna.", "origine_esterna", 403)
            if not request.is_json:
                return _errore("Le richieste devono essere in JSON.", "formato_richiesta", 415)
        return None

    @app.after_request
    def intestazioni(risposta):
        risposta.headers["X-Content-Type-Options"] = "nosniff"
        risposta.headers["Referrer-Policy"] = "no-referrer"
        risposta.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        if request.path.startswith("/api/"):
            risposta.headers["Cache-Control"] = "no-store"
        return risposta

    # --- Pagine ----------------------------------------------------------------
    @app.get("/")
    def indice():
        return render_template("index.html")

    # --- Account ---------------------------------------------------------------
    @app.get("/api/account")
    def account():
        # Chi è entrato e con quante leghe: mai un token.
        return jsonify(asdict(servizio.stato_account()))

    @app.post("/api/accesso")
    def entra():
        dati = _oggetto(request.get_json(silent=True))
        utente, password = dati.get("utente"), dati.get("password")
        # La password non si ripulisce dagli spazi: possono farne parte. E non
        # compare in nessuna risposta, nemmeno negli errori.
        if not isinstance(utente, str) or not utente.strip() or not isinstance(password, str) or not password:
            return _errore("Inserisci username e password.", "parametri", 400)
        if len(utente) > 200 or len(password) > 200:
            return _errore("Username o password troppo lunghi.", "parametri", 400)
        leghe = servizio.accedi(utente, password)
        return jsonify({"leghe": leghe, "account": asdict(servizio.stato_account())})

    @app.post("/api/leghe/aggiorna")
    def aggiorna_leghe():
        leghe = servizio.aggiorna_leghe()
        return jsonify({"leghe": leghe, "account": asdict(servizio.stato_account())})

    @app.post("/api/esci")
    def esci():
        servizio.esci()
        return jsonify(asdict(servizio.stato_account()))

    @app.get("/api/impostazioni")
    def impostazioni():
        return jsonify([asdict(voce) for voce in servizio.impostazioni_leghe()])

    @app.post("/api/impostazioni")
    def salva_impostazioni():
        servizio.salva_impostazioni(_oggetto(request.get_json(silent=True)).get("leghe"))
        return jsonify({"salvate": True})

    # --- API -------------------------------------------------------------------
    @app.get("/api/leghe")
    def leghe():
        stati = servizio.stato_leghe()
        return jsonify(
            [
                {
                    "alias": s.alias,
                    "nome": s.nome,
                    "testata": s.testata,
                    "errore": s.errore,
                    "codice_errore": s.codice_errore,
                    "competizioni": [
                        {
                            "id": c.id,
                            "nome": c.nome,
                            "giornate_totali": c.giornate_totali,
                            "giornate_calcolate": c.giornate_calcolate,
                            "ultima": c.ultima,
                            "supportata": c.supportata,
                            "errore": c.errore,
                        }
                        for c in s.competizioni
                    ],
                }
                for s in stati
            ]
        )

    @app.post("/api/genera")
    def genera():
        dati = request.get_json(silent=True) or {}
        try:
            lega = _testo(dati, "lega")
            competizione = _testo(dati, "competizione")
            giornata = _intero(dati, "giornata")
            seme = _intero(dati, "seme")
        except ValueError as errore:
            return _errore(str(errore), "parametri", 400)

        risultato = servizio.genera(
            lega,
            competizione,
            giornata=giornata,
            seme=seme,
            varia=bool(dati.get("varia")),
            usa_cache=dati.get("usa_cache", True) is not False,
        )
        return jsonify(
            {
                "prompt": risultato.prompt,
                "pagina": asdict(risultato.pagina),
                "lega": risultato.lega,
                "nome_lega": risultato.nome_lega,
                "competizione": risultato.competizione,
                "nome_competizione": risultato.nome_competizione,
                "avvisi": risultato.avvisi,
                "memoria": asdict(risultato.memoria) if risultato.memoria else None,
            }
        )

    # --- Immagini --------------------------------------------------------------
    @app.get("/api/gemini")
    def stato_gemini():
        # Dice se la chiave c'è, non quale sia.
        return jsonify(servizio.stato_gemini())

    @app.post("/api/immagine")
    def immagine():
        dati = request.get_json(silent=True) or {}
        try:
            testo = _testo(dati, "prompt")
            giornata = _intero(dati, "giornata")
            seme = _intero(dati, "seme")
        except ValueError as errore:
            return _errore(str(errore), "parametri", 400)

        dimensione = str(dati.get("dimensione") or gemini.DIMENSIONE_PREDEFINITA)
        if dimensione not in gemini.DIMENSIONI:
            return _errore(
                f"Risoluzione non valida: scegli fra {', '.join(gemini.DIMENSIONI)}.",
                "parametri",
                400,
            )

        bozza = servizio.genera_immagine(
            testo,
            lega=str(dati.get("lega") or ""),
            giornata=giornata,
            seme=seme,
            dimensione=dimensione,
        )
        return jsonify(_bozza_json(bozza))

    @app.get("/immagini/<bozza_id>")
    def file_immagine(bozza_id: str):
        scelta = servizio.bozza(bozza_id)
        return send_file(
            scelta.percorso,
            mimetype=scelta.mime,
            as_attachment=request.args.get("scarica") == "1",
            download_name=scelta.nome_file,
            max_age=0,
        )

    @app.post("/api/immagine/<bozza_id>/salva")
    def salva_immagine(bozza_id: str):
        percorso = servizio.salva_immagine(bozza_id)
        return jsonify({"nome_file": percorso.name, "cartella": str(percorso.parent)})

    @app.post("/api/token")
    def token():
        # Restituisce solo alias e nomi: i token non lasciano mai il server.
        return jsonify({"leghe": servizio.rinnova_token()})

    @app.post("/api/cache")
    def cache():
        return jsonify({"rimossi": servizio.svuota_cache()})

    @app.post("/api/listone")
    def listone():
        dati = _oggetto(request.get_json(silent=True))
        try:
            lega = _testo(dati, "lega")
        except ValueError as errore:
            return _errore(str(errore), "parametri", 400)
        return jsonify({"giocatori": servizio.aggiorna_listone(lega)})

    # --- Errori ----------------------------------------------------------------
    @app.errorhandler(servizio.ErroreServizio)
    def errore_servizio(errore: servizio.ErroreServizio):
        return _errore(errore.messaggio, errore.codice, errore.stato_http)

    @app.errorhandler(404)
    def non_trovato(_eccezione):
        # Il parametro non può chiamarsi _errore: oscurerebbe la funzione qui
        # sotto, e ogni 404 diventerebbe un 500.
        return _errore("Pagina inesistente.", "non_trovato", 404)

    @app.errorhandler(Exception)
    def imprevisto(errore: Exception):
        # Un gestore su Exception intercetta anche gli errori HTTP (405, 400...):
        # vanno restituiti per quello che sono, non spacciati per guasti interni.
        if isinstance(errore, HTTPException):
            return _errore(errore.description or errore.name, "http", errore.code or 500)
        # Il dettaglio resta nel terminale: al browser arriva solo un messaggio,
        # mai una traccia dello stack che potrebbe contenere percorsi o dati.
        registro.exception("Errore imprevisto durante %s %s", request.method, request.path)
        return _errore(
            "Errore imprevisto. Il dettaglio è nel terminale in cui hai avviato l'app.",
            "interno",
            500,
        )

    return app


def _bozza_json(bozza: servizio.Bozza) -> dict:
    return {
        "id": bozza.id,
        "url": f"/immagini/{bozza.id}",
        "url_scarica": f"/immagini/{bozza.id}?scarica=1",
        "nome_file": bozza.nome_file,
        "modello": bozza.modello,
        "proporzioni": bozza.proporzioni,
        "dimensione": bozza.dimensione,
        "secondi": bozza.secondi,
        "costo_stimato": bozza.costo_stimato,
        "commento": bozza.commento,
    }


def _errore(messaggio: str, codice: str, stato: int):
    return jsonify({"errore": messaggio, "codice": codice}), stato


def _oggetto(dati) -> dict:
    """Il corpo JSON solo se è un oggetto: un elenco o un numero valgono come vuoto."""
    return dati if isinstance(dati, dict) else {}


def _testo(dati: dict, chiave: str) -> str:
    valore = dati.get(chiave)
    if valore is None or str(valore).strip() == "":
        raise ValueError(f"Manca il parametro «{chiave}».")
    return str(valore).strip()


def _intero(dati: dict, chiave: str) -> int | None:
    valore = dati.get(chiave)
    if valore is None or valore == "":
        return None
    if isinstance(valore, bool):
        raise ValueError(f"«{chiave}» deve essere un numero intero.")
    try:
        return int(valore)
    except (TypeError, ValueError):
        raise ValueError(f"«{chiave}» deve essere un numero intero.") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", type=int, default=PORTA_PREDEFINITA)
    parser.add_argument("--no-browser", action="store_true", help="Non aprire il browser")
    argomenti = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    indirizzo = f"http://{INDIRIZZO}:{argomenti.porta}"
    print(f"\n  La redazione è aperta su {indirizzo}\n  Ctrl+C per chiudere.\n")

    if not argomenti.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(indirizzo,)).start()

    # threaded: la generazione a cache fredda o il rinnovo dei token possono
    # richiedere secondi, e non devono bloccare il resto dell'interfaccia.
    crea_app().run(host=INDIRIZZO, port=argomenti.porta, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
