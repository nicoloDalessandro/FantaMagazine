"""Le operazioni del progetto, indipendenti da chi le usa.

La riga di comando e l'interfaccia web fanno le stesse cose — entrare con il
proprio account, scegliere leghe e testate, generare la prima pagina e la sua
immagine, svuotare la cache — ma le presentano in modo diverso. Qui vive la logica una volta sola: niente stampe,
niente codici di uscita, niente HTML. Chi chiama riceve dati oppure un
`ErroreServizio` con un codice stabile, e decide lui come mostrarlo.
"""

from __future__ import annotations

import json
import os
import random
import re
import secrets
import shutil
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import requests

from . import (
    accesso,
    analysis,
    api,
    auth,
    browser,
    config,
    gemini,
    impostazioni,
    listone,
    prompt,
    resoconto,
    storico,
    tendenze,
)

MESI = (
    "gennaio febbraio marzo aprile maggio giugno luglio "
    "agosto settembre ottobre novembre dicembre"
).split()

Log = Callable[[str], None]


class ErroreServizio(Exception):
    """Un problema che l'utente può capire e, di solito, risolvere.

    `codice` è stabile e pensato per le macchine: l'interfaccia web lo usa per
    decidere cosa proporre (per esempio il pulsante di rinnovo dei token).
    `uscita` è il codice di uscita della riga di comando: 2 per i problemi di
    autenticazione (compresa una lega senza token e un accesso non riuscito),
    1 per tutto il resto, come prima dell'estrazione.
    """

    STATI_HTTP = {
        "token_mancante": 401,
        "token_scaduto": 401,
        "accesso_credenziali": 401,
        "accesso_sessione_scaduta": 401,
        "accesso_mancante": 409,
        "accesso_applicazione": 502,
        "accesso_risposta": 502,
        "accesso_servizio": 503,
        "accesso_rete": 503,
        "impostazioni_non_valide": 400,
        "lega_sconosciuta": 404,
        "competizione_sconosciuta": 404,
        "giornata_non_disponibile": 404,
        "nessuna_competizione": 409,
        "nessuna_giornata": 409,
        "formato_non_supportato": 422,
        "nessuna_lega": 409,
        "browser": 503,
        "api": 502,
        "rete": 503,
        "immagine_inesistente": 404,
        "gemini_chiave_mancante": 412,
        "gemini_chiave_non_valida": 401,
        "gemini_permesso": 403,
        "gemini_quota": 429,
        "gemini_modello_non_disponibile": 404,
        "gemini_bloccata": 422,
        "gemini_nessuna_immagine": 502,
        "gemini_richiesta_non_valida": 400,
        "gemini_tempo_scaduto": 504,
        "gemini_rete": 503,
        "gemini_servizio": 502,
    }

    def __init__(self, messaggio: str, codice: str) -> None:
        super().__init__(messaggio)
        self.messaggio = messaggio
        self.codice = codice

    @property
    def stato_http(self) -> int:
        return self.STATI_HTTP.get(self.codice, 400)

    @property
    def uscita(self) -> int:
        autenticazione = self.codice.startswith(("token", "accesso_")) or self.codice == "lega_sconosciuta"
        return 2 if autenticazione else 1


# --- Date ---------------------------------------------------------------------
def stagione(oggi: date) -> str:
    inizio = oggi.year if oggi.month >= 7 else oggi.year - 1
    return f"{inizio}-{str(inizio + 1)[-2:]}"


def data_estesa(oggi: date) -> str:
    return f"{oggi.day} {MESI[oggi.month - 1]} {oggi.year}"


# --- Traduzione degli errori ----------------------------------------------------
def _traduci(errore: Exception) -> ErroreServizio:
    if isinstance(errore, ErroreServizio):
        return errore
    if isinstance(errore, api.TokenScaduto):
        return ErroreServizio(
            "L'accesso a questa lega non è più valido: entra di nuovo con il tuo account.",
            "token_scaduto",
        )
    if isinstance(errore, api.ApiError):
        return ErroreServizio(f"L'API di Leghe Fantacalcio ha risposto male: {errore}", "api")
    if isinstance(errore, requests.RequestException):
        return ErroreServizio(
            "Leghe Fantacalcio non è raggiungibile. Controlla la connessione e riprova.",
            "rete",
        )
    if isinstance(errore, auth.TokenMancante):
        return ErroreServizio(
            "Nessun accesso salvato: entra con il tuo account di Leghe Fantacalcio.",
            "token_mancante",
        )
    if isinstance(errore, accesso.ErroreAccesso):
        return ErroreServizio(errore.messaggio, f"accesso_{errore.codice}")
    raise errore


