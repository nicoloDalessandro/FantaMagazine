"""Genera il prompt della prima pagina a partire dall'ultima giornata disputata.

Se la lega non viene indicata, lo script la chiede. Su stdout finisce
esclusivamente il prompt, così è incollabile o reindirizzabile: il menu e ogni
diagnostica passano da stderr.

    python main.py --accedi                 # entra con il tuo account (una volta l'anno)
    python main.py                          # chiede quale lega
    python main.py --lega la-mia-lega       # senza domande
    python main.py --lista                  # elenca leghe e competizioni
    python main.py > prompt.txt             # il menu resta visibile a schermo
    python main.py --verbose                # diagnostica su stderr
    python main.py --giornata 3             # forza una giornata specifica
    python main.py --apertura "Bar Sport"   # quella partita in prima pagina
    python main.py --varia                  # riformula a ogni esecuzione
    python main.py --memoria                # mostra cosa ricorda e cosa usa in pagina
    python main.py --immagine               # genera anche l'immagine con Gemini
    python main.py --rigenera-cache         # riscarica lo storico da zero
    python main.py --rigenera-listone       # riscarica il listone dei giocatori

Per un'interfaccia grafica:  python app.py
"""

from __future__ import annotations

import argparse
import getpass
import sys

from fantamagazine import auth, gemini, impostazioni, listone, servizio

# Il prompt contiene accenti italiani: senza questo, su una console Windows con
# code page legacy l'output verrebbe mutilato.
for flusso in (sys.stdout, sys.stderr):
    try:
        flusso.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Suggerimenti specifici della riga di comando. Il servizio spiega il problema;
# come risolverlo dipende da dove lo si legge (qui un comando, sul web un pulsante).
SUGGERIMENTI = {
    "token_mancante": "Entra con:  python main.py --accedi",
    "token_scaduto": "Entra di nuovo con:  python main.py --accedi",
    "accesso_sessione_scaduta": "Entra di nuovo con:  python main.py --accedi",
    "accesso_mancante": "Entra con:  python main.py --accedi",
    "lega_sconosciuta": "Aggiorna l'elenco con:  python main.py --aggiorna-leghe",
    "browser": "In alternativa entra con username e password:  python main.py --accedi",
    "nessuna_giornata": "Vedi quali competizioni hanno dati con:  python main.py --lista",
    "competizione_sconosciuta": "Vedi le competizioni disponibili con:  python main.py --lista",
    "gemini_quota": "Attiva la fatturazione sul progetto della chiave:  https://aistudio.google.com/apikey",
    "gemini_chiave_mancante": "Salva la chiave nel file .gemini_key o nella variabile GEMINI_API_KEY",
    "gemini_chiave_non_valida": "Crea una nuova chiave su https://aistudio.google.com/apikey",
}


def _chiedi(voci: list[tuple[str, str]], domanda: str) -> str:
    """Menu numerato su stderr. Restituisce la chiave scelta.

    Con una sola voce non chiede nulla. Se stdin non è un terminale (script in
    pipe o in cron) sceglie la prima e lo dichiara, invece di bloccarsi.
    """
    if len(voci) == 1:
        return voci[0][0]

    if not sys.stdin.isatty():
        print(
            f"{domanda}: più opzioni disponibili, scelgo '{voci[0][1]}'. "
            "Usa --lega o --competizione per decidere.",
            file=sys.stderr,
        )
        return voci[0][0]

    print(f"\n{domanda}", file=sys.stderr)
    for numero, (_, etichetta) in enumerate(voci, 1):
        print(f"  {numero}) {etichetta}", file=sys.stderr)

    while True:
        try:
            risposta = input("> ").strip()
        except EOFError:
            # Nessuno può rispondere (pipe, cron, o isatty inaffidabile su
            # Windows): si prosegue con la prima invece di interrompere.
            print(
                f"  nessuna risposta, scelgo '{voci[0][1]}'. "
                "Usa --lega o --competizione per decidere.",
                file=sys.stderr,
            )
            return voci[0][0]
        except KeyboardInterrupt:
            print("\nAnnullato.", file=sys.stderr)
            raise SystemExit(130)

        if not risposta:
            return voci[0][0]
        if risposta.isdigit() and 1 <= int(risposta) <= len(voci):
            return voci[int(risposta) - 1][0]

        # Accetta anche l'alias scritto per esteso.
        for chiave, _ in voci:
            if risposta.lower() == chiave.lower():
                return chiave

        print(f"  Scegli un numero fra 1 e {len(voci)}.", file=sys.stderr)


