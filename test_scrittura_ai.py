"""Prove sulla scrittura con l'AI: fatti, messaggio, risposta, cache e fornitori.

Nessuna prova chiama davvero un modello: le chiamate sono sostituite da
risposte costruite a mano. Per Claude si usa però l'SDK vero, con un trasporto
finto al posto della rete: così si verifica la richiesta che l'SDK costruisce
davvero, non una sua imitazione.

    python test_scrittura_ai.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import requests

from fantamagazine import config, impostazioni, modelli_testo, prompt, resoconto, scrittura_ai, tendenze
from fantamagazine.analysis import RigaClassifica
from fantamagazine.modelli_testo import ErroreTesto
from test_tendenze import _storico_finto

CHIAVE_OPENAI = "sk-proj-chiavediprova1234567890abcdef"
CHIAVE_ANTHROPIC = "sk-ant-api03-chiavediprova1234567890"
CHIAVE_GEMINI = "AIzaSy-chiave-di-prova-1234567890"


# --- Materiale di prova ---------------------------------------------------------------
def _giornata():
    """La quarta giornata dello storico finto, con memoria e classifica.

    Sfigati FC perde sempre e non segna mai, Rossi segna a ogni giornata,
    Muro Difensivo vince sempre: la memoria ha strisce di ogni tipo.
    """
    storia = _storico_finto()
    memoria = tendenze.calcola(storia)
    tabella = [
        RigaClassifica(squadra="Muro Difensivo", punti=12, giocate=4, vinte=4, gol_fatti=8,
                       gol_subiti=4, fantapunti=296.0),
        RigaClassifica(squadra="Bomber United", punti=12, giocate=4, vinte=4, gol_fatti=12,
                       fantapunti=312.0),
        RigaClassifica(squadra="Media Mediocre", punti=0, giocate=4, perse=4, gol_fatti=4,
                       gol_subiti=8, fantapunti=264.0),
        RigaClassifica(squadra="Sfigati FC", punti=0, giocate=4, perse=4, gol_subiti=12,
                       fantapunti=234.0),
    ]
    return storia[4], tabella, memoria


def _dossier_dal_messaggio(messaggio: str) -> dict:
    return json.loads(messaggio.split("\n", 1)[1].split("\n\nINDICAZIONI")[0])


def _risposta(dati: dict, **cambi) -> str:
    """Una risposta valida per quel dossier: un trafiletto per ogni partita minore."""
    codici = {f["soggetto"]: f["codice"] for f in dati["fatti_della_memoria"]}
    corpo = {
        "titolo": "Notte fonda per Sfigati FC",
        "sottotitolo": "Quarta sconfitta di fila",
        "racconto": ["Primo paragrafo del racconto.", "Secondo paragrafo."],
        "pezzo_lungo_titolo": "La vetta è condivisa",
        "pezzo_lungo_testo": "Muro Difensivo e Bomber United a braccetto.",
        "trafiletti": [
            {"partita": v["numero"], "titolo": f"Trafiletto {v['numero']}",
             "testo": f"{v['casa']} contro {v['trasferta']}.", "fatti": []}
            for v in dati["partite"] if not v["in_apertura"]
        ],
        "fatti_titolo": [codici.get("Sfigati FC", "F99")],
        "fatti_racconto": [],
        "fatti_pezzo_lungo": [],
    }
    corpo.update(cambi)
    return json.dumps(corpo, ensure_ascii=False)


@contextlib.contextmanager
def _modello_finto(risposta=None):
    """Sostituisce la chiamata al modello; registra ogni richiesta."""
    chiamate = []
    originale = modelli_testo.scrivi

    def finto(fornitore, modello, sistema, messaggio, schema):
        chiamate.append({"fornitore": fornitore, "modello": modello, "sistema": sistema,
                         "messaggio": messaggio, "schema": schema})
        if isinstance(risposta, Exception):
            raise risposta
        dati = _dossier_dal_messaggio(messaggio)
        return risposta(dati) if callable(risposta) else (risposta or _risposta(dati))

    modelli_testo.scrivi = finto
    try:
        yield chiamate
    finally:
        modelli_testo.scrivi = originale


@contextlib.contextmanager
def _cache():
    originale = scrittura_ai.CACHE
    with tempfile.TemporaryDirectory() as cartella:
        scrittura_ai.CACHE = Path(cartella) / "scritture"
        try:
            yield scrittura_ai.CACHE
        finally:
            scrittura_ai.CACHE = originale


@contextlib.contextmanager
def _chiavi(**valori):
    """Chiavi finte in file temporanei, e nessuna chiave vera dall'ambiente."""
    nomi = {"OPENAI_KEY_FILE": ".openai_key", "ANTHROPIC_KEY_FILE": ".anthropic_key",
            "GEMINI_KEY_FILE": ".gemini_key", "IMPOSTAZIONI_FILE": ".fanta_impostazioni.json"}
    originali = {nome: getattr(config, nome) for nome in nomi}
    ambiente = {v: os.environ.pop(v, None) for v in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")}
    with tempfile.TemporaryDirectory() as cartella:
        for nome, file in nomi.items():
            setattr(config, nome, Path(cartella) / file)
        for fornitore, chiave in valori.items():
            modelli_testo.fornitore(fornitore).file_chiave.write_text(chiave, encoding="utf-8")
        try:
            yield Path(cartella)
        finally:
            for nome, valore in originali.items():
                setattr(config, nome, valore)
            for variabile, valore in ambiente.items():
                if valore is not None:
                    os.environ[variabile] = valore


def _componi(giornata=None, **opzioni):
    # La partita in apertura dev'essere proprio uno degli oggetti della giornata:
    # chi la sceglie passa anche la giornata da cui l'ha presa.
    partite, tabella, memoria = giornata or _giornata()
    parametri = {"id_fornitore": "claude", "id_modello": "claude-sonnet-5"}
    parametri.update(opzioni)
    return scrittura_ai.componi(partite, tabella, 4, "2026-27", "21 settembre 2026",
                                "LA GAZZETTA DI PROVA", memoria, **parametri)


def _errore(funzione) -> ErroreTesto:
    try:
        funzione()
    except ErroreTesto as errore:
        return errore
    raise AssertionError("doveva sollevare un errore")


# --- Il dossier e il messaggio --------------------------------------------------------
def test_il_dossier_porta_tutti_i_fatti() -> None:
    partite, tabella, memoria = _giornata()
    gara = prompt.partita_di_apertura(partite)
    dati = scrittura_ai.dossier(partite, tabella, 4, "2026-27", "LA PROVA", memoria, gara, False)

    assert [(v["casa"], v["trasferta"], v["risultato"]) for v in dati["partite"]] == [
        (p.casa.squadra, p.trasferta.squadra, p.risultato) for p in partite
    ]
    assert sum(v["in_apertura"] for v in dati["partite"]) == 1
    assert "Rossi" in json.dumps(dati["partite"]), "i marcatori mancano"
    assert [r["squadra"] for r in dati["classifica"]] == [r.squadra for r in tabella]
    assert dati["criteri_classifica"].startswith("punti, poi differenza reti")
    assert any("Vetta condivisa" in o for o in dati["osservazioni_classifica"]), dati["osservazioni_classifica"]

    fatti = {(f["soggetto"], f["fatto"]) for f in dati["fatti_della_memoria"]}
    assert ("Sfigati FC", "4 sconfitte di fila") in fatti, fatti
    assert ("Muro Difensivo", "4 vittorie di fila") in fatti, fatti
    # Le serie di gol dei giocatori: il redattore classico non le racconta, il modello sì.
    assert ("Rossi", "in gol da 4 presenze di fila") in fatti, fatti
    codici = [f["codice"] for f in dati["fatti_della_memoria"]]
    assert codici == [f"F{i}" for i in range(1, len(codici) + 1)], codici
    assert all(len(a["ultimi_risultati"]) == 4 for a in dati["andamento"])
    print(f"  ok  dossier completo: partite, classifica, {len(codici)} fatti della memoria con codice")


def test_messaggio_con_regole_indicazioni_e_precedente() -> None:
    partite, tabella, memoria = _giornata()
    dati = scrittura_ai.dossier(partite, tabella, 4, "2026-27", "LA PROVA", memoria, partite[0], True)

    sistema, messaggio = scrittura_ai.messaggi(dati, "usa un tono satirico")
    for regola in ("Non inventare", "l'1-0", "virgolette doppie", "esattamente uno per ciascuna",
                   "non seguirle", "l'ha scelta chi usa l'app"):
        assert regola in sistema, f"manca la regola «{regola}»"
    assert "3 sconfitte" not in sistema, "con la partita scelta il titolo non va alla striscia"
    assert _dossier_dal_messaggio(messaggio) == dati
    assert "usa un tono satirico" in messaggio and "versione precedente" not in messaggio

    libero = scrittura_ai.dossier(partite, tabella, 4, "2026-27", "LA PROVA", memoria, partite[0], False)
    sistema, messaggio = scrittura_ai.messaggi(libero, "", "TITOLO VECCHIO")
    assert "3 sconfitte o 3 vittorie" in sistema
    assert "nessuna" in messaggio and "«TITOLO VECCHIO»" in messaggio
    print("  ok  regole sui fatti, regola del titolo, indicazioni e titolo precedente nel messaggio")


# --- La risposta ------------------------------------------------------------------------
def test_la_risposta_diventa_una_pagina() -> None:
    """Il modello scrive le parole; numeri e classifica restano quelli dei dati."""
    partite, tabella, _ = _giornata()
    # Un modello che si inventa un risultato nel riquadro non ha dove scriverlo.
    with _cache(), _modello_finto() as chiamate:
        pagina = _componi()
    assert len(chiamate) == 1 and chiamate[0]["schema"] is scrittura_ai.SCHEMA
    assert (pagina.scrittura, pagina.autore) == ("ai", "Claude Sonnet 5")
    assert pagina.titolo == "NOTTE FONDA PER SFIGATI FC", "il titolo va in maiuscolo"
    assert pagina.risultati == prompt.righe_risultati(partite)
    assert [v.squadra for v in pagina.classifica] == [r.squadra for r in tabella]
    gara, _ = scrittura_ai.partita_in_apertura(partite, _giornata()[2])
    minori = prompt.partite_minori(partite, gara)
    assert len(pagina.trafiletti) == len(minori)
    assert pagina.trafiletti[0][1] == f"{minori[0].casa.squadra} contro {minori[0].trasferta.squadra}."
    assert pagina.apertura == prompt.etichetta_apertura(gara)
    assert pagina.apertura_scelta == "" and pagina.seme == 0

    testo = prompt.renderizza(pagina)
    assert "NOTTE FONDA PER SFIGATI FC" in testo and "Primo paragrafo del racconto." in testo
    print("  ok  testi dal modello, risultati e classifica dai dati, prompt completo")


def test_partita_scelta_arriva_al_modello() -> None:
    giornata = _giornata()
    scelta = giornata[0][0]
    with _cache(), _modello_finto() as chiamate:
        pagina = _componi(giornata, apertura=scelta)
    dati = _dossier_dal_messaggio(chiamate[0]["messaggio"])
    assert dati["apertura"] == {"partita": 1, "scelta_da_chi_usa_l_app": True,
                                "motivo": "l'ha scelta chi usa l'app"}
    assert "l'ha scelta chi usa l'app" in chiamate[0]["sistema"]
    assert pagina.apertura_scelta == scelta.casa.squadra
    assert pagina.apertura == prompt.etichetta_apertura(scelta)
    print("  ok  la partita scelta arriva al modello, e al titolo è detto di parlarne")


def test_titolo_e_racconto_sulla_stessa_partita() -> None:
    """Il difetto segnalato: titolo su una partita, racconto su un'altra.

    Qui Sfigati FC è alla quarta sconfitta di fila - la notizia da titolo - ma
    la partita più ricca di eventi è l'altra. Senza scelta di chi usa l'app,
    l'apertura dev'essere la partita di Sfigati, e al modello va detto che il
    titolo parla di quella.
    """
    partite, tabella, memoria = _giornata()
    piu_ricca = prompt.partita_di_apertura(partite)
    della_crisi = next(p for p in partite if "Sfigati FC" in (p.casa.squadra, p.trasferta.squadra))
    assert piu_ricca is not della_crisi, "la prova ha senso solo se le due partite sono diverse"

    gara, motivo = scrittura_ai.partita_in_apertura(partite, memoria)
    assert gara is della_crisi and motivo == "Sfigati FC è a 4 sconfitte di fila", motivo

    with _cache(), _modello_finto() as chiamate:
        pagina = _componi((partite, tabella, memoria))
    dati = _dossier_dal_messaggio(chiamate[0]["messaggio"])
    numero = partite.index(della_crisi) + 1
    assert dati["apertura"] == {"partita": numero, "scelta_da_chi_usa_l_app": False,
                                "motivo": "Sfigati FC è a 4 sconfitte di fila"}, dati["apertura"]
    assert "la stessa del racconto" in chiamate[0]["sistema"]
    assert "scegli il fatto più rilevante" not in chiamate[0]["sistema"]
    assert pagina.apertura == prompt.etichetta_apertura(della_crisi)
    assert [t for t, _ in pagina.trafiletti] == [f"Trafiletto {partite.index(piu_ricca) + 1}"]

    # Senza strisce da titolo resta la partita più ricca di eventi, come nella pagina classica.
    for senza in (None, tendenze.calcola({4: partite})):
        gara, motivo = scrittura_ai.partita_in_apertura(partite, senza)
        assert gara is piu_ricca and "ricca di eventi" in motivo, motivo
    print("  ok  apertura automatica sulla partita della notizia: titolo e racconto coincidono")


def test_testi_ripuliti() -> None:
    lungo = "Prima frase del trafiletto. " + "parole " * 120
    risposta = lambda dati: _risposta(  # noqa: E731
        dati,
        titolo='Il "Muro"\tnon crolla',
        sottotitolo="“Imbattibili” e basta",
        trafiletti=[{"partita": v["numero"], "titolo": "T", "testo": lungo, "fatti": []}
                    for v in dati["partite"] if not v["in_apertura"]],
    )
    with _cache(), _modello_finto(risposta):
        pagina = _componi()
    assert pagina.titolo == "IL «MURO» NON CROLLA", pagina.titolo
    assert pagina.sottotitolo == "«Imbattibili» e basta", pagina.sottotitolo
    testo = pagina.trafiletti[0][1]
    assert len(testo) <= scrittura_ai.LIMITI["trafiletto_testo"] + 1, len(testo)
    assert '"' not in prompt.renderizza(pagina).split("TITOLO PRINCIPALE")[1].split("\n")[1][1:-1]
    print("  ok  virgolette doppie diventano basse, spazi ripuliti, testi troppo lunghi accorciati")


def test_risposte_storte() -> None:
    casi = {
        "non è JSON": lambda dati: "Ecco la tua pagina!",
        "manca il titolo": lambda dati: _risposta(dati, titolo=""),
        "manca il racconto": lambda dati: _risposta(dati, racconto=[]),
        "manca un trafiletto": lambda dati: _risposta(dati, trafiletti=[]),
    }
    for nome, risposta in casi.items():
        with _cache(), _modello_finto(risposta):
            errore = _errore(_componi)
        assert errore.codice == "risposta_non_valida", (nome, errore.codice)

    # Tollerate: JSON in un blocco di codice, trafiletti doppi o della partita in apertura.
    def generosa(dati):
        corpo = json.loads(_risposta(dati))
        apertura = next(v["numero"] for v in dati["partite"] if v["in_apertura"])
        corpo["trafiletti"] += corpo["trafiletti"] + [
            {"partita": apertura, "titolo": "Di troppo", "testo": "Di troppo.", "fatti": []},
            {"partita": 99, "titolo": "Inesistente", "testo": "Inesistente.", "fatti": []},
        ]
        return "```json\n" + json.dumps(corpo) + "\n```"

    with _cache(), _modello_finto(generosa):
        pagina = _componi()
    assert len(pagina.trafiletti) == 1 and "Di troppo" not in str(pagina.trafiletti)
    print("  ok  risposte inservibili fermate; quelle con qualcosa in più tenute, senza il superfluo")


def test_richiami_solo_se_davvero_nel_testo() -> None:
    """Il modello dichiara i fatti usati: si crede solo a quelli che si leggono."""
    def risposta(dati):
        # Per soggetto e fatto: Sfigati FC ne ha due, la striscia e il digiuno di gol.
        codici = {(f["soggetto"], f["fatto"]): f["codice"] for f in dati["fatti_della_memoria"]}
        return _risposta(
            dati,
            fatti_titolo=[
                codici[("Sfigati FC", "4 sconfitte di fila")],
                # La stessa squadra, ma il fatto sbagliato: il titolo parla di
                # sconfitte, non del digiuno di gol. Non va accreditato.
                codici[("Sfigati FC", "senza gol da 4 giornate")],
                "F999",
            ],
            # Rossi non compare nel racconto: la dichiarazione non vale.
            fatti_racconto=[codici[("Rossi", "in gol da 4 presenze di fila")]],
            pezzo_lungo_testo="Muro Difensivo vince ancora, a braccetto con Bomber United.",
            fatti_pezzo_lungo=[codici[("Muro Difensivo", "4 vittorie di fila")]],
        )

    partite, _, memoria = _giornata()
    with _cache(), _modello_finto(risposta):
        pagina = _componi()
    tracce = {(r.sezione, r.tipo, r.squadra) for r in pagina.richiami}
    assert tracce == {("titolo", "sconfitte", "Sfigati FC"),
                      ("dietro_i_numeri", "vittorie", "Muro Difensivo")}, tracce

    resoconto_pagina = resoconto.componi(memoria, pagina)
    usate = {n.soggetto: n.sezioni for n in resoconto_pagina.notizie if n.sezioni}
    assert usate == {"Sfigati FC": ["titolo"], "Muro Difensivo": ["dietro_i_numeri"]}, usate
    print("  ok  scheda Memoria: solo i fatti dichiarati e davvero scritti, nella loro sezione")


# --- La cache ------------------------------------------------------------------------------
def test_stessa_richiesta_non_paga_due_volte() -> None:
    with _cache() as cartella, _modello_finto() as chiamate:
        prima = _componi()
        seconda = _componi()
        assert len(chiamate) == 1, f"{len(chiamate)} chiamate per due pagine uguali"
        assert prima.titolo == seconda.titolo

        _componi(nuova=True, precedente="NOTTE FONDA PER SFIGATI FC")
        assert len(chiamate) == 2 and "«NOTTE FONDA PER SFIGATI FC»" in chiamate[-1]["messaggio"]

        _componi(indicazioni="tono satirico")
        _componi(id_modello="claude-haiku-4-5")
        assert len(chiamate) == 4, "indicazioni o modello diversi vogliono una pagina nuova"

        for file in cartella.glob("*.json"):
            file.write_text("{rotto", encoding="utf-8")
        _componi()
        assert len(chiamate) == 5, "una versione salvata illeggibile si riscrive"
    print("  ok  stessa richiesta dalla cache; versione nuova, indicazioni o modello diversi chiamano")


def test_modello_e_fornitore_devono_esistere() -> None:
    with _cache(), _modello_finto() as chiamate:
        assert _errore(lambda: _componi(id_fornitore="bard")).codice == "richiesta_non_valida"
        assert _errore(lambda: _componi(id_modello="gpt-6-astra")).codice == "richiesta_non_valida"
    assert not chiamate, "un modello inesistente non deve diventare una chiamata"
    print("  ok  fornitori e modelli fuori elenco rifiutati prima di chiamare")


# --- Le impostazioni ----------------------------------------------------------------------
def test_modello_scelto_nelle_impostazioni() -> None:
    with _chiavi():
        assert impostazioni.testo_scelto() == (modelli_testo.fornitore("claude"), "claude-opus-5")
        impostazioni.salva_testo(impostazioni.SceltaTesto("gemini", "gemini-3.5-flash-lite"))
        voce, modello = impostazioni.testo_scelto()
        assert (voce.id, modello) == ("gemini", "gemini-3.5-flash-lite")
        # Il modello salvato vale solo per il suo fornitore.
        assert impostazioni.testo_scelto("chatgpt")[1] == "gpt-5.6-terra"
        # Una scelta salvata ritirata dal listino non blocca; una scelta esplicita sbagliata sì.
        impostazioni.salva_testo(impostazioni.SceltaTesto("gemini", "gemini-1.0-pro"))
        assert impostazioni.testo_scelto()[1] == "gemini-3.8-flash"
        try:
            impostazioni.testo_scelto("gemini", "gemini-1.0-pro")
        except ErroreTesto:
            pass
        else:
            raise AssertionError("un modello esplicito inesistente doveva essere rifiutato")
    print("  ok  predefiniti, scelta salvata per fornitore, scelte ritirate che non bloccano")


# --- I fornitori: OpenAI -------------------------------------------------------------------
class _RispostaFinta:
    def __init__(self, stato: int, corpo) -> None:
        self.status_code = stato
        self._corpo = corpo
        self.text = corpo if isinstance(corpo, str) else json.dumps(corpo)

    def json(self):
        if isinstance(self._corpo, str):
            raise ValueError("non JSON")
        return self._corpo


@contextlib.contextmanager
def _rete(*risposte):
    """requests.post restituisce le risposte date, in ordine, e registra le richieste."""
    inviate = []
    coda = list(risposte)
    originale = requests.post

    def finto(url, headers=None, json=None, timeout=None):
        inviate.append({"url": url, "headers": headers or {}, "json": json, "timeout": timeout})
        risposta = coda.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        return risposta

    requests.post = finto
    try:
        yield inviate
    finally:
        requests.post = originale


def _uscita_openai(testo: str) -> dict:
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": testo}]},
    ]}