def _lega(alias: str) -> auth.Lega:
    try:
        leghe = auth.carica_leghe()
    except auth.TokenMancante as errore:
        raise _traduci(errore) from errore
    if not leghe:
        raise _traduci(auth.TokenMancante())
    if alias not in leghe:
        raise ErroreServizio(
            f"Nessun token per la lega «{alias}». Se ne fai parte, aggiorna l'elenco delle leghe.",
            "lega_sconosciuta",
        )
    return leghe[alias]


def competizioni(alias: str, tutte: bool = False) -> list[tuple[str, str]]:
    """(id, nome) delle competizioni di una lega, senza scaricarne i calendari.

    Per difetto solo quelle che l'utente non ha escluso; `tutte` le restituisce
    comunque, per chi deve mostrarle tutte e lasciarle scegliere.
    """
    lega = _lega(alias)
    try:
        trovate = api.competizioni_disponibili(api.Client(lega.token))
    except (api.ApiError, requests.RequestException) as errore:
        raise _traduci(errore) from errore
    if not trovate:
        raise ErroreServizio(f"{lega.nome} non ha competizioni.", "nessuna_competizione")
    if tutte:
        return trovate
    scelta = impostazioni.scelta(alias)
    scelte = [(i, n) for i, n in trovate if scelta.usa_competizione(i)]
    if not scelte:
        raise ErroreServizio(
            f"Hai escluso tutte le competizioni di {lega.nome}: riattivane una fra le tue leghe.",
            "nessuna_competizione",
        )
    return scelte


# --- Elenco delle leghe ---------------------------------------------------------
@dataclass
class StatoCompetizione:
    id: str
    nome: str
    giornate_totali: int = 0
    giornate_calcolate: list[int] = field(default_factory=list)
    supportata: bool | None = None
    errore: str | None = None
    attiva: bool = True

    @property
    def ultima(self) -> int | None:
        return max(self.giornate_calcolate) if self.giornate_calcolate else None


@dataclass
class StatoLega:
    alias: str
    nome: str
    testata: str
    competizioni: list[StatoCompetizione] = field(default_factory=list)
    errore: str | None = None
    codice_errore: str | None = None
    attiva: bool = True


def stato_leghe(tutte: bool = False) -> list[StatoLega]:
    """Le leghe con token, con competizioni e giornate già disputate.

    Per difetto solo quelle che l'utente usa: leghe attive e competizioni non
    escluse, che sono anche le sole di cui si scaricano i calendari. Con
    `tutte` compaiono anche le altre, segnate come non attive.

    Un problema su una singola lega non ferma l'elenco: resta annotato sulla
    lega, così le altre restano utilizzabili.
    """
    try:
        leghe = auth.carica_leghe()
    except auth.TokenMancante as errore:
        raise _traduci(errore) from errore
    if not leghe:
        raise _traduci(auth.TokenMancante())

    scelte = impostazioni.carica()
    risultato: list[StatoLega] = []
    for alias, lega in sorted(leghe.items()):
        scelta = scelte.get(alias, impostazioni.SceltaLega())
        if not scelta.attiva and not tutte:
            continue
        stato = StatoLega(
            alias=alias,
            nome=lega.nome,
            testata=impostazioni.testata(alias, lega.nome),
            attiva=scelta.attiva,
        )
        try:
            client = api.Client(lega.token)
            for identificativo, nome in api.competizioni_disponibili(client):
                if not scelta.usa_competizione(identificativo) and not tutte:
                    continue
                voce = StatoCompetizione(
                    id=identificativo, nome=nome, attiva=scelta.usa_competizione(identificativo)
                )
                try:
                    calendario = client.calendario(identificativo)
                    disputate = analysis.giornate_calcolate(calendario)
                    voce.giornate_totali = len(calendario)
                    voce.giornate_calcolate = sorted(g["matchDay"] for g in disputate)
                    if disputate:
                        ultima = max(disputate, key=lambda g: g["matchDay"])
                        voce.supportata = analysis.scontri_diretti(ultima)
                except api.TokenScaduto:
                    raise
                except (api.ApiError, requests.RequestException) as errore:
                    voce.errore = _traduci(errore).messaggio
                stato.competizioni.append(voce)
        except (api.ApiError, requests.RequestException) as errore:
            tradotto = _traduci(errore)
            stato.errore = tradotto.messaggio
            stato.codice_errore = tradotto.codice
        risultato.append(stato)
    return risultato


