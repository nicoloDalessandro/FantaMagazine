"""Generazione del prompt per un modello testo-immagine.

Trasforma i dati della giornata in un prompt che descrive la prima pagina di un
quotidiano sportivo: testata, titolo, il racconto di una partita, i risultati,
la classifica, un pezzo sulla classifica e un trafiletto per ciascuna delle
altre gare.

Tre scelte di scrittura attraversano tutto il modulo.

**Una gara in apertura, le altre una per trafiletto.** Così ogni partita è
coperta una volta sola e nessuna squadra viene raccontata due volte con parole
diverse.

**Angoli, non soggetti.** Due trafiletti che dicono "tot fantapunti, trascinata
da Tizio" cambiando solo i nomi si leggono come lo stesso pezzo stampato due
volte. Ogni gara propone quindi più angoli — vetta, prima vittoria, crisi,
dominio... — e l'assegnazione scarta quelli già presi. Ogni partita ha in fondo
al mazzo un angolo garantito, con chiave unica, perché nessuna resti senza
trafiletto: era il difetto che faceva sparire dalla pagina il secondo pareggio
di giornata.

**Non si nomina mai la squadra di Serie A di un giocatore.** In una lega di
fantacalcio i lettori conoscono i propri giocatori, e "Frattesi (LAZ)" suona
come una scheda anagrafica, non come un giornale.

Il `seme` che attraversa le funzioni decide quali formule vengono scelte. Per
difetto è il numero di giornata, quindi lo stesso turno rigenera sempre lo
stesso prompt: comodo da verificare, ma va chiesto esplicitamente (--varia)
quando si vogliono più versioni fra cui scegliere.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .analysis import Formazione, Partita, RigaClassifica
from .tendenze import SOGLIA_DIGIUNO, SOGLIA_STRISCIA, Memoria, StoricoSquadra

# Un commento è una terna: titoletto, testo, chiavi citate (per la deduplica).
Commento = tuple[str, str, frozenset]

# Una serie finisce nel titolo solo se dura: a caratteri cubitali, la seconda
# sconfitta di fila suonerebbe come un allarme esagerato.
SOGLIA_TITOLO = 3


@dataclass
class Richiamo:
    """Un punto della pagina che senza la memoria non si potrebbe scrivere.

    Risponde a una domanda precisa: la storia pesa davvero su quello che si
    legge? Titoli, frasi e trafiletti nati da una serie o da una prima volta
    lasciano qui il testo esatto che finisce in pagina e il dato che li ha fatti
    scattare. La traccia si raccoglie mentre la pagina si compone, invece di
    ricostruirla dopo: così non può raccontare una storia diversa da quella
    stampata.
    """

    sezione: str  # "titolo", "racconto", "dietro_i_numeri", "trafiletti"
    tipo: str  # "sconfitte", "vittorie", "digiuno", "prima_vittoria", ...
    squadra: str
    valore: int  # la lunghezza della serie; 1 per le prime volte
    titolo: str  # titolo o titoletto; vuoto per una frase dentro un pezzo
    testo: str  # sottotitolo, frase o testo del trafiletto, come in pagina

ORDINALI = {
    2: "seconda",
    3: "terza",
    4: "quarta",
    5: "quinta",
    6: "sesta",
    7: "settima",
    8: "ottava",
}

LETTERE = {7: "SETTE", 8: "OTTO", 9: "NOVE", 10: "DIECI"}


def _n(valore: float) -> str:
    """82.0 -> '82', 82.5 -> '82,5' (virgola decimale, come si scrive in Italia)."""
    return f"{valore:g}".replace(".", ",")


def _ordinale(n: int) -> str:
    return ORDINALI.get(n, f"{n}ª")


def _elenco(nomi: Sequence[str]) -> str:
    """['A'] -> 'A'; ['A','B'] -> 'A e B'; ['A','B','C'] -> 'A, B e C'."""
    nomi = list(nomi)
    if not nomi:
        return ""
    if len(nomi) == 1:
        return nomi[0]
    return f"{', '.join(nomi[:-1])} e {nomi[-1]}"


def _frase(testo: str) -> str:
    """Chiude la frase con un punto, senza raddoppiarlo.

    Molti cognomi arrivano abbreviati ("Yeboah J."), quindi la punteggiatura
    va aggiunta solo quando serve davvero.
    """
    testo = testo.rstrip()
    return testo if testo.endswith((".", "!", "?")) else f"{testo}."


def _scelta(seme: int, chiave: str, quante: int) -> int:
    """Indice riproducibile per un punto di scelta.

    Il seme viene mescolato con una chiave che identifica il punto di scelta,
    così ogni punto sceglie indipendentemente dagli altri. Con un semplice
    `seme % quante` tutti i punti a due o tre formule si muovevano insieme, e
    sessanta semi producevano appena sei testi diversi.

    crc32 e non hash(): hash() sulle stringhe cambia a ogni avvio di Python,
    mentre la stessa giornata con lo stesso seme deve dare sempre lo stesso
    prompt.
    """
    return zlib.crc32(f"{seme}\x1f{chiave}".encode("utf-8")) % quante


def _variante(opzioni: Sequence[str], seme: int) -> str:
    """Sceglie una formula fra più opzioni, in modo vario ma riproducibile."""
    return opzioni[_scelta(seme, opzioni[0], len(opzioni))]


def _formule(seme: int, *varianti: tuple[str, str]) -> tuple[str, str]:
    """Sceglie titolo e testo fra più formulazioni della stessa notizia.

    Titolo e testo restano accoppiati: ogni variante è scritta perché le due
    parti si leggano insieme senza ripetere lo stesso nome.
    """
    return varianti[_scelta(seme, "\x1f".join(varianti[0]), len(varianti))]


def _maiuscola(testo: str) -> str:
    """Prima lettera maiuscola, il resto intatto.

    str.capitalize() abbasserebbe anche i nomi delle squadre che seguono.
    """
    return testo[:1].upper() + testo[1:]


def _col_articolo(risultato: str, preposizione: str = "") -> str:
    """Il punteggio con l'articolo giusto: il 2-1, l'1-1, lo 0-0, sull'1-0.

    L'articolo segue la pronuncia del primo numero, come nei giornali: "l'"
    davanti a uno, otto e undici, "lo" davanti a zero, "il" negli altri casi.
    Scrivere sempre "il" produceva "il 1-1" e "sul 0-0".
    """
    primo = risultato.split("-", 1)[0].strip()
    if primo == "0":
        forma = "lo"
    elif primo in {"1", "8", "11"}:
        forma = "l'"
    else:
        forma = "il"
    articoli = {
        "": {"il": "il ", "l'": "l'", "lo": "lo "},
        "su": {"il": "sul ", "l'": "sull'", "lo": "sullo "},
        "di": {"il": "del ", "l'": "dell'", "lo": "dello "},
        "da": {"il": "dal ", "l'": "dall'", "lo": "dallo "},
    }
    return articoli[preposizione][forma] + risultato


def _un_risultato(risultato: str) -> str:
    """"un 2-1", ma "uno 0-0"."""
    return ("uno " if risultato.split("-", 1)[0].strip() == "0" else "un ") + risultato


def _punti(valore: int) -> str:
    """"1 punto", "0 punti", "7 punti"."""
    return f"{valore} punto" if valore == 1 else f"{valore} punti"


def _fantapunti(valore: float) -> str:
    """"un fantapunto", "0,5 fantapunti", "18 fantapunti"."""
    return "un fantapunto" if valore == 1 else f"{_n(valore)} fantapunti"


def _marcatori_con_gol(formazione: Formazione) -> list[str]:
    """['Malen (doppietta)', 'Volpato']."""
    voci = []
    for g in formazione.marcatori:
        if g.gol >= 3:
            voci.append(f"{g.nome} (tripletta)")
        elif g.gol == 2:
            voci.append(f"{g.nome} (doppietta)")
        else:
            voci.append(g.nome)
    return voci


# --- Titolo -----------------------------------------------------------------
def _titolo_crisi(
    peggiore: StoricoSquadra, seme: int, richiami: list[Richiamo] | None = None
) -> tuple[str, str]:
    """Il titolo di una striscia di sconfitte, con la sua traccia in memoria."""
    nome = peggiore.nome.upper()
    ordinale = _ordinale(peggiore.striscia_sconfitte)
    principale, sottotitolo = _formule(
        seme,
        (
            f"{nome} NON SI RIALZA",
            f"{ordinale.capitalize()} sconfitta consecutiva: la crisi non "
            f"accenna a fermarsi",
        ),
        (
            f"NOTTE FONDA PER {nome}",
            f"{ordinale.capitalize()} sconfitta di fila, e la risalita sembra "
            f"lontana",
        ),
        (
            f"{nome}, CRISI SENZA FINE",
            f"Arriva la {ordinale} sconfitta consecutiva: serve una svolta",
        ),
        (
            f"{nome} AFFONDA ANCORA",
            f"{ordinale.capitalize()} sconfitta di fila: la classifica si fa "
            f"pesante",
        ),
    )
    if richiami is not None:
        richiami.append(
            Richiamo("titolo", "sconfitte", peggiore.nome,
                     peggiore.striscia_sconfitte, principale, sottotitolo)
        )
    return principale, sottotitolo


def _titolo_serie(
    migliore: StoricoSquadra, seme: int, richiami: list[Richiamo] | None = None
) -> tuple[str, str]:
    """Il titolo di una striscia di vittorie, con la sua traccia in memoria."""
    nome = migliore.nome.upper()
    ordinale = _ordinale(migliore.striscia_vittorie)
    principale, sottotitolo = _formule(
        seme,
        (
            f"{nome} NON SI FERMA PIÙ",
            f"{ordinale.capitalize()} vittoria di fila, e la classifica sorride",
        ),
        (
            f"{nome} VOLA",
            f"{ordinale.capitalize()} vittoria consecutiva: nessuno sembra in "
            f"grado di fermarla",
        ),
        (
            f"INARRESTABILE {nome}",
            f"Con la {ordinale} vittoria di fila allunga il passo",
        ),
        (
            f"{nome}, CHE MARCIA",
            f"{ordinale.capitalize()} vittoria consecutiva: ritmo da grande",
        ),
    )
    if richiami is not None:
        richiami.append(
            Richiamo("titolo", "vittorie", migliore.nome,
                     migliore.striscia_vittorie, principale, sottotitolo)
        )
    return principale, sottotitolo


def _titolo_partita(
    partita: Partita,
    memoria: Memoria | None = None,
    seme: int = 0,
    richiami: list[Richiamo] | None = None,
) -> tuple[str, str]:
    """Il titolo quando la partita d'apertura l'ha scelta chi usa l'app.

    Il titolo deve parlare di quella partita, non della giornata. Se una delle
    due squadre ha una striscia da prima pagina la si racconta, perche' questa
    partita e' l'ultimo anello della striscia; con le stesse soglie e la stessa
    precedenza del titolo automatico: prima la crisi, poi la serie positiva.
    Una striscia di chi non gioca questa partita resta fuori: la scelta di chi
    usa l'app viene prima.

    Altrimenti il titolo nasce dalla partita stessa, con le stesse soglie del
    racconto (pareggio, dominio, vittoria sul filo, in casa, in trasferta) ma
    con verbi diversi, cosi' titolo e attacco del pezzo non ripetono la stessa
    parola a tre righe di distanza. Ogni caso ha piu' formule: "Scrivila
    diversamente" deve poter cambiare anche il titolo.
    """
    if memoria and memoria.abbastanza_storia:
        schede = [
            scheda
            for scheda in (memoria.squadre.get(f.squadra) for f in (partita.casa, partita.trasferta))
            if scheda
        ]
        crisi = max(
            (s for s in schede if s.striscia_sconfitte >= SOGLIA_TITOLO),
            key=lambda s: s.striscia_sconfitte,
            default=None,
        )
        if crisi:
            return _titolo_crisi(crisi, seme, richiami)
        serie = max(
            (s for s in schede if s.striscia_vittorie >= SOGLIA_TITOLO),
            key=lambda s: s.striscia_vittorie,
            default=None,
        )
        if serie:
            return _titolo_serie(serie, seme, richiami)

    casa, trasferta = partita.casa, partita.trasferta
    risultato = partita.risultato

    if partita.gol_casa == partita.gol_trasferta:
        a, b = casa.squadra.upper(), trasferta.squadra.upper()
        return _formule(
            seme,
            (f"PARI TRA {a} E {b}", f"Finisce {risultato}: un punto per parte"),
            (
                f"{a} E {b} NON SI FANNO MALE",
                f"{_maiuscola(_col_articolo(risultato))} non premia nessuno",
            ),
            (
                f"{a} E {b}, TUTTO IN EQUILIBRIO",
                f"La sfida si chiude {_col_articolo(risultato, 'su')}, senza padroni",
            ),
        )

    vincente = casa if partita.gol_casa > partita.gol_trasferta else trasferta
    perdente = trasferta if vincente is casa else casa
    v, p = vincente.squadra.upper(), perdente.squadra.upper()
    scarto = round(abs(casa.totale - trasferta.totale), 1)

    if scarto >= 15:
        return _formule(
            seme,
            (f"{v} DILAGA CONTRO {p}", f"Finisce {risultato}, con {_fantapunti(scarto)} di margine"),
            (
                f"{v} NON FA SCONTI A {p}",
                f"{_maiuscola(_col_articolo(risultato))} chiude una partita mai in discussione",
            ),
            (f"{v} SCHIACCIA {p}", f"Vittoria per {risultato} e {_fantapunti(scarto)} di vantaggio"),
        )

    if scarto <= 3:
        return _formule(
            seme,
            (f"{v}, VITTORIA SUL FILO", f"Finisce {risultato}: a decidere sono pochi decimi"),
            (
                f"{v} VINCE DI MISURA",
                f"Contro {perdente.squadra} basta {_un_risultato(risultato)} costruito sui decimali",
            ),
            (f"{v} DI UN SOFFIO SU {p}", f"{_maiuscola(_col_articolo(risultato))} arriva allo sprint"),
        )

    if vincente is casa:
        return _formule(
            seme,
            (f"{v} PIEGA {p}", f"Il fattore campo pesa: finisce {risultato}"),
            (
                f"{v} FA SUA LA SFIDA CON {p}",
                f"{_maiuscola(_col_articolo(risultato))} e tre punti davanti al proprio pubblico",
            ),
            (f"{v} BATTE {p}", f"Finisce {risultato}, e i tre punti restano in casa"),
        )

    return _formule(
        seme,
        (f"COLPO DI {v} IN CASA DI {p}", f"Finisce {risultato}: tre punti pesanti in trasferta"),
        (f"BLITZ DI {v} CONTRO {p}", f"Vittoria esterna per {risultato}"),
        (
            f"{v} SBANCA IL CAMPO DI {p}",
            f"{_maiuscola(_col_articolo(risultato))} in trasferta vale tre punti",
        ),
    )


def _titolo_completo(
    partite: list[Partita],
    memoria: Memoria | None = None,
    seme: int = 0,
    richiami: list[Richiamo] | None = None,
) -> tuple[str, str, frozenset]:
    """Titolo, sottotitolo e i soggetti che il titolo consuma.

    Il seme sceglie la formulazione, mai la notizia: quale fatto va in prima
    pagina lo decide la sua importanza, e con abbastanza storia alle spalle una
    striscia lunga batte qualunque fatto della singola giornata.
    """
    if memoria and memoria.abbastanza_storia:
        crisi = memoria.in_crisi()
        if crisi and crisi[0].striscia_sconfitte >= SOGLIA_TITOLO:
            principale, sottotitolo = _titolo_crisi(crisi[0], seme, richiami)
            return (principale, sottotitolo, frozenset({crisi[0].nome}))

        serie = memoria.in_serie_positiva()
        if serie and serie[0].striscia_vittorie >= SOGLIA_TITOLO:
            principale, sottotitolo = _titolo_serie(serie[0], seme, richiami)
            return (principale, sottotitolo, frozenset({serie[0].nome}))

    trasferta = sum(1 for p in partite if p.gol_trasferta > p.gol_casa)
    casa = sum(1 for p in partite if p.gol_casa > p.gol_trasferta)
    totali = len(partite)

    # Un titolo che parla dell'intera giornata non consuma nessun soggetto.
    if totali and trasferta == totali:
        principale, sottotitolo = _formule(
            seme,
            (
                "IN TRASFERTA COMANDANO TUTTI",
                f"Nessuna squadra di casa raccoglie punti: {totali} successi esterni "
                f"su {totali} partite",
            ),
            (
                "IL CAMPO AMICO NON AIUTA NESSUNO",
                f"Su {totali} partite, {totali} vittorie in trasferta",
            ),
            (
                "GIORNATA DA TRASFERTISTI",
                f"Tutte le ospiti tornano a casa con i tre punti: {totali} su {totali}",
            ),
        )
        return (principale, sottotitolo, frozenset())

    if totali and casa == totali:
        principale, sottotitolo = _formule(
            seme,
            (
                "IL FATTORE CAMPO NON TRADISCE",
                f"Tutte le padrone di casa vincono: {totali} successi interni su {totali}",
            ),
            (
                "IN CASA NON SI PASSA",
                "Nessuna ospite fa punti: le padrone di casa vincono ogni partita",
            ),
            (
                "FORTINI INESPUGNABILI",
                f"Su {totali} partite, {totali} vittorie per chi giocava davanti al "
                f"proprio pubblico",
            ),
        )
        return (principale, sottotitolo, frozenset())

    migliore = max(
        (f for p in partite for f in (p.casa, p.trasferta)),
        key=lambda f: f.totale,
        default=None,
    )
    if migliore:
        nome = migliore.squadra.upper()
        punteggio = _n(migliore.totale)
        principale, sottotitolo = _formule(
            seme,
            (f"{nome} FA IL VUOTO", f"Miglior punteggio di giornata con {punteggio} fantapunti"),
            (f"{nome} SUL TETTO DELLA GIORNATA", f"Nessuno fa meglio dei suoi {punteggio} fantapunti"),
            (f"IL TURNO È DI {nome}", f"Con {punteggio} fantapunti firma il punteggio più alto"),
            (f"{nome} DETTA LEGGE", f"Firma il miglior punteggio di giornata: {punteggio} fantapunti"),
        )
        return (principale, sottotitolo, frozenset({migliore.squadra}))
    return ("GIORNATA DI FANTACALCIO", "", frozenset())


def titolo(
    partite: list[Partita], memoria: Memoria | None = None, seme: int = 0
) -> tuple[str, str]:
    """Titolo principale e sottotitolo."""
    principale, sottotitolo, _ = _titolo_completo(partite, memoria, seme)
    return principale, sottotitolo


# --- Il racconto ------------------------------------------------------------
def _interesse(partita: Partita) -> float:
    """Quanto una partita merita di essere raccontata per esteso."""
    punteggio = 0.0
    if partita.casa.incompleta or partita.trasferta.incompleta:
        punteggio += 100
    punteggio += sum(len(f.marcatori) for f in (partita.casa, partita.trasferta)) * 6
    punteggio += sum(len(f.insufficienti) for f in (partita.casa, partita.trasferta)) * 3
    # A parità di tutto, una partita equilibrata si racconta meglio di una scontata.
    punteggio += max(0.0, 20.0 - abs(partita.casa.totale - partita.trasferta.totale))
    return punteggio


def _apertura(partita: Partita, seme: int) -> str:
    """L'attacco del pezzo: deve suonare come una cronaca, non come un referto."""
    casa, trasferta = partita.casa, partita.trasferta
    scarto = abs(casa.totale - trasferta.totale)

    if partita.gol_casa == partita.gol_trasferta:
        return _variante(
            (
                f"Nessuna delle due riesce a piegare l'altra: {casa.squadra} e "
                f"{trasferta.squadra} si dividono la posta "
                f"{_col_articolo(partita.risultato, 'su')}",
                f"Finisce senza vincitori, {partita.risultato}, e il pareggio lascia "
                f"l'amaro in bocca sia a {casa.squadra} sia a {trasferta.squadra}",
                f"{casa.squadra} e {trasferta.squadra} si annullano a vicenda: "
                f"{partita.risultato} e un punto per parte",
            ),
            seme,
        )

    vincente = casa if partita.gol_casa > partita.gol_trasferta else trasferta
    perdente = trasferta if vincente is casa else casa
    in_casa = vincente is casa

    if scarto >= 15:
        return _variante(
            (
                f"Non c'è mai partita: {vincente.squadra} travolge {perdente.squadra} "
                f"per {partita.risultato}",
                f"Una sola squadra in campo. {vincente.squadra} passeggia "
                f"{_col_articolo(partita.risultato, 'su')} contro {perdente.squadra}",
            ),
            seme,
        )

    if scarto <= 3:
        return _variante(
            (
                f"Bastano pochi decimi. {vincente.squadra} la spunta per "
                f"{partita.risultato} su {perdente.squadra}",
                f"Si decide tutto sul filo: {vincente.squadra} batte "
                f"{perdente.squadra} {partita.risultato}",
            ),
            seme,
        )

    if in_casa:
        return _variante(
            (
                f"Il campo amico spinge {casa.squadra}, che regola "
                f"{trasferta.squadra} per {partita.risultato}",
                f"{casa.squadra} fa valere il fattore campo e supera "
                f"{trasferta.squadra} {partita.risultato}",
            ),
            seme,
        )

    return _variante(
        (
            f"Colpo esterno di {trasferta.squadra}, che espugna il campo di "
            f"{casa.squadra} per {partita.risultato}",
            f"{casa.squadra} cade fra le mura amiche: {trasferta.squadra} si impone "
            f"{partita.risultato}",
        ),
        seme,
    )


