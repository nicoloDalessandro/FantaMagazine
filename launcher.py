"""Avvio della redazione: prima il server locale, poi il browser.

E' il punto d'ingresso dell'eseguibile per Windows, e la stessa strada che segue
`python app.py`. La differenza rispetto a un semplice `app.run()` sta
nell'ordine: il socket viene aperto **prima** di lanciare il browser, cosi' la
pagina non puo' arrivare su una porta che non ascolta ancora. E se la porta e'
occupata - la redazione gia' aperta, o un altro programma - ne prova qualcuna
piu' avanti invece di fermarsi con un errore.

    python launcher.py                # come python app.py
    python launcher.py --porta 9000
    python launcher.py --no-browser

Indirizzo e difese restano quelli di app.py: il server ascolta su 127.0.0.1, ed
e' raggiungibile da questo computer e da nessun altro.
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import webbrowser

from werkzeug.serving import make_server

PORTE_DA_PROVARE = 20


def _console_utf8() -> None:
    """Accenti leggibili anche su una console Windows con code page legacy."""
    for flusso in (sys.stdout, sys.stderr):
        try:
            flusso.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _libera(indirizzo: str, porta: int) -> bool:
    """Vero se la porta si puo' aprire: la si apre davvero, e si richiude subito.

    Chiedere al sistema operativo e' l'unico modo per avere una risposta sola a
    due domande diverse: se qualcuno sta gia' ascoltando li' (la redazione
    aperta due volte) e se Windows rifiuta quella porta comunque - interi
    intervalli sono riservati da Hyper-V o da WSL, e chi ci capita in mezzo si
    prende un errore di permessi che non ha niente a che fare con noi.

    Il socket di prova non attiva SO_REUSEADDR: senza quell'opzione una porta
    occupata fa fallire il bind, che e' esattamente la risposta che serve.
    Werkzeug invece la attiva, e per questo un suo bind riuscito non
    dimostrerebbe che la porta era libera.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as presa:
        try:
            presa.bind((indirizzo, porta))
        except OSError:
            return False
    return True


def _server(applicazione, indirizzo: str, porta: int):
    """Il primo server che riesce ad aprire la porta, partendo da quella chiesta.

    `make_server` lega il socket subito: se torna, la redazione sta gia'
    ascoltando, e da quel momento aprire il browser e' sicuro. In *threaded*
    perche' una generazione a cache fredda o il rinnovo dei token possono
    richiedere secondi, e non devono bloccare il resto dell'interfaccia.
    """
    for tentativo in range(PORTE_DA_PROVARE):
        prova = porta + tentativo
        if not _libera(indirizzo, prova):
            continue
        try:
            return make_server(indirizzo, prova, applicazione, threaded=True)
        except (OSError, SystemExit):
            # Fra la prova e questo bind la porta puo' essere stata presa da
            # qualcun altro. SystemExit perche' Werkzeug, se il bind fallisce,
            # stampa un avviso e chiama sys.exit: senza intercettarlo, l'app
            # morirebbe qui invece di provare la porta seguente.
            continue
    ultima = porta + PORTE_DA_PROVARE - 1
    raise SystemExit(
        f"Nessuna porta libera fra {porta} e {ultima}. "
        "La redazione è forse già aperta in un'altra finestra?"
    )


def avvia(porta: int | None = None, apri_browser: bool = True) -> int:
    # Importato qui e non in cima: app.py si appoggia a sua volta a questo modulo
    # per il proprio avvio, e due import incrociati in cima non si reggerebbero.
    from app import INDIRIZZO, PORTA_PREDEFINITA, crea_app

    _console_utf8()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    servitore = _server(crea_app(), INDIRIZZO, PORTA_PREDEFINITA if porta is None else porta)
    indirizzo = f"http://{INDIRIZZO}:{servitore.server_port}"
    # flush: se l'avvio viene rediretto su file, l'indirizzo compare subito e
    # non resta in attesa nel buffer finche' il server non si ferma.
    print(f"\n  La redazione è aperta su {indirizzo}", flush=True)
    print("  Chiudi questa finestra, o premi Ctrl+C, per fermarla.\n", flush=True)

    if apri_browser:
        # Il socket ascolta gia': il ritardo serve solo a far comparire prima il
        # messaggio qui sopra, non ad aspettare che il server sia pronto.
        threading.Timer(0.2, webbrowser.open, args=(indirizzo,)).start()

    try:
        servitore.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servitore.server_close()
    print("\n  Redazione chiusa.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Avvia la redazione di FantaMagazine.")
    parser.add_argument("--porta", type=int, default=None, help="Porta da provare per prima")
    parser.add_argument("--no-browser", action="store_true", help="Non aprire il browser")
    argomenti = parser.parse_args()
    return avvia(argomenti.porta, not argomenti.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
