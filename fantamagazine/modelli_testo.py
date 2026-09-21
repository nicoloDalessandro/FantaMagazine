"""I modelli che possono scrivere la prima pagina al posto del redattore classico.

Tre fornitori - ChatGPT, Claude e Gemini - ciascuno con la chiave di chi usa
l'app: la chiamata parte da questo computer, con la sua chiave, e la spesa è
sua. Qui dentro c'è solo il trasporto: prendere un messaggio, chiedere al
modello una risposta in JSON conforme a uno schema e restituirne il testo, o un
errore che si capisca. Cosa mandare e come leggere la risposta lo decide
`scrittura_ai`.

Le tre API sono diverse, e ognuna si chiama come la documenta il suo fornitore:

- OpenAI con la Responses API e `text.format` (JSON schema rigoroso);
- Anthropic con il suo SDK ufficiale e `output_config.format`;
- Google con `generateContent` e `responseSchema`, via REST come le immagini.

Le chiavi non compaiono mai in un messaggio d'errore: i messaggi dei fornitori
possono ripeterne un pezzo (OpenAI lo fa, mascherato a metà), quindi quel che
arriva da fuori viene ripulito prima di essere mostrato.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from . import config, gemini

# Una pagina è lunga qualche migliaio di token, più il ragionamento dei modelli
# che ragionano: c'è margine, perché troncare a metà un JSON lo butterebbe via.
MASSIMO_TOKEN = 16000
TEMPO_MASSIMO = float(os.getenv("FANTA_TIMEOUT_TESTO", "180"))

URL_OPENAI = "https://api.openai.com/v1/responses"


@dataclass(frozen=True)
class Modello:
    id: str
    nome: str
    nota: str
    gratuito: bool = False  # esiste un piano gratuito che lo include


@dataclass(frozen=True)
class Fornitore:
    id: str  # quello da usare in riga di comando: chatgpt, claude, gemini
    nome: str
    azienda: str
    variabile: str  # la variabile d'ambiente con la chiave
    nome_file: str  # l'attributo di config con il file della chiave
    url_chiavi: str
    modelli: tuple[Modello, ...]
    predefinito: str

    @property
    def file_chiave(self) -> Path:
        # Letto ogni volta da config: le prove lo spostano in una cartella temporanea.
        return getattr(config, self.nome_file)

    def modello(self, identificativo: str | None) -> Modello:
        for scheda in self.modelli:
            if scheda.id == identificativo:
                return scheda
        raise ErroreTesto(
            f"{self.nome} non ha un modello «{identificativo}». "
            f"Scegli fra: {', '.join(m.id for m in self.modelli)}.",
            "richiesta_non_valida",
        )


# Prezzi dai listini ufficiali, settembre 2026, per milione di token: indicativi.
FORNITORI: tuple[Fornitore, ...] = (
    Fornitore(
        id="chatgpt",
        nome="ChatGPT",
        azienda="OpenAI",
        variabile="OPENAI_API_KEY",
        nome_file="OPENAI_KEY_FILE",
        url_chiavi="https://platform.openai.com/api-keys",
        modelli=(
            Modello("gpt-5.6-luna", "GPT-5.6 Luna",
                    "Il più economico: 0,20 $ in ingresso e 1,20 $ in uscita per milione di token."),
            Modello("gpt-5.6-terra", "GPT-5.6 Terra",
                    "Via di mezzo: 2 $ e 12 $ per milione di token."),
            Modello("gpt-6-astra", "GPT-6 Astra",
                    "Il più capace e il più caro: 10 $ e 50 $ per milione di token."),
        ),
        predefinito="gpt-5.6-terra",
    ),
    Fornitore(
        id="claude",
        nome="Claude",
        azienda="Anthropic",
        variabile="ANTHROPIC_API_KEY",
        nome_file="ANTHROPIC_KEY_FILE",
        url_chiavi="https://console.anthropic.com/settings/keys",
        modelli=(
            Modello("claude-haiku-4-5", "Claude Haiku 4.5",
                    "Il più rapido ed economico: 1 $ in ingresso e 5 $ in uscita per milione di token."),
            Modello("claude-sonnet-5", "Claude Sonnet 5",
                    "Via di mezzo: 2 $ e 10 $ per milione di token."),
            Modello("claude-opus-5", "Claude Opus 5",
                    "Il più capace: 5 $ e 25 $ per milione di token."),
        ),
        predefinito="claude-opus-5",
    ),
    Fornitore(
        id="gemini",
        nome="Gemini",
        azienda="Google",
        variabile="GEMINI_API_KEY",
        nome_file="GEMINI_KEY_FILE",
        url_chiavi="https://aistudio.google.com/apikey",
        modelli=(
            Modello("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite",
                    "Il più economico, e incluso nel piano gratuito.", gratuito=True),
            Modello("gemini-3.8-flash", "Gemini 3.8 Flash",
                    "Rapido e capace, incluso nel piano gratuito.", gratuito=True),
            Modello("gemini-3.1-pro-preview", "Gemini 3.1 Pro (anteprima)",
                    "Il più capace, senza piano gratuito: 2 $ e 12 $ per milione di token."),
        ),
        predefinito="gemini-3.8-flash",
    ),
)
FORNITORE_PREDEFINITO = "claude"


class ErroreTesto(RuntimeError):
    """Un problema con il modello che scrive, che l'utente può capire e risolvere."""

    def __init__(self, messaggio: str, codice: str) -> None:
        super().__init__(messaggio)
        self.messaggio = messaggio
        self.codice = codice