def _frase_gol(formazione: Formazione, seme: int, prima: bool) -> str:
    """Chi ha segnato, nominando sempre la squadra.

    Quando segnano entrambe, una frase come "ci mette la firma Rossi" non dice
    di chi stiamo parlando: il nome della squadra non è ornamentale.
    """
    gol = _marcatori_con_gol(formazione)
    if not gol:
        return ""
    elenco = _elenco(gol)
    squadra = formazione.squadra
    if len(gol) == 1:
        modelli = (
            f"Per {squadra} ci mette la firma {elenco}",
            f"{squadra} trova il gol con {elenco}",
            f"{squadra} si affida alla zampata di {elenco}",
        )
    else:
        modelli = (
            f"{squadra} costruisce il bottino con {elenco}",
            f"{squadra} va a bersaglio con {elenco}",
            f"Il peso dell'attacco, per {squadra}, lo portano {elenco}",
        )
    return _frase(_variante(modelli, seme + (0 if prima else 1)))


def _paragrafo(
    partita: Partita,
    memoria: Memoria | None,
    seme: int,
    disteso: bool,
    soggetti: set[str] | None = None,
    richiami: list[Richiamo] | None = None,
) -> str:
    """Il testo del pezzo; `soggetti`, se passato, raccoglie chi viene nominato."""
    casa, trasferta = partita.casa, partita.trasferta

    def segna(*nomi: str) -> None:
        if soggetti is not None:
            soggetti.update(nomi)

    segna(casa.squadra, trasferta.squadra)
    frasi: list[str] = [_frase(_apertura(partita, seme))]

    if not disteso:
        # Nel pezzo breve basta il risultato e chi ha segnato.
        for indice, formazione in enumerate((casa, trasferta)):
            testo = _frase_gol(formazione, seme, prima=indice == 0)
            if testo:
                segna(*(g.nome for g in formazione.marcatori))
                frasi.append(testo)
        return " ".join(frasi)

    frasi.append(
        _frase(
            _variante(
                (
                    f"Sul tabellino dei fantapunti si legge {_n(casa.totale)} contro "
                    f"{_n(trasferta.totale)}",
                    f"I numeri dicono {_n(casa.totale)} a {_n(trasferta.totale)}",
                    f"{_n(casa.totale)} fantapunti da una parte, {_n(trasferta.totale)} "
                    f"dall'altra",
                ),
                seme,
            )
        )
    )

    for indice, formazione in enumerate((casa, trasferta)):
        testo = _frase_gol(formazione, seme, prima=indice == 0)
        if testo:
            segna(*(g.nome for g in formazione.marcatori))
            frasi.append(testo)

    if not casa.marcatori and not trasferta.marcatori:
        frasi.append(
            "Nessuno trova la via del gol: a decidere sono i voti puri, "
            "una partita di rendite e di pazienza."
        )

    tutti = casa.giocatori + trasferta.giocatori
    if tutti:
        migliore = max(tutti, key=lambda g: (g.fantavoto, g.voto))
        squadra_migliore = casa if migliore in casa.giocatori else trasferta
        segna(migliore.nome)
        # Niente preposizioni articolate: i nomi delle squadre vanno da
        # "Ouzonion" a "FC Coccoventus", e l'elisione corretta andrebbe decisa
        # sul suono, non sulla lettera. La parentesi evita il problema.
        frasi.append(
            _frase(
                _variante(
                    (
                        f"Su tutti spicca {migliore.nome} ({squadra_migliore.squadra}), "
                        f"{_n(migliore.voto)} in pagella che i bonus portano a "
                        f"{_n(migliore.fantavoto)}",
                        f"L'uomo della giornata è {migliore.nome} "
                        f"({squadra_migliore.squadra}): {_n(migliore.voto)} secco, "
                        f"{_n(migliore.fantavoto)} una volta contati i bonus",
                    ),
                    seme,
                )
            )
        )

    premiati = [
        g.nome for f in (casa, trasferta) for g in f.giocatori if g.bonus and not g.gol
    ]
    if premiati:
        scelti = premiati[:3]
        segna(*scelti)
        elenco_bonus = _elenco(scelti)
        singolo = len(scelti) == 1
        frasi.append(
            _frase(
                _variante(
                    (
                        f"Si fa sentire anche {elenco_bonus}, che raccoglie bonus "
                        f"senza segnare"
                        if singolo
                        else f"Si fanno sentire anche {elenco_bonus}, che raccolgono "
                        f"bonus senza segnare",
                        f"Contributo pesante pure da {elenco_bonus}"
                        if singolo
                        else f"Contributi pesanti pure da {elenco_bonus}",
                    ),
                    seme,
                )
            )
        )

    for formazione in (casa, trasferta):
        cattivi = formazione.insufficienti
        if not cattivi:
            continue
        segna(*(g.nome for g in cattivi))
        elenco = _elenco([f"{g.nome} ({_n(g.voto)})" for g in cattivi])
        frasi.append(
            _frase(
                _variante(
                    (
                        f"A pesare in senso opposto è {elenco}",
                        f"Sul fronte opposto {formazione.squadra} paga {elenco}",
                    ),
                    seme,
                )
                if len(cattivi) == 1
                else f"{formazione.squadra} paga invece le insufficienze di {elenco}"
            )
        )

    for formazione in (casa, trasferta):
        if formazione.incompleta:
            frasi.append(
                f"Resta però un dato che spiega tutto il resto: {formazione.squadra} "
                f"è scesa in campo con {len(formazione.giocatori)} giocatori a "
                f"referto. I titolari senza voto non hanno trovato rimpiazzo in "
                f"panchina, e quei buchi pesano più di qualunque prestazione."
            )

    scarto = abs(casa.totale - trasferta.totale)
    if scarto == 0:
        frasi.append(
            "Due squadre separate da nulla, con lo stesso identico bottino: "
            "più equilibrio di così è difficile immaginarlo."
        )
    elif scarto <= 2:
        frasi.append(
            f"Alla fine è questione di {_n(scarto)} fantapunti: sarebbe bastato "
            f"un singolo voto diverso per ribaltare il verdetto."
        )

    if memoria:
        for formazione in (casa, trasferta):
            scheda = memoria.squadre.get(formazione.squadra)
            if not scheda:
                continue
            if scheda.striscia_sconfitte >= SOGLIA_STRISCIA:
                tipo, valore = "sconfitte", scheda.striscia_sconfitte
                frase = (
                    f"Per {formazione.squadra} è la "
                    f"{_ordinale(scheda.striscia_sconfitte)} sconfitta di fila, e la "
                    f"media stagionale scivola a "
                    f"{_n(round(scheda.media_fantapunti, 1))} fantapunti."
                )
            elif scheda.striscia_vittorie >= SOGLIA_STRISCIA:
                tipo, valore = "vittorie", scheda.striscia_vittorie
                frase = (
                    f"{formazione.squadra} sale invece alla "
                    f"{_ordinale(scheda.striscia_vittorie)} vittoria consecutiva, "
                    f"e comincia a fare paura."
                )
            elif scheda.digiuno_gol >= SOGLIA_DIGIUNO:
                tipo, valore = "digiuno", scheda.digiuno_gol
                frase = (
                    f"{formazione.squadra} non trova il gol ormai da "
                    f"{scheda.digiuno_gol} giornate."
                )
            else:
                continue
            frasi.append(frase)
            if richiami is not None:
                richiami.append(Richiamo("racconto", tipo, formazione.squadra, valore, "", frase))

    return " ".join(frasi)


