# adbpo_toolbox

Plugin QGIS per la valutazione del rischio in aree allagabili. Si integra come **provider di
Processing** (`AdBPo`, id `adbpo`) e mette a disposizione tre algoritmi, raggruppati sotto
"Rischio aree allagabili" nella Processing Toolbox, per costruire la filiera:

```
uso del suolo (CLC) → classe di danno → rischio per ambito territoriale → rischio massimo senza sovrapposizioni
```

## Requisiti

- QGIS >= 3.40 (vedi `metadata.txt`)
- Ambiente Python di QGIS con il pacchetto `PyYAML` disponibile (usato per leggere
  `matrici_rischio.yaml`)

## Installazione

Copiare la cartella del plugin nella directory dei plugin del proprio profilo QGIS e attivarlo
da *Gestione plugin*. Non essendoci una toolbar/UI dedicata, tutti gli algoritmi compaiono
esclusivamente nella **Processing Toolbox**, sotto il provider "AdBPo".

## Algoritmi

### 1. Risolvi sovrapposizioni poligonali — `adbpo:risolvi_overlay_poligonali`

Genera, a partire da uno o più layer poligonali che possono sovrapporsi, un unico layer
**partizionato senza sovrapposizioni spaziali** (dissolve per layer → merge → poligoni→linee →
polygonize sull'unione di tutti i bordi). Per ciascun poligono della partizione viene individuata
la feature di input, tra quelle che lo intersecano oltre una soglia areale, con il **valore
massimo** nel campo indicato; il poligono di output riceve **tutti gli attributi originali** di
quella feature vincente (non solo il valore del campo confrontato).

Parametri:

| Parametro | Descrizione | Default |
|---|---|---|
| `INPUT` | Layer poligonali di input (multipli) | — |
| `FIELD` | Nome del campo da confrontare (case-insensitive) | `p` |
| `CRS` | CRS di lavoro; i layer vengono riproiettati automaticamente se diverso | `EPSG:3035` |
| `AREA_THRESHOLD` | Soglia areale (unità mappa) sotto la quale un'intersezione viene ignorata (filtro anti-sliver) | `1.0` |
| `CLEAN` | Scarta i poligoni della partizione senza alcuna feature attribuita | `True` |

Output: layer poligonale con lo schema campi risultante dall'**unione** degli schemi di tutti i
layer di input (nomi deduplicati case-insensitive); ogni feature porta i valori originali della
feature di input vincente.

Nota: il campo indicato in `FIELD` deve contenere valori interi (non è prevista pericolosità
frazionaria).

### 2. Associa classe di danno — `adbpo:clc_danno`

Converte i codici Corine Land Cover di un layer poligonale in una classe di danno numerica
(campo `D`), usando la mappa statica `processing/algoritmi/clc2damage.json`. I codici non
presenti in mappa ricadono nella classe di danno di default (`1`).

Parametri: layer CLC, campo contenente il codice CLC, CRS di lavoro (default `EPSG:3035`).

Output: layer poligonale con il campo CLC originale + il campo `D`.

### 3. Determina rischio massimo — `adbpo:flood_risk`

Algoritmo principale: incrocia un layer danno obbligatorio (con campo `D`, tipicamente prodotto da
`clc_danno`) con fino a 5 layer di ambito territoriale opzionali, ciascuno con un campo di
pericolosità `P`:

- Reticolo principale
- Reticolo secondario collinare-montano
- Reticolo secondario di pianura
- Ambito costiero-marino
- Ambito costiero-lacuale

Per ogni ambito presente: riproiezione al CRS target se necessaria, intersezione con il layer
danno, calcolo del campo rischio `R = matrice[P][D]` (la matrice usata dipende dal tipo di
ambito, vedi sotto). Gli output per singolo ambito sono opzionali (checkbox dedicata per ognuno).
Alla fine gli ambiti vengono fusi risolvendo le sovrapposizioni tramite
`risolvi_overlay_poligonali` (campo `R`), producendo l'output principale **"Rischio massimo"**,
che ora riporta anche gli attributi originali (`P`, `D`, `R` e i campi propri dell'ambito
vincente) grazie all'aggiornamento dello schema di output descritto sopra.

## Configurazione dati

- `processing/algoritmi/clc2damage.json` — mapping statico codice CLC (stringa) → classe di
  danno (intero 1-4).
- `processing/algoritmi/matrici_rischio.yaml` — tre matrici `pericolosità (P) → danno (D) →
  rischio (R)`:
  - `mat1` — Reticolo principale, Reticolo secondario collinare-montano
  - `mat2` — Ambito costiero-marino, Ambito costiero-lacuale
  - `mat3` — Reticolo secondario di pianura

## Convenzioni sui campi

- `P` — pericolosità/valore di sovrapposizione (intero)
- `D` — classe di danno (intero 1-4), prodotta da `clc_danno`
- `R` — rischio calcolato come `matrice[P][D]`

## Note di versione (3.1.2rc)

- **Fix**: il conteggio di debug di `risolvi_overlay_poligonali` non sovrascriveva più
  correttamente gli indicatori di intersezione valida/nulla tra una feature candidata e l'altra.
- **Fix**: il confronto del nome campo (`FIELD`) è ora case-insensitive (`lookupField` al posto
  di `indexOf`), evitando eccezioni quando il case digitato non combacia con quello del layer.
- **Fix**: rimossa un'ambiguità di naming (shadowing) tra la feature di partizione e le feature
  candidate nel ciclo di attribuzione.
- **Cambio di comportamento**: l'output di `risolvi_overlay_poligonali` (e quindi anche l'output
  "Rischio massimo" di `flood_risk`) non contiene più un unico campo ricalcolato, ma tutti gli
  attributi originali della feature di input individuata.

Per il dettaglio implementativo di ciascun algoritmo vedi `processing/PLUGIN_QGIS.md` e i sorgenti
in `processing/algoritmi/`.