def fornitore(identificativo: str | None) -> Fornitore:
    for voce in FORNITORI:
        if voce.id == identificativo:
            return voce
    raise ErroreTesto(
        f"Fornitore sconosciuto «{identificativo}»: scegli fra "
        f"{', '.join(v.id for v in FORNITORI)}.",
        "richiesta_non_valida",
    )


# --- Le chiavi ------------------------------------------------------------------------
def chiave_da_ambiente(voce: Fornitore) -> bool:
    return bool(os.getenv(voce.variabile, "").strip())


def carica_chiave(voce: Fornitore) -> str:
    """La chiave: prima dall'ambiente, poi dal file escluso da git."""
    if voce.id == "gemini":
        # La stessa delle immagini: una chiave sola per fornitore.
        try:
            return gemini.carica_chiave()
        except gemini.ErroreGemini:
            pass
    else:
        chiave = os.getenv(voce.variabile, "").strip()
        if not chiave and voce.file_chiave.exists():
            chiave = voce.file_chiave.read_text(encoding="utf-8").strip()
        if chiave:
            return chiave
    raise ErroreTesto(
        f"Manca la chiave di {voce.nome}. Aggiungila nelle Impostazioni della redazione, "
        f"oppure nella variabile {voce.variabile}. Si crea su {voce.url_chiavi}",
        "chiave_mancante",
    )


def chiave_presente(voce: Fornitore) -> bool:
    try:
        carica_chiave(voce)
    except ErroreTesto:
        return False
    return True


_SEGRETI = re.compile(r"(sk-ant-[\w\-*.]{4,}|sk-[\w\-*.]{4,}|AIza[\w\-]{8,})")


def _pulisci(testo: object, chiave: str = "") -> str:
    """Un messaggio arrivato da fuori, senza chiavi, su una riga, non troppo lungo."""
    testo = str(testo or "")
    if chiave:
        testo = testo.replace(chiave, "[chiave]")
    testo = _SEGRETI.sub("[chiave]", testo)
    testo = re.sub(r"\s+", " ", testo).strip()
    return testo[:300]


