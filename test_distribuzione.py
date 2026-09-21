"""Prove sulla distribuzione: avvio, percorsi dei dati e cancelli della release.

Questa parte del progetto si usa una volta per versione, e proprio per questo
puo' rompersi senza che nessuno se ne accorga fino al momento peggiore: la
release e' gia' pubblicata e qualcuno ha gia' scaricato lo ZIP. Qui si prova
quello che a mano non si guarderebbe:

  - il ripiego sulla porta libera, che su Windows non e' ovvio;
  - dove finiscono i dati quando l'app gira come eseguibile;
  - i due controlli che precedono la pubblicazione, presi per il verso giusto e
    per quello sbagliato: devono anche saper dire no.

Niente rete, nessun eseguibile costruito: si lavora su cartelle temporanee e su
archivi finti.
"""

from __future__ import annotations

import contextlib
import os
import re
import socket
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import launcher
from distribuzione import controlla_zip
from fantamagazine import __version__, config

RADICE = Path(__file__).resolve().parent


@contextlib.contextmanager
def _cartella():
    """Una cartella temporanea, con il percorso già risolto.

    `resolve()` non è un vezzo: su Windows la cartella temporanea può stare
    dentro un nome abbreviato in forma 8.3 - sui runner di GitHub la TEMP
    contiene `RUNNER~1` - e l'app risolve i percorsi prima di usarli. Senza
    risolvere anche questo, il confronto fallirebbe pur essendo lo stesso posto.
    """
    with tempfile.TemporaryDirectory() as nome:
        yield Path(nome).resolve()


@contextlib.contextmanager
def _in_ascolto():
    """Una porta davvero occupata, come lo sarebbe da una redazione gia' aperta.

    La porta la sceglie il sistema (`bind` sulla 0) invece di essere scritta qui:
    su Windows interi intervalli sono riservati - da Hyper-V, da WSL - e un
    numero fisso prima o poi finisce dentro uno di quelli, con un rifiuto di
    accesso che non ha nulla a che vedere con cio' che si sta provando.
    """
    presa = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        presa.bind(("127.0.0.1", 0))
        presa.listen(1)
        yield presa.getsockname()[1]
    finally:
        presa.close()


def _applicazione_finta(_ambiente, rispondi):
    rispondi("200 OK", [("Content-Type", "text/plain")])
    return [b"ok"]


def _zip_finto(percorso: Path, voci: dict[str, str]) -> Path:
    with zipfile.ZipFile(percorso, "w") as archivio:
        for nome, contenuto in voci.items():
            archivio.writestr(nome, contenuto)
    return percorso


def _completo(prefisso: str = "") -> dict[str, str]:
    """Un pacchetto con tutto il necessario, come quello che esce dalla CI."""
    return {f"{prefisso}{nome}": "x" for nome in controlla_zip.NECESSARI}


# --- L'avvio -----------------------------------------------------------------
def test_porta_occupata_viene_saltata() -> None:
    """La porta chiesta e' occupata: il server deve finire su una di quelle dopo.

    Non e' scontato. Werkzeug attiva SO_REUSEADDR, e su Windows quell'opzione
    lascia legare una porta gia' in uso: due redazioni si sarebbero messe sullo
    stesso indirizzo senza che nessuno protestasse.
    """
    with _in_ascolto() as occupata:
        assert launcher._libera("127.0.0.1", occupata) is False
        servitore = launcher._server(_applicazione_finta, "127.0.0.1", occupata)
        try:
            scelta = servitore.server_port
            assert scelta != occupata, f"il server si è messo sulla porta occupata {scelta}"
            assert occupata < scelta <= occupata + launcher.PORTE_DA_PROVARE, scelta
        finally:
            servitore.server_close()
    print("  ok  una porta occupata viene saltata, non rubata")