def _elenca() -> int:
    """Elenca leghe, competizioni e quante giornate hanno già dati, anche quelle escluse."""
    for lega in servizio.stato_leghe(tutte=True):
        esclusa = "" if lega.attiva else "  [non usata]"
        print(f"{lega.alias}  ({lega.nome})  testata: {lega.testata}{esclusa}")
        if lega.errore:
            print(f"    [non raggiungibile: {lega.errore}]")
            continue
        for voce in lega.competizioni:
            if voce.errore:
                stato = f"errore: {voce.errore}"
            elif voce.giornate_calcolate:
                stato = (
                    f"{len(voce.giornate_calcolate)}/{voce.giornate_totali} giornate, "
                    f"ultima: {voce.ultima}"
                )
            else:
                stato = f"0/{voce.giornate_totali} giornate - non ancora iniziata"
            if not voce.attiva:
                stato += "  [esclusa]"
            print(f"    {voce.id:<8} {voce.nome:<28} {stato}")
    return 0


def _accedi() -> int:
    """Chiede username e password e salva i token. La password non si vede e non si salva."""
    print("Accesso a Leghe Fantacalcio. La password serve solo ora: non viene salvata.", file=sys.stderr)
    try:
        print("Username o email: ", end="", file=sys.stderr, flush=True)
        username = input().strip()
        password = getpass.getpass("Password: ", stream=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print("\nAccesso annullato.", file=sys.stderr)
        return 130
    leghe = servizio.accedi(username, password)
    del password
    print(f"\nAccesso riuscito: {len(leghe)} {'lega' if len(leghe) == 1 else 'leghe'}.", file=sys.stderr)
    for voce in leghe:
        print(f"  {voce['alias']:<28} {voce['nome']}", file=sys.stderr)
    print(
        "\nPer scegliere leghe, competizioni e nome del giornale apri la redazione "
        "(python app.py) oppure usa --imposta-testata.",
        file=sys.stderr,
    )
    return 0


def _aggiorna_leghe() -> int:
    leghe = servizio.aggiorna_leghe()
    print(f"Elenco aggiornato: {len(leghe)} {'lega' if len(leghe) == 1 else 'leghe'}.", file=sys.stderr)
    for voce in leghe:
        print(f"  {voce['alias']:<28} {voce['nome']}", file=sys.stderr)
    return 0


def _imposta_testata(alias: str, testo: str) -> int:
    leghe = auth.carica_leghe()
    if alias not in leghe:
        raise servizio.ErroreServizio(f"Nessuna lega «{alias}» fra le tue.", "lega_sconosciuta")
    scelta = impostazioni.scelta(alias)
    servizio.salva_impostazioni([{
        "alias": alias,
        "attiva": scelta.attiva,
        "testata": testo,
        "competizioni_escluse": scelta.competizioni_escluse,
    }])
    print(f"Testata di {leghe[alias].nome}: {impostazioni.testata(alias, leghe[alias].nome)}", file=sys.stderr)
    return 0


SEZIONI = {
    "titolo": "Titolo",
    "racconto": "Il racconto",
    "dietro_i_numeri": "Dietro i numeri",
    "trafiletti": "Trafiletti",
}


def _numero(valore: float) -> str:
    return f"{valore:g}".replace(".", ",")


def _stampa_memoria(risultato: servizio.Risultato, giocatori: int = 10) -> None:
    """Che cosa ricorda la memoria e che cosa ne è finito in pagina, su stderr.

    Su stdout resta solo il prompt: così `--memoria` si può usare anche
    reindirizzando il prompt su un file.
    """
    resoconto = risultato.memoria
    if resoconto is None:
        return

    def scrivi(riga: str = "") -> None:
        print(riga, file=sys.stderr)

    scrivi()
    scrivi("MEMORIA")
    scrivi(resoconto.sintesi)

    richiami = risultato.pagina.richiami
    if richiami:
        scrivi()
        scrivi("In pagina grazie alla memoria")
        for richiamo in richiami:
            testo = " — ".join(parte for parte in (richiamo.titolo, richiamo.testo) if parte)
            scrivi(f"  {SEZIONI.get(richiamo.sezione, richiamo.sezione):<16} {testo}")
            notizia = next(
                (n for n in resoconto.notizie
                 if n.tipo == richiamo.tipo and n.soggetto == richiamo.squadra),
                None,
            )
            fatto = notizia.fatto if notizia else richiamo.tipo
            scrivi(f"  {'':<16} perché {richiamo.squadra}: {fatto}")

    if resoconto.notizie:
        scrivi()
        scrivi("Notizie in memoria")
        for notizia in resoconto.notizie:
            if notizia.sezioni:
                stato = "in pagina"
            elif notizia.raccontabile:
                stato = "fuori"
            else:
                stato = "non usata"
            soggetto = notizia.soggetto
            if notizia.squadra != notizia.soggetto:
                soggetto += f" ({notizia.squadra})"
            dove = ", ".join(SEZIONI.get(s, s).lower() for s in notizia.sezioni)
            scrivi(f"  {stato:<10} {soggetto}: {notizia.fatto}" + (f"  [{dove}]" if dove else ""))

    scrivi()
    scrivi("Squadre")
    for squadra in resoconto.squadre:
        posizione = f"{squadra.posizione:>2}" if squadra.posizione else " -"
        andamento = " ".join(squadra.esiti[-10:])
        serie = ", ".join(squadra.serie) or "-"
        scrivi(
            f"  {posizione} {squadra.nome:<28} {andamento:<20} {serie:<34} "
            f"media {_numero(squadra.media_fantapunti)}"
        )

    if resoconto.giocatori:
        scrivi()
        scrivi(f"Giocatori (i primi {min(giocatori, len(resoconto.giocatori))} di {len(resoconto.giocatori)})")
        for giocatore in resoconto.giocatori[:giocatori]:
            nome = f"{giocatore.nome} ({giocatore.squadra})"
            di_fila = f", in gol da {giocatore.striscia_gol} di fila" if giocatore.striscia_gol >= 2 else ""
            presenze = "1 presenza" if giocatore.presenze == 1 else f"{giocatore.presenze} presenze"
            scrivi(
                f"  {nome:<40} {giocatore.gol} gol in {presenze}{di_fila}, "
                f"media voto {_numero(giocatore.media_voto)}"
            )
    scrivi()
    scrivi("Regole: dove può entrare la memoria")
    for sezione, regola in resoconto.regole:
        scrivi(f"  {sezione}: {regola}")


def _esegui(argomenti: argparse.Namespace) -> int:
    loud = argomenti.verbose

    def log(messaggio: str, sempre: bool = False) -> None:
        if loud or sempre:
            print(messaggio, file=sys.stderr)

    if argomenti.accedi:
        return _accedi()
    if argomenti.esci:
        servizio.esci()
        print("Accesso dimenticato: utente e token cancellati da questo computer.", file=sys.stderr)
        return 0
    if argomenti.aggiorna_leghe:
        return _aggiorna_leghe()
    if argomenti.imposta_testata:
        return _imposta_testata(*argomenti.imposta_testata)
    if argomenti.lista:
        return _elenca()

    # --- Scelta della lega -------------------------------------------------
    if argomenti.lega:
        # Una lega indicata per nome si usa anche se nel menu è esclusa.
        alias = argomenti.lega
    else:
        try:
            leghe = auth.carica_leghe()
        except auth.TokenMancante as errore:
            raise servizio.ErroreServizio(str(errore), "token_mancante") from errore
        if not leghe:
            raise servizio.ErroreServizio("Nessun accesso salvato.", "token_mancante")
        scelte = impostazioni.carica()
        attive = {a: l for a, l in leghe.items() if scelte.get(a, impostazioni.SceltaLega()).attiva}
        if not attive:
            raise servizio.ErroreServizio(
                "Hai escluso tutte le tue leghe: riattivane una nella redazione, "
                "oppure indicala con --lega.",
                "nessuna_lega",
            )
        voci = [(a, f"{l.nome}  ({a})") for a, l in sorted(attive.items())]
        alias = _chiedi(voci, "Per quale lega vuoi generare il prompt?")
        log(f"lega: {attive[alias].nome} [{alias}]", sempre=True)

    if argomenti.rigenera_cache:
        log(f"cache svuotata: {servizio.svuota_cache()} file", sempre=True)

    if argomenti.rigenera_listone:
        log(f"listone da riscaricare: {listone.svuota()} file rimossi", sempre=True)

    # --- Scelta della competizione ----------------------------------------
    if argomenti.competizione:
        competizione = str(argomenti.competizione)
    else:
        disponibili = servizio.competizioni(alias)
        competizione = _chiedi(
            [(i, f"{n}  ({i})") for i, n in disponibili],
            "Quale competizione?",
        )

    risultato = servizio.genera(
        alias,
        competizione,
        giornata=argomenti.giornata,
        seme=argomenti.seme,
        varia=argomenti.varia,
        usa_cache=not argomenti.no_cache,
        su_log=log,
        apertura=argomenti.apertura,
    )
    # Gli avvisi di validazione si mostrano sempre, anche senza --verbose.
    if not loud:
        for avviso in risultato.avvisi:
            print(f"  ATTENZIONE: {avviso}", file=sys.stderr)

    print(risultato.prompt)

    if argomenti.memoria:
        sys.stdout.flush()
        _stampa_memoria(risultato)

    if argomenti.immagine:
        # Il prompt è già su stdout: se Gemini fallisce resta comunque utilizzabile.
        sys.stdout.flush()
        modello = argomenti.modello or impostazioni.modello_immagine()
        risoluzione = argomenti.risoluzione or impostazioni.dimensione_immagine(modello)
        costo = gemini.costo(modello, risoluzione)
        spesa = f"circa {costo:.3f} $".rstrip("0").rstrip(",") if costo else "costo non in listino"
        print(
            f"Invio a Gemini ({gemini.modello(modello).nome}, {gemini.PROPORZIONI}, "
            f"{risoluzione}, {spesa}): può richiedere un minuto...",
            file=sys.stderr,
        )
        bozza = servizio.genera_immagine(
            risultato.prompt,
            lega=risultato.lega,
            giornata=risultato.pagina.giornata,
            seme=risultato.pagina.seme,
            dimensione=risoluzione,
            modello=modello,
        )
        percorso = servizio.salva_immagine(bozza.id)
        print(f"Immagine salvata in {percorso} ({bozza.secondi} s)", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    account = parser.add_argument_group("account")
    account.add_argument(
        "--accedi", action="store_true",
        help="Entra con username e password di Leghe Fantacalcio (la password non viene salvata)",
    )
    account.add_argument(
        "--aggiorna-leghe", action="store_true",
        help="Ritrova le tue leghe, anche quelle nuove, senza chiedere la password",
    )
    account.add_argument("--esci", action="store_true", help="Cancella utente e token da questo computer")
    account.add_argument(
        "--imposta-testata", nargs=2, metavar=("ALIAS", "TESTATA"),
        help="Dà un nome al giornale di una lega (vuoto per tornare a quello predefinito)",
    )
    parser.add_argument("--lega", help="Alias della lega (salta la domanda)")
    parser.add_argument("--competizione", help="Id della competizione (salta la domanda)")
    parser.add_argument("--lista", action="store_true", help="Elenca leghe e competizioni")
    parser.add_argument("--giornata", type=int, help="Analizza questa giornata invece dell'ultima")
    parser.add_argument(
        "--apertura",
        metavar="SQUADRA",
        help="Mette in prima pagina la partita di questa squadra, in casa o fuori",
    )
    parser.add_argument("--verbose", action="store_true", help="Diagnostica su stderr")
    parser.add_argument(
        "--varia",
        action="store_true",
        help="Riformula il pezzo a ogni esecuzione (per difetto il testo è stabile)",
    )
    parser.add_argument(
        "--seme",
        type=int,
        help="Seme delle formule: lo stesso seme rigenera lo stesso testo",
    )
    parser.add_argument(
        "--memoria",
        action="store_true",
        help="Mostra su stderr cosa ricorda la memoria e cosa ne è finito in pagina",
    )
    parser.add_argument(
        "--immagine",
        action="store_true",
        help="Manda il prompt a Gemini e salva l'immagine in prime_pagine/",
    )
    parser.add_argument(
        "--modello",
        choices=[scheda.id for scheda in gemini.MODELLI],
        help="Modello per l'immagine (predefinito: quello scelto nelle impostazioni)",
    )
    parser.add_argument(
        "--risoluzione",
        choices=sorted({t for scheda in gemini.MODELLI for t in scheda.dimensioni}),
        help="Risoluzione dell'immagine, fra quelle che il modello sa fare",
    )
    parser.add_argument(
        "--rigenera-cache", action="store_true", help="Svuota la cache e riscarica"
    )
    parser.add_argument(
        "--rigenera-listone",
        action="store_true",
        help="Riscarica il listone dei giocatori, se una rosa è cambiata",
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Ignora la cache senza cancellarla"
    )

    try:
        return _esegui(parser.parse_args())
    except servizio.ErroreServizio as errore:
        print(errore.messaggio, file=sys.stderr)
        if errore.codice in SUGGERIMENTI:
            print(f"  {SUGGERIMENTI[errore.codice]}", file=sys.stderr)
        return errore.uscita


if __name__ == "__main__":
    raise SystemExit(main())
