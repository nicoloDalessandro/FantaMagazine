"""Generazione dell'immagine della prima pagina con Gemini.

Il modulo non sa nulla di leghe o giornate: riceve il testo del prompt e
restituisce un'immagine, oppure un `ErroreGemini` con un codice stabile e un
messaggio che dice cosa fare.

I modelli disponibili sono quattro e si scelgono: cambiano prezzo e qualità del
testo dentro l'immagine. Il predefinito è Gemini 3 Pro Image («Nano Banana
Pro»), che Google indica per i compiti visivi più complessi — una prima pagina
è esattamente questo, decine di righe che devono uscire leggibili e scritte
giuste — ma costa quattro volte il più economico.

**Nessun modello per immagini ha un piano gratuito**: il listino di Google dice
«Free Tier: not available» per tutti. Scegliere il modello serve a spendere
meno, non a non spendere.

La chiave API non compare mai in un messaggio d'errore, in un log o in una
risposta verso il browser.
"""

from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass

import requests

from . import config

API = "https://generativelanguage.googleapis.com/v1beta"

PROPORZIONI = "9:16"
TEMPO_MASSIMO = float(os.getenv("GEMINI_TIMEOUT", "300"))


@dataclass(frozen=True)
class Modello:
    """Un modello per immagini, con quello che serve per sceglierlo.

    I costi sono il listino in dollari per immagine
    (ai.google.dev/gemini-api/docs/pricing): servono a mostrare una stima prima
    di generare, la cifra vera la decide Google.
    """

    id: str
    nome: str
    dimensioni: tuple[str, ...]
    costi: dict[str, float]
    nota: str
    # Nano Banana non accetta la taglia: produce sempre immagini da 1024 px.
    sceglie_taglia: bool = True


MODELLI = (
    Modello(
        "gemini-3-pro-image", "Nano Banana Pro", ("1K", "2K", "4K"),
        {"1K": 0.134, "2K": 0.134, "4K": 0.24},
        "Il più preciso con il testo: per una prima pagina fitta di parole è la scelta migliore.",
    ),
    Modello(
        "gemini-3.1-flash-image", "Nano Banana 2", ("0.5K", "1K", "2K", "4K"),
        {"0.5K": 0.045, "1K": 0.067, "2K": 0.101, "4K": 0.151},
        "Via di mezzo: in 1K costa la metà del Pro.",
    ),
    Modello(
        "gemini-2.5-flash-image", "Nano Banana", ("1K",), {"1K": 0.039},
        "Veloce ed economico, ma con tanto testo sbaglia più lettere. Solo 1K.",
        sceglie_taglia=False,
    ),
    Modello(
        "gemini-3.1-flash-lite-image", "Nano Banana 2 Lite", ("1K",), {"1K": 0.0336},
        "Il più economico: un quarto del Pro, solo in 1K.",
    ),
)

MODELLO_PREDEFINITO = "gemini-3-pro-image"
DIMENSIONE_PREDEFINITA = "2K"  # per Nano Banana Pro costa come 1K, ma si legge meglio


def modello(identificativo: str | None = None) -> Modello:
    """La scheda di un modello. Uno non in elenco si accetta comunque: sarà nuovo."""
    identificativo = (identificativo or MODELLO_PREDEFINITO).strip()
    for scheda in MODELLI:
        if scheda.id == identificativo:
            return scheda
    return Modello(
        identificativo, identificativo, ("0.5K", "1K", "2K", "4K"), {},
        "Modello indicato a mano: prezzo e taglie non sono noti qui.",
    )


def costo(identificativo: str | None, dimensione: str) -> float | None:
    """Il costo stimato di un'immagine, o None se il modello non è in listino."""
    return modello(identificativo).costi.get(dimensione)

# Motivi di stop che significano "immagine rifiutata", non "guasto".
_RIFIUTI = {
    "SAFETY", "IMAGE_SAFETY", "PROHIBITED_CONTENT", "IMAGE_PROHIBITED_CONTENT",
    "BLOCKLIST", "SPII", "RECITATION", "IMAGE_RECITATION",
}