# --- Generazione ------------------------------------------------------------------
@dataclass
class Risultato:
    prompt: str
    pagina: prompt.PrimaPagina
    lega: str
    nome_lega: str
    competizione: str
    nome_competizione: str
    avvisi: list[str] = field(default_factory=list)
    # Che cosa ricorda la memoria e che cosa ne è finito in questa pagina.
    memoria: resoconto.Resoconto | None = None


def genera(
    alias: str,
    competizione: str,
    giornata: int | None = None,
    seme: int | None = None,
    varia: bool = False,
    usa_cache: bool = True,
    oggi: date | None = None,
    su_log: Log | None = None,
) -> Risultato:
    """Genera la prima pagina di una giornata. Solleva ErroreServizio.

    Senza `giornata` si usa l'ultima disputata. `seme` fissa le formule; con
    `varia` se ne sceglie uno a caso. Senza nessuno dei due il testo dipende
    solo dalla giornata, quindi rigenerarla dà lo stesso prompt.
    """
    log = su_log or (lambda _messaggio: None)
    avvisi: list[str] = []
    lega = _lega(alias)
    competizione = str(competizione)

    try:
        client = api.Client(lega.token)
        nomi_competizioni = dict(api.competizioni_disponibili(client))
        if not nomi_competizioni:
            raise ErroreServizio(f"{lega.nome} non ha competizioni.", "nessuna_competizione")
        if competizione not in nomi_competizioni:
            raise ErroreServizio(
                f"La competizione {competizione} non appartiene a {lega.nome}.",
                "competizione_sconosciuta",
            )
        nome_competizione = nomi_competizioni[competizione]

        calendario = client.calendario(competizione)
        log(f"competizione {competizione}, {len(calendario)} giornate in calendario")

        disputate = analysis.giornate_calcolate(calendario)
        if not disputate:
            raise ErroreServizio(
                f"{lega.nome}: nessuna giornata ancora calcolata in «{nome_competizione}». "
                f"Il calendario esiste ({len(calendario)} giornate) ma non si è giocato, "
                f"oppure i punteggi non sono stati elaborati.",
                "nessuna_giornata",
            )

        if not analysis.scontri_diretti(max(disputate, key=lambda g: g["matchDay"])):
            raise ErroreServizio(
                f"«{nome_competizione}» non usa scontri diretti: nella stessa giornata "
                "ogni squadra affronta tutte le altre (formato Royale o simile). "
                "Classifica e commenti assumono partite a coppie, quindi produrrebbero "
                "numeri privi di senso. Scegli un Fanta Campionato.",
                "formato_non_supportato",
            )

        if giornata is not None:
            scelte = [g for g in disputate if g["matchDay"] == int(giornata)]
            if not scelte:
                raise ErroreServizio(
                    f"La giornata {giornata} non esiste o non è ancora calcolata.",
                    "giornata_non_disponibile",
                )
            bersaglio = scelte[0]
        else:
            bersaglio = analysis.ultima_giornata(calendario)

        nomi_squadre = {s["id"]: s["n"].strip() for s in client.squadre()}
        nomi_giocatori = listone.carica(client, lega.alias, usa_cache=usa_cache, su_log=log)
        log(f"{len(nomi_squadre)} squadre, {len(nomi_giocatori)} giocatori")

        # Lo storico si ferma alla giornata analizzata: una giornata passata
        # produce il commento che si sarebbe letto quel giorno, non uno che
        # conosce il futuro.
        fino_a = bersaglio["matchDay"]
        calendario_fino_a = [g for g in calendario if g["matchDay"] <= fino_a]

        def avvisa(messaggio: str) -> None:
            avvisi.append(messaggio)
            log(f"  ATTENZIONE: {messaggio}")

        completo = storico.carica_storico(
            client,
            competizione,
            calendario_fino_a,
            nomi_squadre,
            nomi_giocatori,
            usa_cache=usa_cache,
            su_avviso=avvisa,
            su_progresso=lambda n: log(f"  giornata {n}"),
        )

        # Un giocatore arrivato dal mercato non è nel listone salvato, e in
        # pagina comparirebbe col suo codice: lo si riscarica una volta sola, e
        # le formazioni si rileggono dalla cache senza altre chiamate.
        mancanti = listone.codici_sconosciuti(completo)
        if mancanti and usa_cache and not mancanti <= listone.irrisolti(lega.alias):
            log(f"listone da aggiornare: {len(mancanti)} giocatori sconosciuti")
            nomi_giocatori = listone.carica(client, lega.alias, usa_cache=False, su_log=log)
            completo = storico.carica_storico(
                client,
                competizione,
                calendario_fino_a,
                nomi_squadre,
                nomi_giocatori,
                usa_cache=usa_cache,
                su_avviso=avvisa,
            )
            # Chi non c'è nemmeno nel listone fresco (un ceduto all'estero, per
            # dire) resta senza nome: si annota, o lo si andrebbe a ricercare a
            # ogni generazione.
            ancora = listone.codici_sconosciuti(completo)
            if ancora:
                listone.segna_irrisolti(lega.alias, ancora)
                log(f"  {len(ancora)} giocatori sconosciuti anche al listone aggiornato")
    except ErroreServizio:
        raise
    except (api.ApiError, requests.RequestException, auth.TokenMancante) as errore:
        raise _traduci(errore) from errore

    memoria = tendenze.calcola(completo)
    log(f"memoria: {memoria.giornate} giornate, {len(memoria.giocatori)} giocatori tracciati")
    if memoria.abbastanza_storia:
        for squadra in memoria.in_crisi()[:3]:
            log(f"  crisi: {squadra.nome} ({squadra.striscia_sconfitte} sconfitte)")
        for giocatore in memoria.in_striscia_gol()[:3]:
            log(f"  in gol: {giocatore.nome} ({giocatore.striscia_gol} presenze)")
    else:
        log("  storia insufficiente per le strisce: servono almeno 2 giornate")

    tabella = analysis.classifica(calendario_fino_a, nomi_squadre)
    oggi = oggi or date.today()
    testata = impostazioni.testata(lega.alias, lega.nome)
    log(f"testata: {testata}")

    # Per difetto il testo è stabile: la stessa giornata dà sempre lo stesso
    # prompt. `varia` rompe di proposito questa stabilità quando si vogliono
    # più versioni fra cui scegliere.
    if seme is None and varia:
        seme = random.randrange(10_000)
    if seme is not None:
        log(f"seme: {seme}")

    pagina = prompt.componi(
        partite=completo[fino_a],
        tabella=tabella,
        giornata=fino_a,
        stagione=stagione(oggi),
        data=data_estesa(oggi),
        testata=testata,
        memoria=memoria,
        seme=seme,
    )
    return Risultato(
        prompt=prompt.renderizza(pagina),
        pagina=pagina,
        lega=lega.alias,
        nome_lega=lega.nome,
        competizione=competizione,
        nome_competizione=nome_competizione,
        avvisi=avvisi,
        memoria=resoconto.componi(memoria, pagina),
    )


