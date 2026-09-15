"""Estrae i token di tutte le tue leghe dal Chrome in cui hai già fatto il login.

Ogni lega ha il proprio JWT, con scadenza. Il browser li tiene tutti insieme,
quindi una sola esecuzione li rinnova tutti. Nessuna password viene mai letta,
richiesta o salvata.

Prerequisiti:
  - browser-harness installato   (uv tool install --python 3.12 browser-harness)
  - Chrome aperto, con il debug remoto autorizzato e la sessione attiva

Uso:
    python refresh_token.py

Lo stesso rinnovo è disponibile dall'interfaccia web (python app.py).
"""

from __future__ import annotations

import sys

from fantatana import auth, browser, config


def main() -> int:
    print("Lettura delle leghe dal browser...", file=sys.stderr)
    try:
        leghe = browser.leggi_leghe()
    except browser.ErroreBrowser as errore:
        print(errore, file=sys.stderr)
        return 1

    auth.salva_leghe(leghe)

    # I token non vengono mai stampati: solo quante leghe e dove sono finite.
    print(f"\n{len(leghe)} leghe salvate in {config.LEGHE_FILE}:", file=sys.stderr)
    for voce in sorted(leghe, key=lambda v: v["alias"]):
        print(f"  {voce['alias']:<28} {voce['nome']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
