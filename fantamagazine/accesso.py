"""Accesso a Leghe Fantacalcio con username e password.

Una sola chiamata restituisce tutto: l'utente e, per ciascuna delle sue leghe,
il token con cui interrogare l'API. La password serve soltanto a quella
chiamata: non viene salvata, stampata, registrata né restituita. Su disco
restano i token, che durano un anno.

Il protocollo è quello del sito, ricavato dal suo codice pubblico e verificato
sulla forma delle risposte reali:

    POST {API}/onboarding/v1/login               {"username", "password"}
    GET  {API}/onboarding/v2/profile/{id_utente}  Authorization: Bearer <jwt utente>

Le due risposte hanno la stessa forma: `utente`, `leghe` (ognuna con il suo
`jwt`), e `jwt` e `token_auth` dell'utente. Il profilo permette di ritrovare
le leghe nuove senza chiedere di nuovo la password.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from . import config

# Codici d'errore del servizio di autenticazione, con il testo del sito.
_CODICI = {
    "ATH018": ("credenziali", "Username o password non validi."),
    "ATH006": ("credenziali", "Inserisci username e password."),
    "ATH003": ("sessione_scaduta", "L'accesso non è più valido: entra di nuovo."),
    "ATH004": ("sessione_scaduta", "L'accesso è scaduto: entra di nuovo."),
    "ATH008": ("sessione_scaduta", "L'accesso non è più valido: entra di nuovo."),
    "ATH010": ("sessione_scaduta", "Profilo utente non trovato: entra di nuovo."),
    "ATH011": ("sessione_scaduta", "Profilo utente non valido: entra di nuovo."),
    "ATH012": ("sessione_scaduta", "L'accesso non è più valido: entra di nuovo."),
    "ATH000": ("applicazione", "Leghe Fantacalcio non riconosce più questa applicazione."),
    "ATH007": ("applicazione", "Leghe Fantacalcio non riconosce più questa applicazione."),
    "ATH017": ("applicazione", "Leghe Fantacalcio non riconosce più questa applicazione."),
    "AUTH01": ("servizio", "Il servizio di accesso di Leghe Fantacalcio non risponde. Riprova fra poco."),
    "AUTH04": ("servizio", "Il servizio di accesso di Leghe Fantacalcio non risponde. Riprova fra poco."),
}


class ErroreAccesso(RuntimeError):
    """Un accesso non riuscito, con un codice stabile e un messaggio da mostrare.

    Il messaggio non contiene mai la password né il corpo della richiesta.
    """

    def __init__(self, messaggio: str, codice: str) -> None:
        super().__init__(messaggio)
        self.messaggio = messaggio
        self.codice = codice


@dataclass
class Utente:
    id: int
    username: str
    # I token non compaiono nella rappresentazione: un oggetto finito in un log
    # o in una traccia d'errore non deve portarseli dietro.
    jwt: str = field(repr=False)
    token_auth: str = field(default="", repr=False)


@dataclass
class LegaUtente:
    id: int | None
    alias: str
    nome: str
    token: str = field(repr=False)
    visibile: bool = True
    ordine: int = 0


def _intero(valore: Any) -> int | None:
    try:
        return int(valore)
    except (TypeError, ValueError):
        return None


def _intestazioni() -> dict[str, str]:
    return {
        "accept": "application/json",
        "Content-Type": "application/json",
        "app_key": config.APP_KEY,
        "User-Agent": config.USER_AGENT,
    }


def interpreta(corpo: Any) -> tuple[Utente, list[LegaUtente]]:
    """Utente e leghe da una risposta di accesso o di profilo.

    Separata dalla rete così si può verificare senza account. I dati
    dell'utente stanno in parte in cima e in parte sotto `utente`: il sito li
    fonde, e così si fa qui. Una lega senza token è inutilizzabile e si scarta.
    """
    if not isinstance(corpo, dict):
        raise ErroreAccesso("Leghe Fantacalcio ha risposto in un formato inatteso.", "risposta")
    dati = corpo["data"] if isinstance(corpo.get("data"), dict) else corpo
    fusi = {**dati, **(dati.get("utente") if isinstance(dati.get("utente"), dict) else {})}

    identificativo = _intero(fusi.get("id"))
    jwt = str(fusi.get("jwt") or "").strip()
    if identificativo is None or not jwt:
        raise ErroreAccesso("Leghe Fantacalcio ha risposto senza i dati dell'utente.", "risposta")
    utente = Utente(
        id=identificativo,
        username=str(fusi.get("username") or "").strip(),
        jwt=jwt,
        token_auth=str(fusi.get("token_auth") or "").strip(),
    )

    voci = dati.get("leghe") or []
    if isinstance(voci, dict):
        voci = list(voci.values())
    leghe = []
    for voce in voci if isinstance(voci, list) else []:
        if not isinstance(voce, dict):
            continue
        alias = str(voce.get("alias") or "").strip()
        token = str(voce.get("jwt") or "").strip()
        if not alias or not token:
            continue
        leghe.append(
            LegaUtente(
                id=_intero(voce.get("id")),
                alias=alias,
                nome=str(voce.get("nome") or alias).strip(),
                token=token,
                visibile=voce.get("visibile", True) is not False,
                ordine=_intero(voce.get("ordine")) or 0,
            )
        )
    leghe.sort(key=lambda lega: (lega.ordine, lega.nome.lower()))
    return utente, leghe


def _codice(corpo: Any) -> str:
    """Il codice d'errore, nelle varie forme in cui il servizio lo restituisce."""
    candidati: list[Any] = []
    if isinstance(corpo, dict):
        candidati += [corpo.get("Code"), corpo.get("code")]
        for chiave in ("error", "errors", "error_msgs"):
            valore = corpo.get(chiave)
            voci = valore if isinstance(valore, list) else [valore]
            candidati += [v.get("Code") or v.get("code") for v in voci if isinstance(v, dict)]
    return next((str(c).upper() for c in candidati if c), "")


