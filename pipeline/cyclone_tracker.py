#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline/cyclone_tracker.py — Tracker mondial officiel des cyclones & typhons en temps réel.
========================================================================================
Collecte en Token 0 (zéro clé API, flux publics officiels) :
- NOAA NHC (National Hurricane Center) : Atlantique Nord, Caraïbes, Pacifique Est & Central.
- JTWC (Joint Typhoon Warning Center) : Pacifique Ouest (Typhons), Océan Indien, Pacifique Sud.

Génère un fichier 'cyclones_actifs.json' pour la carte interactive.
"""

import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "MonsieurMeteo-CycloneTracker/1.0 (+https://monsieurmeteo.github.io/gfs-weather-map/)"
}


def fetch_nhc_storms():
    """Récupère les systèmes tropicaux actifs suivis par le National Hurricane Center (NOAA)."""
    storms = []
    url = "https://www.nhc.noaa.gov/CurrentStorms.json"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("activeStorms", []):
                name = item.get("name", "").strip().title()
                classification = item.get("classification", "").strip()
                intensity_mph = float(item.get("intensity", 0))
                intensity_kmh = round(intensity_mph * 1.60934)
                
                # Coordonnées
                lat = float(item.get("latitudeNumeric") if item.get("latitudeNumeric") is not None else str(item.get("latitude", 0)).rstrip("NS"))
                lon = float(item.get("longitudeNumeric") if item.get("longitudeNumeric") is not None else str(item.get("longitude", 0)).rstrip("EW"))
                pressure = int(item.get("pressure", 1010))

                # Catégorie Saffir-Simpson
                cat = "Dépression Tropicale"
                if intensity_kmh >= 252:
                    cat = "Ouragan Catégorie 5 (Monstre)"
                elif intensity_kmh >= 209:
                    cat = "Ouragan Catégorie 4 (Majeur)"
                elif intensity_kmh >= 178:
                    cat = "Ouragan Catégorie 3 (Majeur)"
                elif intensity_kmh >= 154:
                    cat = "Ouragan Catégorie 2"
                elif intensity_kmh >= 119:
                    cat = "Ouragan Catégorie 1"
                elif intensity_kmh >= 63:
                    cat = "Tempête Tropicale"

                # Détermination du bassin
                basin = "antilles"
                if lon < -100:
                    basin = "pacifique_est"

                storms.append({
                    "id": item.get("id", f"NHC_{name}"),
                    "name": f"{classification} {name}".strip(),
                    "category": cat,
                    "wind_kmh": intensity_kmh,
                    "pressure_hpa": pressure,
                    "lat": round(lat, 2),
                    "lon": round(lon, 2),
                    "basin": basin,
                    "movement": f"{item.get('movementDir', 0)}° à {round(float(item.get('movementSpeed', 0))*1.609)} km/h",
                    "source": "NOAA / NHC",
                    "updated_at": item.get("lastUpdate", datetime.now(timezone.utc).isoformat()),
                })
    except Exception as e:
        print(f"[NHC] Erreur : {e}")

    return storms


def fetch_jtwc_storms():
    """Récupère les systèmes tropicaux actifs du Joint Typhoon Warning Center (Typhons Asie & Océanie)."""
    storms = []
    url = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read().decode("utf-8"))
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                desc = item.findtext("description", "")

                if any(k in title.upper() for k in ["WARNING", "TYPHOON", "CYCLONE", "TROPICAL STORM"]):
                    m_coords = re.search(r"NEAR\s+([0-9\.]+)\s*([NS])\s+([0-9\.]+)\s*([EW])", desc.upper())
                    lat, lon = 0.0, 0.0
                    if m_coords:
                        lat = float(m_coords.group(1)) * (-1 if m_coords.group(2) == "S" else 1)
                        lon = float(m_coords.group(3)) * (-1 if m_coords.group(4) == "W" else 1)

                    basin = "pacifique_ouest"
                    if lat < 0 and lon > 130:
                        basin = "pacifique_sud"
                    elif lat < 0 and lon < 100:
                        basin = "ocean_indien"
                    elif lat >= 0 and lon < 100:
                        basin = "ocean_indien_nord"

                    m_wind = re.search(r"SUSTAINED\s+WINDS\s+([0-9]+)\s*KTS", desc.upper())
                    wind_kmh = round(int(m_wind.group(1)) * 1.852) if m_wind else 100

                    cat = "Cyclone Tropical" if "CYCLONE" in title.upper() else "Typhon"
                    if wind_kmh >= 240:
                        cat = "Super-Typhon (Cat. 5)"
                    elif wind_kmh >= 180:
                        cat = "Typhon Très Violent"

                    clean_name = title.split(" - ")[0].replace("WARNING", "").strip().title()
                    storms.append({
                        "id": f"JTWC_{clean_name}",
                        "name": clean_name,
                        "category": cat,
                        "wind_kmh": wind_kmh,
                        "pressure_hpa": 960,
                        "lat": round(lat, 2),
                        "lon": round(lon, 2),
                        "basin": basin,
                        "movement": "En suivi JTWC",
                        "source": "US Navy / JTWC",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })
    except Exception as e:
        print(f"[JTWC] Info : {e}")

    return storms


def update_active_cyclones(out_file="cyclones_actifs.json"):
    """Agrège toutes les tempêtes actives dans le monde et produit le JSON."""
    all_storms = []
    all_storms.extend(fetch_nhc_storms())
    all_storms.extend(fetch_jtwc_storms())

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_active": len(all_storms),
        "storms": all_storms,
    }

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_path = os.path.join(base_dir, out_file)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(all_storms)} cyclone(s)/typhon(s) actif(s) mondialement -> {target_path}")
    return result


if __name__ == "__main__":
    update_active_cyclones()