# --- Account -----------------------------------------------------------------------
@dataclass
class Account:
    collegato: bool  # ci sono token di lega utilizzabili
    username: str | None
    aggiornabile: bool  # c'è l'utente: l'elenco delle leghe si aggiorna senza password
    leghe: int


def stato_account() -> Account:
    """Chi è entrato e con quante leghe. Mai un token."""
    utente = auth.carica_utente()
    try:
        leghe = auth.carica_leghe()
    except auth.TokenMancante:
        leghe = {}
    return Account(
        collegato=bool(leghe),
        username=(utente.username or None) if utente else None,
        aggiornabile=utente is not None,
        leghe=len(leghe),
    )


def _salva_accesso(utente: accesso.Utente, leghe: list[accesso.LegaUtente]) -> list[dict]:
    if not leghe:
        raise ErroreServizio(
            "L'accesso è riuscito, ma il tuo account non partecipa a nessuna lega.",
            "nessuna_lega",
        )
    auth.salva_leghe(
        [{"alias": lega.alias, "nome": lega.nome, "id": lega.id, "token": lega.token} for lega in leghe]
    )
    auth.salva_utente(utente)
    return [{"alias": lega.alias, "nome": lega.nome} for lega in leghe]


def accedi(username: str, password: str) -> list[dict]:
    """Entra con l'account di Leghe Fantacalcio e salva i token delle sue leghe.

    Restituisce alias e nomi, mai i token. La password serve solo alla chiamata
    di accesso: non viene conservata da nessuna parte.
    """
    try:
        utente, leghe = accesso.accedi(username, password)
    except accesso.ErroreAccesso as errore:
        raise _traduci(errore) from None
    return _salva_accesso(utente, leghe)


