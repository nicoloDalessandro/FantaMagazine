"""Le scelte dell'utente: quali leghe e competizioni usare, e il nome del giornale.

Stanno in `.fanta_impostazioni.json`, escluso da git: non sono segrete, ma sono
personali quanto i token. Per difetto tutto è attivo e la testata si ricava dal
nome della lega, così una lega appena trovata funziona senza configurarla.

Delle competizioni si ricordano quelle **escluse**, non quelle scelte: una
coppa creata a metà stagione compare da sola, invece di restare nascosta
finché qualcuno non se ne accorge.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

from . import config

MASSIMO_TESTATA = 60


@dataclass
class SceltaLega:
    attiva: bool = True
    testata: str = ""  # vuota: si usa quella ricavata dal nome della lega
    competizioni_escluse: list[str] = field(default_factory=list)

    def usa_competizione(self, identificativo: str | int) -> bool:
        return str(identificativo) not in self.competizioni_escluse


def pulisci_testata(testo: str) -> str:
    """Una riga sola, senza virgolette doppie, non più lunga di una testata.

    La testata finisce nel prompt fra virgolette doppie: una virgoletta nel
    nome chiuderebbe la stringa a metà. Si sostituisce con quella semplice.
    """
    testo = re.sub(r"[\x00-\x1f\x7f]+", " ", str(testo or ""))
    testo = re.sub(r"\s+", " ", testo.replace('"', "'")).strip()
    return testo[:MASSIMO_TESTATA].rstrip()


def testata_predefinita(nome_lega: str) -> str:
    return pulisci_testata(f"LA GAZZETTA DI {nome_lega.upper()}")


def carica() -> dict[str, SceltaLega]:
    """Le scelte salvate, per alias. Un file illeggibile vale come nessuna scelta."""
    if not config.IMPOSTAZIONI_FILE.exists():
        return {}
    try:
        grezzo = json.loads(config.IMPOSTAZIONI_FILE.read_text(encoding="utf-8"))
        voci = grezzo.get("leghe", {})
    except (OSError, ValueError, AttributeError):
        return {}

    scelte = {}
    for alias, voce in voci.items() if isinstance(voci, dict) else ():
        if not isinstance(voce, dict):
            continue
        escluse = voce.get("competizioni_escluse") or []
        scelte[str(alias)] = SceltaLega(
            attiva=voce.get("attiva", True) is not False,
            testata=pulisci_testata(voce.get("testata") or ""),
            competizioni_escluse=[str(c) for c in escluse] if isinstance(escluse, list) else [],
        )
    return scelte


def salva(scelte: dict[str, SceltaLega]) -> None:
    """Scrive le scelte in un file temporaneo e poi al loro posto."""
    contenuto = {"leghe": {alias: asdict(scelta) for alias, scelta in sorted(scelte.items())}}
    temporaneo = config.IMPOSTAZIONI_FILE.with_name(config.IMPOSTAZIONI_FILE.name + ".tmp")
    temporaneo.write_text(json.dumps(contenuto, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporaneo, config.IMPOSTAZIONI_FILE)


def scelta(alias: str) -> SceltaLega:
    return carica().get(alias, SceltaLega())


def testata(alias: str, nome_lega: str = "") -> str:
    """Il nome del giornale: quello forzato dall'ambiente, poi quello scelto, poi il ricavato."""
    forzata = pulisci_testata(os.getenv("FANTA_TESTATA", ""))
    if forzata:
        return forzata
    return scelta(alias).testata or testata_predefinita(nome_lega or alias)
