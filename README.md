# F1 league standings

Classifiche di una lega privata F1 Fantasy, in due versioni e per ogni weekend:

- **Fantapunti**: somma dei punti fantasy.
- **Punti gara**: in ogni weekend i primi 10 della classifica fantasy prendono 25, 18, 15, 12, 10, 8, 6, 4, 2, 1 punti, gli altri 0 (tabella modificabile in `config.toml`).

Il sito (`docs/index.html`) permette di scegliere tipo di classifica, **Weekend** o **Totale** (cumulativo fino al weekend selezionato, con le posizioni guadagnate o perse) e il weekend. Lo stato sta nell'indirizzo, quindi un link condivide la vista.

## Come funziona

`f1-league` legge dall'API di F1 Fantasy la classifica della lega e i punti di ogni membro per ogni gara (endpoint già usati da f1-fantasy-reporter), calcola le classifiche e scrive `docs/index.html` con i dati incorporati più `docs/data/standings.json`. Non servono snapshot: i punti per gara si ricavano a ogni esecuzione.

## Su GitHub

1. Crea un repo **pubblico** (per Pages gratuito) e carica questi file.
2. **Settings → Secrets and variables → Actions**: aggiungi `F1_FANTASY_TOKEN` (valore del cookie `F1_FANTASY_007` su fantasy.formula1.com, da F12 → Application → Cookies) e `F1_USER_GUID` (nell'URL `/services/user/league/<GUID>/...`, F12 → Network, filtro `privateleague`).
3. **Settings → Pages**: *Deploy from a branch* → `main` → cartella `/docs`.
4. **Actions → Aggiorna classifiche → Run workflow**. Poi gira da solo ogni giorno.

Il cookie dura circa 5 giorni: quando scade il workflow fallisce con le istruzioni nel log; aggiorna il secret `F1_FANTASY_TOKEN` e rilancia.

## In locale (PowerShell)

Crea nella cartella del progetto un file `.env` (è già escluso da git, quindi non finisce su GitHub):

```
F1_FANTASY_TOKEN=valore_del_cookie
F1_USER_GUID=il_tuo_guid
```

Poi:

```powershell
py -m pip install -e ".[dev]"
py -m f1_league
```

### Login assistito (token e GUID in automatico)

Invece di copiare cookie e GUID a mano:

```powershell
py -m pip install -e ".[login]"
py -m f1_league --login
```

Si apre il tuo Chrome (con un profilo dedicato in `~\.f1-league\chrome-profile`, così resti connesso): accedi a F1 Fantasy e, se serve, apri la pagina delle leghe. Il programma legge dallo stesso browser il cookie `F1_FANTASY_007` e il GUID che il sito usa nelle sue richieste, li salva nel `.env` e continua con la generazione. Non gestisce la password e non aggira nessuna protezione: il login lo fai tu. Se Chrome non viene trovato imposta `F1_CHROME_PATH` con il percorso di `chrome.exe`; chiudi prima le altre finestre di Chrome aperte con quel profilo.

Il login resta manuale anche su GitHub Actions: lì il cookie va aggiornato nel secret `F1_FANTASY_TOKEN` quando scade (circa ogni 5 giorni).

Il file si legge dalla cartella da cui lanci il comando (o indicane un altro con `--env-file`). Le variabili d'ambiente già impostate hanno la precedenza sul file. Quando il cookie scade basta aggiornare il `.env`. In alternativa si possono impostare con `$env:F1_FANTASY_TOKEN = '...'` nella stessa finestra.

## Statistiche

Nella pagina c'e' il pulsante **Statistiche**: tabella ordinabile (vittorie, podi, punti gara, fantapunti).
Cliccando il nome di un giocatore (anche nella classifica) si apre la scheda con vittorie, podi,
fantapunti e punti gara attuali con la posizione, il miglior weekend e il dettaglio weekend per weekend.
Vittoria = primo posto nel weekend, podio = primi tre; in caso di pari merito la posizione e' condivisa.

## Configurazione (`config.toml`)

- `leagues`: id delle leghe; vuoto = tutte le tue leghe private fino a `max_members` iscritti.
- `f1_points`: tabella dei punti gara.
- `[race_names]`: nomi dei weekend per id gara, se non vuoi quelli del calendario.

## Regole sui pareggi

- Weekend: stessa posizione e stessi punti (due secondi: entrambi 18, il successivo è quarto).
- Totale fantapunti: a parità, stessa posizione.
- Totale punti gara: più vittorie, poi più secondi posti e così via; poi fantapunti totali.

## Limiti da conoscere

- **Non provato contro l'API reale**: manca un token valido qui. La logica è testata con un'API simulata e gli endpoint sono quelli del progetto originale; alla prima esecuzione controlla gli avvisi nel log.
- I nomi dei weekend assumono che l'id gara di Fantasy coincida con il round del calendario; se non è così usa `[race_names]`.
- Se la somma dei weekend di un membro differisce dal totale ufficiale (penalità, gare non conteggiate), compare un avviso nel sito.
- Le seconde squadre del tuo account non sono leggibili in modo affidabile e vengono escluse con un avviso.
- Una gara compare solo quando almeno un membro ha punti diversi da 0.
- Con Pages pubblico, nomi e punteggi dei giocatori sono visibili a chiunque abbia il link.
