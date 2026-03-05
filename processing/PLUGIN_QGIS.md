**Documentazione plugin QGIS - AdBPo**

Questa pagina descrive i plugin/algoritmi QGIS implementati nel repository e come usarli dalla Processing Toolbox.

**Contesto**
- Provider ID: `adbpo` (classe `ProcessingProvider` in [processing/provider.py](processing/provider.py#L1))
- Gruppo: `Rischio aree allagabili` (groupId `flood_risk`) — le algorithmi sono registrate sotto questo gruppo.
- QGIS Minimum Version: definito in [metadata.txt](metadata.txt#L5) come `3.28`.

**Algoritmi registrati**

- `adbpo:risolvi_overlay_poligonali` — ResolvePolygonOverlay
  - file: [processing/algoritmi/resolve_polygon_overlay.py](processing/algoritmi/resolve_polygon_overlay.py)
  - display name: "Risolvi sovrapposizioni poligonali"
  - Overview: partiziona più layer poligonali in una copertura senza sovrapposizioni e assegna un attributo (es. pericolosità) al poligono risultante scegliendo il valore massimo per area di sovrapposizione.
  - Input principali:
    - layers multipli poligonali (parametro `INPUT`)
    - `FIELD`: nome del campo attributo usato come valore di pericolosità
    - `CRS`: CRS target (default EPSG:7791)
    - `AREA_THRESHOLD`: soglia areale minima per considerare una intersezione
  - Output: layer poligonale senza sovrapposizioni (parametro `Risolvi_Sovrapposizioni`)
  - Note implementative: usa gli algoritmi nativi `mergevectorlayers`, `polygonstolines`, `polygonize` e poi calcola intersezioni per assegnare il valore massimo di `FIELD`.

- `adbpo:clc_danno` — CLCToDamage
  - file: [processing/algoritmi/clc_damage.py](processing/algoritmi/clc_damage.py)
  - display name: "Associa classe di danno"
  - Overview: associa a ogni feature CLC un valore di danno secondo il mapping definito in `clc2damage.json`.
  - Input principali:
    - layer vettoriale poligonale CLC (`INPUT`)
    - `FIELD`: campo CLC da leggere
    - `CRS`: CRS di output (default EPSG:7791)
  - Output: layer poligonale con campo `DANNO` e copia del campo CLC (parametro `CLC_Danno`)
  - Note implementative: legge `clc2damage.json` dalla stessa cartella e crea un sink con i campi di output.

- `adbpo:flood_risk` — CalcRisk
  - file: [processing/algoritmi/flood_risk.py](processing/algoritmi/flood_risk.py)
  - display name: "Determina rischio massimo"
  - Overview: interseca layer di pericolosità e di esposizione/danno, applica matrici di rischio da `matrici_rischio.yaml` e calcola il rischio massimo per intersezione.
  - Input principali:
    - `HAZARD`: layer sorgente pericolosità
    - `HFIELD`: campo pericolosità (numerico)
    - `DAMAGE`: layer esposizione/danno
    - `DFIELD`: campo danno (numerico)
    - `MATRICI`: selezione delle matrici di rischio (definite in `matrici_rischio.yaml`)
    - `CRS`: CRS di output (default EPSG:7791)
  - Output: layer con colonne per ogni matrice selezionata (`R_<matrix>`) e `R_MAX` con il rischio massimo
  - Note implementative: esegue prima `native:intersection` tra i layer, poi applica le matrici caricate da YAML per calcolare i valori di rischio.

**Come usare gli algoritmi in QGIS**
- Dopo l'installazione del plugin nella cartella del progetto (o caricando il plugin in QGIS), gli algoritmi appaiono nella Processing Toolbox sotto: `AdBPo` e nel gruppo `Rischio aree allagabili`.
- ID algoritmo in `processing.run`:
  - `adbpo:risolvi_overlay_poligonali`
  - `adbpo:clc_danno`
  - `adbpo:flood_risk`

Esempio di esecuzione da script Python (all'interno di QGIS/PyQGIS environment):

```python
import processing

# Esempio: eseguire il mapping CLC→Danno
res = processing.run('adbpo:clc_danno',{
    'Corine Land Cover': layer_clc,
    'CAMPO': 'CLC_FIELD',
    'CRS': 'EPSG:7791',
    'CLC_Danno': 'memory:'
}, context=context, feedback=feedback)

# Esempio: eseguire il calcolo del rischio
res = processing.run('adbpo:flood_risk',{
    'HAZARD': hazard_layer,
    'HFIELD': 'P',
    'DAMAGE': damage_layer,
    'DFIELD': 'D',
    'MATRICI': ['default_matrix_name'],
    'CRS': 'EPSG:7791',
    'Rischio': 'memory:'
}, context=context, feedback=feedback)
```

**Dipendenze**
- QGIS (PyQGIS) >= 3.28
- PyQt5
- Librerie Python: `yaml` (PyYAML) per caricare `matrici_rischio.yaml`.

**File rilevanti**
- `main.py` — classe plugin che registra il provider: [main.py](main.py#L1)
- `processing/provider.py` — registra gli algoritmi nel provider `adbpo`: [processing/provider.py](processing/provider.py#L1)
- `processing/algoritmi/*` — implementazione degli algoritmi (vedi sopra)
- `processing/algoritmi/clc2damage.json` — mapping CLC→danno
- `processing/algoritmi/matrici_rischio.yaml` — matrici di rischio

**Limitazioni e consigli**
- Assicurarsi che i CRS dei layer in input siano coerenti; gli algoritmi offrono parametri CRS di output ma alcuni passaggi eseguono trasformazioni manuali.
- Testare su dataset ridotti prima di pipeline su larga scala.
- Validare i file `clc2damage.json` e `matrici_rischio.yaml` per formati e valori mancanti.

---
Documento generato automaticamente: verificare i file sorgente per dettagli di implementazione.
