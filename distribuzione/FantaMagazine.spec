# -*- mode: python ; coding: utf-8 -*-
"""Ricetta di PyInstaller per l'eseguibile Windows di FantaMagazine.

    pyinstaller distribuzione/FantaMagazine.spec --noconfirm --clean

Produce `dist/FantaMagazine/`, con `FantaMagazine.exe` e la cartella `_internal`
accanto: e' la modalita' a cartella, non a file unico. Costa una cartella in
piu' ma l'avvio e' immediato - niente da scompattare a ogni doppio clic - e gli
antivirus ci mettono meno il naso.

Quello che entra nel pacchetto e' solo l'elenco qui sotto: il codice e le pagine
della redazione. Non viene copiata la cartella del progetto, quindi credenziali,
token, chiave di Gemini, scelte personali e cache non hanno una strada per
finirci dentro nemmeno per sbaglio.
"""

from pathlib import Path

RADICE = Path(SPECPATH).parent  # noqa: F821 - SPECPATH lo definisce PyInstaller

analisi = Analysis(  # noqa: F821
    [str(RADICE / "launcher.py")],
    pathex=[str(RADICE)],
    binaries=[],
    # Le pagine e i fogli di stile della redazione: Flask li cerca in
    # `config.RISORSE`, che nell'eseguibile e' la radice del pacchetto.
    datas=[
        (str(RADICE / "web" / "templates"), "web/templates"),
        (str(RADICE / "web" / "static"), "web/static"),
    ],
    # `app` e i suoi moduli arrivano da un import dentro una funzione: dichiararli
    # evita di dipendere da quanto a fondo guarda l'analisi automatica.
    hiddenimports=[
        "app",
        "fantamagazine.accesso",
        "fantamagazine.analysis",
        "fantamagazine.api",
        "fantamagazine.auth",
        "fantamagazine.browser",
        "fantamagazine.config",
        "fantamagazine.gemini",
        "fantamagazine.impostazioni",
        "fantamagazine.listone",
        "fantamagazine.prompt",
        "fantamagazine.resoconto",
        "fantamagazine.servizio",
        "fantamagazine.storico",
        "fantamagazine.tendenze",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # La redazione vive nel browser: dell'interfaccia grafica di Python non ha
    # bisogno, e tenerla fuori risparmia qualche megabyte.
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)

pacchetto = PYZ(analisi.pure)  # noqa: F821

eseguibile = EXE(  # noqa: F821
    pacchetto,
    analisi.scripts,
    [],
    exclude_binaries=True,
    name="FantaMagazine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX no: comprime poco e fa scattare piu' spesso gli antivirus.
    upx=False,
    # Console visibile: e' il posto dove si leggono gli errori, e chiuderla
    # ferma la redazione. Senza, un guasto all'avvio sparirebbe senza traccia.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

COLLECT(  # noqa: F821
    eseguibile,
    analisi.binaries,
    analisi.datas,
    strip=False,
    upx=False,
    name="FantaMagazine",
)