def _schema_gemini(schema: dict) -> dict:
    """Lo stesso schema nel dialetto di responseSchema: tipi in maiuscolo, niente extra."""
    risultato: dict = {}
    for chiave, valore in schema.items():
        if chiave == "additionalProperties":
            continue
        if chiave == "type":
            risultato[chiave] = str(valore).upper()
        elif chiave == "properties":
            risultato[chiave] = {nome: _schema_gemini(sotto) for nome, sotto in valore.items()}
        elif chiave == "items":
            risultato[chiave] = _schema_gemini(valore)
        else:
            risultato[chiave] = valore
    return risultato


# --- La chiamata ---------------------------------------------------------------------
def scrivi(id_fornitore: str, id_modello: str, sistema: str, messaggio: str, schema: dict) -> str:
    """Il testo JSON che il modello restituisce. Solleva ErroreTesto."""
    voce = fornitore(id_fornitore)
    voce.modello(id_modello)  # un modello che non è nell'elenco non parte nemmeno
    chiave = carica_chiave(voce)
    chiamata = {"chatgpt": _openai, "claude": _anthropic, "gemini": _google}[voce.id]
    return chiamata(chiave, id_modello, sistema, messaggio, schema)


def _errore_http(nome: str, risposta: requests.Response, chiave: str) -> ErroreTesto:
    """Traduce un errore HTTP di OpenAI o di Google in un messaggio utile."""
    try:
        dettaglio = risposta.json().get("error", {})
    except ValueError:
        dettaglio = {}
    if not isinstance(dettaglio, dict):
        dettaglio = {}
    messaggio = _pulisci(dettaglio.get("message") or risposta.text[:300], chiave)
    codice_api = str(dettaglio.get("code") or dettaglio.get("status") or "")
    stato = risposta.status_code

    if stato == 401 or "API_KEY_INVALID" in str(dettaglio) or "API key not valid" in messaggio:
        # Qui il messaggio del fornitore non si mostra: è il caso in cui ripete la chiave.
        return ErroreTesto(
            f"{nome} rifiuta la chiave: non è valida o è stata revocata. Creane una nuova e "
            "sostituiscila nelle Impostazioni.",
            "chiave_non_valida",
        )
    if stato == 429 or codice_api == "RESOURCE_EXHAUSTED":
        if "insufficient_quota" in codice_api or "insufficient_quota" in messaggio:
            return ErroreTesto(
                f"Il credito dell'account {nome} è esaurito: ricaricalo dal sito del fornitore, "
                "poi riprova.",
                "quota",
            )
        return ErroreTesto(
            f"Hai raggiunto il limite di richieste di {nome} per il tuo piano. Riprova fra poco.",
            "quota",
        )
    if stato == 403:
        return ErroreTesto(f"{nome} nega l'accesso con questa chiave: {messaggio}", "permesso")
    if stato == 404:
        return ErroreTesto(
            f"Il modello non è disponibile per questa chiave: {messaggio}", "modello_non_disponibile"
        )
    if stato >= 500:
        return ErroreTesto(
            f"Il servizio di {nome} ha avuto un problema temporaneo. Riprova fra poco.", "servizio"
        )
    return ErroreTesto(f"Richiesta rifiutata da {nome}: {messaggio}", "richiesta_non_valida")


def _post(nome: str, url: str, intestazioni: dict, corpo: dict, chiave: str) -> dict:
    try:
        risposta = requests.post(url, headers=intestazioni, json=corpo, timeout=TEMPO_MASSIMO)
    except requests.Timeout:
        raise ErroreTesto(
            f"{nome} non ha risposto entro {round(TEMPO_MASSIMO)} secondi. Riprova, o scegli "
            "un modello più rapido.",
            "tempo_scaduto",
        ) from None
    except requests.RequestException:
        raise ErroreTesto(
            f"Impossibile raggiungere {nome}: controlla la connessione.", "rete"
        ) from None
    if risposta.status_code != 200:
        raise _errore_http(nome, risposta, chiave)
    try:
        return risposta.json()
    except ValueError:
        raise ErroreTesto(f"{nome} ha risposto con qualcosa che non è JSON.", "risposta_non_valida") from None