def test_nessuna_porta_libera_si_ferma_spiegando() -> None:
    originale = launcher.PORTE_DA_PROVARE
    launcher.PORTE_DA_PROVARE = 1  # solo la porta chiesta, che e' occupata
    try:
        with _in_ascolto() as occupata:
            errore = None
            try:
                launcher._server(_applicazione_finta, "127.0.0.1", occupata)
            except SystemExit as esito:
                errore = esito
            assert errore is not None, "senza porte libere non puo' proseguire"
            assert str(occupata) in str(errore) and "già aperta" in str(errore), str(errore)
    finally:
        launcher.PORTE_DA_PROVARE = originale
    print("  ok  senza porte libere si fermerebbe dicendo il perché")


def test_il_server_ascolta_prima_del_browser() -> None:
    """`make_server` lega il socket subito: e' cio' che rende sicuro aprire il browser."""
    with _in_ascolto() as occupata:
        pass  # chiusa all'uscita: una porta che il sistema ha appena dichiarato libera
    servitore = launcher._server(_applicazione_finta, "127.0.0.1", occupata)
    try:
        assert launcher._libera("127.0.0.1", servitore.server_port) is False
    finally:
        servitore.server_close()
    print("  ok  quando il server esiste la porta risponde già: il browser non trova il vuoto")


# --- Dove finiscono i dati ----------------------------------------------------
def test_da_sorgente_i_dati_restano_nel_progetto() -> None:
    assert config.CONGELATO is False
    assert config._cartella_dati() == RADICE
    assert config.RISORSE == RADICE
    assert config.LEGHE_FILE.parent == RADICE and config.IMPOSTAZIONI_FILE.parent == RADICE
    print("  ok  da sorgente i percorsi sono quelli di sempre, nella cartella del progetto")


def test_nell_eseguibile_i_dati_stanno_accanto_all_exe() -> None:
    """Estratto lo ZIP, tutto vive in quella cartella: per disfarsene basta cancellarla."""
    with _cartella() as finta:
        eseguibile = finta / "FantaMagazine.exe"
        eseguibile.write_bytes(b"finto")
        originali = (config.CONGELATO, sys.executable)
        config.CONGELATO = True
        sys.executable = str(eseguibile)
        try:
            scelta = config._cartella_dati()
            assert scelta == finta, f"{scelta} invece di {finta}"
        finally:
            config.CONGELATO, sys.executable = originali
    print("  ok  nell'eseguibile i dati stanno accanto all'exe, non in una cartella temporanea")


def test_se_non_si_scrive_si_ripiega_sui_dati_locali() -> None:
    """In Programmi Windows non lascia scrivere: i token andrebbero persi a ogni avvio."""
    with _cartella() as riserva:
        inesistente = Path(riserva) / "non-esiste" / "FantaMagazine.exe"
        originali = (config.CONGELATO, sys.executable, os.environ.get("LOCALAPPDATA"))
        config.CONGELATO = True
        sys.executable = str(inesistente)
        os.environ["LOCALAPPDATA"] = str(riserva)
        try:
            scelta = config._cartella_dati()
            assert scelta == riserva / "FantaMagazine", scelta
            assert scelta.is_dir(), "la cartella di riserva va creata, non solo nominata"
        finally:
            config.CONGELATO, sys.executable = originali[0], originali[1]
            if originali[2] is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = originali[2]
    print("  ok  dove non si può scrivere i dati vanno in %LOCALAPPDATA%, non nel nulla")


