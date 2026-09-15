"use strict";

/*
 * Redazione — logica dell'interfaccia.
 *
 * Regola ferma: ogni testo che arriva dal server entra nella pagina solo come
 * testo, mai come HTML. I nomi delle squadre li scrivono gli altri
 * partecipanti della lega: una squadra chiamata "<img onerror=...>" non deve
 * poter eseguire nulla in una pagina in cui si scrive la password.
 */
(() => {
  const $ = (id) => document.getElementById(id);

  const nodi = {
    leghe: $("leghe"),
    competizione: $("competizione"),
    notaCompetizione: $("nota-competizione"),
    giornata: $("giornata"),
    seme: $("seme"),
    notaScrittura: $("nota-scrittura"),
    genera: $("genera"),
    svuotaCache: $("svuota-cache"),
    barraAccount: $("barra-account"),
    accountNome: $("account-nome"),
    apriLeghe: $("apri-leghe"),
    esci: $("esci"),
    schermataAccesso: $("schermata-accesso"),
    schermataLeghe: $("schermata-leghe"),
    schermataRedazione: $("schermata-redazione"),
    titoloAccesso: $("titolo-accesso"),
    moduloAccesso: $("modulo-accesso"),
    accessoUtente: $("accesso-utente"),
    accessoPassword: $("accesso-password"),
    erroreAccesso: $("errore-accesso"),
    entra: $("entra"),
    accessoChrome: $("accesso-chrome"),
    titoloLeghe: $("titolo-leghe"),
    elencoLeghe: $("elenco-leghe"),
    aggiornaLeghe: $("aggiorna-leghe"),
    salvaLeghe: $("salva-leghe"),
    annullaLeghe: $("annulla-leghe"),
    avvisoGlobale: $("avviso-globale"),
    schede: $("schede"),
    schedaAnteprima: $("scheda-anteprima"),
    schedaPrompt: $("scheda-prompt"),
    schedaMemoria: $("scheda-memoria"),
    contaMemoria: $("conta-memoria"),
    pannelloAnteprima: $("pannello-anteprima"),
    pannelloPrompt: $("pannello-prompt"),
    pannelloMemoria: $("pannello-memoria"),
    memoria: $("memoria"),
    giornale: $("giornale"),
    prompt: $("prompt"),
    esito: $("esito"),
    avvisi: $("avvisi"),
    vuoto: $("vuoto"),
    caricamento: $("caricamento"),
    caricamentoTesto: $("caricamento-testo"),
    azioniEsito: $("azioni-esito"),
    copia: $("copia"),
    altraVersione: $("altra-versione"),
    dettagliEsito: $("dettagli-esito"),
    schedaImmagine: $("scheda-immagine"),
    pannelloImmagine: $("pannello-immagine"),
    attesaImmagine: $("attesa-immagine"),
    attesaImmagineTesto: $("attesa-immagine-testo"),
    immagine: $("immagine"),
    immagineImg: $("immagine-img"),
    immagineDidascalia: $("immagine-didascalia"),
    azioniImmagine: $("azioni-immagine"),
    generaImmagine: $("genera-immagine"),
    rigeneraImmagine: $("rigenera-immagine"),
    salvaImmagine: $("salva-immagine"),
    scaricaImmagine: $("scarica-immagine"),
    risoluzione: $("risoluzione"),
    costoImmagine: $("costo-immagine"),
  };

  const stato = {
    account: null,
    schermata: null,
    impostazioni: [],
    leghe: [],
    lega: null,
    risultato: null,
    occupato: false,
    scheda: "anteprima",
    gemini: null,
    immagine: null,
  };

  // --- Utilità ---------------------------------------------------------------
  /** Crea un elemento. I figli stringa diventano nodi di testo, mai HTML. */
  function el(tag, opzioni = {}, ...figli) {
    const nodo = document.createElement(tag);
    if (opzioni.classe) nodo.className = opzioni.classe;
    for (const [nome, valore] of Object.entries(opzioni.attributi || {})) {
      nodo.setAttribute(nome, valore);
    }
    for (const figlio of figli) {
      if (figlio === null || figlio === undefined || figlio === false) continue;
      nodo.append(figlio instanceof Node ? figlio : document.createTextNode(String(figlio)));
    }
    return nodo;
  }

  /** 230.5 -> "230,5", come nel prompt. */
  const numero = (valore) => String(valore).replace(".", ",");

  /** 0.134 -> "0,13". */
  const valuta = (valore) => Number(valore).toFixed(2).replace(".", ",");

  const erroreDiGemini = (codice) =>
    ["gemini_quota", "gemini_chiave_mancante", "gemini_chiave_non_valida", "gemini_permesso"].includes(
      codice,
    );

  /** Preferenze del singolo browser: comode, mai indispensabili. */
  const preferenze = {
    leggi(chiave) {
      try {
        return localStorage.getItem(`redazione.${chiave}`);
      } catch {
        return null;
      }
    },
    scrivi(chiave, valore) {
      try {
        localStorage.setItem(`redazione.${chiave}`, valore);
      } catch {
        /* archiviazione non disponibile: si va avanti senza ricordare */
      }
    },
  };

  class ErroreApi extends Error {
    constructor(messaggio, codice, stato) {
      super(messaggio);
      this.codice = codice;
      this.stato = stato;
    }
  }

  /** Errori che si risolvono solo entrando di nuovo con il proprio account. */
  const problemaDiToken = (codice) =>
    typeof codice === "string" &&
    (codice.startsWith("token") || ["accesso_sessione_scaduta", "accesso_mancante"].includes(codice));

  async function chiama(percorso, { metodo = "GET", corpo } = {}) {
    let risposta;
    try {
      risposta = await fetch(percorso, {
        method: metodo,
        headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
        body: corpo === undefined ? undefined : JSON.stringify(corpo),
      });
    } catch {
      throw new ErroreApi(
        "La redazione non risponde. È ancora aperto il terminale in cui hai lanciato python app.py?",
        "server_spento",
        0,
      );
    }

    let dati = null;
    try {
      dati = await risposta.json();
    } catch {
      /* corpo vuoto o non JSON: si usa il codice HTTP */
    }
    if (!risposta.ok) {
      throw new ErroreApi(
        (dati && dati.errore) || `Errore ${risposta.status}`,
        (dati && dati.codice) || "sconosciuto",
        risposta.status,
      );
    }
    return dati;
  }

  // --- Avvisi ----------------------------------------------------------------
  let timerAvviso = null;

  function mostraAvviso(testo, tipo = "") {
    clearTimeout(timerAvviso);
    nodi.avvisoGlobale.textContent = testo;
    nodi.avvisoGlobale.className = `avviso-globale${tipo ? ` avviso-globale--${tipo}` : ""}`;
    nodi.avvisoGlobale.hidden = false;
    if (tipo === "ok") {
      timerAvviso = setTimeout(() => {
        nodi.avvisoGlobale.hidden = true;
      }, 7000);
    }
  }

  function nascondiAvviso() {
    clearTimeout(timerAvviso);
    nodi.avvisoGlobale.hidden = true;
  }

  function impostaOccupato(occupato) {
    stato.occupato = occupato;
    aggiornaControlli();
  }

  function aggiornaControlli() {
    nodi.genera.disabled = stato.occupato || !competizioneCorrente();
    nodi.altraVersione.disabled = stato.occupato;
    nodi.copia.disabled = stato.occupato;
    nodi.svuotaCache.disabled = stato.occupato;
    for (const pulsante of [nodi.entra, nodi.accessoChrome, nodi.apriLeghe, nodi.esci, nodi.aggiornaLeghe, nodi.annullaLeghe]) {
      pulsante.disabled = stato.occupato;
    }
    nodi.salvaLeghe.disabled = stato.occupato || !stato.impostazioni.length;

    const senzaGemini = !stato.gemini || !stato.gemini.disponibile;
    nodi.generaImmagine.disabled = stato.occupato || !stato.risultato || senzaGemini;
    nodi.rigeneraImmagine.disabled = stato.occupato || !stato.risultato || senzaGemini;
    nodi.risoluzione.disabled = stato.occupato || senzaGemini;
    nodi.salvaImmagine.disabled = stato.occupato || !stato.immagine || stato.immagine.salvata;
    nodi.scaricaImmagine.setAttribute("aria-disabled", String(stato.occupato || !stato.immagine));
  }

  // --- Leghe e competizioni --------------------------------------------------
  const utilizzabile = (c) =>
    !c.errore && c.supportata === true && c.giornate_calcolate.length > 0;

  const legaCorrente = () => stato.leghe.find((l) => l.alias === stato.lega) || null;

  function competizioneCorrente() {
    const lega = legaCorrente();
    if (!lega || nodi.competizione.disabled) return null;
    const scelta = lega.competizioni.find((c) => c.id === nodi.competizione.value);
    return scelta && utilizzabile(scelta) ? scelta : null;
  }

  function descriviLega(lega) {
    if (lega.errore) {
      return { testo: lega.errore, tipo: "problema" };
    }
    const pronte = lega.competizioni.filter(utilizzabile);
    if (pronte.length) {
      const ultima = Math.max(...pronte.map((c) => c.ultima));
      return {
        testo: `Pronta · ${ultima === 1 ? "1 giornata disputata" : `ultima giornata ${ultima}`}`,
        tipo: "pronta",
      };
    }
    return { testo: "Campionato non ancora iniziato", tipo: "" };
  }

  async function caricaLeghe() {
    nodi.leghe.setAttribute("aria-busy", "true");
    nodi.leghe.replaceChildren(el("p", { classe: "nota" }, "Caricamento delle leghe…"));
    try {
      stato.leghe = await chiama("/api/leghe");
      disegnaLeghe();
    } catch (errore) {
      stato.leghe = [];
      stato.lega = null;
      nodi.leghe.replaceChildren(el("p", { classe: "nota" }, errore.message));
      nodi.competizione.replaceChildren();
      nodi.competizione.disabled = true;
      nodi.giornata.replaceChildren();
      nodi.giornata.disabled = true;
      if (problemaDiToken(errore.codice)) {
        mostraSchermata("accesso");
        mostraErroreAccesso(errore.message);
      }
      aggiornaControlli();
    } finally {
      nodi.leghe.setAttribute("aria-busy", "false");
    }
  }

  function disegnaLeghe() {
    if (!stato.leghe.length) {
      const scegli = el(
        "button",
        { classe: "pulsante pulsante--leggero", attributi: { type: "button" } },
        "Scegli le tue leghe",
      );
      scegli.addEventListener("click", apriImpostazioni);
      nodi.leghe.replaceChildren(
        el("p", { classe: "nota" }, "Nessuna lega in uso: le hai escluse tutte."),
        scegli,
      );
      stato.lega = null;
      nodi.competizione.replaceChildren();
      nodi.competizione.disabled = true;
      disegnaGiornate();
      return;
    }

    const salvata = preferenze.leggi("lega");
    const iniziale =
      stato.leghe.find((l) => l.alias === salvata) ||
      stato.leghe.find((l) => descriviLega(l).tipo === "pronta") ||
      stato.leghe[0];

    nodi.leghe.replaceChildren(
      ...stato.leghe.map((lega) => {
        const descrizione = descriviLega(lega);
        const scelta = el("input", {
          attributi: { type: "radio", name: "lega", value: lega.alias },
        });
        scelta.checked = lega.alias === iniziale.alias;
        scelta.addEventListener("change", () => selezionaLega(lega.alias));
        return el(
          "label",
          { classe: "lega" },
          scelta,
          el("span", { classe: "lega__nome" }, lega.nome),
          el("span", { classe: "lega__testata" }, lega.testata),
          el(
            "span",
            {
              classe: `lega__stato${descrizione.tipo ? ` lega__stato--${descrizione.tipo}` : ""}`,
            },
            descrizione.testo,
          ),
        );
      }),
    );
    selezionaLega(iniziale.alias);
  }

  function etichettaCompetizione(c) {
    if (c.errore) return `${c.nome} — non raggiungibile`;
    if (!c.giornate_calcolate.length) return `${c.nome} — non ancora iniziata`;
    if (c.supportata === false) return `${c.nome} — formato non supportato`;
    const n = c.giornate_calcolate.length;
    return `${c.nome} — ${n} ${n === 1 ? "giornata" : "giornate"}`;
  }

  function selezionaLega(alias) {
    stato.lega = alias;
    preferenze.scrivi("lega", alias);
    const lega = legaCorrente();
    nodi.competizione.replaceChildren();
    nodi.notaCompetizione.textContent = "";

    if (!lega || lega.errore || !lega.competizioni.length) {
      nodi.competizione.disabled = true;
      nodi.notaCompetizione.textContent = lega && lega.errore ? lega.errore : "Nessuna competizione.";
      disegnaGiornate();
      return;
    }

    for (const c of lega.competizioni) {
      const opzione = el("option", { attributi: { value: c.id } }, etichettaCompetizione(c));
      opzione.disabled = !utilizzabile(c);
      nodi.competizione.append(opzione);
    }

    const pronte = lega.competizioni.filter(utilizzabile);
    const salvata = preferenze.leggi(`competizione.${alias}`);
    const scelta = pronte.find((c) => c.id === salvata) || pronte[0] || null;
    nodi.competizione.disabled = !scelta;

    if (scelta) {
      nodi.competizione.value = scelta.id;
    } else {
      nodi.notaCompetizione.textContent =
        "Nessuna competizione ha ancora giornate disputate: potrai generare la prima pagina quando si sarà giocato.";
    }
    if (lega.competizioni.some((c) => c.supportata === false)) {
      nodi.notaCompetizione.textContent +=
        (nodi.notaCompetizione.textContent ? " " : "") +
        "I formati Royale non sono supportati: ogni squadra affronta tutte le altre nella stessa giornata.";
    }
    disegnaGiornate();
  }

  function disegnaGiornate() {
    const competizione = competizioneCorrente();
    nodi.giornata.replaceChildren();

    if (!competizione) {
      nodi.giornata.disabled = true;
      aggiornaControlli();
      return;
    }

    const giornate = [...competizione.giornate_calcolate].sort((a, b) => b - a);
    nodi.giornata.append(
      el("option", { attributi: { value: "" } }, `Ultima disputata (${giornate[0]})`),
    );
    for (const g of giornate) {
      nodi.giornata.append(el("option", { attributi: { value: String(g) } }, `Giornata ${g}`));
    }
    nodi.giornata.disabled = false;
    aggiornaControlli();
  }

  // --- Scrittura -------------------------------------------------------------
  const scritturaScelta = () =>
    document.querySelector('input[name="scrittura"]:checked')?.value || "stabile";

  function aggiornaNotaScrittura() {
    nodi.notaScrittura.textContent =
      scritturaScelta() === "varia"
        ? "Ogni generazione racconta le stesse notizie con parole diverse."
        : "Rigenerare la stessa giornata dà lo stesso testo.";
  }

  // --- Generazione -----------------------------------------------------------
  function mostraStato(nome) {
    nodi.vuoto.hidden = nome !== "vuoto";
    nodi.caricamento.hidden = nome !== "caricamento";
    const risultato = nome === "risultato";
    nodi.schede.hidden = !risultato;
    nodi.azioniEsito.hidden = !risultato;
    nodi.pannelloAnteprima.hidden = !risultato || stato.scheda !== "anteprima";
    nodi.pannelloPrompt.hidden = !risultato || stato.scheda !== "prompt";
    nodi.pannelloMemoria.hidden = !risultato || stato.scheda !== "memoria";
    nodi.pannelloImmagine.hidden = !risultato || stato.scheda !== "immagine";
  }

  function mostraErrore(errore) {
    nodi.esito.replaceChildren(el("p", { classe: "nota-errore" }, errore.message));
    if (problemaDiToken(errore.codice)) {
      const pulsante = el(
        "button",
        { classe: "pulsante pulsante--primario", attributi: { type: "button" } },
        "Entra di nuovo",
      );
      pulsante.addEventListener("click", () => mostraSchermata("accesso"));
      nodi.esito.append(pulsante);
    }
    if (erroreDiGemini(errore.codice)) {
      nodi.esito.append(
        el(
          "a",
          {
            attributi: {
              href: "https://aistudio.google.com/apikey",
              target: "_blank",
              rel: "noopener noreferrer",
            },
          },
          "Apri Google AI Studio",
        ),
      );
    }
    nodi.esito.hidden = false;
  }

  async function genera({ nuovaVersione = false } = {}) {
    const lega = legaCorrente();
    const competizione = competizioneCorrente();
    if (!lega || !competizione || stato.occupato) return;

    const corpo = {
      lega: lega.alias,
      competizione: competizione.id,
      giornata: nodi.giornata.value || null,
      varia: nuovaVersione || scritturaScelta() === "varia",
    };

    const semeScritto = nodi.seme.value.trim();
    if (semeScritto !== "" && !nuovaVersione) {
      const seme = Number(semeScritto);
      if (!Number.isInteger(seme) || seme < 0) {
        mostraErrore(new ErroreApi("Il seme deve essere un numero intero positivo.", "parametri", 400));
        return;
      }
      corpo.seme = seme;
    }

    nodi.esito.hidden = true;
    nodi.avvisi.hidden = true;
    nascondiAvviso();
    impostaOccupato(true);
    mostraStato("caricamento");
    nodi.caricamentoTesto.textContent = "Il redattore sta scrivendo…";
    const lento = setTimeout(() => {
      nodi.caricamentoTesto.textContent =
        "Prima volta su questa giornata: sto scaricando le formazioni, serve qualche secondo.";
    }, 3500);

    // "Scrivila diversamente" deve mostrare davvero un'altra versione. Un seme
    // casuale può ricadere su un testo già visto, e anche quando il testo
    // cambia il titolo può restare lo stesso (le sue formule sono poche): il
    // titolo è la prima cosa che si guarda, quindi si riprova anche in quel caso.
    const precedente = nuovaVersione && stato.risultato ? stato.risultato : null;
    const troppoSimile = (dati) =>
      precedente !== null &&
      (dati.prompt === precedente.prompt || dati.pagina.titolo === precedente.pagina.titolo);

    try {
      let dati = await chiama("/api/genera", { metodo: "POST", corpo });
      for (let tentativo = 0; troppoSimile(dati) && tentativo < 5; tentativo++) {
        dati = await chiama("/api/genera", { metodo: "POST", corpo });
      }
      stato.risultato = dati;
      azzeraImmagine();
      disegnaGiornale(dati.pagina);
      disegnaMemoria(dati.memoria, dati.pagina.richiami || []);
      nodi.prompt.textContent = dati.prompt;
      nodi.dettagliEsito.textContent =
        `${dati.nome_lega} · ${dati.nome_competizione} · giornata ${dati.pagina.giornata} · seme ${dati.pagina.seme}`;

      if (dati.avvisi.length) {
        nodi.avvisi.replaceChildren(...dati.avvisi.map((a) => el("li", {}, a)));
        nodi.avvisi.hidden = false;
      }
      mostraStato("risultato");
      mostraScheda(stato.scheda);
    } catch (errore) {
      stato.risultato = null;
      mostraStato("vuoto");
      mostraErrore(errore);
    } finally {
      clearTimeout(lento);
      impostaOccupato(false);
    }
  }

  function disegnaGiornale(pagina) {
    const [titoloLungo, testoLungo] = pagina.pezzo_lungo;

    const classifica = el(
      "table",
      { classe: "classifica" },
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          el("th", { attributi: { scope: "col" } }, "#"),
          el("th", { attributi: { scope: "col" } }, "Squadra"),
          el("th", { classe: "numero", attributi: { scope: "col", title: "Punti" } }, "Pt"),
          el("th", { classe: "numero", attributi: { scope: "col", title: "Fantapunti" } }, "Fp"),
        ),
      ),
      el(
        "tbody",
        {},
        ...pagina.classifica.map((voce) =>
          el(
            "tr",
            {},
            el("td", {}, voce.posizione),
            el("td", {}, voce.squadra),
            el("td", { classe: "numero" }, voce.punti),
            el("td", { classe: "numero" }, numero(voce.fantapunti)),
          ),
        ),
      ),
    );

    nodi.giornale.replaceChildren(
      el("h1", { classe: "giornale__testata" }, pagina.testata),
      el(
        "div",
        { classe: "giornale__data" },
        el("span", {}, `Fanta Campionato ${pagina.stagione}`),
        el("span", {}, `Giornata ${pagina.giornata}`),
        el("span", {}, pagina.data),
      ),
      el("h2", { classe: "giornale__titolo" }, pagina.titolo),
      el("p", { classe: "giornale__sottotitolo" }, pagina.sottotitolo),
      el(
        "div",
        { classe: "giornale__corpo" },
        el(
          "section",
          {},
          el("span", { classe: "giornale__occhiello" }, "Il racconto"),
          el("p", { classe: "giornale__apertura" }, pagina.apertura),
          el(
            "div",
            { classe: "giornale__racconto" },
            ...pagina.racconto.map((paragrafo) => el("p", {}, paragrafo)),
          ),
        ),
        el(
          "aside",
          { classe: "giornale__laterale" },
          el(
            "section",
            { classe: "riquadro" },
            el("span", { classe: "giornale__occhiello" }, "I risultati"),
            el("ul", {}, ...pagina.risultati.map((riga) => el("li", {}, riga))),
          ),
          el(
            "section",
            { classe: "riquadro" },
            el("span", { classe: "giornale__occhiello" }, "La classifica"),
            classifica,
          ),
        ),
      ),
      el(
        "section",
        { classe: "giornale__lungo" },
        el("h3", {}, titoloLungo),
        el("p", {}, testoLungo),
      ),
      el(
        "div",
        { classe: "giornale__trafiletti" },
        ...pagina.trafiletti.map(([titoletto, testo]) =>
          el("section", { classe: "trafiletto" }, el("h3", {}, titoletto), el("p", {}, testo)),
        ),
      ),
    );
  }

  // --- La memoria -------------------------------------------------------------
  // Che cosa ricorda la memoria e che cosa ne è finito in pagina: serve a
  // verificare che la storia pesi davvero su quello che si legge.
  const SEZIONI = {
    titolo: "Titolo",
    racconto: "Il racconto",
    dietro_i_numeri: "Dietro i numeri",
    trafiletti: "Trafiletti",
  };
  const ESITI = { V: "vittoria", N: "pareggio", P: "sconfitta" };
  const GIOCATORI_IN_VISTA = 12;

  /** I risultati di una squadra, giornata per giornata: V N P colorati. */
  function andamento(scheda, ultimi = 10) {
    if (!scheda || !scheda.esiti.length) return null;
    const inizio = Math.max(0, scheda.esiti.length - ultimi);
    const visibili = scheda.esiti.slice(inizio);
    const contenitore = el("span", {
      classe: "andamento",
      attributi: {
        role: "img",
        "aria-label": `Andamento: ${visibili.map((esito) => ESITI[esito]).join(", ")}`,
      },
    });
    if (inizio > 0) {
      contenitore.append(el("span", { classe: "andamento__prima", attributi: { "aria-hidden": "true" } }, `+${inizio}`));
    }
    visibili.forEach((esito, posizione) => {
      const i = inizio + posizione;
      contenitore.append(
        el(
          "span",
          {
            classe: `segno segno--${esito}`,
            attributi: {
              "aria-hidden": "true",
              title:
                `Giornata ${scheda.giornate[i]}: ${ESITI[esito]}, ` +
                `${numero(scheda.fantapunti[i])} fantapunti, ${scheda.gol_fatti[i]} gol`,
            },
          },
          esito,
        ),
      );
    });
    return contenitore;
  }

  function blocco(titolo, ...contenuto) {
    return el("section", { classe: "memoria__blocco" }, el("h4", { classe: "occhiello" }, titolo), ...contenuto);
  }

  function intestazioni(...colonne) {
    return el(
      "thead",
      {},
      el(
        "tr",
        {},
        ...colonne.map(([testo, numerica, spiegazione]) =>
          el(
            "th",
            {
              classe: numerica ? "numero" : "",
              attributi: { scope: "col", ...(spiegazione ? { title: spiegazione } : {}) },
            },
            testo,
          ),
        ),
      ),
    );
  }

  function disegnaRichiami(richiami, notizie, squadre) {
    if (!richiami.length) {
      return el("p", { classe: "nota" }, "Nessun punto della pagina viene dalla memoria.");
    }
    return el(
      "ol",
      { classe: "richiami" },
      ...richiami.map((richiamo) => {
        const notizia = notizie.find((n) => n.tipo === richiamo.tipo && n.soggetto === richiamo.squadra);
        return el(
          "li",
          { classe: "richiamo" },
          el("span", { classe: "richiamo__sezione" }, SEZIONI[richiamo.sezione] || richiamo.sezione),
          el(
            "blockquote",
            { classe: "ritaglio" },
            richiamo.titolo ? el("strong", { classe: "ritaglio__titolo" }, richiamo.titolo) : null,
            richiamo.testo ? el("span", { classe: "ritaglio__testo" }, richiamo.testo) : null,
          ),
          el(
            "p",
            { classe: "richiamo__perche" },
            el("span", {}, "Perché ", el("strong", {}, richiamo.squadra), `: ${notizia ? notizia.fatto : richiamo.tipo}`),
            andamento(squadre.get(richiamo.squadra)),
          ),
        );
      }),
    );
  }

  function disegnaNotizie(notizie, giornate) {
    if (!notizie.length) {
      return el(
        "p",
        { classe: "nota" },
        giornate.length > 1
          ? "Nessuna serie in corso e nessuna prima volta della stagione."
          : "Nessuna notizia: una serie o una prima volta si riconoscono solo dalla seconda giornata.",
      );
    }
    return el(
      "ul",
      { classe: "notizie" },
      ...notizie.map((notizia) => {
        const [tipo, etichetta] = notizia.sezioni.length
          ? ["usata", "In pagina"]
          : notizia.raccontabile
            ? ["fuori", "Fuori pagina"]
            : ["ignorata", "Non raccontata"];
        return el(
          "li",
          { classe: `notizia notizia--${tipo}` },
          el("span", { classe: "notizia__stato" }, etichetta),
          el(
            "span",
            { classe: "notizia__soggetto" },
            notizia.soggetto,
            notizia.squadra !== notizia.soggetto ? el("span", { classe: "nota" }, ` · ${notizia.squadra}`) : null,
          ),
          el("span", { classe: "notizia__fatto" }, notizia.fatto),
          el(
            "span",
            { classe: "nota notizia__dove" },
            notizia.sezioni.map((sezione) => SEZIONI[sezione] || sezione).join(", "),
          ),
        );
      }),
    );
  }

  function disegnaSquadre(squadre) {
    return el(
      "div",
      { classe: "tabella-scorrevole" },
      el(
        "table",
        { classe: "tabella-memoria" },
        intestazioni(
          ["#"],
          ["Squadra"],
          ["Andamento"],
          ["In corso"],
          ["Media", true, "Media fantapunti"],
          ["Max", true, "Miglior punteggio"],
          ["Min", true, "Peggior punteggio"],
        ),
        el(
          "tbody",
          {},
          ...squadre.map((scheda) =>
            el(
              "tr",
              {},
              el("td", {}, scheda.posizione ?? "–"),
              el(
                "td",
                { classe: "tabella-memoria__nome" },
                scheda.nome,
                scheda.incomplete
                  ? el(
                      "span",
                      { classe: "nota" },
                      ` · ${scheda.incomplete} ${scheda.incomplete === 1 ? "formazione incompleta" : "formazioni incomplete"}`,
                    )
                  : null,
              ),
              el("td", {}, andamento(scheda)),
              el("td", {}, scheda.serie.join(" · ") || "—"),
              el("td", { classe: "numero" }, numero(scheda.media_fantapunti)),
              el("td", { classe: "numero" }, numero(scheda.miglior_prestazione)),
              el("td", { classe: "numero" }, numero(scheda.peggior_prestazione)),
            ),
          ),
        ),
      ),
    );
  }

  function disegnaGiocatori(giocatori) {
    if (!giocatori.length) return [el("p", { classe: "nota" }, "Nessun giocatore in memoria.")];

    const righe = giocatori.map((g) => ({
      testo: `${g.nome} ${g.squadra}`.toLowerCase(),
      riga: el(
        "tr",
        {},
        el("td", { classe: "tabella-memoria__nome" }, g.nome),
        el("td", {}, g.squadra),
        el("td", { classe: "numero" }, g.presenze),
        el("td", { classe: "numero" }, g.gol),
        el("td", { classe: "numero" }, g.striscia_gol >= 2 ? g.striscia_gol : "–"),
        el("td", { classe: "numero" }, numero(g.media_voto)),
        el("td", { classe: "numero" }, g.insufficienze || "–"),
        el("td", { classe: "numero" }, g.ammonizioni || "–"),
      ),
    }));

    let tutti = false;
    const cerca = el("input", {
      attributi: { type: "search", placeholder: "Cerca un giocatore o una squadra", "aria-label": "Cerca fra i giocatori" },
    });
    const mostraTutti = el("button", { classe: "pulsante pulsante--leggero", attributi: { type: "button" } });
    const conteggio = el("span", { classe: "nota", attributi: { "aria-live": "polite" } });

    function filtra() {
      const cercato = cerca.value.trim().toLowerCase();
      let visibili = 0;
      righe.forEach(({ testo, riga }, indice) => {
        const mostra = cercato ? testo.includes(cercato) : tutti || indice < GIOCATORI_IN_VISTA;
        riga.hidden = !mostra;
        if (mostra) visibili += 1;
      });
      mostraTutti.hidden = Boolean(cercato) || righe.length <= GIOCATORI_IN_VISTA;
      mostraTutti.textContent = tutti ? `Mostra solo i primi ${GIOCATORI_IN_VISTA}` : `Mostra tutti i ${righe.length}`;
      conteggio.textContent = cercato
        ? `${visibili} ${visibili === 1 ? "giocatore trovato" : "giocatori trovati"}`
        : `${visibili} di ${righe.length} giocatori, dal miglior marcatore`;
    }

    cerca.addEventListener("input", filtra);
    mostraTutti.addEventListener("click", () => {
      tutti = !tutti;
      filtra();
    });
    filtra();

    return [
      el("div", { classe: "filtro-giocatori" }, cerca, conteggio),
      el(
        "div",
        { classe: "tabella-scorrevole" },
        el(
          "table",
          { classe: "tabella-memoria" },
          intestazioni(
            ["Giocatore"],
            ["Squadra"],
            ["Pres.", true, "Presenze"],
            ["Gol", true],
            ["Di fila", true, "Presenze consecutive in gol"],
            ["Media", true, "Media voto"],
            ["Sotto il 5", true, "Voti sotto il 5"],
            ["Amm.", true, "Ammonizioni"],
          ),
          el("tbody", {}, ...righe.map(({ riga }) => riga)),
        ),
      ),
      mostraTutti,
    ];
  }

  function disegnaMemoria(memoria, richiami) {
    nodi.schedaMemoria.hidden = !memoria;
    if (!memoria) {
      nodi.memoria.replaceChildren();
      return;
    }

    // Il numero sulla scheda è un colpo d'occhio: il nome della scheda resta
    // «Memoria», e la stessa informazione è scritta per esteso nel pannello.
    nodi.contaMemoria.textContent = String(richiami.length);
    nodi.contaMemoria.hidden = richiami.length === 0;
    nodi.contaMemoria.title = `${richiami.length} ${
      richiami.length === 1 ? "punto della pagina viene" : "punti della pagina vengono"
    } dalla memoria`;

    const squadre = new Map(memoria.squadre.map((scheda) => [scheda.nome, scheda]));

    nodi.memoria.replaceChildren(
      el(
        "header",
        { classe: "memoria__testa" },
        el("h3", { classe: "memoria__titolo" }, "La memoria di questa pagina"),
        el("p", { classe: "memoria__sintesi" }, memoria.sintesi),
        el(
          "p",
          { classe: "nota" },
          `${memoria.squadre.length} squadre e ${memoria.giocatori.length} giocatori in memoria. ` +
            "Passa sui risultati per vedere giornata e fantapunti.",
        ),
      ),
      blocco("In pagina grazie alla memoria", disegnaRichiami(richiami, memoria.notizie, squadre)),
      blocco(
        "Notizie in memoria",
        disegnaNotizie(memoria.notizie, memoria.giornate),
        el(
          "details",
          { classe: "dettagli regole" },
          el("summary", {}, "Dove può entrare la memoria, e perché una notizia resta fuori"),
          el(
            "dl",
            {},
            ...memoria.regole.flatMap(([sezione, regola]) => [el("dt", {}, sezione), el("dd", {}, regola)]),
          ),
        ),
      ),
      blocco("Squadre", disegnaSquadre(memoria.squadre)),
      blocco("Giocatori", ...disegnaGiocatori(memoria.giocatori)),
    );
  }

  // --- Schede ----------------------------------------------------------------
  const elencoSchede = () => [
    ["anteprima", nodi.schedaAnteprima, nodi.pannelloAnteprima],
    ["prompt", nodi.schedaPrompt, nodi.pannelloPrompt],
    ["memoria", nodi.schedaMemoria, nodi.pannelloMemoria],
    ["immagine", nodi.schedaImmagine, nodi.pannelloImmagine],
  ];

  function mostraScheda(nome) {
    const visibili = elencoSchede()
      .filter(([, bottone]) => !bottone.hidden)
      .map(([chiave]) => chiave);
    stato.scheda = visibili.includes(nome) ? nome : "anteprima";
    for (const [chiave, bottone, pannello] of elencoSchede()) {
      const attiva = chiave === stato.scheda;
      bottone.setAttribute("aria-selected", String(attiva));
      bottone.tabIndex = attiva ? 0 : -1;
      if (stato.risultato) pannello.hidden = !attiva;
    }
    // L'immagine non sopravvive a un ricaricamento: non la si ricorda come scheda.
    if (stato.scheda !== "immagine") preferenze.scrivi("scheda", stato.scheda);
  }

  // --- Immagine con Gemini -----------------------------------------------------
  async function caricaGemini() {
    try {
      stato.gemini = await chiama("/api/gemini");
    } catch {
      stato.gemini = null;
    }
    nodi.risoluzione.replaceChildren();
    if (stato.gemini) {
      for (const dimensione of stato.gemini.dimensioni) {
        const etichetta =
          dimensione === stato.gemini.dimensione_predefinita ? `${dimensione} · consigliata` : dimensione;
        nodi.risoluzione.append(el("option", { attributi: { value: dimensione } }, etichetta));
      }
      const salvata = preferenze.leggi("risoluzione");
      nodi.risoluzione.value = stato.gemini.dimensioni.includes(salvata)
        ? salvata
        : stato.gemini.dimensione_predefinita;
    }
    aggiornaCosto();
    aggiornaControlli();
  }

  function aggiornaCosto() {
    if (!stato.gemini) {
      nodi.costoImmagine.textContent = "Gemini non raggiungibile.";
      return;
    }
    if (!stato.gemini.disponibile) {
      nodi.costoImmagine.textContent = "Manca la chiave di Gemini.";
      return;
    }
    const costo = stato.gemini.costi[nodi.risoluzione.value];
    nodi.costoImmagine.textContent = `circa ${valuta(costo)} $ a immagine`;
  }

  function azzeraImmagine() {
    stato.immagine = null;
    nodi.schedaImmagine.hidden = true;
    nodi.immagine.hidden = true;
    nodi.azioniImmagine.hidden = true;
    nodi.attesaImmagine.hidden = true;
    nodi.immagineImg.removeAttribute("src");
    if (stato.scheda === "immagine") stato.scheda = "anteprima";
  }

  function mostraImmagine(dati) {
    stato.immagine = { ...dati, salvata: false };
    nodi.immagineImg.setAttribute("src", dati.url);
    nodi.immagineDidascalia.textContent =
      `${dati.modello} · ${dati.proporzioni} · ${dati.dimensione} · ` +
      `${numero(dati.secondi)} s · circa ${valuta(dati.costo_stimato)} $`;
    nodi.scaricaImmagine.setAttribute("href", dati.url_scarica);
    nodi.scaricaImmagine.setAttribute("download", dati.nome_file);
    nodi.salvaImmagine.textContent = "Salva nell'archivio";
    nodi.immagine.hidden = false;
    nodi.azioniImmagine.hidden = false;
  }

  async function generaImmagine() {
    if (!stato.risultato || stato.occupato) return;
    const risultato = stato.risultato;
    const corpo = {
      prompt: risultato.prompt,
      lega: risultato.lega,
      giornata: risultato.pagina.giornata,
      seme: risultato.pagina.seme,
      dimensione: nodi.risoluzione.value,
    };
    preferenze.scrivi("risoluzione", corpo.dimensione);

    const precedente = stato.immagine;
    nodi.esito.hidden = true;
    nascondiAvviso();
    impostaOccupato(true);
    nodi.schedaImmagine.hidden = false;
    nodi.immagine.hidden = true;
    nodi.azioniImmagine.hidden = true;
    nodi.attesaImmagine.hidden = false;
    mostraScheda("immagine");

    // L'attesa è lunga: un contatore dice che sta succedendo qualcosa.
    const inizio = Date.now();
    const aggiornaAttesa = () => {
      const trascorsi = Math.round((Date.now() - inizio) / 1000);
      nodi.attesaImmagineTesto.textContent =
        `Gemini sta impaginando la prima pagina in ${corpo.dimensione}. ` +
        `Di solito servono fra 20 e 60 secondi: ne sono passati ${trascorsi}.`;
    };
    aggiornaAttesa();
    const contatore = setInterval(aggiornaAttesa, 1000);

    try {
      mostraImmagine(await chiama("/api/immagine", { metodo: "POST", corpo }));
    } catch (errore) {
      // Se c'era già un'immagine resta visibile: è fallito solo il nuovo tentativo.
      if (precedente) {
        stato.immagine = precedente;
        nodi.immagine.hidden = false;
        nodi.azioniImmagine.hidden = false;
      } else {
        azzeraImmagine();
        mostraScheda("anteprima");
      }
      mostraErrore(errore);
    } finally {
      clearInterval(contatore);
      nodi.attesaImmagine.hidden = true;
      impostaOccupato(false);
    }
  }

  async function salvaImmagine() {
    if (!stato.immagine || stato.occupato) return;
    impostaOccupato(true);
    try {
      const dati = await chiama(`/api/immagine/${stato.immagine.id}/salva`, {
        metodo: "POST",
        corpo: {},
      });
      stato.immagine.salvata = true;
      nodi.salvaImmagine.textContent = "Salvata nell'archivio";
      mostraAvviso(`Prima pagina salvata come ${dati.nome_file} in ${dati.cartella}.`, "ok");
    } catch (errore) {
      mostraAvviso(errore.message, "errore");
    } finally {
      impostaOccupato(false);
    }
  }

  // --- Azioni ----------------------------------------------------------------
  function segnala(pulsante, testo) {
    const originale = pulsante.dataset.originale || pulsante.textContent.trim();
    pulsante.dataset.originale = originale;
    pulsante.textContent = testo;
    clearTimeout(pulsante.timerSegnale);
    pulsante.timerSegnale = setTimeout(() => {
      pulsante.textContent = originale;
    }, 1800);
  }

  async function copia() {
    if (!stato.risultato) return;
    try {
      await navigator.clipboard.writeText(stato.risultato.prompt);
      segnala(nodi.copia, "Copiato");
    } catch {
      // Appunti non disponibili: si seleziona il testo, così basta Ctrl+C.
      mostraScheda("prompt");
      const intervallo = document.createRange();
      intervallo.selectNodeContents(nodi.prompt);
      const selezione = window.getSelection();
      selezione.removeAllRanges();
      selezione.addRange(intervallo);
      segnala(nodi.copia, "Selezionato: premi Ctrl+C");
    }
  }

  // --- Account -------------------------------------------------------------------
  const quanteLeghe = (n) => `${n} ${n === 1 ? "lega" : "leghe"}`;

  function mostraSchermata(nome) {
    stato.schermata = nome;
    nodi.schermataAccesso.hidden = nome !== "accesso";
    nodi.schermataLeghe.hidden = nome !== "leghe";
    nodi.schermataRedazione.hidden = nome !== "redazione";
    nodi.barraAccount.hidden = nome === "accesso" || !(stato.account && stato.account.collegato);
    nodi.apriLeghe.hidden = nome === "leghe";
    // Il fuoco va dove si comincia a leggere: chi usa un lettore di schermo
    // deve accorgersi che la pagina è cambiata.
    if (nome === "accesso") {
      (nodi.accessoUtente.value ? nodi.accessoPassword : nodi.accessoUtente).focus();
    } else if (nome === "leghe") {
      nodi.titoloLeghe.focus();
    }
  }

  function aggiornaAccount(account) {
    stato.account = account;
    const collegato = Boolean(account && account.collegato);
    nodi.accountNome.textContent = collegato ? account.username || "Accesso copiato da Chrome" : "";
    nodi.barraAccount.hidden = !collegato || stato.schermata === "accesso";
  }

  async function caricaAccount() {
    try {
      aggiornaAccount(await chiama("/api/account"));
    } catch (errore) {
      aggiornaAccount(null);
      mostraAvviso(errore.message, "errore");
    }
    return stato.account;
  }

  function mostraErroreAccesso(testo) {
    nodi.erroreAccesso.textContent = testo || "";
    nodi.erroreAccesso.hidden = !testo;
  }

  async function entra(evento) {
    evento.preventDefault();
    if (stato.occupato) return;
    const utente = nodi.accessoUtente.value.trim();
    const password = nodi.accessoPassword.value;
    if (!utente || !password) {
      mostraErroreAccesso("Inserisci username e password.");
      (utente ? nodi.accessoPassword : nodi.accessoUtente).focus();
      return;
    }

    mostraErroreAccesso("");
    nascondiAvviso();
    impostaOccupato(true);
    const etichetta = nodi.entra.textContent;
    nodi.entra.textContent = "Accesso in corso…";
    let riuscito = false;
    try {
      const dati = await chiama("/api/accesso", { metodo: "POST", corpo: { utente, password } });
      aggiornaAccount(dati.account);
      mostraAvviso(`Accesso riuscito: ${quanteLeghe(dati.leghe.length)} trovate.`, "ok");
      riuscito = true;
    } catch (errore) {
      mostraErroreAccesso(errore.message);
    } finally {
      // La password non resta nel modulo, che l'accesso sia riuscito o no.
      nodi.accessoPassword.value = "";
      nodi.entra.textContent = etichetta;
      impostaOccupato(false);
    }
    if (riuscito) {
      azzeraRedazione();
      await apriImpostazioni();
    } else {
      nodi.accessoPassword.focus();
    }
  }

  async function accessoChrome() {
    if (stato.occupato) return;
    mostraErroreAccesso("");
    impostaOccupato(true);
    mostraAvviso(
      "Sto copiando l'accesso da Chrome. Se compare il popup «Allow remote debugging?», clicca Allow: può volerci un minuto.",
    );
    let riuscito = false;
    try {
      const dati = await chiama("/api/token", { metodo: "POST", corpo: {} });
      await caricaAccount();
      mostraAvviso(`Accesso copiato da Chrome: ${quanteLeghe(dati.leghe.length)}.`, "ok");
      riuscito = true;
    } catch (errore) {
      nascondiAvviso();
      mostraErroreAccesso(errore.message);
    } finally {
      impostaOccupato(false);
    }
    if (riuscito) {
      azzeraRedazione();
      await apriImpostazioni();
    }
  }

  async function esci() {
    if (stato.occupato) return;
    const conferma = window.confirm(
      "Uscire da questo account?\n\nUtente e token delle leghe verranno cancellati da questo computer: " +
        "per tornare servirà di nuovo la password. Le scelte su leghe e testate restano.",
    );
    if (!conferma) return;
    impostaOccupato(true);
    try {
      aggiornaAccount(await chiama("/api/esci", { metodo: "POST", corpo: {} }));
      azzeraRedazione();
      mostraSchermata("accesso");
      mostraAvviso("Sei uscito: utente e token sono stati cancellati da questo computer.", "ok");
    } catch (errore) {
      mostraAvviso(errore.message, "errore");
    } finally {
      impostaOccupato(false);
    }
  }

  /** Dimentica leghe e pagina mostrate: appartenevano all'accesso di prima. */
  function azzeraRedazione() {
    stato.leghe = [];
    stato.lega = null;
    stato.risultato = null;
    azzeraImmagine();
    nodi.leghe.replaceChildren();
    nodi.competizione.replaceChildren();
    nodi.competizione.disabled = true;
    nodi.giornata.replaceChildren();
    nodi.giornata.disabled = true;
    nodi.esito.hidden = true;
    nodi.avvisi.hidden = true;
    mostraStato("vuoto");
  }

  // --- Le tue leghe ------------------------------------------------------------------
  async function apriImpostazioni() {
    if (stato.occupato) return;
    mostraSchermata("leghe");
    await caricaImpostazioni();
  }

  async function caricaImpostazioni(bozza = null) {
    impostaOccupato(true);
    nodi.elencoLeghe.setAttribute("aria-busy", "true");
    nodi.elencoLeghe.replaceChildren(
      el("p", { classe: "nota" }, "Carico le tue leghe e le loro competizioni…"),
    );
    try {
      stato.impostazioni = await chiama("/api/impostazioni");
      // Chi aggiorna l'elenco a metà delle modifiche non deve perderle.
      for (const voce of stato.impostazioni) {
        const modificata = bozza && bozza.find((b) => b.alias === voce.alias);
        if (!modificata) continue;
        voce.attiva = modificata.attiva;
        voce.testata = modificata.testata;
        for (const competizione of voce.competizioni) {
          competizione.attiva = !modificata.competizioni_escluse.includes(competizione.id);
        }
      }
      disegnaImpostazioni();
    } catch (errore) {
      stato.impostazioni = [];
      nodi.elencoLeghe.replaceChildren(el("p", { classe: "nota-errore" }, errore.message));
      if (problemaDiToken(errore.codice)) {
        mostraSchermata("accesso");
        mostraErroreAccesso(errore.message);
      }
    } finally {
      nodi.elencoLeghe.setAttribute("aria-busy", "false");
      impostaOccupato(false);
    }
  }

  function disegnaImpostazioni() {
    if (!stato.impostazioni.length) {
      nodi.elencoLeghe.replaceChildren(el("p", { classe: "nota" }, "Il tuo account non ha leghe."));
      return;
    }
    nodi.elencoLeghe.replaceChildren(...stato.impostazioni.map(disegnaSceltaLega));
  }

  function disegnaSceltaLega(voce) {
    const scheda = el("fieldset", { classe: "scelta-lega", attributi: { "data-alias": voce.alias } });
    const attiva = el("input", { classe: "scelta-lega__attiva", attributi: { type: "checkbox" } });
    attiva.checked = voce.attiva;

    const testata = el("input", {
      classe: "scelta-lega__testata",
      attributi: { type: "text", maxlength: "60", placeholder: voce.testata_predefinita, spellcheck: "false" },
    });
    testata.value = voce.testata;

    let competizioni;
    if (voce.errore) {
      competizioni = el("p", { classe: "nota-errore" }, `Competizioni non disponibili: ${voce.errore}`);
    } else if (!voce.competizioni.length) {
      competizioni = el("p", { classe: "nota" }, "Nessuna competizione.");
    } else {
      competizioni = el(
        "div",
        { classe: "scelta-lega__competizioni" },
        ...voce.competizioni.map((competizione) => {
          const casella = el("input", { attributi: { type: "checkbox", value: competizione.id } });
          casella.checked = competizione.attiva;
          return el("label", { classe: "casella" }, casella, el("span", {}, competizione.nome));
        }),
      );
    }

    const aggiornaAspetto = () => {
      scheda.classList.toggle("scelta-lega--spenta", !attiva.checked);
      testata.disabled = !attiva.checked;
      for (const casella of scheda.querySelectorAll(".scelta-lega__competizioni input")) {
        casella.disabled = !attiva.checked;
      }
    };
    attiva.addEventListener("change", aggiornaAspetto);

    scheda.append(
      el(
        "legend",
        { classe: "scelta-lega__testa" },
        el("label", { classe: "casella" }, attiva, el("span", { classe: "scelta-lega__nome" }, voce.nome)),
      ),
      el(
        "label",
        { classe: "gruppo" },
        el("span", { classe: "gruppo__titolo" }, "Nome del giornale"),
        testata,
        el("span", { classe: "nota" }, `Se lo lasci vuoto: ${voce.testata_predefinita}`),
      ),
      el("div", { classe: "gruppo" }, el("span", { classe: "gruppo__titolo" }, "Competizioni"), competizioni),
    );
    aggiornaAspetto();
    return scheda;
  }

  function raccogliImpostazioni() {
    return [...nodi.elencoLeghe.querySelectorAll(".scelta-lega")].map((scheda) => {
      const voce = stato.impostazioni.find((v) => v.alias === scheda.dataset.alias);
      const caselle = [...scheda.querySelectorAll(".scelta-lega__competizioni input")];
      return {
        alias: scheda.dataset.alias,
        attiva: scheda.querySelector(".scelta-lega__attiva").checked,
        testata: scheda.querySelector(".scelta-lega__testata").value,
        // Se le competizioni non si sono potute caricare, le esclusioni salvate
        // restano quelle di prima invece di azzerarsi.
        competizioni_escluse:
          voce && voce.errore
            ? voce.competizioni_escluse
            : caselle.filter((casella) => !casella.checked).map((casella) => casella.value),
      };
    });
  }

  async function salvaImpostazioni() {
    if (stato.occupato || !stato.impostazioni.length) return;
    const leghe = raccogliImpostazioni();
    impostaOccupato(true);
    let riuscito = false;
    try {
      await chiama("/api/impostazioni", { metodo: "POST", corpo: { leghe } });
      mostraAvviso(
        stato.risultato
          ? "Scelte salvate. Rigenera la pagina per vedere la nuova testata."
          : "Scelte salvate.",
        "ok",
      );
      riuscito = true;
    } catch (errore) {
      mostraAvviso(errore.message, "errore");
    } finally {
      impostaOccupato(false);
    }
    if (riuscito) {
      mostraSchermata("redazione");
      await caricaLeghe();
    }
  }

  async function aggiornaElenco() {
    if (stato.occupato) return;
    const bozza = raccogliImpostazioni();
    // Chi è entrato da Chrome non ha un utente salvato: l'elenco si rilegge da lì.
    const daChrome = !(stato.account && stato.account.aggiornabile);
    impostaOccupato(true);
    mostraAvviso(daChrome ? "Rileggo le tue leghe da Chrome: può volerci un minuto." : "Cerco le tue leghe…");
    let riuscito = false;
    try {
      const dati = await chiama(daChrome ? "/api/token" : "/api/leghe/aggiorna", { metodo: "POST", corpo: {} });
      if (dati.account) aggiornaAccount(dati.account);
      else await caricaAccount();
      mostraAvviso(`Elenco aggiornato: ${quanteLeghe(dati.leghe.length)}.`, "ok");
      riuscito = true;
    } catch (errore) {
      mostraAvviso(errore.message, "errore");
      if (problemaDiToken(errore.codice)) {
        mostraSchermata("accesso");
        mostraErroreAccesso(errore.message);
      }
    } finally {
      impostaOccupato(false);
    }
    if (riuscito) await caricaImpostazioni(bozza);
  }

  function tornaAllaRedazione() {
    mostraSchermata("redazione");
    if (!stato.leghe.length) caricaLeghe();
  }

  async function svuotaCache() {
    if (stato.occupato) return;
    impostaOccupato(true);
    try {
      const dati = await chiama("/api/cache", { metodo: "POST", corpo: {} });
      mostraAvviso(
        dati.rimossi
          ? `Cache svuotata: ${dati.rimossi} ${dati.rimossi === 1 ? "file rimosso" : "file rimossi"}.`
          : "La cache era già vuota.",
        "ok",
      );
    } catch (errore) {
      mostraAvviso(errore.message, "errore");
    } finally {
      impostaOccupato(false);
    }
  }

  // --- Avvio -----------------------------------------------------------------
  function avvia() {
    nodi.competizione.addEventListener("change", () => {
      preferenze.scrivi(`competizione.${stato.lega}`, nodi.competizione.value);
      disegnaGiornate();
    });
    for (const scelta of document.querySelectorAll('input[name="scrittura"]')) {
      scelta.addEventListener("change", aggiornaNotaScrittura);
    }
    nodi.genera.addEventListener("click", () => genera());
    nodi.altraVersione.addEventListener("click", () => genera({ nuovaVersione: true }));
    nodi.copia.addEventListener("click", copia);
    nodi.svuotaCache.addEventListener("click", svuotaCache);
    nodi.moduloAccesso.addEventListener("submit", entra);
    nodi.accessoChrome.addEventListener("click", accessoChrome);
    nodi.apriLeghe.addEventListener("click", apriImpostazioni);
    nodi.esci.addEventListener("click", esci);
    nodi.aggiornaLeghe.addEventListener("click", aggiornaElenco);
    nodi.salvaLeghe.addEventListener("click", salvaImpostazioni);
    nodi.annullaLeghe.addEventListener("click", tornaAllaRedazione);
    nodi.schedaAnteprima.addEventListener("click", () => mostraScheda("anteprima"));
    nodi.schedaPrompt.addEventListener("click", () => mostraScheda("prompt"));
    nodi.schedaMemoria.addEventListener("click", () => mostraScheda("memoria"));
    nodi.schedaImmagine.addEventListener("click", () => mostraScheda("immagine"));
    nodi.schede.addEventListener("keydown", (evento) => {
      if (evento.key !== "ArrowLeft" && evento.key !== "ArrowRight") return;
      evento.preventDefault();
      const visibili = elencoSchede().filter(([, bottone]) => !bottone.hidden);
      const attuale = visibili.findIndex(([chiave]) => chiave === stato.scheda);
      const passo = evento.key === "ArrowRight" ? 1 : -1;
      const [chiave, bottone] = visibili[(attuale + passo + visibili.length) % visibili.length];
      mostraScheda(chiave);
      bottone.focus();
    });
    nodi.generaImmagine.addEventListener("click", generaImmagine);
    nodi.rigeneraImmagine.addEventListener("click", generaImmagine);
    nodi.salvaImmagine.addEventListener("click", salvaImmagine);
    nodi.risoluzione.addEventListener("change", () => {
      preferenze.scrivi("risoluzione", nodi.risoluzione.value);
      aggiornaCosto();
    });

    const schedaSalvata = preferenze.leggi("scheda");
    stato.scheda = ["prompt", "memoria"].includes(schedaSalvata) ? schedaSalvata : "anteprima";
    mostraScheda(stato.scheda);
    mostraStato("vuoto");
    aggiornaNotaScrittura();
    caricaGemini();
    avviaAccount();
  }

  /** Senza un accesso si parte dal modulo; con un accesso, dalla redazione. */
  async function avviaAccount() {
    const account = await caricaAccount();
    if (account && account.collegato) {
      mostraSchermata("redazione");
      await caricaLeghe();
    } else {
      mostraSchermata("accesso");
    }
  }

  avvia();
})();