def aggiorna_leghe() -> list[dict]:
    """Ritrova le leghe dell'utente, comprese quelle nuove, senza chiedere la password."""
    utente = auth.carica_utente()
    if utente is None:
        raise ErroreServizio(
            "Per aggiornare l'elenco delle leghe entra con username e password.",
            "accesso_mancante",
        )
    try:
        nuovo, leghe = accesso.profilo(utente)
    except accesso.ErroreAccesso as errore:
        raise _traduci(errore) from None
    return _salva_accesso(nuovo, leghe)


def esci() -> None:
    """Dimentica utente e token. Le scelte su leghe e testate restano per il prossimo accesso."""
    auth.cancella_sessione()


def rinnova_token() -> list[dict]:
    """Rilegge i token dal Chrome dell'utente e li salva. Restituisce alias e nomi, mai i token.

    È la strada per chi entra nel sito con Google o Facebook e non ha una
    password. I token arrivano dal browser e non da un accesso: l'utente di un
    accesso precedente, che potrebbe essere un altro account, si dimentica.
    """
    try:
        leghe = browser.leggi_leghe()
    except browser.ErroreBrowser as errore:
        raise ErroreServizio(str(errore), "browser") from errore
    auth.salva_leghe(leghe)
    auth.dimentica_utente()
    return [{"alias": v["alias"], "nome": v["nome"]} for v in sorted(leghe, key=lambda v: v["alias"])]


# --- Scelte dell'utente ---------------------------------------------------------------
@dataclass
class ImpostazioneCompetizione:
    id: str
    nome: str
    attiva: bool


@dataclass
class ImpostazioneLega:
    alias: str
    nome: str
    attiva: bool
    testata: str
    testata_predefinita: str
    competizioni: list[ImpostazioneCompetizione] = field(default_factory=list)
    # Le esclusioni salvate: se le competizioni non si caricano, chi salva le
    # rimanda tali e quali invece di azzerarle.
    competizioni_escluse: list[str] = field(default_factory=list)
    errore: str | None = None
    codice_errore: str | None = None


def impostazioni_leghe() -> list[ImpostazioneLega]:
    """Tutte le leghe dell'utente con le sue scelte, per poterle cambiare."""
    try:
        leghe = auth.carica_leghe()
    except auth.TokenMancante as errore:
        raise _traduci(errore) from errore
    if not leghe:
        raise _traduci(auth.TokenMancante())

    scelte = impostazioni.carica()
    risultato = []
    for alias, lega in sorted(leghe.items(), key=lambda voce: voce[1].nome.lower()):
        scelta = scelte.get(alias, impostazioni.SceltaLega())
        voce = ImpostazioneLega(
            alias=alias,
            nome=lega.nome,
            attiva=scelta.attiva,
            testata=scelta.testata,
            testata_predefinita=impostazioni.testata_predefinita(lega.nome),
            competizioni_escluse=list(scelta.competizioni_escluse),
        )
        try:
            for identificativo, nome in api.competizioni_disponibili(api.Client(lega.token)):
                voce.competizioni.append(
                    ImpostazioneCompetizione(identificativo, nome, scelta.usa_competizione(identificativo))
                )
        except (api.ApiError, requests.RequestException) as errore:
            tradotto = _traduci(errore)
            voce.errore, voce.codice_errore = tradotto.messaggio, tradotto.codice
        risultato.append(voce)
    return risultato