def test_openai_richiesta_e_risposta() -> None:
    with _chiavi(chatgpt=CHIAVE_OPENAI), _rete(_RispostaFinta(200, _uscita_openai('{"ok": 1}'))) as inviate:
        testo = modelli_testo.scrivi("chatgpt", "gpt-5.6-luna", "SISTEMA", "MESSAGGIO", scrittura_ai.SCHEMA)
    assert testo == '{"ok": 1}'
    richiesta = inviate[0]
    assert richiesta["url"] == "https://api.openai.com/v1/responses"
    assert richiesta["headers"]["Authorization"] == f"Bearer {CHIAVE_OPENAI}"
    corpo = richiesta["json"]
    assert CHIAVE_OPENAI not in json.dumps(corpo) and CHIAVE_OPENAI not in richiesta["url"]
    assert corpo["model"] == "gpt-5.6-luna"
    assert corpo["input"] == [{"role": "system", "content": "SISTEMA"},
                              {"role": "user", "content": "MESSAGGIO"}]
    formato = corpo["text"]["format"]
    assert formato["type"] == "json_schema" and formato["strict"] is True
    assert formato["schema"] is scrittura_ai.SCHEMA
    assert corpo["reasoning"] == {"effort": "low"} and "temperature" not in corpo
    print("  ok  OpenAI: Responses API, chiave nell'intestazione, JSON schema rigoroso")


