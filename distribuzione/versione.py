"""Controlla che il tag di git e la versione dell'app dicano la stessa cosa.

    python distribuzione/versione.py v1.0.0

Il tag decide qual e' la release; `fantamagazine.__version__` decide che numero
l'app dichiara di se' stessa. Se i due divergono, chi scarica lo ZIP v1.1.0 si
trova un'app che si chiama 1.0.0 e non c'e' modo di accorgersene dopo. Meglio
fermare la pubblicazione qui.

Senza argomenti stampa la versione, che e' quello che serve allo ZIP.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fantamagazine import __version__  # noqa: E402 - dopo l'aggiunta al path

SEMANTICA = re.compile(r"^\d+\.\d+\.\d+$")


def main() -> int:
    if not SEMANTICA.match(__version__):
        print(
            f"__version__ = {__version__!r} non e' una versione semantica "
            "(MAJOR.MINOR.PATCH): correggi fantamagazine/__init__.py.",
            file=sys.stderr,
        )
        return 1

    if len(sys.argv) < 2:
        print(__version__)
        return 0

    tag = sys.argv[1].strip()
    atteso = f"v{__version__}"
    if tag != atteso:
        print(
            f"Il tag {tag!r} non corrisponde alla versione dell'app {__version__!r}.\n"
            f"Aggiorna __version__ in fantamagazine/__init__.py, committa, "
            f"poi rifai il tag - oppure usa il tag {atteso!r}.",
            file=sys.stderr,
        )
        return 1

    print(f"Tag {tag} e versione {__version__}: coincidono.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