def salva_impostazioni(voci: list) -> None:
    """Salva le scelte inviate, una voce per lega. Solleva ErroreServizio se non tornano.

    Le leghe non nominate conservano le scelte che avevano.
    """
    try:
        leghe = auth.carica_leghe()
    except auth.TokenMancante as errore:
        raise _traduci(errore) from errore
    if not isinstance(voci, list):
        raise ErroreServizio("Le scelte devono essere un elenco di leghe.", "impostazioni_non_valide")

    scelte = impostazioni.carica()
    for voce in voci:
        alias = voce.get("alias") if isinstance(voce, dict) else None
        if alias not in leghe:
            raise ErroreServizio("Una delle leghe indicate non è fra le tue.", "impostazioni_non_valide")
        attiva = voce.get("attiva", True)
        testata = voce.get("testata", "")
        escluse = voce.get("competizioni_escluse", [])
        valide = (
            isinstance(attiva, bool)
            and isinstance(testata, str)
            and isinstance(escluse, list)
            and all(isinstance(c, (str, int)) and not isinstance(c, bool) for c in escluse)
        )
        if not valide:
            raise ErroreServizio(
                f"Scelte non valide per «{leghe[alias].nome}».", "impostazioni_non_valide"
            )
        scelte[alias] = impostazioni.SceltaLega(
            attiva=attiva,
            testata=impostazioni.pulisci_testata(testata),
            competizioni_escluse=sorted({str(c) for c in escluse}),
        )
    impostazioni.salva(scelte)


# --- Manutenzione -----------------------------------------------------------------


def svuota_cache() -> int:
    return storico.svuota_cache()


def aggiorna_listone(alias: str) -> int:
    """Riscarica il listone di una lega. Restituisce quanti giocatori conosce ora."""
    lega = _lega(alias)
    try:
        nomi = listone.carica(api.Client(lega.token), lega.alias, usa_cache=False)
    except (api.ApiError, requests.RequestException) as errore:
        raise _traduci(errore) from errore
    return len(nomi)


# --- Immagini con Gemini ----------------------------------------------------------
_ID_BOZZA = re.compile(r"[0-9a-f]{32}")
# Una chiave di Google: una riga sola, senza spazi.
_CHIAVE_GEMINI = re.compile(r"[A-Za-z0-9_\-]{20,200}")
_SLUG = re.compile(r"[^a-z0-9-]+")


@dataclass
class Bozza:
    """Un'immagine generata, conservata anche se nessuno la salva.

    Ogni immagine costa: una bozza non salvata resta comunque in
    `.cache/immagini`, così un clic mancato non fa perdere quanto già pagato.
    """

    id: str
    percorso: Path
    mime: str
    nome_file: str
    modello: str
    proporzioni: str
    dimensione: str
    secondi: float
    costo_stimato: float
    commento: str = ""
    salvata: str | None = None


def stato_gemini() -> dict:
    """Ciò che serve all'interfaccia per proporre la generazione. Mai la chiave.

    Nessun modello per immagini ha un piano gratuito: i costi servono a
    scegliere quanto spendere, non se spendere.
    """
    modello = impostazioni.modello_immagine()
    return {
        "disponibile": gemini.chiave_presente(),
        "chiave_da_ambiente": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "chiave_file": config.GEMINI_KEY_FILE.name,
        "modello": modello,
        "modello_da_ambiente": bool(os.getenv("GEMINI_MODELLO", "").strip()),
        "proporzioni": gemini.PROPORZIONI,
        "dimensione": impostazioni.dimensione_immagine(modello),
        "modelli": [
            {
                "id": scheda.id,
                "nome": scheda.nome,
                "nota": scheda.nota,
                "dimensioni": list(scheda.dimensioni),
                "costi": scheda.costi,
            }
            for scheda in gemini.MODELLI
        ],
    }


def salva_chiave_gemini(chiave: str) -> None:
    """Scrive la chiave nel file escluso da git. Non la restituisce mai."""
    chiave = (chiave or "").strip()
    if not _CHIAVE_GEMINI.fullmatch(chiave):
        raise ErroreServizio(
            "Questa non sembra una chiave di Gemini: dovrebbe essere una riga sola di "
            "lettere, numeri, trattini e underscore. Copiala da Google AI Studio.",
            "gemini_chiave_non_valida",
        )
    config.GEMINI_KEY_FILE.write_text(chiave, encoding="utf-8")
    try:
        os.chmod(config.GEMINI_KEY_FILE, 0o600)
    except OSError:
        pass


def rimuovi_chiave_gemini() -> None:
    """Cancella la chiave da questo computer."""
    try:
        config.GEMINI_KEY_FILE.unlink()
    except FileNotFoundError:
        pass


def salva_impostazioni_immagine(modello: str, dimensione: str) -> None:
    """Salva modello e taglia predefiniti per le immagini."""
    if modello not in {scheda.id for scheda in gemini.MODELLI}:
        raise ErroreServizio("Modello non fra quelli disponibili.", "impostazioni_non_valide")
    if dimensione not in gemini.modello(modello).dimensioni:
        raise ErroreServizio(
            f"{gemini.modello(modello).nome} non fa immagini in «{dimensione}».",
            "impostazioni_non_valide",
        )
    impostazioni.salva_immagine(impostazioni.SceltaImmagine(modello=modello, dimensione=dimensione))


