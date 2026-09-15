"""Lettura dei token dal Chrome in cui l'utente ha già fatto il login.

Ogni lega ha il proprio JWT, con scadenza. Il browser li tiene tutti insieme,
quindi una sola lettura li rinnova tutti. Nessuna password viene mai letta,
richiesta o salvata: si copiano valori già presenti nel browser dopo un accesso
fatto dall'utente.

Usato sia da `refresh_token.py` sia dall'interfaccia web.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from . import config

MARCATORE = "___LEGHE___"

ESTRATTORE = f"""
import json, time
new_tab({config.SITE_BASE!r})
wait_for_load()
time.sleep(6)
trovate = js('''
(() => {{
  const grezzo = localStorage.getItem('LEAGUES2024_LOCAL');
  if (!grezzo) return [];
  const dati = JSON.parse(grezzo);
  const viste = {{}};
  const cerca = (nodo) => {{
    if (!nodo || typeof nodo !== 'object') return;
    if (nodo.alias && nodo.token && !viste[nodo.alias]) {{
      viste[nodo.alias] = {{alias: nodo.alias, nome: nodo.name || nodo.alias,
                           id: nodo.id || null, token: nodo.token}};
    }}
    Object.keys(nodo).forEach((k) => cerca(nodo[k]));
  }};
  cerca(dati);
  return Object.keys(viste).map((k) => viste[k]);
}})()
''')
print({MARCATORE!r} + json.dumps(trovate or []))
"""


class ErroreBrowser(RuntimeError):
    """Qualcosa impedisce di leggere i token: il messaggio spiega cosa fare."""


def trova_eseguibile() -> str | None:
    return shutil.which("browser-harness") or shutil.which("browser-use")


def interpreta_uscita(stdout: str) -> list[dict]:
    """Estrae l'elenco delle leghe dall'output dello script.

    Separata dal lancio del processo così si può verificare senza Chrome.
    """
    for riga in stdout.splitlines():
        if riga.startswith(MARCATORE):
            try:
                voci = json.loads(riga[len(MARCATORE):])
            except json.JSONDecodeError:
                return []
            return [v for v in voci if isinstance(v, dict) and v.get("alias") and v.get("token")]
    return []


def leggi_leghe(timeout: float = 240, eseguibile: str | None = None) -> list[dict]:
    """Legge alias, nome, id e token di ogni lega. Solleva ErroreBrowser."""
    eseguibile = eseguibile or trova_eseguibile()
    if not eseguibile:
        raise ErroreBrowser(
            "browser-harness non è installato o non è nel PATH. "
            "Installalo con: uv tool install --python 3.12 browser-harness, "
            "poi riapri il terminale."
        )

    try:
        esito = subprocess.run(
            [eseguibile],
            input=ESTRATTORE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as errore:
        raise ErroreBrowser(
            f"Chrome non ha risposto entro {int(timeout)} secondi. Se è comparso il "
            "popup «Allow remote debugging?», clicca Allow e riprova."
        ) from errore
    except OSError as errore:
        raise ErroreBrowser(f"Impossibile avviare browser-harness: {errore}") from errore

    leghe = interpreta_uscita(esito.stdout)
    if not leghe:
        dettaglio = (esito.stderr or "").strip()[:300]
        raise ErroreBrowser(
            "Nessuna lega trovata nel browser. Verifica che Chrome sia aperto, che tu "
            "abbia fatto l'accesso a leghe.fantacalcio.it e che il debug remoto sia "
            "autorizzato su chrome://inspect/#remote-debugging."
            + (f" Dettaglio: {dettaglio}" if dettaglio else "")
        )
    return leghe