# --- La ricetta del pacchetto -------------------------------------------------
def test_la_ricetta_include_tutte_le_risorse_del_web() -> None:
    """Una cartella nuova sotto web/ va dichiarata, o nell'eseguibile non ci sarebbe.

    E' l'errore che non si vede provando dal sorgente: lì i file ci sono comunque.
    """
    ricetta = (RADICE / "distribuzione" / "FantaMagazine.spec").read_text(encoding="utf-8")
    for cartella in sorted(p for p in (RADICE / "web").iterdir() if p.is_dir()):
        atteso = f'"web/{cartella.name}"'
        assert atteso in ricetta, f"web/{cartella.name} non è dichiarata nello .spec"

    attesi = {
        f"_internal/{risorsa.relative_to(RADICE).as_posix()}"
        for risorsa in (RADICE / "web").rglob("*")
        if risorsa.is_file()
    }
    mancanti = attesi - set(controlla_zip.NECESSARI)
    assert not mancanti, f"file del web non controllati nello ZIP: {sorted(mancanti)}"
    print(f"  ok  le {len(attesi)} risorse del web sono nella ricetta e fra i file controllati")


# --- I cancelli prima della pubblicazione -------------------------------------
def test_lo_zip_completo_passa() -> None:
    with _cartella() as cartella:
        for prefisso in ("", "FantaMagazine/"):
            archivio = _zip_finto(cartella / f"buono{len(prefisso)}.zip", _completo(prefisso))
            assert controlla_zip.controlla(archivio) == [], prefisso
    print("  ok  uno ZIP completo passa, con o senza la cartella di primo livello")


def test_lo_zip_senza_le_pagine_non_passa() -> None:
    """Senza il template la redazione si aprirebbe su un errore 500."""
    with _cartella() as cartella:
        voci = _completo("FantaMagazine/")
        del voci["FantaMagazine/_internal/web/templates/index.html"]
        problemi = controlla_zip.controlla(_zip_finto(cartella / "mutilo.zip", voci))
        assert len(problemi) == 1 and "index.html" in problemi[0], problemi

        vuoto = controlla_zip.controlla(_zip_finto(cartella / "vuoto.zip", {}))
        assert any("vuoto" in p for p in vuoto), vuoto
    print("  ok  uno ZIP a cui manca una pagina, o vuoto, viene fermato")


def test_lo_zip_con_dati_personali_non_passa() -> None:
    """Il cancello che conta: non si fida della ricetta, guarda il risultato."""
    intrusi = (
        ".gemini_key",
        ".openai_key",
        ".anthropic_key",
        "credentials",
        ".env",
        ".fanta_leghe.json",
        ".fanta_utente.json",
        ".fanta_impostazioni.json",
        ".cache/giornate/1.json",
        "prime_pagine/pagina.png",
        ".claude/launch.json",
        ".idea/workspace.xml",
        "chiavi/id_rsa",
        "certificato.pfx",
    )
    with _cartella() as cartella:
        for numero, intruso in enumerate(intrusi):
            voci = _completo("FantaMagazine/")
            voci[f"FantaMagazine/{intruso}"] = "segreto"
            problemi = controlla_zip.controlla(_zip_finto(cartella / f"s{numero}.zip", voci))
            assert len(problemi) == 1, f"{intruso}: {problemi}"
            assert intruso in problemi[0], f"{intruso}: {problemi}"

        # I certificati pubblici di requests contengono ".pem" ma servono: senza,
        # nessuna chiamata HTTPS riuscirebbe.
        voci = _completo("FantaMagazine/")
        voci["FantaMagazine/_internal/certifi/cacert.pem"] = "certificati"
        assert controlla_zip.controlla(_zip_finto(cartella / "certifi.zip", voci)) == []
    print(f"  ok  {len(intrusi)} tipi di file personali fermano la release; i certificati no")