def racconto(
    partite: list[Partita],
    memoria: Memoria | None = None,
    seme: int = 0,
    soggetti: set[str] | None = None,
    richiami: list[Richiamo] | None = None,
    apertura: Partita | None = None,
) -> list[str]:
    """Il pezzo di apertura: la partita del giorno per esteso.

    Passando `soggetti` si ottiene l'elenco di squadre e giocatori nominati,
    che il resto della pagina userà per non ripetersi. `apertura` impone la
    partita; senza, è quella con l'evento più rilevante del turno.
    """
    if not partite:
        return []
    # Una sola partita in apertura. Le altre hanno il loro trafiletto, così le
    # cinque gare sono coperte una volta sola ciascuna.
    gara = apertura if apertura is not None else partita_di_apertura(partite)
    return [_paragrafo(gara, memoria, seme, disteso=True, soggetti=soggetti, richiami=richiami)]


def partita_di_apertura(partite: list[Partita]) -> Partita | None:
    """La gara che finisce nel pezzo di apertura quando nessuno la sceglie."""
    if not partite:
        return None
    return max(partite, key=_interesse)


def partite_minori(partite: list[Partita], apertura: Partita | None = None) -> list[Partita]:
    """Tutte le altre, nell'ordine di calendario: una per trafiletto."""
    if apertura is None:
        apertura = partita_di_apertura(partite)
    return [p for p in partite if p is not apertura]