def test_openai_errori() -> None:
    casi = [
        (_RispostaFinta(401, {"error": {"message": f"Incorrect API key provided: {CHIAVE_OPENAI[:12]}****cdef"}}),
         "chiave_non_valida"),
        (_RispostaFinta(429, {"error": {"code": "insufficient_quota", "message": "You exceeded your quota"}}),
         "quota"),
        (_RispostaFinta(429, {"error": {"code": "rate_limit_exceeded", "message": "Slow down"}}), "quota"),
        (_RispostaFinta(404, {"error": {"message": "The model gpt-x does not exist"}}), "modello_non_disponibile"),
        # Un messaggio che si mostra e ripete la chiave mascherata a metà: la
        # sostituzione della chiave esatta non basta, serve riconoscerne la forma.
        (_RispostaFinta(403, {"error": {"message": f"Project key {CHIAVE_OPENAI[:12]}****cdef lacks access"}}),
         "permesso"),
        (_RispostaFinta(400, {"error": {"message": f"Bad key {CHIAVE_OPENAI} in request"}}), "richiesta_non_valida"),
        (_RispostaFinta(503, "Service Unavailable"), "servizio"),
        (requests.Timeout(), "tempo_scaduto"),
        (requests.ConnectionError(), "rete"),
        (_RispostaFinta(200, {"status": "incomplete",
                              "incomplete_details": {"reason": "max_output_tokens"}}), "risposta_non_valida"),
        (_RispostaFinta(200, {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "refusal", "refusal": "Non posso"}]}]}), "bloccata"),
    ]
    for risposta, atteso in casi:
        with _chiavi(chatgpt=CHIAVE_OPENAI), _rete(risposta):
            errore = _errore(lambda: modelli_testo.scrivi("chatgpt", "gpt-5.6-terra", "S", "M", {}))
        assert errore.codice == atteso, (atteso, errore.codice, errore.messaggio)
        assert CHIAVE_OPENAI not in errore.messaggio and CHIAVE_OPENAI[:12] not in errore.messaggio, errore.messaggio
    print(f"  ok  OpenAI: {len(casi)} errori tradotti, e la chiave non compare mai nei messaggi")