class ErroreGemini(RuntimeError):
    """Un problema con Gemini che l'utente può capire e, di solito, risolvere."""

    def __init__(self, messaggio: str, codice: str) -> None:
        super().__init__(messaggio)
        self.messaggio = messaggio
        self.codice = codice


@dataclass
class Immagine:
    dati: bytes
    mime: str
    modello: str
    proporzioni: str
    dimensione: str
    secondi: float
    commento: str = ""

    @property
    def estensione(self) -> str:
        return {"image/jpeg": "jpg", "image/webp": "webp"}.get(self.mime, "png")


def carica_chiave() -> str:
    """La chiave API: prima dall'ambiente, poi dal file escluso da git."""
    chiave = os.getenv("GEMINI_API_KEY", "").strip()
    if not chiave and config.GEMINI_KEY_FILE.exists():
        chiave = config.GEMINI_KEY_FILE.read_text(encoding="utf-8").strip()
    if not chiave:
        raise ErroreGemini(
            f"Manca la chiave di Gemini. Salvala nel file {config.GEMINI_KEY_FILE.name} "
            f"nella cartella del progetto, oppure nella variabile GEMINI_API_KEY.",
            "chiave_mancante",
        )
    return chiave


def chiave_presente() -> bool:
    try:
        carica_chiave()
    except ErroreGemini:
        return False
    return True


def _errore_http(risposta: requests.Response) -> ErroreGemini:
    """Traduce una risposta d'errore dell'API in un messaggio utile."""
    try:
        dettaglio = risposta.json().get("error", {})
    except ValueError:
        dettaglio = {}
    messaggio_api = str(dettaglio.get("message") or risposta.text[:300]).strip()
    stato = str(dettaglio.get("status") or "")
    ragioni = " ".join(
        str(voce.get("reason", "")) for voce in dettaglio.get("details", []) if isinstance(voce, dict)
    )

    if "API_KEY_INVALID" in ragioni or "API key not valid" in messaggio_api:
        return ErroreGemini(
            "Gemini rifiuta la chiave: non è valida o è stata revocata. Creane una nuova "
            "su aistudio.google.com e sostituiscila nel file della chiave.",
            "chiave_non_valida",
        )
    if risposta.status_code == 429 or stato == "RESOURCE_EXHAUSTED":
        # Il messaggio grezzo di Google elenca metriche e indirizzi su più righe:
        # a chi legge serve sapere quale dei due casi è, e cosa fare.
        if "free_tier" in messaggio_api and "limit: 0" in messaggio_api:
            return ErroreGemini(
                "La chiave è sul piano gratuito, che non include la generazione di "
                "immagini. Attiva la fatturazione sul progetto della chiave in Google AI "
                "Studio, poi riprova: la stessa chiave funzionerà.",
                "quota",
            )
        attesa = re.search(r"retry in ([0-9.]+)s", messaggio_api)
        return ErroreGemini(
            "Hai raggiunto il limite di richieste di Gemini per il tuo piano. "
            + (f"Riprova fra {round(float(attesa.group(1)))} secondi." if attesa else "Riprova fra poco."),
            "quota",
        )
    if risposta.status_code in (401, 403):
        return ErroreGemini(
            f"Gemini nega l'accesso con questa chiave. Messaggio di Google: {messaggio_api}",
            "permesso",
        )
    if risposta.status_code == 404:
        return ErroreGemini(
            f"Il modello non è disponibile per questa chiave. Messaggio di Google: {messaggio_api}",
            "modello_non_disponibile",
        )
    if risposta.status_code >= 500:
        return ErroreGemini(
            "Il servizio di Gemini ha avuto un problema temporaneo. Riprova fra poco.",
            "servizio",
        )
    return ErroreGemini(f"Richiesta rifiutata da Gemini: {messaggio_api}", "richiesta_non_valida")