def _nome_file(lega: str, giornata: int | None, seme: int | None, estensione: str) -> str:
    """mia-lega_giornata-03_seme-3_2026-09-15_21-34-05.png

    Il seme nel nome permette di rigenerare esattamente la stessa pagina.
    """
    pulito = _SLUG.sub("-", (lega or "lega").lower()).strip("-") or "lega"
    parti = [pulito]
    if giornata is not None:
        parti.append(f"giornata-{int(giornata):02d}")
    if seme is not None:
        parti.append(f"seme-{int(seme)}")
    parti.append(datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    return "_".join(parti) + f".{estensione}"


def _meta(bozza_id: str) -> Path:
    return config.BOZZE_DIR / f"{bozza_id}.json"


def genera_immagine(
    prompt_testo: str,
    lega: str = "",
    giornata: int | None = None,
    seme: int | None = None,
    dimensione: str = "",
    modello: str = "",
) -> Bozza:
    """Manda il prompt a Gemini e conserva l'immagine come bozza.

    Senza modello o taglia si usano quelli scelti nelle impostazioni.
    """
    if len(prompt_testo) > 30_000:
        raise ErroreServizio("Il prompt è troppo lungo per essere inviato.", "gemini_richiesta_non_valida")
    modello = modello or impostazioni.modello_immagine()
    dimensione = dimensione or impostazioni.dimensione_immagine(modello)
    try:
        immagine = gemini.genera(prompt_testo, dimensione=dimensione, modello_scelto=modello)
    except gemini.ErroreGemini as errore:
        raise ErroreServizio(errore.messaggio, f"gemini_{errore.codice}") from errore

    config.BOZZE_DIR.mkdir(parents=True, exist_ok=True)
    bozza_id = secrets.token_hex(16)
    percorso = config.BOZZE_DIR / f"{bozza_id}.{immagine.estensione}"
    percorso.write_bytes(immagine.dati)

    bozza = Bozza(
        id=bozza_id,
        percorso=percorso,
        mime=immagine.mime,
        nome_file=_nome_file(lega, giornata, seme, immagine.estensione),
        modello=immagine.modello,
        proporzioni=immagine.proporzioni,
        dimensione=immagine.dimensione,
        secondi=immagine.secondi,
        costo_stimato=gemini.costo(immagine.modello, immagine.dimensione) or 0.0,
        commento=immagine.commento,
    )
    _meta(bozza_id).write_text(
        json.dumps({**asdict(bozza), "percorso": percorso.name}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bozza


def bozza(bozza_id: str) -> Bozza:
    """Recupera una bozza. L'id deve avere il formato generato qui: niente percorsi."""
    if not _ID_BOZZA.fullmatch(bozza_id or ""):
        raise ErroreServizio("Immagine inesistente.", "immagine_inesistente")
    meta = _meta(bozza_id)
    if not meta.exists():
        raise ErroreServizio("Immagine inesistente.", "immagine_inesistente")
    dati = json.loads(meta.read_text(encoding="utf-8"))
    percorso = config.BOZZE_DIR / Path(dati["percorso"]).name
    if not percorso.exists():
        raise ErroreServizio("Il file dell'immagine non c'è più.", "immagine_inesistente")
    return Bozza(**{**dati, "percorso": percorso})


def salva_immagine(bozza_id: str) -> Path:
    """Copia la bozza nell'archivio delle prime pagine. Salvare due volte non duplica."""
    scelta = bozza(bozza_id)
    if scelta.salvata and Path(scelta.salvata).exists():
        return Path(scelta.salvata)

    config.ARCHIVIO_DIR.mkdir(parents=True, exist_ok=True)
    destinazione = config.ARCHIVIO_DIR / scelta.nome_file
    numero = 2
    while destinazione.exists():
        destinazione = config.ARCHIVIO_DIR / f"{Path(scelta.nome_file).stem}-{numero}{Path(scelta.nome_file).suffix}"
        numero += 1
    shutil.copyfile(scelta.percorso, destinazione)

    meta = _meta(bozza_id)
    dati = json.loads(meta.read_text(encoding="utf-8"))
    dati["salvata"] = str(destinazione)
    meta.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
    return destinazione
