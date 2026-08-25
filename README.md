# ⚡ Météo AROME HD — Cartographie Météorologique Haute Définition

Plateforme météorologique en temps réel développée par **Météo-Climat Pro** / **Monsieur Météo**.
Décodage des sorties du modèle **AROME HD 1,3 km de Météo-France** (open data gratuit, sans clé API) et
rendu cartographique interactif style « météociel / météo-npdc », automatisé 24/7 via GitHub Actions.

---

## 🔗 Liens utiles

| Quoi | URL |
|---|---|
| 🌐 **Site en ligne (carte interactive)** | <https://monsieurmeteo.github.io/arome-weather-map/> |
| 🏘️ **Prévisions par commune** (recherche, géoloc, tableaux) | <https://monsieurmeteo.github.io/arome-weather-map/previsions.html> |
| 📦 **Dépôt GitHub** | <https://github.com/monsieurmeteo/arome-weather-map> |
| ⏱️ **Runs GitHub Actions (pipeline météo)** | <https://github.com/monsieurmeteo/arome-weather-map/actions/workflows/update_models.yml> |
| 📊 **Source des données (data.gouv.fr)** | <https://www.data.gouv.fr/fr/datasets/paquets-arome-resolution-0-01deg/> |
| 🗺️ **Référence visuelle** (rendu cible) | <https://meteo-npdc.fr> |

> ⚠️ **Cache navigateur** : après chaque mise à jour du code, faire **Ctrl+F5** (ou vider le cache).
> La version du moteur est dans `index.html` : `js/arome-map.js?v=5.4.0` — la bumper à chaque changement de `arome-map.js`.

---

## 🚀 Ce que fait l'outil

1. **Télécharge** les sorties GRIB2 d'AROME HD (0,01° ≈ 1,3 km) publiées par Météo-France sur l'open data
   (paquets `HP1`, `SP1`, `SP2`, `SP3` — aucune clé API requise).
2. **Décode** les champs (température, vent, rafales, pluie, neige, orages, pression, humidité…) via `eccodes`/`cfgrib`.
3. **Régrid** chaque champ sur une grille Mercator **2200×1640** limitée à la France métropolitaine + Corse
   (cadrage réduit `lon -8.5…13.5 / lat 39.5…52.5`, comme météo-npdc).
4. **Rend** des dalles WebP colorées avec les **palettes météociel exactes** + fond de carte Positron
   (pays voisins visibles) + frontières SVG (départements/ régions / pays).
5. **Publie** le tout sur GitHub Pages automatiquement toutes les 3 h (cron) — aucune intervention manuelle.

Le site affiche la carte en **plein écran immersif** (le maillage couvre tout le domaine AROME, y compris
la mer et les pays voisins, comme la référence météo-npdc), avec :
- 22 couches météo commutables,
- timeline H+00 → H+51 (52 échéances), lecture animée (GIF exportable),
- survol pixel (sonde de valeurs), épingle, zoom/pan fluides,
- recherche/zoom par région (France, Hauts-de-France, Normandie, Île-de-France, …),
- **export PNG / JPEG / GIF** haute résolution avec cartouche professionnel,
  légende colorimétrique et villes prioritaires par région,
- page **prévisions par commune** : recherche par nom ou code postal, géolocalisation,
  tableaux horaires (général / orages / neige), records journaliers, rafale max et échéance.

---

## 🧱 Architecture