def _errore(stato: int, corpo: Any, contesto: str) -> ErroreAccesso:
    codice = _codice(corpo)
    if codice in _CODICI:
        tipo, messaggio = _CODICI[codice]
        return ErroreAccesso(messaggio, tipo)
    if stato in (401, 403):
        if contesto == "accesso":
            return ErroreAccesso("Username o password non validi.", "credenziali")
        return ErroreAccesso("L'accesso non è più valido: entra di nuovo.", "sessione_scaduta")
    if stato >= 500:
        return ErroreAccesso(
            "Leghe Fantacalcio ha un problema temporaneo. Riprova fra poco.", "servizio"
        )
    return ErroreAccesso(
        f"Leghe Fantacalcio ha rifiutato la richiesta ({codice or stato}).", "risposta"
    )


def _chiama(metodo: str, url: str, contesto: str, **opzioni: Any) -> Any:
    try:
        # Niente reindirizzamenti: la richiesta di accesso porta la password, e
        # non deve essere rispedita a un indirizzo diverso da quello scelto qui.
        risposta = requests.request(
            metodo, url, timeout=config.TIMEOUT, allow_redirects=False, **opzioni
        )
    except requests.Timeout:
        # `from None`: l'eccezione originale porta con sé la richiesta, e con
        # essa il corpo. Non deve arrivare in nessuna traccia d'errore.
        raise ErroreAccesso("Leghe Fantacalcio non ha risposto in tempo. Riprova fra poco.", "rete") from None
    except requests.RequestException:
        raise ErroreAccesso(
            "Leghe Fantacalcio non è raggiungibile. Controlla la connessione e riprova.", "rete"
        ) from None

    try:
        corpo = risposta.json()
    except ValueError:
        corpo = None
    if not 200 <= risposta.status_code < 300:
        raise _errore(risposta.status_code, corpo, contesto)
    if isinstance(corpo, dict) and corpo.get("success") is False:
        raise _errore(401 if contesto == "accesso" else 400, corpo, contesto)
    return corpo


def accedi(username: str, password: str) -> tuple[Utente, list[LegaUtente]]:
    """Entra con username e password. Solleva ErroreAccesso."""
    username = (username or "").strip()
    if not username or not password:
        raise ErroreAccesso("Inserisci username e password.", "credenziali")
    corpo = _chiama(
        "POST",
        config.URL_ACCESSO,
        "accesso",
        json={"username": username, "password": password},
        headers=_intestazioni(),
    )
    return interpreta(corpo)


def profilo(utente: Utente) -> tuple[Utente, list[LegaUtente]]:
    """Rilegge utente e leghe con il token dell'utente, senza password."""
    corpo = _chiama(
        "GET",
        config.URL_PROFILO.format(id_utente=utente.id),
        "profilo",
        headers={
            **_intestazioni(),
            "Authorization": f"Bearer {utente.jwt}",
            "Cache-Control": "no-cache",
        },
    )
    nuovo, leghe = interpreta(corpo)
    # Il profilo può non ripetere il nome utente: si tiene quello che c'era.
    nuovo.username = nuovo.username or utente.username
    nuovo.token_auth = nuovo.token_auth or utente.token_auth
    return nuovo, leghe