def trova_partita(partite: list[Partita], squadra: str) -> Partita | None:
    """La partita giocata da `squadra` in questa giornata, in casa o fuori.

    Negli scontri diretti ogni squadra gioca una partita sola per giornata, e
    il suo nome la identifica senza ambiguità: da riga di comando basta
    scrivere una delle due squadre, senza sapere chi giocava in casa. Maiuscole
    e spazi ai lati non contano.
    """
    cercata = squadra.strip().casefold()
    if not cercata:
        return None
    for partita in partite:
        if cercata in (partita.casa.squadra.strip().casefold(), partita.trasferta.squadra.strip().casefold()):
            return partita
    return None


# --- Il pezzo di raccordo ----------------------------------------------------
def _fantapunti_altrove(migliore: RigaClassifica, prima: RigaClassifica, seme: int) -> str:
    """La frase per chi produce più fantapunti senza essere primo.

    Le varianti cambiano le parole, non l'affermazione: il motivo per cui la
    squadra non è prima resta lo stesso in ognuna.
    """
    nome = migliore.squadra
    if migliore.punti == prima.punti:
        # È in vetta a pari punti: dietro la tiene solo la differenza reti.
        return _variante(
            (
                f"Il conto dei fantapunti premia però {nome}, che con "
                f"{_n(migliore.fantapunti)} ne ha prodotti più di tutti: a parità di "
                f"punti la tiene dietro soltanto la differenza reti.",
                f"La più prolifica è però {nome}, con {_fantapunti(migliore.fantapunti)}: "
                f"a parità di punti la tiene dietro soltanto la differenza reti.",
            ),
            seme,
        )
    return _variante(
        (
            f"Il conto dei fantapunti premia però {nome}, che con "
            f"{_n(migliore.fantapunti)} ne ha prodotti più di tutti senza trovarsi in "
            f"testa: segno di un rendimento sprecato negli incroci sbagliati.",
            f"Chi produce di più è però {nome}, con {_fantapunti(migliore.fantapunti)}, "
            f"senza trovarsi in testa: tanta sostanza raccolta male negli scontri diretti.",
        ),
        seme,
    )


def _vetta_appaiata(
    prima: RigaClassifica, seconda: RigaClassifica, migliore: RigaClassifica, seme: int
) -> list[str]:
    """Le prime due a pari punti, con il motivo vero del loro ordine."""
    punti = _punti(prima.punti)
    # Entrambe le formule finiscono sui punti, così i pezzi che seguono si
    # agganciano allo stesso modo, e nominano le squadre nello stesso ordine:
    # "la prima" e "quest'ultima" indicano sempre la squadra giusta.
    coppia = _variante(
        (
            f"In vetta {prima.squadra} e {seconda.squadra} viaggiano appaiate a {punti}",
            f"{prima.squadra} e {seconda.squadra} dividono la vetta a {punti}",
        ),
        seme,
    )
    decide_differenza = prima.differenza_reti != seconda.differenza_reti

    if migliore.squadra == seconda.squadra:
        # Possibile solo se decide la differenza reti: altrimenti i fantapunti
        # l'avrebbero messa davanti.
        return [
            _variante(
                (
                    f"{coppia}, e quest'ultima ha perfino prodotto più fantapunti di "
                    f"tutti, {_n(seconda.fantapunti)}: a tenerla dietro è soltanto la "
                    f"differenza reti.",
                    f"{coppia}, ma quest'ultima vanta il bottino di fantapunti più ricco, "
                    f"{_n(seconda.fantapunti)}: la tiene al secondo posto soltanto la "
                    f"differenza reti.",
                ),
                seme,
            )
        ]

    if migliore.squadra == prima.squadra:
        if decide_differenza:
            return [
                _variante(
                    (
                        f"{coppia}: la prima è davanti per differenza reti e ha anche il "
                        f"bottino di fantapunti più ricco, {_n(prima.fantapunti)}.",
                        f"{coppia}, ma la prima è davanti per differenza reti e vanta pure "
                        f"più fantapunti di tutti, {_n(prima.fantapunti)}.",
                    ),
                    seme,
                )
            ]
        if prima.fantapunti == seconda.fantapunti:
            return [
                _variante(
                    (
                        f"{coppia}, con la stessa differenza reti e gli stessi fantapunti: "
                        f"più appaiate di così non si può.",
                        f"{coppia}: stessa differenza reti, stessi fantapunti, nessun "
                        f"dettaglio le separa.",
                    ),
                    seme,
                )
            ]
        return [
            _variante(
                (
                    f"{coppia} e con la stessa differenza reti: a mettere davanti la prima "
                    f"sono i fantapunti, {_n(prima.fantapunti)}, i migliori della lega.",
                    f"{coppia}, a pari differenza reti: a mettere davanti la prima sono i "
                    f"fantapunti, {_n(prima.fantapunti)}.",
                ),
                seme,
            )
        ]

    separate = _variante(
        (
            f"{coppia}, separate "
            f"{'dalla differenza reti' if decide_differenza else 'dai fantapunti'}.",
            f"{coppia}, e a separarle "
            f"{'è la differenza reti' if decide_differenza else 'sono i fantapunti'}.",
        ),
        seme,
    )
    return [separate, _fantapunti_altrove(migliore, prima, seme)]


