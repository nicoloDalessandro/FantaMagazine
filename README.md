# FantaProject

Genera la prima pagina di un quotidiano sportivo a partire dall'ultima giornata
disputata della tua lega su [leghe.fantacalcio.it](https://leghe.fantacalcio.it):
prima il prompt, poi, se vuoi, l'immagine vera e propria con Gemini.

Funziona con qualunque account: entri con le tue credenziali di Leghe
Fantacalcio, scegli quali leghe e competizioni usare e dai un nome al giornale
di ciascuna.

## Il modo più semplice: la redazione

```bash
python app.py
```

Si apre il browser su `http://127.0.0.1:8765`. La prima volta chiede di
**entrare con l'account di Leghe Fantacalcio**, poi mostra **le tue leghe**: scegli
quali usare, quali competizioni tenere e il nome del giornale di ciascuna (vedi
[Accesso e scelte](#accesso-e-scelte)).

Da lì in avanti scegli la lega, la competizione e la giornata, generi la prima
pagina, ne vedi l'**anteprima impaginata**, e con «Genera l'immagine» la mandi a
**Gemini**, che la restituisce come immagine in 9:16 da guardare, salvare o
scaricare. In alto a destra «Le tue leghe» riapre le scelte ed «Esci» cancella
l'accesso da questo computer.

- **Stabile / Nuova versione**: per difetto la stessa giornata dà lo stesso
  testo; «Scrivila diversamente» racconta le stesse notizie con altre parole —
  titolo, racconto, trafiletti e pezzo sulla classifica — e garantisce almeno un
  titolo diverso da quello a schermo.
- **Seme preciso**: il seme usato compare sotto l'anteprima; riscriverlo
  riproduce esattamente quella versione.
- **Memoria**: la scheda mostra che cosa ricorda la memoria delle giornate
  passate e quali punti della pagina ne sono nati, con il testo esatto e il dato
  che li ha fatti scattare (vedi [Vedere la memoria al lavoro](#vedere-la-memoria-al-lavoro)).
- Lega e competizione scelte vengono ricordate dal browser.

```bash
python app.py --porta 9000    # su un'altra porta
python app.py --no-browser    # senza aprire il browser
```

## La riga di comando

Tutto ciò che fa la redazione si può fare anche da terminale. Su stdout finisce
**solo il prompt**, pronto da incollare in Gemini o in un altro modello
testo-immagine.

```bash
python main.py --accedi         # entra con username e password (una volta l'anno)
python main.py                  # chiede lega e competizione, poi genera
python main.py --lista          # elenca leghe, competizioni e stato dei dati
python main.py --lega mia-lega  # salta le domande
python main.py > prompt.txt     # il menu resta a schermo, il prompt sul file
python main.py --verbose        # diagnostica su stderr
python main.py --giornata 3     # forza una giornata specifica
python main.py --varia          # riformula il pezzo a ogni esecuzione
python main.py --seme 42        # riformula in modo riproducibile
python main.py --memoria        # su stderr: cosa ricorda la memoria e cosa usa la pagina
python main.py --immagine       # genera anche l'immagine e la salva in prime_pagine/
python main.py --immagine --risoluzione 4K
python main.py --rigenera-cache # riscarica lo storico da zero
python main.py --rigenera-listone # riscarica il listone dei giocatori
python main.py --aggiorna-leghe # ritrova le leghe nuove, senza password
python main.py --imposta-testata mia-lega "Il Corriere del Bar"
python main.py --esci           # cancella utente e token da questo computer
```

Menu e diagnostica passano da **stderr**, il prompt da **stdout**: si può
redirigere su file continuando a vedere le domande. Anche con `--immagine` su
stdout resta solo il prompt, scritto prima di chiamare Gemini: se la generazione
fallisce il prompt è già lì, e il percorso dell'immagine salvata va su stderr.

### Le prove

```bash
python test_accesso.py    # accesso: richiesta, risposte, errori, nessuna password salvata
python test_impostazioni.py # leghe, competizioni e testate scelte dall'utente
python test_listone.py    # cache del listone e ricarico automatico
python test_tendenze.py   # memoria storica
python test_memoria.py    # vista della memoria: ogni richiamo è davvero in pagina
python test_menu.py       # menu di scelta della riga di comando
python test_prompt.py     # struttura, angoli, lingua e classifica del prompt
python test_web.py        # interfaccia web: difese, validazione, errori
python test_gemini.py     # integrazione con Gemini, con risposte simulate
```

Nessuna prova usa la rete, Chrome o un account vero.

## Installazione

Serve Python 3.9 o più recente (qui è provato su 3.12). Dalla cartella del
progetto, una volta sola, si crea l'ambiente virtuale:

```bash
python -m venv .venv
```

Poi lo si attiva — su Windows con PowerShell:

```bash
.\.venv\Scripts\Activate.ps1
```

con il Prompt dei comandi `.venv\Scripts\activate.bat`, su Mac e Linux
`source .venv/bin/activate` — e si installano le dipendenze:

```bash
pip install -r requirements.txt
```

Le dipendenze sono due: `requests` per l'API e `flask` per la redazione. Anche
Gemini si chiama con `requests`, senza librerie in più.

**L'ambiente virtuale non sta in git**, quindi dopo un `git clone` su un altro
computer va rifatto: senza, il primo avvio finisce con
`ModuleNotFoundError: No module named 'flask'`. Se PowerShell rifiuta di
attivarlo per via delle policy, si può usare direttamente il suo Python:

```bash
.venv\Scripts\python.exe app.py
```

Dal repository non arrivano nemmeno l'accesso alle leghe, le scelte su leghe e
testate, la chiave di Gemini e la cache: l'accesso si rifà dalla redazione, le
scelte si rifanno o si copiano da `.fanta_impostazioni.json`, la chiave si
ricopia in `.gemini_key` e la cache si ricostruisce da sola.

`browser-harness` serve solo a chi nel sito entra con Google o Facebook e una
password non ce l'ha (vedi sotto):

```bash
uv tool install --python 3.12 browser-harness
```

## Accesso e scelte

### Entrare

Si entra con username (o email) e password di Leghe Fantacalcio, dalla redazione
o con `python main.py --accedi`. Una sola chiamata, la stessa del sito,
restituisce l'utente e **tutte le sue leghe**, ciascuna con il proprio token:

    POST https://apileague.fantacalcio.it/onboarding/v1/login

L'API usa infatti un **JWT per lega**: non esiste un token che le apra tutte.

**La password serve solo a quella chiamata**: non viene salvata, stampata,
registrata né restituita dalla redazione, e il modulo la svuota subito, riuscito
o no l'accesso. Su disco restano i token, in file esclusi da git:

| File | Contenuto |
|---|---|
| `.fanta_leghe.json` | Il token di ogni lega, come mappa `alias -> {nome, id, token}` |
| `.fanta_utente.json` | Id, nome utente e token dell'utente |

Da terminale la password si scrive senza che compaia a schermo. In Git Bash la
lettura nascosta può non funzionare: usa PowerShell, il Prompt dei comandi o la
redazione.

I token durano **un anno**. Con quello dell'utente la redazione rilegge il
profilo e ritrova le leghe nuove senza chiedere di nuovo la password («Aggiorna
l'elenco», o `--aggiorna-leghe`). Quando un token scade, la redazione torna al
modulo di accesso. «Esci» (o `--esci`) cancella entrambi i file; le scelte
restano per il prossimo accesso.

Il protocollo è stato ricavato dal codice pubblico del sito e verificato sulla
forma della risposta reale del profilo. **L'accesso con password non è provato
automaticamente**, perché servirebbe un account vero: le prove usano risposte
costruite sulla stessa forma.

### Senza password: Google o Facebook

Chi nel sito entra con Google o Facebook non ha una password. Può copiare
l'accesso dal proprio Chrome: dalla redazione («Nel sito entri con Google o
Facebook?») o da terminale.

1. Apri Chrome e accedi a `leghe.fantacalcio.it`.
2. Autorizza il debug remoto su `chrome://inspect/#remote-debugging`
   (spunta "Allow remote debugging for this browser instance").
3. Premi «Copia l'accesso da Chrome», oppure esegui:

```bash
python refresh_token.py
```

In questo caso i token arrivano dal browser e non c'è un utente salvato:
«Aggiorna l'elenco» li rilegge da Chrome.

In alternativa si può passare un token dall'ambiente, utile in CI:

```bash
export FANTA_TOKEN="eyJhbGciOi..."
export FANTA_LEAGUE_ALIAS="mia-lega"
```

### Scegliere leghe, competizioni e testata

Dopo l'accesso la schermata **Le tue leghe** mostra ogni lega dell'account, con
le sue competizioni:

- **usa questa lega**: una lega spenta sparisce dalla redazione e dal menu della
  riga di comando, e non se ne scaricano più i dati;
- **competizioni**: quelle deselezionate non compaiono, per esempio una Royale,
  che la redazione non sa raccontare;
- **nome del giornale**: se resta vuoto vale quello ricavato dal nome della lega,
  `LA GAZZETTA DI <NOME DELLA LEGA>`.

Le scelte stanno in `.fanta_impostazioni.json`, escluso da git:

```json
{
  "leghe": {
    "mia-lega": {
      "attiva": true,
      "testata": "Il Corriere del Bar",
      "competizioni_escluse": ["12661"]
    }
  }
}
```

Delle competizioni si ricordano quelle **escluse**, non quelle scelte: una coppa
creata a metà stagione compare da sola, invece di restare nascosta finché
qualcuno non se ne accorge. Una lega indicata esplicitamente con `--lega` si
usa anche se è spenta.

## L'immagine con Gemini

Il prompt va direttamente a **Gemini 3 Pro Image** («Nano Banana Pro»), il
modello che Google indica per i compiti visivi più complessi: una prima pagina
fitta di testo che deve uscire leggibile e scritta giusta è esattamente questo.
L'immagine è sempre in **9:16**.

### Prima di cominciare: la fatturazione

**La generazione di immagini non ha un piano gratuito.** Con una chiave sul
piano gratuito Google risponde con un rifiuto di quota, e la redazione lo dice
chiaramente. Serve attivare la fatturazione sul progetto della chiave, da
[Google AI Studio](https://aistudio.google.com/apikey): dopo, la stessa chiave
funziona senza cambiare nulla qui.

Conviene impostare anche un **avviso di spesa** (budget alert) sul progetto
Google Cloud collegato: ogni immagine costa, e un tetto evita sorprese.

### Costi e risoluzione

| Risoluzione | Costo indicativo | Note |
|---|---|---|
| 1K | circa 0,13 $ | |
| **2K** | **circa 0,13 $** | predefinita: stesso prezzo di 1K, più leggibile |
| 4K | circa 0,24 $ | per stampe o schermi grandi |

Le cifre vengono dal listino di Google e servono solo come stima prima del
clic: il costo vero lo decide Google. Una richiesta rifiutata (chiave non
valida, quota, parametri sbagliati) non costa nulla.

### Bozze e archivio

Ogni immagine generata viene conservata subito in `.cache/immagini/`, anche se
non la salvi nell'archivio: un'immagine pagata non va persa per un clic mancato.
«Salva nell'archivio» la copia in **`prime_pagine/`** con un nome che dice
tutto: `mia-lega_giornata-03_seme-7_2026-09-15_21-34-05.png`. Salvare due volte
non duplica, e due omonimi non si sovrascrivono. «Scarica» la passa invece al
browser, e «Rigenera l'immagine» ne chiede un'altra dallo stesso prompt.

Il seme nel nome riproduce il **testo**, non il disegno: lo stesso prompt dà a
ogni generazione un'immagine diversa, e ognuna si paga.

Da riga di comando `--immagine` salva direttamente in archivio.

### La chiave

La chiave si legge dalla variabile `GEMINI_API_KEY` o, in mancanza, dal file
`.gemini_key` nella cartella del progetto, escluso da git. Viaggia verso Google
nell'header `x-goog-api-key` e non nell'indirizzo, dove finirebbe nei log di
proxy e cronologie. Alla pagina arriva soltanto l'informazione che la chiave
c'è, mai la chiave.

Le prove lo verificano: `test_gemini.py` fa fallire la richiesta in tutti i modi
previsti e controlla che la chiave non compaia in nessun messaggio d'errore,
`test_web.py` che non esca dall'API locale.

### Come è stato verificato

La richiesta segue lo schema del documento di discovery ufficiale
(`generationConfig.imageConfig` con `aspectRatio` e `imageSize`). Una verifica
contro l'API vera, senza costi, lo conferma: un campo con un refuso o una
proporzione inesistente vengono respinti come richiesta non valida, mentre la
richiesta dell'app supera la validazione e si ferma solo sulla quota.

La lettura della risposta — l'immagine finale, scartando le bozze intermedie
che il modello marca come `thought`, e i vari motivi di rifiuto — è provata con
risposte simulate costruite sullo stesso schema, perché senza fatturazione non
si può ottenere un'immagine vera.

## Sicurezza della redazione

La redazione riceve la tua password, conserva i token delle tue leghe e la
chiave di Gemini, quindi anche da app locale è costruita con alcune difese:

- ascolta **solo su 127.0.0.1**: nessun altro computer della rete la raggiunge;
- **non parte mai in modalità debug**: il debugger di Werkzeug permetterebbe di
  eseguire codice arbitrario dal browser;
- rifiuta richieste con un **Host** diverso da `127.0.0.1` o `localhost`, che
  blocca il DNS rebinding (un dominio esterno fatto risolvere al tuo computer);
- le richieste che modificano qualcosa devono essere **JSON** e arrivare dalla
  pagina stessa: un sito esterno aperto nel browser non può inviarle, nemmeno
  un tentativo di accesso o un'uscita;
- la **password** non viene salvata né restituita, nemmeno nei messaggi
  d'errore; l'errore di rete che la conterrebbe nella richiesta non si propaga,
  e utente e leghe non mostrano i token nemmeno quando finiscono in un log;
- i **token e la chiave di Gemini non lasciano mai il server**: il rinnovo
  restituisce alias e nomi, lo stato di Gemini dice solo se la chiave c'è;
- le immagini si recuperano solo con l'identificativo generato dal server, mai
  con un percorso: un nome con `..` non raggiunge file fuori dalla cartella;
- i nomi delle squadre, scritti dagli altri partecipanti, entrano nella pagina
  **solo come testo** e mai come HTML, e una Content-Security-Policy vieta
  comunque gli script non serviti dall'app.

`test_web.py` verifica ciascuno di questi punti, compreso un controllo sul
JavaScript che fallisce se vi ricompare `innerHTML`.

## Scelta della lega

Senza argomenti lo script chiede su quale lega lavorare, e poi su quale
competizione, proponendo solo quelle in uso. Si risponde con il numero o con
l'alias per esteso; l'invio a vuoto sceglie la prima.

```
Per quale lega vuoi generare il prompt?
  1) Amici di Sempre  (amici-di-sempre)
  2) Lega del Bar  (lega-del-bar)
> 2
```

Con una sola opzione non chiede nulla. Se nessuno puo' rispondere (pipe, cron)
prosegue con la prima dichiarandolo su stderr, invece di restare bloccato.

`--lista` mostra dove ci sono davvero dati prima di scegliere, comprese leghe e
competizioni escluse:

```
amici-di-sempre  (Amici di Sempre)  testata: Il Corriere del Bar
    12200    Fanta Campionato 2026-27     3/37 giornate, ultima: 3
    12661    Fanta Royale 2026-27         3/37 giornate, ultima: 3  [esclusa]
lega-del-bar  (Lega del Bar)  testata: LA GAZZETTA DI LEGA DEL BAR  [non usata]
    462721   Fanta Campionato 2026-27     0/36 giornate - non ancora iniziata
```

## Configurazione

Tutto sovrascrivibile da variabili d'ambiente (vedi `fantamagazine/config.py`):

| Variabile | Default | Significato |
|---|---|---|
| `FANTA_LEAGUE_ALIAS` | — | Lega da usare col token d'ambiente |
| `FANTA_COMPETITION_ID` | — | Competizione; se vuoto viene chiesta |
| `FANTA_TOKEN` | — | Token singolo, se non si usa il file |
| `FANTA_LEGHE_FILE` | `.fanta_leghe.json` | Dove stanno i token delle leghe |
| `FANTA_UTENTE_FILE` | `.fanta_utente.json` | Dove sta il token dell'utente |
| `FANTA_IMPOSTAZIONI_FILE` | `.fanta_impostazioni.json` | Leghe, competizioni e testate scelte |
| `FANTA_TESTATA` | — | Forza la testata per ogni lega |
| `GEMINI_API_KEY` | — | Chiave di Gemini, se non si usa il file |
| `GEMINI_KEY_FILE` | `.gemini_key` | Dove sta la chiave di Gemini |
| `GEMINI_MODELLO` | `gemini-3-pro-image` | Modello per le immagini |
| `GEMINI_TIMEOUT` | `300` | Secondi di attesa massima per un'immagine |
| `FANTA_ARCHIVIO` | `prime_pagine` | Cartella delle prime pagine salvate |

Leghe e competizioni non sono cablate: arrivano dall'accesso dell'utente e
dall'endpoint `/league/competitions`.

## Come funziona

Il sito e' una SPA Angular e le pagine sono gusci vuoti: `/standings` e
`/fixtures` non renderizzano nulla se aperte a freddo. I dati arrivano tutti
dall'API, quindi qui non si usa alcun browser (se non per il token).

```
app.py               interfaccia web (Flask, solo 127.0.0.1)
web/
  templates/         la pagina
  static/            stile e JavaScript
main.py              riga di comando
refresh_token.py     accesso copiato da Chrome, per chi non ha una password
fantamagazine/
  servizio.py        le operazioni, condivise da web e riga di comando
  config.py          parametri ed endpoint
  accesso.py         accesso con username e password, profilo dell'utente
  auth.py            conservazione dei token, header
  impostazioni.py    leghe, competizioni e testate scelte dall'utente
  browser.py         lettura dei token dal Chrome dell'utente
  gemini.py          generazione dell'immagine con Gemini
  api.py             client HTTP
  analysis.py        ricostruzione formazioni, classifica
  storico.py         cache su disco delle giornate passate
  listone.py         cache dei nomi dei giocatori
  tendenze.py        memoria: strisce e ricorrenze
  resoconto.py       che cosa ricorda la memoria e che cosa usa la pagina
  prompt.py          la pagina come dati, poi come prompt
test_*.py            le prove
```

Web e riga di comando non contengono logica: entrambe chiamano
`fantamagazine/servizio.py`, che restituisce dati oppure un `ErroreServizio` con un
codice stabile. La riga di comando lo traduce in un messaggio e in un codice di
uscita, il web in una risposta JSON e, per i problemi di token, nel ritorno al
modulo di accesso. Per la stessa lega, giornata e seme i due producono quindi lo stesso
prompt, byte per byte: è stato verificato sulle tre leghe e su giornate passate
confrontando l'output reale, ma non è una prova automatica, perché richiederebbe
rete e token.

Allo stesso modo `prompt.componi()` produce la pagina come **dati**
(`PrimaPagina`) e `prompt.renderizza()` la trasforma nel prompt: l'anteprima web
usa i dati, senza dover ripescare titoli e trafiletti dentro una stringa.

## La prima pagina

Il prompt descrive queste zone, nell'ordine:

| Zona | Contenuto |
|---|---|
| Testata | Il nome del giornale, diverso per ogni lega |
| Titolo | La notizia della giornata, con sottotitolo |
| **IL RACCONTO** | **Una** partita per esteso: quella con l'evento più rilevante |
| I RISULTATI | Le cinque partite |
| LA CLASSIFICA | Tabella completa |
| **DIETRO I NUMERI** | Trafiletto lungo sulla classifica |
| **Trafiletti brevi** | Tutte le altre partite, **una per trafiletto** |

L'impianto è quello di una prima pagina vera: **una gara in apertura, le altre
una per trafiletto**. Così ogni partita è coperta una volta sola, e nessuna
squadra viene raccontata due volte con parole diverse.

Il numero di trafiletti dipende dalla lega: dieci squadre fanno cinque partite,
quindi uno in apertura e quattro brevi; otto squadre ne fanno quattro, quindi
uno e tre. Le etichette nel prompt seguono i dati e non un valore cablato.

La gara di apertura la sceglie `prompt._interesse()`: pesa le anomalie (una
squadra incompleta vale più di tutto), poi gol e insufficienze, e a parità
premia le gare equilibrate, che si raccontano meglio di quelle scontate.

Il trafiletto lungo guarda la **classifica**, non le partite: con tutte e cinque
già raccontate altrove, una rassegna delle gare qui ripeterebbe soltanto. Lo
spazio serve invece a dire ciò che i pezzi sui singoli match non dicono — chi
guida, di quanto, e soprattutto chi produce più fantapunti senza trasformarli in
punti.

L'ordine della classifica è punti, poi differenza reti, poi fantapunti, e il
pezzo deve dire il motivo **vero**. Era uscito «separate solo dai fantapunti»
per due squadre appaiate in cui era prima quella con *meno* fantapunti, e «senza
trovarsi in testa» per una squadra che in testa c'era, a pari punti. Un test
passa dieci situazioni di vetta — pari con ciascun motivo, pari a tre, distacchi
con chi produce di più in ogni posizione — e in nessuna ammette affermazioni
false o una squadra nominata due volte.

### Gli angoli, non i soggetti

Il difetto più insidioso non è nominare due volte la stessa squadra: è scrivere
due trafiletti che dicono la stessa cosa su squadre diverse.

```
"IL PESO DI DESAPARECIDOS"      "72 fantapunti, un bottino da metà classifica..."
"BUONA PROVA PER FC COCCOVENTUS" "70 fantapunti, un bottino da metà classifica..."
```

Cambiano i nomi, ma è lo stesso pezzo. La varietà non sta nei soggetti: sta nel
**motivo** per cui quella partita è una notizia.

Ogni gara propone quindi i suoi angoli — `vetta`, `prima_vittoria`,
`prima_sconfitta`, `crisi`, `striscia`, `dominio`, `bomber`, `misura`,
`divario` — in ordine di forza. L'assegnazione è golosa e scarta gli angoli già
presi, così quattro trafiletti raccontano quattro cose diverse. Le partite con
meno alternative scelgono per prime, per non restare senza.

Quando tutti gli angoli forti sono esauriti restano diverse **chiusure di
ripiego**, formulate in modo diverso l'una dall'altra proprio perché due gare
che ci finiscono entrambe non producano lo stesso testo. In fondo al mazzo ogni
partita ha poi un **angolo garantito**, con chiave che contiene l'indice della
gara e quindi impossibile da occupare: è la certezza che nessuna partita resti
senza trafiletto.

Quella garanzia è nata da un difetto vero. I pareggi offrivano un solo angolo,
`pari`: in una giornata con due pari il primo lo prendeva e il secondo restava
muto, sparendo dalla pagina. Ora i pari hanno tanti angoli quanto le gare
decise — `pari_bloccato` per uno 0-0, `pari_frenata` per chi era in alto,
`pari_primo` per il primo pareggio stagionale — e un test verifica il caso
limite di una giornata fatta di soli pareggi.

Un test confronta l'«ossatura» dei trafiletti — le parole tolti nomi propri e
numeri — e fallisce se due coincidono. È quel test ad aver scoperto che il
ripiego originale, unico, generava frasi identiche.

### Il testo è stabile per difetto

Ogni pezzo della pagina ha più formulazioni, scelte da un **seme** che per
difetto è il numero di giornata. Due turni di fila leggono diversi, ma
**rigenerare la stessa giornata dà sempre lo stesso prompt**: il risultato è
riproducibile e verificabile.

Per avere più versioni fra cui scegliere:

```bash
python main.py --varia      # seme casuale: testo diverso ogni volta
python main.py --seme 42    # seme scelto: diverso, ma riproducibile
```

#### Il seme cambia le parole, mai la notizia

| Pezzo | Cosa cambia col seme | Cosa resta fisso |
|---|---|---|
| Titolo e sottotitolo | La formulazione (quattro per situazione) | Il fatto scelto: crisi, serie positiva, miglior punteggio… |
| Il racconto | Le frasi | La partita raccontata |
| Trafiletti brevi | Titoletto e testo (due o tre per angolo) | L'angolo di ogni partita: vetta, prima vittoria, crisi… |
| Dietro i numeri | Le frasi | Il nome della rubrica e ogni affermazione sulla classifica |
| Testata, risultati, classifica | — | Tutto |

Quale fatto finisce in un trafiletto lo decide la sua importanza, quindi con
un seme diverso D.V.D. ONI resta la squadra della *prima vittoria stagionale*:
cambia soltanto se si legge «D.V.D. ONI C'È» o «D.V.D. ONI SI SBLOCCA».

Con due o tre formule per pezzo, fra due versioni qualche trafiletto può restare
identico: la pagina nel suo insieme cambia, non ogni singola riga. Il titolo sì:
«Scrivila diversamente» riprova finché non è diverso da quello a schermo.

All'inizio il seme arrivava soltanto al racconto: titolo, trafiletti e pezzo
sulla classifica avevano una formula sola e non cambiavano mai.

#### Scelte indipendenti

Ogni punto di scelta mescola il seme con la propria formula (`zlib.crc32`), così
i punti scelgono indipendentemente l'uno dall'altro. Con `seme % len(opzioni)`,
e quasi tutti i punti a due o tre formule, contava solo il seme modulo sei:
sessanta semi producevano sei testi. Si usa crc32 e non `hash()` perché `hash()`
sulle stringhe cambia a ogni avvio di Python.

#### Varianti sì, contraddizioni no

Più formule significano più occasioni di sbagliare, e un errore può nascondersi
in una variante che esce una volta su tre. Per questo le prove non guardano un
seme solo:

- **ogni formulazione di ogni angolo**, generata con quaranta semi su partite
  costruite per accenderli quasi tutti, deve nominare entrambe le squadre e
  nessuna due volte, non iniziare con un numero, e usare articoli giusti;
- il pezzo sulla classifica viene controllato in dieci situazioni di vetta per
  quaranta semi, e nessuna variante può dire il falso sul motivo dell'ordine;
- se la vetta è condivisa, nessun trafiletto può dire che «la vetta è sua»:
  succedeva sulla pagina vera, mentre il pezzo sulla classifica, due righe più
  su, diceva che le prime due la dividevano.

### Le testate

Ogni lega ha il suo quotidiano, e il nome lo sceglie l'utente (vedi
[Scegliere leghe, competizioni e testata](#scegliere-leghe-competizioni-e-testata)).
Senza una scelta se ne ricava uno dal nome della lega (`LA GAZZETTA DI ...`),
così una lega nuova non resta senza testata; `FANTA_TESTATA` le forza tutte.

La testata si usa come è scritta, maiuscole comprese, e l'anteprima la mostra
allo stesso modo. Va su una riga, fino a 60 caratteri; le virgolette doppie
diventano semplici, perché nel prompt la testata sta fra virgolette.

### Lingua

Il testo generato è italiano vero: accenti al posto giusto, virgola decimale
(`82,5`), elenchi chiusi con la `e`. Un paio di trappole che i test presidiano:

- molti cognomi arrivano abbreviati (`Yeboah J.`), quindi la punteggiatura si
  aggiunge solo quando serve, altrimenti si ottiene `Yeboah J..`;
- le preposizioni articolate sono evitate di proposito. Con nomi che vanno da
  `Ouzonion` a `FC Coccoventus` l'elisione corretta andrebbe decisa sul suono e
  non sulla lettera, quindi si scrive `Mandragora (Afrikaans Raptors)` invece di
  tentare `del`/`dell'`;
- i verbi concordano col numero di marcatori: `decide Politano` ma
  `decidono Piccoli e Martinez L.`;
- gli articoli davanti ai punteggi seguono la pronuncia: `il 2-1`, `l'1-1`,
  `lo 0-0`, `sull'1-0`, `uno 0-0`; e il singolare vale anche per i numeri:
  `1 punto`, `un fantapunto`;
- **la squadra di Serie A del giocatore non si nomina mai.** In una lega di
  fantacalcio i lettori conoscono i propri giocatori, e `Frattesi (LAZ)` suona
  come una scheda anagrafica, non come un giornale. Un test lo presidia.

`main.py` riconfigura stdout in UTF-8: senza, una console Windows con code page
legacy restituirebbe accenti illeggibili.

## Memoria storica

Una sconfitta e' un dato; la quarta sconfitta di fila e' una storia. Il modulo
`tendenze.py` ricostruisce, sulle giornate disputate in ordine:

| Per squadra | Per giocatore |
|---|---|
| sconfitte / vittorie consecutive | presenze consecutive andate a segno |
| giornate senza vittoria, imbattuta da | gol e media voto stagionali |
| digiuno di gol | insufficienze ricorrenti |
| media, miglior e peggior punteggio | ammonizioni |
| formazioni incomplete schierate | |

La memoria entra nella pagina in quattro punti, ciascuno con la sua soglia:

| Sezione | Che cosa usa della memoria |
|---|---|
| Titolo | la crisi più lunga, da almeno 3 sconfitte di fila; se non c'è, la serie positiva più lunga, da almeno 3 vittorie |
| Il racconto | per le due squadre della gara di apertura, la serie da 2 in su oppure il digiuno di gol da 2 giornate |
| Dietro i numeri | una serie da 2 in su di una squadra che il pezzo non ha già nominato |
| Trafiletti | prima vittoria, prima sconfitta, primo pareggio e serie da 2 in su, se la gara non offre un angolo più forte |

Le serie dei giocatori — chi va in gol da più giornate — la memoria le calcola,
ma **la pagina non le usa ancora**. La scheda Memoria lo mostra apertamente.

Sotto le due giornate nessuna striscia viene calcolata: `abbastanza_storia`
blocca le regole storiche invece di produrre "prima sconfitta consecutiva".

### Vedere la memoria al lavoro

Una memoria che non si vede è difficile da giudicare: la frase sulla terza
sconfitta di fila è frutto della storia o di un caso? Per rispondere, ogni
titolo, frase o trafiletto nato da una giornata passata lascia una traccia mentre
la pagina si compone: un `Richiamo`, con il testo esatto e il dato che l'ha
fatto scattare. La traccia non si ricostruisce dopo, quindi non può raccontare
una storia diversa da quella stampata.

`resoconto.py` la mette accanto a ciò che la memoria sa. La scheda **Memoria**
della redazione, e `python main.py --memoria` da terminale, mostrano:

- **in pagina grazie alla memoria**: i punti nati dal passato, come ritagli di
  giornale, ciascuno col suo perché e l'andamento della squadra;
- **notizie in memoria**: tutto ciò che la memoria conosce, segnato *in pagina*,
  *fuori pagina* (un angolo più forte l'ha preceduta, o la squadra era già
  citata) oppure *non raccontata* (la pagina non sa ancora scriverla), con le
  regole che spiegano dove può entrare;
- **squadre**: i risultati giornata per giornata, la serie in corso, la media e
  i punteggi estremi;
- **giocatori**: gol, presenze, serie in gol, media voto, insufficienze e
  ammonizioni, con una ricerca.

In cima una sintesi dice subito come stanno le cose. Sulla giornata 3 di
FantaTana: *«La memoria copre 3 giornate, dalla 1 alla 3. Conosce 9 notizie: 3
sono entrate in pagina.»* Titolo e racconto nascono dalle tre sconfitte di fila
di Ouzonion, due trafiletti dalla prima vittoria di D.V.D. ONI e dalla prima
sconfitta di FC Coccoventus; le serie in gol di Thuram e Kvernadze restano non
raccontate.

`test_memoria.py` controlla che ogni richiamo si legga davvero nella sezione che
dichiara — 920 richiami, tutte le 12 combinazioni di sezione e fatto — e che,
**togliendo la memoria, ogni testo richiamato sparisca dalla pagina**: è la
prova che quel testo esiste grazie alla storia. All'esordio gli angoli come
«parte col piede giusto» escono comunque, ma non lasciano richiami: dietro non
c'è nessuna giornata passata.

Aggiungere la traccia non ha cambiato il testo: 473 prompt, sintetici e reali,
confrontati prima e dopo, sono identici. Il confronto non è una prova
automatica, perché i casi reali richiedono rete e token.

### Perche' esiste una cache

Il calendario arriva in una richiesta, le formazioni no: una per partita per
giornata, cinque in una lega da dieci squadre. A fine stagione sarebbero quasi
duecento richieste a ogni esecuzione, per dati ormai immutabili. Le giornate
gia' calcolate finiscono quindi in `.cache/giornate/` e vengono rilette: la
giornata nuova costa cinque richieste la prima volta e nessuna dopo.

In cache sta anche il **listone dei giocatori**, che serve solo a tradurre il
codice di un giocatore nel suo nome. È la risposta più pesante dell'API e
cambia di rado, quindi se ne conserva la sola mappa dei nomi in
`.cache/listone/`: 17 KB invece di 400. Sulla lega di prova, una generazione è
passata da 4 richieste e 435 KB a 3 richieste e 35 KB.

Il listone si riscarica da solo quando in una formazione compare un giocatore
che non conosce — chi arriva dal mercato — così in pagina non finisce mai un
codice al posto del nome. Chi resta senza nome anche dopo, come un ceduto
all'estero che compare solo nelle giornate vecchie, viene annotato: non si
riscarica il listone per lui a ogni pagina.

Nella redazione, sotto «Manutenzione», ci sono i due pulsanti «Svuota la cache»
e «Aggiorna il listone». Da terminale:

```bash
python main.py --rigenera-cache   # svuota le giornate e riscarica
python main.py --rigenera-listone # riscarica i nomi dei giocatori
python main.py --no-cache         # ignora entrambe senza cancellare
```

`--giornata N` limita anche la memoria alle giornate fino alla N: si ottiene il
commento che si sarebbe letto quel giorno, non uno che conosce il futuro.

### Verificare la memoria adesso

A inizio stagione esiste una sola giornata reale, quindi le strisce non possono
manifestarsi. `test_tendenze.py` costruisce quattro giornate sintetiche con
andamenti noti (una squadra che perde sempre, un giocatore che segna sempre) e
verifica che il motore li riconosca, che non inventi strisce con una sola
giornata, e che la memoria cambi davvero l'esito rispetto al solo dato di
giornata.

### Il punto delicato: chi era davvero in campo

Il JSON delle formazioni contiene 22 giocatori per squadra, e **anche i
panchinari rimasti fuori hanno un voto**. Sommarli tutti gonfia il risultato:
i marcatori diventano il doppio di quelli reali.

La formazione effettiva e':

- i titolari con `ptype != "U"` e con voto reale;
- piu' i panchinari con `ptype == "E"`, cioe' subentrati.

Le righe con voto >= 50 e fantavoto == 100 sono sentinelle per **s.v.**, non
punteggi.

`analysis.valida_totali()` verifica la ricostruzione confrontando la somma dei
fantavoti piu' i modificatori di squadra con il totale ufficiale dell'API. Sulla
giornata 1 tornano tutti e dieci, al decimale. Se un giorno non tornasse,
`main.py --verbose` lo segnala invece di produrre silenziosamente numeri
sbagliati.

### Eventi dedotti

Il campo `b` e' un vettore di 16 slot. La corrispondenza e' stata ricavata dai
dati, non da documentazione:

| slot | evento | effetto |
|---|---|---|
| 0 | ammonizione | −0.5 |
| 2 | gol segnato | +3 |
| 3 | gol subito (portiere) | −1 |
| 10, 13, 14 | bonus (assist, porta inviolata) | +1 |

Gol e voti sono certi. I tre slot da +1 restano indistinti: valgono lo stesso e
i dati osservati non bastano a separarli.

## Limiti noti

- La **classifica e' cumulativa** su tutte le giornate calcolate, com'e'
  corretto che sia; risultati, marcatori e commenti riguardano invece la sola
  ultima giornata.
- L'ordine fra squadre a pari punti usa differenza reti e poi fantapunti. La tua
  lega puo' avere criteri diversi: il valore non e' letto dalle impostazioni.
- Il listone resta in cache finché non compare un giocatore sconosciuto: se una
  rosa cambia senza che nessuno scenda in campo, i nomi nuovi si vedono solo
  dopo «Aggiorna il listone».
- **Le serie dei giocatori non entrano in pagina.** La memoria sa chi va in gol
  da più giornate, ma nessuna sezione lo racconta: la scheda Memoria le segna
  come *non raccontate*.
- Le strisce si azzerano se una giornata viene ricalcolata a posteriori senza
  rigenerare la cache.
- **I formati Royale non sono supportati.** Li' ogni squadra affronta tutte le
  altre nella stessa giornata, mentre classifica e commenti qui assumono partite
  a coppie. Lo strumento riconosce il caso (`analysis.scontri_diretti`) e si
  ferma spiegando perche', invece di produrre numeri privi di senso.
- Una squadra che non schiera affatto ha `starts` a None: viene trattata come
  formazione vuota, non fa piu' esplodere l'analisi.
- **Il testo dentro l'immagine può contenere errori.** Gemini 3 Pro Image è il
  modello più affidabile con le scritte, ma resta un modello che disegna le
  lettere: un nome storpiato o un numero sbagliato vanno controllati a occhio
  prima di condividere la pagina.
