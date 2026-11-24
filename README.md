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

```powershell
pip install -e ".[dev]"
$env:F1_FANTASY_TOKEN = 'valore_cookie'
$env:F1_USER_GUID = 'il_tuo_guid'
f1-league
python -m http.server 8000 --directory docs   # poi http://localhost:8000
pytest
```

Le variabili vanno impostate con `$env:` nella stessa finestra in cui lanci il comando.

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