def dietro_i_numeri(
    tabella: list[RigaClassifica],
    memoria: Memoria | None = None,
    seme: int = 0,
    richiami: list[Richiamo] | None = None,
) -> tuple[str, str]:
    """Trafiletto lungo sulla classifica, non sulle partite.

    Con una gara in apertura e le altre nei trafiletti brevi, tutte sono già
    raccontate: una rassegna delle partite qui ripeterebbe soltanto. Questo
    spazio guarda invece la classifica, l'unica cosa che i pezzi sui singoli
    match non dicono. Il nome della rubrica resta fisso, come nei giornali
    veri; il seme cambia soltanto le parole del pezzo.
    """
    if not tabella:
        return ("DIETRO I NUMERI", "Classifica non ancora disponibile.")

    frasi: list[str] = []
    prima = tabella[0]
    ultima = tabella[-1]
    migliore_fantapunti = max(tabella, key=lambda r: r.fantapunti)
    punti_prima = _punti(prima.punti)

    if len(tabella) == 1:
        frasi.append(
            _variante(
                (
                    f"{prima.squadra} guida la classifica con {punti_prima}.",
                    f"{prima.squadra} è in testa alla classifica con {punti_prima}.",
                ),
                seme,
            )
        )
    else:
        seconda = tabella[1]
        distacco = prima.punti - seconda.punti

        if distacco == 0:
            # A pari punti l'ordine lo decide la differenza reti, e solo dopo i
            # fantapunti. Sbagliare il motivo significa scrivere il falso sulla
            # vetta: "separate dai fantapunti" quando è prima chi ne ha meno.
            frasi.extend(_vetta_appaiata(prima, seconda, migliore_fantapunti, seme))
        elif migliore_fantapunti.squadra == seconda.squadra:
            # Chi produce di più è proprio l'inseguitrice: due frasi separate la
            # nominerebbero una dietro l'altra, quindi il dato entra nella prima.
            if distacco == 1:
                frasi.append(
                    _variante(
                        (
                            f"{prima.squadra} guida con {punti_prima}, ma {seconda.squadra} "
                            f"è a un solo punto e ha prodotto più fantapunti di tutti, "
                            f"{_n(seconda.fantapunti)}: nulla è deciso.",
                            f"{prima.squadra} è in testa con {punti_prima}, ma "
                            f"{seconda.squadra} è a un solo punto e ha prodotto più "
                            f"fantapunti di tutti, {_n(seconda.fantapunti)}: la corsa è "
                            f"apertissima.",
                        ),
                        seme,
                    )
                )
            else:
                frasi.append(
                    _variante(
                        (
                            f"{prima.squadra} comanda con {punti_prima}, {distacco} in più "
                            f"di {seconda.squadra}, che pure ha prodotto più fantapunti di "
                            f"tutti, {_n(seconda.fantapunti)}: un rendimento che non si è "
                            f"ancora trasformato in punti.",
                            f"{prima.squadra} è in testa con {punti_prima} e {distacco} di "
                            f"vantaggio su {seconda.squadra}, che pure ha prodotto più "
                            f"fantapunti di tutti, {_n(seconda.fantapunti)}: sostanza che "
                            f"non si è ancora tradotta in classifica.",
                        ),
                        seme,
                    )
                )
        else:
            if distacco == 1:
                frasi.append(
                    _variante(
                        (
                            f"{prima.squadra} guida con {punti_prima}, ma {seconda.squadra} "
                            f"è a un solo punto: nulla è deciso.",
                            f"{prima.squadra} è in testa con {punti_prima}, ma "
                            f"{seconda.squadra} insegue a un solo punto.",
                        ),
                        seme,
                    )
                )
            else:
                frasi.append(
                    _variante(
                        (
                            f"{prima.squadra} comanda con {punti_prima}, {distacco} in più "
                            f"di {seconda.squadra}.",
                            f"{prima.squadra} è in testa con {punti_prima} e {distacco} di "
                            f"vantaggio su {seconda.squadra}.",
                        ),
                        seme,
                    )
                )
            if migliore_fantapunti.squadra == prima.squadra:
                # "È anche la squadra che..." sarebbe ambiguo: l'ultima nominata è
                # la seconda. "La capolista" non lascia dubbi e non ripete il nome.
                frasi.append(
                    _variante(
                        (
                            f"Primato pieno, del resto: nessuno ha prodotto più fantapunti "
                            f"della capolista, {_n(prima.fantapunti)}.",
                            f"E la capolista è anche la più prolifica del gruppo, con "
                            f"{_fantapunti(prima.fantapunti)}.",
                        ),
                        seme,
                    )
                )
            else:
                frasi.append(_fantapunti_altrove(migliore_fantapunti, prima, seme))

    # Da qui in poi si tiene il conto di chi è già stato nominato: ripetere la
    # stessa squadra a due righe di distanza fa sembrare il pezzo scritto male.
    citate = {prima.squadra, migliore_fantapunti.squadra}
    if len(tabella) > 1:
        citate.add(tabella[1].squadra)

    # La zona bassa.
    if len(tabella) > 2 and ultima.squadra not in citate:
        penultima = tabella[-2]
        punti_ultima = _punti(ultima.punti)
        if ultima.punti == penultima.punti and penultima.squadra not in citate:
            frasi.append(
                _variante(
                    (
                        f"In fondo {ultima.squadra} e {penultima.squadra} condividono lo "
                        f"stesso bottino, {punti_ultima}.",
                        f"In coda {ultima.squadra} e {penultima.squadra} restano appaiate "
                        f"a {punti_ultima}.",
                    ),
                    seme,
                )
            )
            citate.update({ultima.squadra, penultima.squadra})
        else:
            raccolti = _fantapunti(ultima.fantapunti)
            frasi.append(
                _variante(
                    (
                        f"Chiude {ultima.squadra}, ferma a {punti_ultima} e con {raccolti} "
                        f"raccolti.",
                        f"Fanalino di coda è {ultima.squadra}: {punti_ultima} e {raccolti}.",
                        f"In fondo alla classifica resta {ultima.squadra}, con "
                        f"{punti_ultima} e {raccolti}.",
                    ),
                    seme,
                )
            )
            citate.add(ultima.squadra)

    if memoria and memoria.abbastanza_storia:
        candidati = [
            (
                s,
                "vittorie",
                s.striscia_vittorie,
                (
                    f"Il momento migliore è di {s.nome}, che arriva da "
                    f"{s.striscia_vittorie} vittorie di fila.",
                    f"In gran forma {s.nome}: {s.striscia_vittorie} vittorie consecutive.",
                ),
            )
            for s in memoria.in_serie_positiva()
        ] + [
            (
                s,
                "sconfitte",
                s.striscia_sconfitte,
                (
                    f"Il momento peggiore è di {s.nome}, che arriva da "
                    f"{s.striscia_sconfitte} sconfitte consecutive.",
                    f"Periodo nero per {s.nome}: {s.striscia_sconfitte} sconfitte di fila.",
                ),
            )
            for s in memoria.in_crisi()
        ]
        for scheda, tipo, valore, formule in candidati:
            if scheda.nome in citate:
                continue
            frase = _variante(formule, seme)
            frasi.append(frase)
            if richiami is not None:
                richiami.append(Richiamo("dietro_i_numeri", tipo, scheda.nome, valore, "", frase))
            break

    return ("DIETRO I NUMERI", " ".join(frasi))


# --- I trafiletti brevi ------------------------------------------------------
# Una partita per trafiletto, e soprattutto un *angolo* diverso per ciascuno.
# Due pezzi che dicono "tot fantapunti, trascinata da Tizio" cambiando solo i
# nomi si leggono come lo stesso pezzo stampato due volte: la varietà non sta
# nei soggetti ma nel motivo per cui quella partita è una notizia.
#
# Ogni partita propone i suoi angoli in ordine di forza; l'assegnazione è
# golosa e scarta gli angoli già usati, così quattro trafiletti raccontano
# quattro cose diverse.

# (chiave angolo, titoletto, testo)
Angolo = tuple[str, str, str]


def _esiti(memoria: Memoria | None, squadra: str) -> str:
    if not memoria:
        return ""
    scheda = memoria.squadre.get(squadra)
    return "".join(scheda.esiti) if scheda else ""


_CHIUSURE_GARANTITE = (
    ("CRONACA IN BREVE", "{a} e {b} scendono in campo: finisce {r}"),
    ("IL VERDETTO", "Fra {a} e {b} il verdetto è {r}, e dice quasi tutto"),
    ("FISCHIO FINALE", "Il confronto fra {a} e {b} si chiude {sul_r}"),
    ("IL TABELLINO", "{a} contro {b}: il tabellino recita {r}"),
    ("ULTIME DAL CAMPO", "Si chiude {r} la sfida fra {a} e {b}"),
)


def _angolo_garantito(partita: Partita, indice: int, seme: int = 0) -> Angolo:
    """Un angolo che non può mai essere occupato da un'altra partita.

    La chiave contiene l'indice della gara, quindi è unica per definizione: è
    la garanzia che ogni partita ottenga il suo trafiletto. Le formule ruotano
    tutte insieme col seme, ma restano sfalsate dall'indice: due gare che
    finiscono qui non escono mai con lo stesso titolo né con lo stesso testo.
    """
    rotazione = _scelta(seme, "garantito", len(_CHIUSURE_GARANTITE))
    titoletto, formula = _CHIUSURE_GARANTITE[(indice + rotazione) % len(_CHIUSURE_GARANTITE)]
    return (
        f"garantito_{indice}",
        titoletto,
        formula.format(
            a=partita.casa.squadra,
            b=partita.trasferta.squadra,
            r=partita.risultato,
            sul_r=_col_articolo(partita.risultato, "su"),
        ),
    )