def estrai_immagine(risposta: dict) -> tuple[bytes, str, str]:
    """Dati, tipo MIME e commento testuale dalla risposta dell'API.

    Separata dalla chiamata di rete così si può verificare senza spendere.
    Le parti marcate `thought` sono bozze intermedie del modello: non vanno
    restituite, conta solo l'immagine finale.
    """
    feedback = risposta.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise ErroreGemini(
            f"Gemini ha bloccato il prompt ({feedback['blockReason']}). Può capitare con "
            "nomi o parole che il filtro fraintende: prova a rigenerare la pagina con "
            "un'altra versione del testo.",
            "bloccata",
        )

    candidati = risposta.get("candidates") or []
    if not candidati:
        raise ErroreGemini("Gemini non ha restituito nessun risultato.", "nessuna_immagine")

    candidato = candidati[0]
    motivo = candidato.get("finishReason", "")
    parti = (candidato.get("content") or {}).get("parts") or []

    immagine = None
    commento = []
    for parte in parti:
        if parte.get("thought"):
            continue
        dati = parte.get("inlineData")
        if dati and str(dati.get("mimeType", "")).startswith("image/"):
            immagine = dati
        elif parte.get("text"):
            commento.append(parte["text"].strip())

    if immagine is None:
        spiegazione = candidato.get("finishMessage") or " ".join(commento) or motivo
        if motivo in _RIFIUTI:
            raise ErroreGemini(
                f"Gemini ha rifiutato di generare l'immagine ({motivo}). {spiegazione}".strip(),
                "bloccata",
            )
        raise ErroreGemini(
            f"Gemini ha risposto senza un'immagine ({motivo or 'motivo non indicato'}). "
            f"{spiegazione}".strip(),
            "nessuna_immagine",
        )

    try:
        contenuto = base64.b64decode(immagine["data"])
    except (KeyError, ValueError) as errore:
        raise ErroreGemini("L'immagine ricevuta da Gemini è illeggibile.", "nessuna_immagine") from errore
    return contenuto, immagine.get("mimeType", "image/png"), " ".join(commento)


def genera(
    prompt: str,
    dimensione: str = DIMENSIONE_PREDEFINITA,
    modello_scelto: str | None = None,
) -> Immagine:
    """Genera l'immagine in 9:16 con il modello scelto. Solleva ErroreGemini."""
    scheda = modello(modello_scelto)
    if dimensione not in scheda.dimensioni:
        raise ErroreGemini(
            f"{scheda.nome} non fa immagini in «{dimensione}»: "
            f"scegli fra {', '.join(scheda.dimensioni)}.",
            "richiesta_non_valida",
        )
    if not prompt.strip():
        raise ErroreGemini("Il prompt è vuoto.", "richiesta_non_valida")

    chiave = carica_chiave()
    inizio = time.monotonic()

    # Prima si chiede la sola immagine: il testo di accompagnamento si pagherebbe
    # senza servire. Se un modello non accettasse la richiesta di sola immagine,
    # risponderebbe 400 senza addebito, e si riprova chiedendo anche il testo.
    for modalita in (["IMAGE"], ["TEXT", "IMAGE"]):
        immagine = {"aspectRatio": PROPORZIONI}
        if scheda.sceglie_taglia:
            immagine["imageSize"] = dimensione
        corpo = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": modalita, "imageConfig": immagine},
        }
        try:
            risposta = requests.post(
                f"{API}/models/{scheda.id}:generateContent",
                headers={"x-goog-api-key": chiave, "Content-Type": "application/json"},
                json=corpo,
                timeout=TEMPO_MASSIMO,
            )
        except requests.Timeout as errore:
            raise ErroreGemini(
                f"Gemini non ha risposto entro {int(TEMPO_MASSIMO)} secondi. Le immagini in "
                "alta risoluzione possono richiedere più tempo: riprova, magari in 2K.",
                "tempo_scaduto",
            ) from errore
        except requests.RequestException as errore:
            raise ErroreGemini(
                "Gemini non è raggiungibile. Controlla la connessione e riprova.", "rete"
            ) from errore

        if risposta.status_code == 400 and "modalit" in risposta.text.lower() and len(modalita) == 1:
            continue
        break

    if not risposta.ok:
        raise _errore_http(risposta)

    try:
        dati, mime, commento = estrai_immagine(risposta.json())
    except ValueError as errore:
        raise ErroreGemini("Gemini ha restituito una risposta illeggibile.", "servizio") from errore

    return Immagine(
        dati=dati,
        mime=mime,
        modello=scheda.id,
        proporzioni=PROPORZIONI,
        dimensione=dimensione,
        secondi=round(time.monotonic() - inizio, 1),
        commento=commento,
    )