def test_il_tag_deve_corrispondere_alla_versione() -> None:  # noqa: D401
    """Uno ZIP v1.1.0 con dentro un'app che si dichiara 1.0.0 non e' verificabile dopo."""
    controllo = RADICE / "distribuzione" / "versione.py"
    for tag, atteso in ((f"v{__version__}", 0), ("v9.9.9", 1), ("1.0.0", 1), ("", 1)):
        esito = subprocess.run(
            [sys.executable, str(controllo), tag],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert esito.returncode == atteso, f"tag {tag!r}: uscita {esito.returncode}"

    senza = subprocess.run(
        [sys.executable, str(controllo)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert senza.returncode == 0 and senza.stdout.strip() == __version__, senza.stdout
    print("  ok  il tag sbagliato blocca la pubblicazione; senza argomenti stampa la versione")


def test_la_versione_e_semantica_e_una_sola() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__
    assert config.USER_AGENT == f"FantaMagazine/{__version__}", config.USER_AGENT
    print(f"  ok  versione {__version__}, semantica, ed e' quella che l'app dichiara in rete")


# --- I workflow ---------------------------------------------------------------
def test_i_workflow_non_chiedono_segreti() -> None:
    """Il build deve essere rifacibile da chiunque, senza credenziali personali.

    L'unico segreto ammesso e' GITHUB_TOKEN, che GitHub crea per il singolo
    workflow: una chiave di Gemini o una password di Fantacalcio qui sarebbero
    un errore grave, e finirebbero nella storia del repository.
    """
    for nome in ("ci.yml", "release.yml"):
        testo = (RADICE / ".github" / "workflows" / nome).read_text(encoding="utf-8")
        usati = set(re.findall(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)", testo))
        assert usati <= {"GITHUB_TOKEN"}, f"{nome} usa segreti: {sorted(usati)}"
        assert "permissions:" in testo, f"{nome} non limita i permessi"
        assert "pull_request_target" not in testo, f"{nome} usa pull_request_target"
        for chiave in ("GEMINI", "password", "FANTA_APP_KEY", "fantacalcio.it/login"):
            assert chiave not in testo, f"{nome} contiene «{chiave}»"
    print("  ok  i workflow limitano i permessi e non chiedono segreti oltre a GITHUB_TOKEN")


def test_i_file_personali_restano_fuori_da_git() -> None:
    """Le regole di .gitignore, verificate una per una invece che a memoria."""
    personali = (
        "credentials", ".gemini_key", ".openai_key", ".anthropic_key", ".env",
        ".fanta_leghe.json", ".fanta_utente.json",
        ".fanta_impostazioni.json", ".fanta_token", ".cache/giornate/1.json",
        "prime_pagine/x.png", "dist/FantaMagazine/FantaMagazine.exe", "build/x",
        "FantaMagazine-Windows-v1.0.0.zip", ".idea/workspace.xml", ".claude/launch.json",
    )
    # --no-index: risponde sulle regole di .gitignore anche per un percorso che
    # git per qualche ragione conosce gia'.
    try:
        esclusi = subprocess.run(
            ["git", "check-ignore", "--no-index", *personali],
            cwd=RADICE, capture_output=True, text=True,
        )
    except OSError:
        # Da uno ZIP del codice, senza git installato, non c'e' niente da
        # controllare: le regole vivono nel repository, non qui.
        print("  --  git non disponibile: regole di .gitignore non verificate")
        return
    fuori = set(esclusi.stdout.split())
    dentro = subprocess.run(
        ["git", "ls-files"], cwd=RADICE, capture_output=True, text=True,
    ).stdout.split()

    mancanti = [voce for voce in personali if voce not in fuori]
    assert not mancanti, f".gitignore non esclude: {mancanti}"
    for tracciato in dentro:
        assert not tracciato.startswith((".fanta", ".gemini", ".claude/", ".idea/", "dist/")), (
            f"file personale tracciato da git: {tracciato}"
        )
    print(f"  ok  {len(personali)} percorsi personali esclusi da git, e nessuno è tracciato")


def main_test() -> int:
    prove = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    falliti = 0
    for prova in prove:
        try:
            prova()
        except AssertionError as errore:
            falliti += 1
            print(f"  FALLITO  {prova.__name__}: {errore}")
    print(f"\n{len(prove) - falliti}/{len(prove)} prove superate")
    return 1 if falliti else 0


if __name__ == "__main__":
    raise SystemExit(main_test())