def _angoli_partita(
    partita: Partita,
    memoria: Memoria | None,
    posizioni: dict[str, int],
    indice: int,
    seme: int = 0,
    vetta_condivisa: bool = False,
    fonti: dict[str, tuple[str, str, int]] | None = None,
) -> list[Angolo]:
    """Tutti i modi in cui questa partita può diventare una notizia.

    L'elenco degli angoli, e il loro ordine di forza, dipende solo dai fatti.
    Il seme sceglie soltanto con quali parole raccontare ciascun angolo: con
    semi diversi un trafiletto parla della stessa cosa, detta in un altro modo.

    `fonti`, se passato, raccoglie per ogni angolo nato dalle giornate passate
    il dato che lo giustifica: (tipo, squadra, valore).
    """
    casa, trasferta = partita.casa, partita.trasferta
    risultato = partita.risultato
    scarto = abs(casa.totale - trasferta.totale)
    angoli: list[Angolo] = []

    def aggiungi(
        chiave: str, *varianti: tuple[str, str], fonte: tuple[str, str, int] | None = None
    ) -> None:
        angoli.append((chiave, *_formule(seme, *varianti)))
        if fonte is not None and fonti is not None:
            fonti[chiave] = fonte

    # --- Pareggi ------------------------------------------------------------
    # I pareggi hanno bisogno di tanti angoli quanto le gare decise: in una
    # giornata con due pari, se ne esistesse uno solo, la seconda partita
    # resterebbe senza trafiletto.
    if partita.gol_casa == partita.gol_trasferta:
        c, t = casa.squadra, trasferta.squadra
        cu, tu = c.upper(), t.upper()
        reti = partita.gol_casa + partita.gol_trasferta

        if reti >= 4:
            aggiungi(
                "pari_spettacolo",
                (f"{cu} E {tu}, CHE SPETTACOLO",
                 f"{_maiuscola(_un_risultato(risultato))} pieno di gol che non accontenta "
                 f"nessuna delle due"),
                (f"GOL A RAFFICA FRA {cu} E {tu}",
                 f"Finisce {risultato}, e alla fine non vince nessuno"),
                (f"{cu} E {tu} NON SI RISPARMIANO",
                 f"{_maiuscola(_col_articolo(risultato))} finale è una festa del gol senza "
                 f"vincitori"),
            )
        if reti == 0:
            aggiungi(
                "pari_bloccato",
                (f"NIENTE DA FARE FRA {cu} E {tu}",
                 "Uno 0-0 senza emozioni, deciso dai voti e da nessun episodio"),
                (f"{cu} E {tu} SI ANNULLANO", "Nessun gol e tanta attesa: finisce 0-0"),
                (f"ZERO A ZERO FRA {cu} E {tu}",
                 "Né da una parte né dall'altra si trova la via della rete"),
            )

        # Un pari pesa in modo diverso a seconda di dove sei in classifica.
        for alta, altra in ((c, t), (t, c)):
            if 0 < posizioni.get(alta, 0) <= 3:
                aggiungi(
                    "pari_frenata",
                    (f"{alta.upper()} FRENA",
                     f"{_maiuscola(_col_articolo(risultato))} con {altra} costa due punti "
                     f"a chi puntava in alto"),
                    (f"{alta.upper()} RALLENTA",
                     f"Contro {altra} arriva un pareggio che fa comodo a chi insegue"),
                    (f"MEZZO PASSO FALSO PER {alta.upper()}",
                     f"Con {altra} finisce {risultato}, e le inseguitrici si avvicinano"),
                )
                break

        for squadra, altra in ((c, t), (t, c)):
            esiti = _esiti(memoria, squadra)
            if esiti.count("N") != 1:
                continue
            if len(esiti) == 1:
                # All'esordio non c'è nessuna "serie" da interrompere, e nessuna
                # giornata passata da cui trarre la notizia: niente fonte.
                aggiungi(
                    "pari_primo",
                    (f"{squadra.upper()} PARTE CON UN PARI",
                     f"All'esordio con {altra} finisce {risultato}"),
                    (f"PRIMO PUNTO PER {squadra.upper()}",
                     f"Il campionato si apre con un pareggio contro {altra}"),
                )
            else:
                aggiungi(
                    "pari_primo",
                    (f"PRIMO PARI PER {squadra.upper()}",
                     f"{_maiuscola(_col_articolo(risultato))} con {altra} interrompe una "
                     f"serie fatta solo di vittorie e sconfitte"),
                    (f"{squadra.upper()} SCOPRE IL PAREGGIO",
                     f"Contro {altra} arriva il primo segno X della stagione"),
                    (f"{squadra.upper()} SI DIVIDE LA POSTA",
                     f"Con {altra} finisce {risultato}: è il primo pareggio stagionale"),
                    fonte=("primo_pareggio", squadra, 1),
                )
            break

        aggiungi(
            "pari",
            (f"{cu} E {tu} PARI",
             f"Finisce {risultato}: un punto a testa e poco altro da salvare"),
            (f"UN PUNTO A TESTA FRA {cu} E {tu}",
             f"{_maiuscola(_col_articolo(risultato))} non scontenta nessuno ma non "
             f"accontenta neppure"),
        )
        aggiungi(
            "pari_diviso",
            (f"POSTA DIVISA FRA {cu} E {tu}",
             f"{_maiuscola(_col_articolo(risultato))} finale muove poco la classifica di "
             f"entrambe"),
            (f"{cu} E {tu} SI ACCONTENTANO",
             "Un pareggio che dà un punto per parte e rinvia i verdetti"),
        )
        aggiungi(
            "pari_rimpianto",
            (f"{cu} SI MORDE LE MANI",
             f"Davanti al proprio pubblico non basta {_col_articolo(risultato)} contro {t}"),
            (f"{cu}, CHE RIMPIANTO", f"In casa contro {t} arriva solo un pareggio"),
        )
        aggiungi(
            "pari_punto",
            (f"UN PUNTO PER {tu}",
             f"Dal campo di {c} arriva {_un_risultato(risultato)} che vale poco ma non è "
             f"nulla"),
            (f"{tu} MUOVE LA CLASSIFICA", f"Sul campo di {c} strappa un pareggio"),
        )
        angoli.append(_angolo_garantito(partita, indice, seme))
        return angoli

    vincente = casa if partita.gol_casa > partita.gol_trasferta else trasferta
    perdente = trasferta if vincente is casa else casa
    v, p = vincente.squadra, perdente.squadra
    vu, pu = v.upper(), p.upper()
    gol_perdente = min(partita.gol_casa, partita.gol_trasferta)
    esiti_v = _esiti(memoria, v)
    esiti_p = _esiti(memoria, p)
    posto_v = posizioni.get(v, 0)
    posto_p = posizioni.get(p, 0)

    # --- Formazione incompleta: resta l'anomalia più forte -------------------
    for formazione, avversaria in ((vincente, perdente), (perdente, vincente)):
        if not formazione.incompleta:
            continue
        numero = len(formazione.giocatori)
        nome, altra = formazione.squadra, avversaria.squadra
        aggiungi(
            f"incompleta_{nome}",
            (f"{nome.upper()} IN {LETTERE.get(numero, str(numero))}",
             f"Appena {numero} giocatori a referto contro {altra}: titolari senza voto e "
             f"panchina esaurita"),
            (f"{nome.upper()}, MANCA QUALCUNO",
             f"Contro {altra} scende in campo con soli {numero} giocatori a referto"),
            (f"BUCHI IN FORMAZIONE PER {nome.upper()}",
             f"Nella sfida con {altra} i titolari senza voto restano senza sostituti"),
        )

    # --- Classifica ---------------------------------------------------------
    if posto_v == 1 and vetta_condivisa:
        # Prima, ma a pari punti: "la vetta è sua" contraddirebbe il pezzo sulla
        # classifica, che nella stessa pagina dice che la vetta è divisa.
        aggiungi(
            "vetta",
            (f"{vu} IN VETTA", f"Il successo su {p} vale il primo posto, ma in coabitazione"),
            (f"{vu} DIVIDE LA VETTA",
             f"Dopo il successo contro {p} è prima, a pari punti con un'altra squadra"),
            (f"PRIMO POSTO PER {vu}", f"Battuta {p}, guida la classifica, ma non da sola"),
        )
    elif posto_v == 1:
        aggiungi(
            "vetta",
            (f"{vu} IN VETTA", f"Il successo su {p} vale la testa della classifica"),
            (f"{vu} COMANDA", f"Battuta {p}, è prima in classifica"),
            (f"{vu} GUARDA TUTTI DALL'ALTO", f"Dopo il successo contro {p} la vetta è sua"),
        )
    elif 0 < posto_v <= 3:
        posto_maschile = {2: "secondo", 3: "terzo"}[posto_v]
        aggiungi(
            "aggancio",
            (f"{vu} SI AVVICINA",
             f"Battuta {p}, ora è {_ordinale(posto_v)} e la vetta non è lontana"),
            (f"{vu} RESTA IN SCIA",
             f"Il successo su {p} vale il {posto_maschile} posto, a ridosso della vetta"),
            (f"{vu} ALZA LA VOCE",
             f"Tre punti contro {p} e la testa della classifica è a un passo"),
        )
    if posto_p and posizioni and posto_p >= len(posizioni) - 1:
        aggiungi(
            "fondo",
            (f"{pu} SEMPRE PIÙ GIÙ", f"Il ko con {v} la inchioda in fondo alla classifica"),
            (f"NOTTE FONDA PER {pu}",
             f"La sconfitta contro {v} la lascia nei bassifondi della classifica"),
            (f"{pu} NON TROVA LA RISALITA",
             f"Contro {v} arriva uno stop che la tiene nella zona più bassa"),
        )

    # --- Primati stagionali -------------------------------------------------
    if esiti_v.count("V") == 1:
        if len(esiti_v) == 1:
            aggiungi(
                "prima_vittoria",
                (f"{vu} PARTE COL PIEDE GIUSTO", f"Esordio vincente contro {p}"),
                (f"BUONA LA PRIMA PER {vu}", f"Il campionato si apre con un successo su {p}"),
                (f"{vu} C'È", f"Prima uscita e prima vittoria, contro {p}"),
            )
        else:
            aggiungi(
                "prima_vittoria",
                (f"{vu} C'È", f"Prima vittoria stagionale, a spese di {p}"),
                (f"PRIMA GIOIA PER {vu}", f"Il primo successo della stagione arriva contro {p}"),
                (f"{vu} SI SBLOCCA", f"Contro {p} arriva la prima vittoria della stagione"),
                fonte=("prima_vittoria", v, 1),
            )
    if esiti_p.count("P") == 1:
        if len(esiti_p) == 1:
            aggiungi(
                "prima_sconfitta",
                (f"FALSA PARTENZA PER {pu}", f"Esordio amaro contro {v}"),
                (f"{pu} PARTE IN SALITA",
                 f"La prima uscita si chiude con una sconfitta contro {v}"),
                (f"{pu} SI ARRENDE", f"All'esordio a fermarla è {v}"),
            )
        else:
            aggiungi(
                "prima_sconfitta",
                (f"{pu} SI ARRENDE", f"Prima sconfitta stagionale: a fermarla è {v}"),
                (f"CADE L'IMBATTIBILITÀ DI {pu}",
                 f"La prima sconfitta della stagione porta la firma di {v}"),
                (f"{pu} SCOPRE LA SCONFITTA", f"Il primo stop della stagione arriva contro {v}"),
                fonte=("prima_sconfitta", p, 1),
            )

    # --- Strisce ------------------------------------------------------------
    striscia_v = len(esiti_v) - len(esiti_v.rstrip("V"))
    striscia_p = len(esiti_p) - len(esiti_p.rstrip("P"))
    if striscia_v >= SOGLIA_STRISCIA:
        ordinale = _ordinale(striscia_v)
        aggiungi(
            "striscia",
            (f"{vu} NON SI FERMA",
             f"{ordinale.capitalize()} vittoria di fila, stavolta contro {p}"),
            (f"{vu} IN SERIE", f"Anche {p} cade: è la {ordinale} vittoria consecutiva"),
            (f"{vu} INGRANA", f"Il successo su {p} allunga la serie: {ordinale} vittoria di fila"),
            fonte=("vittorie", v, striscia_v),
        )
    if striscia_p >= SOGLIA_STRISCIA:
        ordinale = _ordinale(striscia_p)
        aggiungi(
            "crisi",
            (f"{pu} NON SI RIALZA",
             f"{ordinale.capitalize()} sconfitta consecutiva, stavolta contro {v}"),
            (f"{pu}, ANCORA UN KO", f"Anche {v} passa: è la {ordinale} sconfitta di fila"),
            (f"BUIO PESTO PER {pu}", f"Contro {v} arriva la {ordinale} sconfitta consecutiva"),
            fonte=("sconfitte", p, striscia_p),
        )

    # --- Il campo -----------------------------------------------------------
    if gol_perdente == 0:
        aggiungi(
            "dominio",
            (f"{vu}, GARA PERFETTA",
             f"Un secco {risultato} contro {p}, senza mai concedere nulla"),
            (f"{vu} NON CONCEDE NULLA",
             f"Contro {p} finisce {risultato}, e dietro non si rischia mai"),
            (f"PORTA INVIOLATA PER {vu}",
             f"{_maiuscola(_col_articolo(risultato))} su {p} arriva senza subire gol"),
        )

    multipli = [g for g in vincente.marcatori if g.gol >= 2]
    if multipli:
        marcatore = max(multipli, key=lambda g: g.gol)
        etichetta = "tripletta" if marcatore.gol >= 3 else "doppietta"
        nome = marcatore.nome.upper()
        aggiungi(
            "bomber",
            (f"LA {etichetta.upper()} DI {nome}",
             f"Da solo piega {p} e trascina {v} al successo"),
            (f"{nome} SI PRENDE LA SCENA",
             f"Con una {etichetta} decide la sfida fra {v} e {p}"),
            (f"{nome} SPACCA LA PARTITA",
             f"La sua {etichetta} vale il successo di {v} contro {p}"),
        )

    margine = _fantapunti(scarto)
    if scarto <= 3:
        aggiungi(
            "misura",
            (f"{vu} DI MISURA", f"Contro {p} il margine è di appena {margine}"),
            (f"{vu} LA SPUNTA SUL FILO", f"Su {p} vince con uno scarto di {margine}"),
            (f"VITTORIA SOFFERTA PER {vu}", f"Solo {margine} di margine nella sfida con {p}"),
        )
    elif scarto >= 15:
        aggiungi(
            "divario",
            (f"{pu} TRAVOLTA", f"Contro {v} finisce con {margine} di distacco"),
            (f"{vu} SENZA PIETÀ", f"{p} ne esce con {margine} di distacco"),
            (f"UN ABISSO FRA {vu} E {pu}", f"Il divario finale è di {margine}"),
        )

    firme = [g.nome for g in vincente.marcatori[:2]]
    if firme:
        elenco = _elenco(firme)
        plurale = len(firme) > 1
        aggiungi(
            "firme",
            (f"{vu} PASSA",
             f"{elenco} {'stendono' if plurale else 'stende'} {p} per {risultato}"),
            (f"{vu} COLPISCE",
             f"Contro {p} {'le firme sono' if plurale else 'la firma è'} di {elenco}"),
            (f"{vu} VINCE",
             f"Contro {p} {'vanno' if plurale else 'va'} a segno {elenco}"),
        )

    # Ultima rete. Più di un ripiego, e ciascuno formulato in modo diverso: se
    # due partite finissero entrambe qui con la stessa frase, si leggerebbero
    # come lo stesso trafiletto stampato due volte.
    aggiungi(
        "chiusura_punteggio",
        (f"{vu} BATTE {pu}",
         f"Finisce {risultato}, con {_n(vincente.totale)} fantapunti contro "
         f"{_n(perdente.totale)}"),
        (f"{vu} SUPERA {pu}",
         f"Il tabellino dice {risultato}: {_n(vincente.totale)} fantapunti a "
         f"{_n(perdente.totale)}"),
    )
    aggiungi(
        "chiusura_tre_punti",
        (f"TRE PUNTI PER {vu}",
         f"{p} esce a mani vuote dal confronto, deciso {_col_articolo(risultato, 'su')}"),
        (f"{vu} INCASSA I TRE PUNTI",
         f"{p} resta a mani vuote dopo {_col_articolo(risultato)} finale"),
    )
    aggiungi(
        "chiusura_muro",
        (f"{vu} REGGE",
         f"{_maiuscola(_col_articolo(risultato))} su {p} vale un passo avanti in classifica"),
        (f"{vu} TIENE BOTTA",
         f"Contro {p} arriva {_un_risultato(risultato)} che muove la classifica"),
    )
    aggiungi(
        "chiusura_occasione",
        (f"{pu} SI FERMA", f"Occasione mancata: passa {v} col punteggio di {risultato}"),
        (f"PASSO FALSO PER {pu}", f"Contro {v} finisce {risultato}, e l'occasione sfuma"),
    )
    aggiungi(
        "chiusura_equilibrio",
        (f"{vu}, LA SPUNTA",
         f"Serve tutto {_col_articolo(risultato)} per avere ragione di {p}"),
        (f"{vu} LA PORTA A CASA", f"Contro {p} basta {_col_articolo(risultato)}"),
    )
    angoli.append(_angolo_garantito(partita, indice, seme))
    return angoli


