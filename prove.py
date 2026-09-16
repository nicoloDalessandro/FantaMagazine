"""Esegue tutte le prove del progetto, una per file.

    python prove.py            # tutte
    python prove.py gemini web # solo i file che contengono «gemini» o «web»

Ogni `test_*.py` resta eseguibile da solo, come prima: questo script li lancia
uno per uno in un processo separato - cosi' nessuna prova puo' lasciare in
eredita' alle altre un modulo modificato - e alla fine dice quante sono passate.
Esce con 1 se una qualunque fallisce: e' il comando che usa anche la CI.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent

# Le prove parlano italiano, con accenti e virgolette basse. Senza questo, su una
# console Windows con code page legacy - come quella della CI - il riepilogo
# uscirebbe mutilato o si fermerebbe su un errore di codifica.
for _flusso in (sys.stdout, sys.stderr):
    try:
        _flusso.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _file_di_prova(filtri: list[str]) -> list[Path]:
    trovati = sorted(RADICE.glob("test_*.py"))
    if not filtri:
        return trovati
    return [f for f in trovati if any(filtro.lower() in f.name.lower() for filtro in filtri)]


def main() -> int:
    prove = _file_di_prova(sys.argv[1:])
    if not prove:
        print("Nessun file di prova corrisponde.", file=sys.stderr)
        return 1

    # Gli accenti e le virgolette basse delle prove si leggono anche su una
    # console Windows con code page legacy, come quella della CI.
    ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    falliti: list[str] = []
    for prova in prove:
        print(f"\n=== {prova.name} " + "=" * max(0, 60 - len(prova.name)), flush=True)
        esito = subprocess.run(
            [sys.executable, str(prova)],
            cwd=RADICE,
            env=ambiente,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print((esito.stdout or "").rstrip(), flush=True)
        if esito.stderr:
            print(esito.stderr.rstrip(), file=sys.stderr, flush=True)
        if esito.returncode != 0:
            falliti.append(prova.name)

    print("\n" + "=" * 70)
    if falliti:
        print(f"FALLITE {len(falliti)} su {len(prove)}: {', '.join(falliti)}")
        return 1
    print(f"Tutti i {len(prove)} file di prova sono passati.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
