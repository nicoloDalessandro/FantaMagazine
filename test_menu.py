"""Verifica del menu di scelta della lega.

Su Windows `sys.stdin.isatty()` non e' affidabile (Git Bash lo riporta True
anche con stdin rediretto), quindi il comportamento del menu si prova qui
sostituendo input(), invece che affidandosi alla pipe della shell.

    python test_menu.py
"""

from __future__ import annotations

import builtins
import contextlib
import io
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import main

VOCI = [
    ("fantatana", "FantaTana"),
    ("fantatana--mantra", "FANTATANA - Mantra"),
    ("madonna-del-pozzo-league", "Madonna Del Pozzo League"),
]


class _FintoStdin:
    def __init__(self, terminale: bool) -> None:
        self._terminale = terminale

    def isatty(self) -> bool:
        return self._terminale


@contextlib.contextmanager
def _risposte(valori: list[str], terminale: bool = True):
    """Sostituisce input() e stdin per la durata del blocco."""
    originale_input, originale_stdin = builtins.input, sys.stdin
    sequenza = iter(valori)

    def falso_input(*_):
        try:
            return next(sequenza)
        except StopIteration:
            raise EOFError

    builtins.input = falso_input
    sys.stdin = _FintoStdin(terminale)
    try:
        yield
    finally:
        builtins.input = originale_input
        sys.stdin = originale_stdin


def _scegli(valori: list[str], terminale: bool = True) -> str:
    with _risposte(valori, terminale), contextlib.redirect_stderr(io.StringIO()):
        return main._chiedi(VOCI, "Quale?")


def test_numero_valido() -> None:
    assert _scegli(["3"]) == "madonna-del-pozzo-league"
    print("  ok  il numero seleziona la voce giusta")


def test_alias_per_esteso() -> None:
    assert _scegli(["madonna-del-pozzo-league"]) == "madonna-del-pozzo-league"
    print("  ok  si puo' digitare l'alias invece del numero")


def test_invio_sceglie_la_prima() -> None:
    assert _scegli([""]) == "fantatana"
    print("  ok  invio a vuoto sceglie la prima")


def test_ripete_finche_serve() -> None:
    assert _scegli(["9", "banana", "2"]) == "fantatana--mantra"
    print("  ok  input non validi vengono rifiutati senza uscire")


def test_eof_prosegue() -> None:
    """Senza nessuno che risponda si va avanti, non si esce."""
    assert _scegli([]) == "fantatana"
    print("  ok  EOF prosegue con la prima invece di interrompere")


def test_voce_unica_non_chiede() -> None:
    with _risposte([]), contextlib.redirect_stderr(io.StringIO()):
        assert main._chiedi([("solo", "Unica")], "Quale?") == "solo"
    print("  ok  con una sola opzione non fa domande")


def test_non_terminale_sceglie_la_prima() -> None:
    assert _scegli(["3"], terminale=False) == "fantatana"
    print("  ok  fuori da un terminale non si blocca ad aspettare")


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