def trafiletti(
    partite: list[Partita],
    memoria: Memoria | None = None,
    posizioni: dict[str, int] | None = None,
    seme: int = 0,
    vetta_condivisa: bool = False,
    richiami: list[Richiamo] | None = None,
) -> list[tuple[str, str]]:
    """Un trafiletto per partita, ciascuno su un angolo diverso.

    L'assegnazione è golosa: le partite con meno alternative scelgono per
    prime, così non restano senza angolo libero. Gli angoli assegnati non
    dipendono dal seme; le parole con cui vengono raccontati sì.
    """
    posizioni = posizioni or {}
    proposte = []
    for indice, partita in enumerate(partite):
        fonti: dict[str, tuple[str, str, int]] = {}
        angoli = _angoli_partita(
            partita, memoria, posizioni, indice, seme, vetta_condivisa, fonti=fonti
        )
        proposte.append((partita, angoli, fonti))
    # Chi ha meno modi di essere raccontato va servito prima.
    proposte.sort(key=lambda voce: len(voce[1]))

    usati: set[str] = set()
    per_partita: dict[int, tuple[str, str]] = {}
    tracce: dict[int, Richiamo] = {}

    for partita, angoli, fonti in proposte:
        for chiave, titoletto, testo in angoli:
            if chiave in usati:
                continue
            usati.add(chiave)
            per_partita[id(partita)] = (titoletto, _frase(testo))
            if chiave in fonti:
                tipo, squadra, valore = fonti[chiave]
                tracce[id(partita)] = Richiamo(
                    "trafiletti", tipo, squadra, valore, titoletto, _frase(testo)
                )
            break

    # Si restituisce nell'ordine originale delle partite, non in quello di scelta.
    if richiami is not None:
        richiami.extend(tracce[id(p)] for p in partite if id(p) in tracce)
    return [per_partita[id(p)] for p in partite if id(p) in per_partita]


# --- La pagina come dati -----------------------------------------------------
@dataclass
class VoceClassifica:
    posizione: int
    squadra: str
    punti: int
    fantapunti: float


@dataclass
class VocePartita:
    """Una partita della giornata, per chi deve sceglierne una da mettere in apertura."""

    casa: str
    trasferta: str
    risultato: str


