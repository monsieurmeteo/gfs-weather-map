# ⚡ Cartes Météo GFS & ARPEGE — Europe & France

Plateforme cartographique HD (2200×1640, projection Mercator unique) des modèles
**GFS 0,25° (NOAA)** et **ARPEGE Europe 0,1° (Météo-France, open data)** —
automatisée 24/7 via GitHub Actions et publiée sur GitHub Pages.

| Modèle | Résolution | Domaine | Échéances | Source |
|---|---|---|---|---|
| **GFS Europe** | 0,25° (~25 km) | Europe synoptique | H+00 → H+120 (3 h) | NOAA NOMADS (open data) |
| **GFS France** | 0,25° (~25 km) | France métropolitaine + Corse | H+00 → H+120 (3 h) | NOAA NOMADS (open data) |
| **ARPEGE Europe** | 0,1° (~11 km) | Europe | H+00 → H+102 (3 h) | Météo-France open data (data.gouv.fr) |

> 🖥️ **Site en ligne** : <https://monsieurmeteo.github.io/gfs-weather-map/>

---

## 🚀 Ce que fait l'outil

1. **Télécharge** les sorties des modèles (GRIB2) en open data, **sans clé API** :
   - GFS via le filtre sous-région de NOMADS (TLS vérifié, timeouts, 3 tentatives) ;
   - ARPEGE via le bucket S3 `meteofrance-pnt` avec **extraction sélective des
     messages GRIB2** (requêtes HTTP Range) : ~0,5 Go téléchargés au lieu de 3,7 Go.
2. **Décode** (cfgrib/eccodes), régrid sur une grille Mercator unique 2200×1640
   (domaines définis **une seule fois** dans `pipeline/domains.py`).
3. **Rend** des dalles WebP avec les palettes météociel, sondes au survol (HKV1),
   communes (couche villes), manifeste `index.json` exact par modèle.
4. **Déploie** sur GitHub Pages dans le même workflow (artefact) — les dalles ne
   sont **jamais commitées** dans git.

### Couches (par modèle, selon disponibilité réelle des champs)

Température, température ressentie (formules physiques), point de rosée,
humidex, vent, rafales + cumul, nébulosité, nuages bas/moyens/élevés, humidité,
MUCAPE, pression MSL, pression au sol (GFS), **géopotentiel 500 hPa + isobares**
(couche maîtresse), précipitations 3 h, précipitations cumulées, neige au sol.

> ⚠️ Honnêteté des données : les couches physiquement absentes des produits GFS /
> ARPEGE (réflectivité radar, graupel) ne sont **pas** affichées (elles étaient
> simulées à tort dans l'ancienne version).

---

## 🧱 Architecture

```
.github/workflows/gfs_cron.yml   (schedule 05:30/11:30/17:30/23:30 UTC + dispatch)
  └─ python pipeline/run_all.py --max-hours 120 --models gfs,arpege
       ├─ generate_fond_gfs.py (fonds Europe + France, alignés sur les dalles)
       ├─ gfs_open_data.py     → output/gfs/maps + output/gfs_france/maps
       ├─ arpege_open_data.py  → output/arpege/maps (gribscan sélectif)
       └─ assemble _site → upload-pages-artifact → deploy-pages
```

| Fichier | Rôle |
|---|---|
| `pipeline/domains.py` | **Source unique** des domaines (Europe/France) et grilles Mercator |
| `pipeline/render.py` | Palettes, regrid, WebP, sondes HKV1, communes, manifeste, Z500+isobares, formules physiques |
| `pipeline/gribscan.py` | Extraction sélective GRIB2 par requêtes HTTP Range (ARPEGE) |
| `pipeline/gfs_open_data.py` | Pipeline GFS (NOMADS, décodage cfgrib, Europe + France) |
| `pipeline/arpege_open_data.py` | Pipeline ARPEGE (S3 Météo-France, paquets SP1/SP2/IP1) |
| `pipeline/generate_fond_gfs.py` | Fonds de carte, masque des terres, frontières SVG (par domaine) |
| `pipeline/palettes_data.py` | Palettes météociel (source Python, extraites de l'ancien module) |
| `js/arome-map.js` | Moteur cartographique (WebGL + fallback 2D, sonde, exports, GIF) |
| `js/regions.js` | Régions/villes : centres et zooms (France → domaine France, pays → Europe) |
| `index.html` | Carte interactive + sélecteur de modèle (GFS Europe / GFS France / ARPEGE) |

## ⚙️ Automatisation

- **Cron** : 4×/jour (00Z/06Z/12Z/18Z, décalage de disponibilité pris en compte).
- **Dispatch manuel** : entrées validées (`max_hours` 24-120, `models`).
- **Déploiement** : intégré au workflow (Pages source = GitHub Actions) ;
  aucun push de données, aucun `git pull --rebase -X theirs` dangereux.

## 💻 Développement local

```bash
python -m http.server 8791        # servir le site (si output/ généré)
python -u pipeline/run_all.py --max-hours 24 --models gfs,arpege   # pipeline complet
```

## 🧭 Notes

- Le dépôt **arome-weather-map** (AROME HD 1,3 km) reste séparé et inchangé.
- Dépôt public → minutes GitHub Actions gratuites ; artefact Pages < 1 Go.
- Après modification du code, **Ctrl+F5** (le manifeste porte sa date de génération).
