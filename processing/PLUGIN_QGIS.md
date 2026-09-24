## Descrizione generale

Il plugin `adbpo_toolbox` è un plugin QGIS orientato all’analisi del rischio in aree allagabili.  
Si integra come provider nella `Processing Toolbox` di QGIS, offrendo algoritmi per:

- risolvere sovrapposizioni poligonali,
- associare classi di danno ai layer Corine Land Cover,
- calcolare il rischio massimo da aree allagabili sulla base di matrici di rischio territoriali.

Il plugin è definito in __init__.py / main.py e registrato nel Processing tramite provider.py.

## Metadata

Da metadata.txt:

- nome: `adbpo_toolbox`
- descrizione: `Valutazione rischio aree allagabili`
- versione: `3.1.1rc`
- QGIS minimo: `3.40`
- categoria: `Analysis`
- autore: `Vincenzo Critelli`

## Struttura principale

- __init__.py
  - esporta `classFactory` per QGIS e inizializza `AdBPoRisk`
- main.py
  - classe `AdBPoRisk`
  - registra / rimuove il provider di algoritmi in `QgsApplication.processingRegistry()`

- provider.py
  - definisce il provider `AdBPo`
  - carica tre algoritmi:
    - `ResolvePolygonOverlay`
    - `CLCToDamage`
    - `CalcRisk`

- utils.py
  - contiene helper che chiamano algoritmi di processing nativi (`reprojectlayer`, `intersection`, `dissolve`, `mergevectorlayers`, `polygonize`, `polygonstolines`)
  - implementa `solve_overlap` che chiama il custom algorithm `adbpo:risolvi_overlay_poligonali`

## Algoritmi implementati

### 1) `risolvi_overlay_poligonali` (`ResolvePolygonOverlay`)

File: resolve_polygon_overlay.py

Funzionalità:

- prende in input più layer poligonali
- normalizza i CRS verso un CRS target (`EPSG:3035` di default)
- dissolve ciascun layer sul campo specificato
- unisce i layer dissolti
- converte in linee e polygonizza per ottenere una partizione senza sovrapposizioni
- per ogni poligono risultante assegna il valore massimo del campo specificato tra le geometrie in sovrapposizione
- opzionalmente scarta i poligoni senza attributo se `CLEAN=True`
- usa soglia di area per ignorare intersezioni molto piccole

È pensato per produrre un output poligonale disjoint con l’attributo `P` (o altro campo) valorizzato in base alla massima sovrapposizione.

### 2) `clc_danno` (`CLCToDamage`)

File: clc_damage.py

Funzionalità:

- legge un layer Corine Land Cover polygon e un campo che contiene il codice CLC
- riperietta il layer se necessario verso il CRS scelto (`EPSG:3035` di default)
- usa il mapping in clc2damage.json
- crea un nuovo layer con:
  - il campo originale CLC
  - un campo `D` contenente la classe di danno associata

In pratica converte codici CLC in classi di danno numeriche utili per la valutazione del rischio.

### 3) `flood_risk` (`CalcRisk`)

File: flood_risk.py

Funzionalità:

- input obbligatorio:
  - layer danno (`DANNO`)
- input opzionali:
  - `Reticolo principale` (RP)
  - `Reticolo secondario collinare-montano` (RSCM)
  - `Reticolo secondario di pianura` (RSP)
  - `Ambito costiero-marino` (ACM)
  - `Ambito costiero-lacuale` (ACL)

- per ciascun input opzionale:
  - riperietta al CRS target se necessario
  - calcola l’intersezione con il layer danno
  - aggiunge il campo `R` usando una matrice di rischio corrispondente
  - può generare in output i risultati per ciascun ambito (opzionale)

- usa le matrici di rischio definite in matrici_rischio.yaml
- alla fine risolve eventuali sovrapposizioni tra i layer di rischio territoriali con `solve_overlap`
- produce un output finale `Rischio massimo`

### Matrici e configurazione

- matrici_rischio.yaml
  - contiene le matrici di conversione da classe di danno (`D`) e P a rischio `R`
- clc2damage.json
  - mappa i codici CLC alle classi di danno

## Comportamento e scopo

Il plugin è un toolbox specialistico per valutare il rischio da allagamento:

- parte da dati di uso del suolo (CLC),
- traduce i codici CLC in classe di danno,
- incrocia il danno con diversi ambiti territoriali/reticoli
- stima il rischio massimo
- gestisce sovrapposizioni tra layer per ottenere un output pulito
