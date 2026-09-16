"""Ispeziona lo ZIP della release: c'e' tutto, e non c'e' niente di personale.

    python distribuzione/controlla_zip.py FantaMagazine-Windows-v1.0.0.zip

Due domande, entrambe a cui una persona non riuscirebbe a rispondere guardando
un elenco di duemila file:

1. l'app funziona? Servono l'eseguibile e le pagine della redazione: senza il
   template, la prima pagina aperta nel browser sarebbe un errore 500;
2. c'e' finito dentro qualcosa di mio? Credenziali, token, la chiave di Gemini,
   le scelte personali, la cache, le prime pagine generate. La ricetta di
   PyInstaller non le include, ma questo controllo non si fida della ricetta:
   guarda il risultato.

Esce con 1 al primo problema, e stampa che cosa e' mancato o che cosa e' di
troppo. E' il cancello prima della pubblicazione.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

# Senza questi la redazione non si apre.
NECESSARI = (
    "FantaMagazine.exe",
    "_internal/web/templates/index.html",
    "_internal/web/static/app.css",
    "_internal/web/static/app.js",
    "LEGGIMI.txt",
    "README.md",
    "LICENSE",
)

# Nomi che non devono comparire da nessuna parte nello ZIP. Si confrontano in
# minuscolo sul percorso intero, cosi' vale anche per un file dentro una
# sottocartella.
VIETATI = (
    "credentials",
    ".gemini_key",
    ".env",
    ".fanta_token",
    ".fanta_leghe",
    ".fanta_utente",
    ".fanta_impostazioni",
    ".cache/",
    "prime_pagine/",
    ".idea/",
    ".claude/",
    ".git/",
    "id_rsa",
    ".pem",
    ".pfx",
    ".netrc",
)

# Eccezioni ai nomi vietati, una per una e con la ragione accanto. L'elenco
# esiste perche' un ".pem" non e' sempre una chiave privata.
AMMESSI = {
    # I certificati pubblici delle autorita', che `requests` usa per verificare
    # HTTPS: senza, nessuna chiamata a Leghe Fantacalcio o a Gemini riuscirebbe.
    "_internal/certifi/cacert.pem",
}


def _senza_radice(voci: list[str]) -> list[str]:
    """Toglie la cartella di primo livello, se e' una sola.

    Lo ZIP della release contiene una cartella `FantaMagazine/` che raccoglie
    tutto, cosi' chi lo trascina fuori non si ritrova duemila file sparsi sul
    Desktop. I controlli qui sotto parlano invece di percorsi come li vede
    l'app, e non devono cambiare se un giorno quella cartella sparisse.
    """
    radici = {voce.split("/", 1)[0] for voce in voci}
    if len(radici) != 1:
        return voci
    radice = radici.pop()
    if not all(voce.startswith(f"{radice}/") for voce in voci):
        return voci
    return [voce[len(radice) + 1 :] for voce in voci]


def controlla(percorso: Path) -> list[str]:
    with zipfile.ZipFile(percorso) as archivio:
        nomi = archivio.namelist()
    # Qualche strumento Windows scrive i separatori alla rovescia: qui dentro
    # contano i percorsi, non chi ha creato l'archivio.
    voci = [nome.replace("\\", "/") for nome in nomi]
    voci = _senza_radice([voce for voce in voci if not voce.endswith("/")])

    problemi = [f"manca {atteso}" for atteso in NECESSARI if atteso not in voci]
    for voce in voci:
        if voce in AMMESSI:
            continue
        minuscolo = voce.lower()
        for vietato in VIETATI:
            if vietato in minuscolo:
                # Messaggi in puro ASCII: questo script parla a un log della CI,
                # la cui code page non e' detto sappia scrivere gli accenti.
                problemi.append(f"file personale o segreto: {voce} (contiene '{vietato}')")
    if not voci:
        problemi.append("lo ZIP e' vuoto")
    return problemi


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python distribuzione/controlla_zip.py <archivio.zip>", file=sys.stderr)
        return 1

    percorso = Path(sys.argv[1])
    if not percorso.is_file():
        print(f"Archivio inesistente: {percorso}", file=sys.stderr)
        return 1

    problemi = controlla(percorso)
    if problemi:
        print(f"{percorso.name}: {len(problemi)} problemi", file=sys.stderr)
        for problema in problemi:
            print(f"  - {problema}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(percorso) as archivio:
        quanti = len(archivio.namelist())
    peso = percorso.stat().st_size / 1_000_000
    print(f"{percorso.name}: {quanti} voci, {peso:.1f} MB.")
    print("Ci sono tutti i file necessari, e nessun dato personale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