def _troncata(nome: str) -> ErroreTesto:
    return ErroreTesto(
        f"La risposta di {nome} si è interrotta prima della fine. Riprova: se si ripete, "
        "accorcia le indicazioni per il modello.",
        "risposta_non_valida",
    )


def _bloccata(nome: str, motivo: str = "") -> ErroreTesto:
    return ErroreTesto(
        f"{nome} ha rifiutato di scrivere questa pagina"
        + (f" ({motivo})" if motivo else "")
        + ". Prova con indicazioni diverse, o con la scrittura classica.",
        "bloccata",
    )


def _openai(chiave: str, modello: str, sistema: str, messaggio: str, schema: dict) -> str:
    dati = _post(
        "ChatGPT",
        URL_OPENAI,
        {"Authorization": f"Bearer {chiave}", "Content-Type": "application/json"},
        {
            "model": modello,
            "input": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": messaggio},
            ],
            # Scrivere una pagina non chiede di ragionare a fondo: basso costa
            # meno e risponde prima.
            "reasoning": {"effort": "low"},
            "max_output_tokens": MASSIMO_TOKEN,
            "text": {
                "format": {"type": "json_schema", "name": "prima_pagina", "strict": True, "schema": schema}
            },
        },
        chiave,
    )
    if dati.get("status") == "incomplete":
        motivo = str((dati.get("incomplete_details") or {}).get("reason") or "")
        if motivo == "content_filter":
            raise _bloccata("ChatGPT", "filtro dei contenuti")
        raise _troncata("ChatGPT")

    testi = []
    for voce in dati.get("output") or []:
        if not isinstance(voce, dict) or voce.get("type") != "message":
            continue
        for parte in voce.get("content") or []:
            if not isinstance(parte, dict):
                continue
            if parte.get("type") == "refusal":
                raise _bloccata("ChatGPT", _pulisci(parte.get("refusal"), chiave))
            if parte.get("type") == "output_text":
                testi.append(str(parte.get("text") or ""))
    if not "".join(testi).strip():
        raise ErroreTesto("ChatGPT ha risposto senza testo.", "risposta_non_valida")
    return "".join(testi)