@dataclass
class PrimaPagina:
    """La prima pagina come dati, prima di diventare testo.

    Il prompt è solo una delle sue rappresentazioni. L'interfaccia web ne usa i
    campi per mostrare un'anteprima leggibile, e nessuno deve ripescare il
    titolo o i trafiletti dentro una stringa di sessanta righe.
    """

    testata: str
    stagione: str
    giornata: int
    data: str
    seme: int
    titolo: str
    sottotitolo: str
    apertura: str
    racconto: list[str]
    risultati: list[str]
    classifica: list[VoceClassifica]
    pezzo_lungo: tuple[str, str]
    trafiletti: list[tuple[str, str]]
    # I punti che la pagina deve alla memoria, nell'ordine in cui si leggono.
    # Il prompt non li usa: servono a chi vuole verificare che la storia pesi.
    richiami: list[Richiamo] = field(default_factory=list)
    # Le partite della giornata, per poterne scegliere una da mettere in
    # apertura, e la squadra di casa di quella scelta ("" se l'ha decisa la
    # pagina). Nemmeno questi finiscono nel prompt.
    partite: list[VocePartita] = field(default_factory=list)
    apertura_scelta: str = ""
    # Chi ha scritto i testi: il redattore classico, o un modello ("ai") di cui
    # `autore` dice il nome. Risultati e classifica vengono sempre dai dati.
    scrittura: str = "classica"
    autore: str = ""


def righe_risultati(partite: list[Partita]) -> list[str]:
    """I risultati come si leggono nel riquadro: "Casa 2-1 Trasferta"."""
    return [f"{p.casa.squadra} {p.risultato} {p.trasferta.squadra}" for p in partite]


def voci_classifica(tabella: list[RigaClassifica]) -> list[VoceClassifica]:
    return [
        VoceClassifica(posizione=indice, squadra=r.squadra, punti=r.punti, fantapunti=r.fantapunti)
        for indice, r in enumerate(tabella, 1)
    ]


def voci_partite(partite: list[Partita]) -> list[VocePartita]:
    return [
        VocePartita(casa=p.casa.squadra, trasferta=p.trasferta.squadra, risultato=p.risultato)
        for p in partite
    ]


def etichetta_apertura(gara: Partita | None) -> str:
    return f"{gara.casa.squadra} {gara.risultato} {gara.trasferta.squadra}" if gara else ""


_NUMERI = {
    1: "UNA",
    2: "DUE",
    3: "TRE",
    4: "QUATTRO",
    5: "CINQUE",
    6: "SEI",
    7: "SETTE",
    8: "OTTO",
    9: "NOVE",
    10: "DIECI",
}


def componi(
    partite: list[Partita],
    tabella: list[RigaClassifica],
    giornata: int,
    stagione: str,
    data: str,
    testata: str,
    memoria: Memoria | None = None,
    seme: int | None = None,
    apertura: Partita | None = None,
) -> PrimaPagina:
    """Decide il contenuto della pagina.

    Impianto: una partita in apertura, le altre una per trafiletto. Così ogni
    gara è coperta una volta sola, e nessuna squadra viene raccontata due volte
    con parole diverse.

    `apertura` mette in prima pagina una partita scelta da chi usa l'app: la
    racconta il pezzo d'apertura e ne parla il titolo. Senza, la pagina sceglie
    da sola - la partita più ricca di eventi per il racconto, il fatto più
    rilevante della giornata per il titolo - come ha sempre fatto.

    `seme` decide quali formule vengono scelte. Per difetto è il numero di
    giornata: la stessa giornata rigenera sempre la stessa pagina, che rende il
    risultato riproducibile e verificabile. Un seme diverso racconta le stesse
    notizie con altre parole.
    """
    if seme is None:
        seme = giornata
    if apertura is not None and not any(p is apertura for p in partite):
        raise ValueError("La partita in apertura non è fra quelle della giornata.")
    # Ogni sezione annota qui ciò che deve alla memoria. Le sezioni si compongono
    # nell'ordine di lettura, così i richiami seguono la pagina.
    richiami: list[Richiamo] = []
    if apertura is not None:
        principale, sottotitolo = _titolo_partita(apertura, memoria, seme, richiami)
    else:
        principale, sottotitolo, _ = _titolo_completo(partite, memoria, seme, richiami)
    posizioni = {riga.squadra: indice for indice, riga in enumerate(tabella, 1)}
    gara_apertura = apertura if apertura is not None else partita_di_apertura(partite)
    paragrafi = racconto(partite, memoria, seme, richiami=richiami, apertura=gara_apertura)
    pezzo_lungo = dietro_i_numeri(tabella, memoria, seme, richiami=richiami)
    brevi = trafiletti(
        partite_minori(partite, gara_apertura),
        memoria,
        posizioni,
        seme,
        # Il pezzo sulla classifica racconta la vetta condivisa: i trafiletti
        # devono saperlo per non dire il contrario nella stessa pagina.
        vetta_condivisa=len(tabella) > 1 and tabella[0].punti == tabella[1].punti,
        richiami=richiami,
    )

    return PrimaPagina(
        testata=testata,
        stagione=stagione,
        giornata=giornata,
        data=data,
        seme=seme,
        titolo=principale,
        sottotitolo=sottotitolo,
        apertura=etichetta_apertura(gara_apertura),
        racconto=paragrafi,
        risultati=righe_risultati(partite),
        classifica=voci_classifica(tabella),
        pezzo_lungo=pezzo_lungo,
        trafiletti=brevi,
        richiami=richiami,
        partite=voci_partite(partite),
        apertura_scelta=apertura.casa.squadra if apertura is not None else "",
    )


def renderizza(pagina: PrimaPagina) -> str:
    """Trasforma la pagina nel prompt per il modello testo-immagine."""
    paragrafi = "\n\n".join(f'"{t}"' for t in pagina.racconto)
    righe_risultati = "\n".join(f'"{r}"' for r in pagina.risultati)
    righe_classifica = "\n".join(
        f'"{v.posizione} {v.squadra} {v.punti} {_n(v.fantapunti)}"' for v in pagina.classifica
    )
    titolo_lungo, testo_lungo = pagina.pezzo_lungo
    blocchi = "\n".join(
        f'{i}. "{t}" - "{c}"' for i, (t, c) in enumerate(pagina.trafiletti, 1)
    )
    # Il numero di partite cambia con la lega: otto squadre fanno quattro gare,
    # dieci ne fanno cinque. Le etichette seguono i dati, non un valore cablato.
    parola = _NUMERI.get(len(pagina.trafiletti), str(len(pagina.trafiletti)))
    righe_gare = _NUMERI.get(len(pagina.risultati), str(len(pagina.risultati))).lower()

    return f"""\
Fotografia realistica della prima pagina di un quotidiano sportivo italiano,
appoggiato su un tavolo di legno chiaro, luce naturale morbida da una finestra
laterale, grana della carta di giornale ben visibile, bordi appena increspati,
ombra naturale leggera. Inquadratura dall'alto, frontale, pagina intera
perfettamente leggibile. Carta di colore rosa salmone, come i quotidiani
sportivi italiani, inchiostro nero e titoli in rosso.

TESTATA in alto, grande, carattere graziato condensato nero:
"{pagina.testata}"
Sottotestata sottile: "Fanta Campionato {pagina.stagione} — Giornata {pagina.giornata} — {pagina.data}"

TITOLO PRINCIPALE a tutta pagina, enorme, nero:
"{pagina.titolo}"
Sottotitolo su una riga: "{pagina.sottotitolo}"

FOTO CENTRALE: immagine calcistica in bianco e nero, un giocatore che esulta
correndo verso la curva, taglio drammatico, larga, collocata sotto il titolo.

ARTICOLO DI APERTURA sotto la foto, su tre colonne giustificate, con
occhiello rosso "IL RACCONTO" e testo in corpo piccolo ma leggibile:

{paragrafi}

RIQUADRO A SINISTRA, intestazione rossa "I RISULTATI", elenco su {righe_gare} righe:
{righe_risultati}

RIQUADRO A DESTRA, intestazione rossa "LA CLASSIFICA", tabella a tre colonne
(squadra, punti, fantapunti):
{righe_classifica}

TRAFILETTO LUNGO in fondo alla pagina, su due colonne, subito sopra i
trafiletti brevi, con titoletto in grassetto:
"{titolo_lungo}"
"{testo_lungo}"

{parola} TRAFILETTI BREVI in fondo alla pagina, affiancati, ciascuno con
titoletto in grassetto e una o due righe di testo:
{blocchi}

Stile grafico: impaginazione da quotidiano italiano anni Novanta, filetti neri
sottili a separare i riquadri, gerarchia tipografica marcata, colonne di testo
giustificate. Tutto il testo in italiano corretto, con gli accenti al posto
giusto, nitido e leggibile. Nessun watermark e nessun logo inventato oltre alla
testata."""


def costruisci(
    partite: list[Partita],
    tabella: list[RigaClassifica],
    giornata: int,
    stagione: str,
    data: str,
    testata: str,
    memoria: Memoria | None = None,
    seme: int | None = None,
    apertura: Partita | None = None,
) -> str:
    """Il prompt completo della prima pagina, in un passo solo."""
    return renderizza(
        componi(partite, tabella, giornata, stagione, data, testata, memoria, seme, apertura)
    )