```
┌─────────────────────────── GitHub Actions (cron 3 h) ───────────────────────────┐
│  .github/workflows/update_models.yml                                           │
│    └─ python -u pipeline/arome_open_data.py                                     │
│         ├─ Télécharge les GRIB2 (HP1/SP1/SP2/SP3) du run le plus récent        │
│         ├─ pipeline/fetch_and_render_all.py  → regrid + palettes → WebP        │
│         ├─ pipeline/generate_fond.py        → fond Positron + masque + SVG     │
│         ├─ pipeline/render_arome_grib.py    → (briques de rendu partagées)     │
│         ├─ Écrit output/arome/maps/ (dalles, probes, communes, manifeste)      │
│         ├─ Commit + push (merge -X ours) sur main                              │
│         └─ Déploiement GitHub Pages intégré (configure-pages + deploy-pages)   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
┌────────────────────────── GitHub Pages (statique, sans serveur) ───────────────┐
│  index.html        → carte interactive (header 2 barres + timeline + légende)  │
│  previsions.html   → tableau de bord par commune (design premium sombre)       │
│  js/arome-map.js   → moteur carte : WebGL (shader) + fallback 2D, projection   │
│                      UNIQUE computeMapRect (raster/vecteurs/labels/probes/     │
│                      export/GIF tous alignés), export 2200×1640, GIF, probes   │
│  js/palettes.js    → 22 palettes météociel (stops exacts) + ticks + CSS        │
│  js/regions.js     → zones France/régions : centres, zooms, villes officielles │
│  js/previsions.js  → moteur de la page commune (MCV2, graphiques, tableaux)    │
│  output/arome/maps/→ données générées par le pipeline (voir plus bas)          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Détail des fichiers clés

| Fichier | Rôle |
|---|---|
| `pipeline/arome_open_data.py` | Orchestrateur : run le plus récent, téléchargement GRIB2, calcul des champs dérivés (température ressentie, humidex, LCL, risque orage/neige…), rendu, manifeste, probes, fichiers communaux |
| `pipeline/fetch_and_render_all.py` | `BOUNDS` réduit (39.5/-8.5/52.5/13.5), `WIDTH=2200`, `HEIGHT=1640`, regrid Mercator (interpolation bilinéaire), application des palettes |
| `pipeline/generate_fond.py` | Fond de carte style Positron (pays voisins), masque France, frontières SVG (3 niveaux d'épaisseur = département/région/pays) |
| `js/arome-map.js` | Moteur complet : chargement manifeste, WebGL + fallback 2D, `computeMapRect` (projection unique cover+clamp), cadrage France automatique, vecteurs, labels villes (anti-collision), probes HKV1, export PNG/JPEG/GIF, zoom/pan/épingle |
| `js/palettes.js` | `window.getLayerPalette(key)`, `paletteGradientCSS`, `paletteTicks`, `WEATHER_PALETTES` |
| `js/regions.js` | `window.Europe1Regions` : `{france, hdf, normandie, ile-de-france, grand-est, bretagne, pdl, cvl, bfc, naq, ara, occitanie, paca, corse, cnews}` avec `center`, `zoom`, `cities[]` |

---

## 📦 Données générées — `output/arome/maps/`

| Élément | Format | Description |
|---|---|---|
| `index.json` | JSON | Manifeste : `model_name`, `run_time`, `bounds`, `steps[]` (52 échéances H+00…H+51 avec fichiers WebP + probes), `layers{}` (label/unité/décimales), `places`, `overlay` |
| `{layer}/{lead}.webp` | WebP 2200×1640 | Dalle météo du champ, couleurs palette météociel, alpha = données (NaN → transparent) |
| `fond.webp` | WebP 2200×1640 | Fond de carte Positron : océan (143,163,184), terres (237,234,226), France (232,228,218) |
| `mask_france.png` | PNG 2200×1640 | Masque France (255 = France) — sert au **cadrage intelligent** (bbox du maillage) |
| `frontieres.svg` | SVG | 3 jeux de chemins : départements (stroke-width ≤ 1.0), régions (≤ 1.6), pays/côtes (épais) |
| `communes.json` | JSON | ~34 746 communes : `[nom, population, lat, lon, code, dept]` triées par population |
| `communes/{dept}.bin.gz` | MCV2 binaire gzip | 37 colonnes int16 par commune du département (température, vent, rafales cumulées, neige, orages, altitude…), NaN = `-32768` |
| `values/{layer}/{lead}.hkv.gz` | HKV1 binaire gzip | Grille de valeurs 440×328 pour la **sonde au survol** : en-tête `HKV1` + w u16 + h u16 + min f32 + max f32 + données u16 (65535 = NaN) |

### Format MCV2 (fichiers communaux)
- 37 colonnes `int16` (noms sur 32 octets, données alignées 2 octets), NaN marqué `-32768`.
- Valeur réelle : `q * colScale[ci] - colOffset[ci]` (échelles/offsets par colonne).
- Colonnes notables : `temperature_c`, `wind_gust_max_kmh` (rafale max cumulée), `thunder_risk_code`, `snow_risk_code`, `altitude_m`…

---

## 🛰️ Sources de données

- **Dataset** : <https://www.data.gouv.fr/api/1/datasets/paquets-arome-resolution-0-01deg/>
- **URL GRIB2** (pattern) :
  ```
  https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt/{run}/arome/001/{pkg}/arome__001__{pkg}__{lead:02d}H__{run}.grib2
  ```
  avec `{pkg}` ∈ `HP1` (champs de base) / `SP1` / `SP2` / `SP3` (champs spécialisés).
- **Mapping champs** (noms `cfgrib`) : `t2m`, `r2`, `u10/v10`, `efg10/nfg10` (rafales), `cape`, `sp`,
  `lcc/mcc/hcc` (nuages), `tirf` (pluie cumulée — **horaire = cumul(H+n) − cumul(H+n−1)**),
  `tsnowp` (neige), `tgrp` (grésil), `refl` (réflectivité radar dBZ), `h` (altitude).
- **Grille native AROME** : régulière `regular_ll`, NI=2801, NJ=1791, LAT0=55.4, LON0=−12.0, STEP=0.01.

---

## ⚙️ Automatisation (GitHub Actions)

### `update_models.yml` — Pipeline météo (cron `15 1,4,7,10,13,16,19,22 * * *`, toutes les 3 h)
1. `checkout` + Python 3.11 + `libeccodes` + `numpy pillow requests eccodes cfgrib xarray scipy`.
2. `python -u pipeline/arome_open_data.py` (téléchargement, décodage, rendu, probes, communes).
3. Commit de `output/` + **merge `-X ours`** (on garde nos artefacts, évite les conflits binaires) + push.
4. Déploiement GitHub Pages **intégré** (le push du bot ne redéclenche pas `deploy-pages.yml`).

> ⚠️ **Règles d'or** :
> - **Ne jamais pousser manuellement pendant qu'un run est actif** (conflit de commit → cartes perdues).
>   Attendre la fin du run, ou rebaser son commit sur `FETCH_HEAD` avant de pousser.
> - `concurrency: weather-pipeline` avec `cancel-in-progress: false` : les runs manuels se mettent en file
>   derrière le cron (ne pas les annuler, ils finiront par passer).
> - Le commit automatique pousse en `-X ours` : si vous avez poussé entre-temps, vos fichiers `output/`
>   peuvent être écrasés au merge suivant — c'est voulu (les cartes sont régénérées).

### `deploy-pages.yml` — Déploiement statique (sur push `main`)
Copie `index.html`, `previsions.html`, `logo.png`, `js/`, `css/`, `output/` vers `_site/`
puis `configure-pages` → `upload-pages-artifact` → `deploy-pages`.

---

## 💻 Développement local

```bash
# 1. Servir le site (les données output/ existent déjà dans le repo)
python -m http.server 8791
#    → http://127.0.0.1:8791