def _anthropic(chiave: str, modello: str, sistema: str, messaggio: str, schema: dict) -> str:
    # Importato qui: chi non usa Claude non paga il tempo di caricamento dell'SDK.
    import anthropic

    client = anthropic.Anthropic(api_key=chiave, timeout=TEMPO_MASSIMO, max_retries=1)
    uscita: dict = {"format": {"type": "json_schema", "schema": schema}}
    if modello != "claude-haiku-4-5":
        # Opus 5 e Sonnet 5 scrivono bene anche a sforzo medio, che costa meno;
        # Haiku 4.5 non accetta il parametro.
        uscita["effort"] = "medium"
    parametri = {
        "model": modello,
        "max_tokens": MASSIMO_TOKEN,
        "system": sistema,
        "messages": [{"role": "user", "content": messaggio}],
        "output_config": uscita,
    }
    try:
        if modello == "claude-opus-5":
            # Se i controlli di sicurezza di Opus 5 declinano la richiesta, il
            # server la ripete su un altro modello invece di restituire un rifiuto.
            risposta = client.beta.messages.create(
                **parametri, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
            )
        else:
            risposta = client.messages.create(**parametri)
    except anthropic.AuthenticationError:
        raise ErroreTesto(
            "Claude rifiuta la chiave: non è valida o è stata revocata. Creane una nuova e "
            "sostituiscila nelle Impostazioni.",
            "chiave_non_valida",
        ) from None
    except anthropic.PermissionDeniedError as errore:
        raise ErroreTesto(
            f"Claude nega l'accesso con questa chiave: {_pulisci(errore.message, chiave)}", "permesso"
        ) from None
    except anthropic.NotFoundError as errore:
        raise ErroreTesto(
            f"Il modello non è disponibile per questa chiave: {_pulisci(errore.message, chiave)}",
            "modello_non_disponibile",
        ) from None
    except anthropic.RateLimitError:
        raise ErroreTesto(
            "Hai raggiunto il limite di richieste di Claude per il tuo piano. Riprova fra poco.",
            "quota",
        ) from None
    except anthropic.BadRequestError as errore:
        testo = _pulisci(errore.message, chiave)
        if "credit balance" in testo.lower():
            raise ErroreTesto(
                "Il credito dell'account Claude è esaurito: ricaricalo dalla console di "
                "Anthropic, poi riprova.",
                "quota",
            ) from None
        raise ErroreTesto(f"Richiesta rifiutata da Claude: {testo}", "richiesta_non_valida") from None
    except anthropic.APITimeoutError:
        # Prima di APIConnectionError, di cui è un caso particolare.
        raise ErroreTesto(
            f"Claude non ha risposto entro {round(TEMPO_MASSIMO)} secondi. Riprova, o scegli un "
            "modello più rapido.",
            "tempo_scaduto",
        ) from None
    except anthropic.APIConnectionError:
        raise ErroreTesto("Impossibile raggiungere Claude: controlla la connessione.", "rete") from None
    except anthropic.APIStatusError as errore:
        if errore.status_code >= 500:
            raise ErroreTesto(
                "Il servizio di Claude ha avuto un problema temporaneo. Riprova fra poco.", "servizio"
            ) from None
        raise ErroreTesto(
            f"Richiesta rifiutata da Claude: {_pulisci(errore.message, chiave)}", "richiesta_non_valida"
        ) from None

    # Un rifiuto arriva con esito HTTP 200: va controllato prima di leggere il testo.
    if risposta.stop_reason == "refusal":
        raise _bloccata("Claude")
    if risposta.stop_reason == "max_tokens":
        raise _troncata("Claude")
    testo = "".join(
        blocco.text for blocco in risposta.content if getattr(blocco, "type", "") == "text"
    )
    if not testo.strip():
        raise ErroreTesto("Claude ha risposto senza testo.", "risposta_non_valida")
    return testo


def _google(chiave: str, modello: str, sistema: str, messaggio: str, schema: dict) -> str:
    dati = _post(
        "Gemini",
        f"{gemini.API}/models/{modello}:generateContent",
        # Nell'intestazione e non nell'indirizzo, dove finirebbe nei log.
        {"x-goog-api-key": chiave, "Content-Type": "application/json"},
        {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [{"role": "user", "parts": [{"text": messaggio}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _schema_gemini(schema),
                "maxOutputTokens": MASSIMO_TOKEN,
            },
        },
        chiave,
    )
    bloccato = (dati.get("promptFeedback") or {}).get("blockReason")
    if bloccato:
        raise _bloccata("Gemini", str(bloccato))
    candidati = dati.get("candidates") or []
    if not candidati:
        raise ErroreTesto("Gemini ha risposto senza testo.", "risposta_non_valida")
    candidato = candidati[0] if isinstance(candidati[0], dict) else {}
    motivo = str(candidato.get("finishReason") or "")
    if motivo in gemini._RIFIUTI:
        raise _bloccata("Gemini", motivo)
    if motivo == "MAX_TOKENS":
        raise _troncata("Gemini")
    parti = (candidato.get("content") or {}).get("parts") or []
    # I pensieri dei modelli che ragionano non sono la risposta.
    testo = "".join(
        str(p.get("text") or "") for p in parti if isinstance(p, dict) and not p.get("thought")
    )
    if not testo.strip():
        raise ErroreTesto("Gemini ha risposto senza testo.", "risposta_non_valida")
    return testo