# --- I fornitori: Gemini ------------------------------------------------------------------
def test_gemini_richiesta_e_risposta() -> None:
    risposta = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "ragionamento", "thought": True}, {"text": '{"ok": 2}'}]}}]}
    with _chiavi(gemini=CHIAVE_GEMINI), _rete(_RispostaFinta(200, risposta)) as inviate:
        testo = modelli_testo.scrivi("gemini", "gemini-3.8-flash", "SISTEMA", "MESSAGGIO", scrittura_ai.SCHEMA)
    assert testo == '{"ok": 2}', "i pensieri del modello non sono la risposta"
    richiesta = inviate[0]
    assert richiesta["url"].endswith("/models/gemini-3.8-flash:generateContent"), richiesta["url"]
    assert richiesta["headers"]["x-goog-api-key"] == CHIAVE_GEMINI
    assert CHIAVE_GEMINI not in richiesta["url"] and CHIAVE_GEMINI not in json.dumps(richiesta["json"])
    configurazione = richiesta["json"]["generationConfig"]
    assert configurazione["responseMimeType"] == "application/json"
    schema = json.dumps(configurazione["responseSchema"])
    assert '"OBJECT"' in schema and '"STRING"' in schema and "additionalProperties" not in schema
    assert richiesta["json"]["systemInstruction"] == {"parts": [{"text": "SISTEMA"}]}

    for corpo, atteso in (
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "bloccata"),
        ({"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}, "bloccata"),
        ({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{"}]}}]},
         "risposta_non_valida"),
    ):
        with _chiavi(gemini=CHIAVE_GEMINI), _rete(_RispostaFinta(200, corpo)):
            errore = _errore(lambda: modelli_testo.scrivi("gemini", "gemini-3.8-flash", "S", "M", {}))
        assert errore.codice == atteso, (corpo, errore.codice)
    print("  ok  Gemini: la stessa chiave delle immagini, schema nel suo dialetto, blocchi riconosciuti")


# --- I fornitori: Claude, con l'SDK vero ------------------------------------------------------
@contextlib.contextmanager
def _anthropic_finto(*risposte):
    """L'SDK vero di Anthropic, con un trasporto finto al posto della rete."""
    import anthropic
    import httpx2

    richieste = []
    coda = list(risposte)

    def gestore(richiesta):
        richieste.append(richiesta)
        risposta = coda.pop(0)
        if isinstance(risposta, Exception):
            raise risposta
        stato, corpo = risposta
        return httpx2.Response(stato, json=corpo)

    originale = anthropic.Anthropic

    class Finto(originale):
        def __init__(self, **opzioni):
            # Senza tentativi ripetuti: la prova vuole vedere ogni errore alla prima.
            opzioni["max_retries"] = 0
            super().__init__(**opzioni, http_client=httpx2.Client(transport=httpx2.MockTransport(gestore)))

    anthropic.Anthropic = Finto
    try:
        yield richieste
    finally:
        anthropic.Anthropic = originale


def _messaggio_claude(testo: str, fine: str = "end_turn") -> tuple[int, dict]:
    return 200, {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5",
                 "content": [{"type": "text", "text": testo}], "stop_reason": fine,
                 "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}


def test_claude_richiesta_con_sdk_vero() -> None:
    with _chiavi(claude=CHIAVE_ANTHROPIC), _anthropic_finto(_messaggio_claude('{"ok": 3}'),
                                                             _messaggio_claude('{"ok": 4}')) as richieste:
        opus = modelli_testo.scrivi("claude", "claude-opus-5", "SISTEMA", "MESSAGGIO", scrittura_ai.SCHEMA)
        haiku = modelli_testo.scrivi("claude", "claude-haiku-4-5", "SISTEMA", "MESSAGGIO", scrittura_ai.SCHEMA)
    assert (opus, haiku) == ('{"ok": 3}', '{"ok": 4}')

    prima, seconda = richieste
    assert prima.headers["x-api-key"] == CHIAVE_ANTHROPIC and CHIAVE_ANTHROPIC not in str(prima.url)
    corpo = json.loads(prima.content)
    assert CHIAVE_ANTHROPIC not in prima.content.decode("utf-8")
    # Opus 5: se i controlli di sicurezza declinano, il server ripiega da solo.
    assert "beta=true" in str(prima.url) and prima.headers["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert corpo["fallbacks"] == "default"
    assert corpo["output_config"]["effort"] == "medium"
    assert corpo["output_config"]["format"] == {"type": "json_schema", "schema": scrittura_ai.SCHEMA}
    assert corpo["system"] == "SISTEMA" and corpo["messages"] == [{"role": "user", "content": "MESSAGGIO"}]
    assert "temperature" not in corpo and corpo["max_tokens"] == modelli_testo.MASSIMO_TOKEN

    corpo = json.loads(seconda.content)
    assert "beta" not in str(seconda.url) and "fallbacks" not in corpo
    assert "effort" not in corpo["output_config"], "Haiku 4.5 non accetta lo sforzo"
    print("  ok  Claude: SDK ufficiale, JSON schema, ripiego lato server per Opus 5, niente sforzo per Haiku")


def test_claude_errori_con_sdk_vero() -> None:
    import httpx2

    def errore_api(stato: int, tipo: str, messaggio: str) -> tuple[int, dict]:
        return stato, {"type": "error", "error": {"type": tipo, "message": messaggio}}

    casi = [
        (errore_api(401, "authentication_error", "invalid x-api-key"), "chiave_non_valida"),
        (errore_api(403, "permission_error", "no access"), "permesso"),
        (errore_api(404, "not_found_error", "model: claude-x"), "modello_non_disponibile"),
        (errore_api(429, "rate_limit_error", "slow down"), "quota"),
        (errore_api(400, "invalid_request_error", "Your credit balance is too low"), "quota"),
        (errore_api(400, "invalid_request_error", f"bad {CHIAVE_ANTHROPIC}"), "richiesta_non_valida"),
        (errore_api(529, "overloaded_error", "overloaded"), "servizio"),
        (httpx2.ReadTimeout("lento"), "tempo_scaduto"),
        (httpx2.ConnectError("giù"), "rete"),
        (_messaggio_claude("", fine="refusal"), "bloccata"),
        (_messaggio_claude('{"tronc', fine="max_tokens"), "risposta_non_valida"),
    ]
    for risposta, atteso in casi:
        with _chiavi(claude=CHIAVE_ANTHROPIC), _anthropic_finto(risposta):
            errore = _errore(lambda: modelli_testo.scrivi("claude", "claude-sonnet-5", "S", "M", {}))
        assert errore.codice == atteso, (atteso, errore.codice, errore.messaggio)
        assert CHIAVE_ANTHROPIC not in errore.messaggio, errore.messaggio
    print(f"  ok  Claude: {len(casi)} esiti dell'SDK tradotti, rifiuti e troncamenti compresi")


def test_chiave_mancante_non_parte() -> None:
    with _chiavi(), _rete() as inviate:
        for fornitore, modello in (("chatgpt", "gpt-5.6-luna"), ("claude", "claude-opus-5"),
                                   ("gemini", "gemini-3.8-flash")):
            errore = _errore(lambda: modelli_testo.scrivi(fornitore, modello, "S", "M", {}))
            assert errore.codice == "chiave_mancante", (fornitore, errore.codice)
            assert modelli_testo.fornitore(fornitore).variabile in errore.messaggio
    assert not inviate, "senza chiave non deve partire nessuna richiesta"
    print("  ok  senza chiave nessuna richiesta, e il messaggio dice dove metterla")


# --- Dentro la generazione ----------------------------------------------------------------
def test_generazione_ai_dal_servizio() -> None:
    """Dal servizio: controlli prima di scaricare, errori tradotti, versione nuova su richiesta."""
    from datetime import date

    from fantamagazine import auth, servizio
    from test_accesso import _cartella
    from test_listone import ClientFinto, _servizio_finto
    from test_listone import _cache as _cache_listone

    oggi = date(2026, 9, 21)
    with _cartella(), _cache_listone(), _servizio_finto(), _cache():
        with _chiavi():
            auth.salva_leghe([{"alias": "mia-lega", "nome": "Mia Lega", "token": "eyJ.finto"}])
            try:
                servizio.genera("mia-lega", "1", oggi=oggi, scrittura="ai", fornitore="claude")
            except servizio.ErroreServizio as errore:
                assert errore.codice == "testo_chiave_mancante" and errore.stato_http == 412
            else:
                raise AssertionError("senza chiave doveva fermarsi")
            # Si ferma prima di chiedere qualunque cosa a Fantacalcio.
            assert ClientFinto.listone_chiesto == 0, "ha scaricato prima di controllare la chiave"

        with _chiavi(claude=CHIAVE_ANTHROPIC):
            auth.salva_leghe([{"alias": "mia-lega", "nome": "Mia Lega", "token": "eyJ.finto"}])
            with _modello_finto() as chiamate:
                risultato = servizio.genera("mia-lega", "1", oggi=oggi, scrittura="ai",
                                            fornitore="claude", indicazioni="tono satirico")
                servizio.genera("mia-lega", "1", oggi=oggi, scrittura="ai",
                                fornitore="claude", indicazioni="tono satirico")
                assert len(chiamate) == 1, "la stessa richiesta doveva venire dalla cache"
                servizio.genera("mia-lega", "1", oggi=oggi, scrittura="ai", fornitore="claude",
                                indicazioni="tono satirico", varia=True, precedente="TITOLO A SCHERMO")
                assert len(chiamate) == 2 and "«TITOLO A SCHERMO»" in chiamate[-1]["messaggio"]
            pagina = risultato.pagina
            assert (pagina.scrittura, pagina.autore) == ("ai", "Claude Opus 5"), (pagina.scrittura, pagina.autore)
            assert chiamate[0]["modello"] == "claude-opus-5" and "tono satirico" in chiamate[0]["messaggio"]
            assert pagina.risultati == ["Casa FC 1-0 Ospiti FC"]
            assert "NOTTE FONDA PER SFIGATI FC" in risultato.prompt

            with _modello_finto(ErroreTesto("Limite raggiunto.", "quota")):
                try:
                    servizio.genera("mia-lega", "1", oggi=oggi, scrittura="ai", fornitore="claude", varia=True)
                except servizio.ErroreServizio as errore:
                    assert (errore.codice, errore.stato_http) == ("testo_quota", 429), errore.codice
                else:
                    raise AssertionError("l'errore del modello doveva arrivare")

            for storto in ({"scrittura": "poesia"}, {"scrittura": "ai", "fornitore": "bard"},
                           {"scrittura": "ai", "fornitore": "claude", "modello_testo": "gpt-6-astra"}):
                try:
                    servizio.genera("mia-lega", "1", oggi=oggi, **storto)
                except servizio.ErroreServizio:
                    pass
                else:
                    raise AssertionError(f"scelta storta accettata: {storto}")
    print("  ok  servizio: chiave controllata prima di scaricare, cache, versione nuova, errori tradotti")


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