# 2. Relancer le pipeline complet (nécessite accès internet + libeccodes)
python -u pipeline/arome_open_data.py
```

> ⚠️ **Pièges locaux connus** :
> - Le pipeline écrit des fichiers GRIB temporaires ; si l'environnement bloque `%TEMP%`
>   (sandbox), le fallback local échoue → les données viennent des runs GitHub (cron).
> - Le rendu WebGL utilise `resolvePath('maps/...')` relatif à `output/arome/` : servir depuis la racine
>   du repo (pas d'ouverture en `file://`).
> - Bumper `?v=` de `arome-map.js` dans `index.html` + **Ctrl+F5** après chaque modification.

### Tester les cadrages (sans navigateur)
La fonction de projection unique est `computeMapRect(width, height, transform)` dans `js/arome-map.js` :
- vue France (scale ≤ 1.15) : **cover + clamp** sur le bbox du masque France → jamais de bandes vides,
  la France (Corse incluse) tient entière sur les ratios paysage ;
- zoom (région/département) : cover pur (le surplus est découpé, jamais de déformation) ;
- transition 1.0 → 1.15 **interpolée** (pas de saut au premier zoom).

---

## 🎯 Conventions & décisions de design

- **Rendu cible** : météo-npdc.fr — fond Positron clair, maillage visible sur tout le domaine,
  France proportionnelle (jamais étirée), bordure de domaine sombre.
- **Palettes** : couleurs **exactes** de meteociel.fr (voir `js/palettes.js`, stops par palier).
- **UI** : dark premium, accent cyan `#00d2ff` / `#38bdf8`, header top bar 62 px + command bar 86 px,
  contrôles 56 px, radius 14 px, timeline 70 px, légende compacte en bas à gauche.
- **Ne jamais modifier** : la logique météo, les calculs, les paramètres, les exports de données —
  uniquement l'UI/UX et le rendu (toute évolution data = nouvelle branche + revue).
- **Cartouche export** : « AROME HD • Température à 2 m (°C) » — les libellés propres viennent de
  `js/palettes.js` (pas du manifeste brut qui contient « degC »).

---

## 🧭 Prochaines étapes possibles

- Réactiver les autres modèles (ARPEGE, ICON-EU, GFS, ECMWF) dans le pipeline multi-modèles.
- Ajouter des couches supplémentaires (isobares, theta-e, indices de soulèvement…).
- Améliorer la page commune (graphiques horaires, comparateur multi-modèles).
- PWA / installation, partage réseaux sociaux (OG image générée).

---

© 2026 Météo-Climat Pro — Tous droits réservés.
