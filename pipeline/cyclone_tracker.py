#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline/cyclone_tracker.py — Tracker mondial officiel : Cyclones, Typhons ET INVESTs en temps réel.
==================================================================================================
Collecte en Token 0 (zéro clé API, 100 % flux publics officiels) :
- NOAA NHC (National Hurricane Center) :
    * Cyclones & Ouragans actifs (CurrentStorms.json)
    * INVESTs & Ondes sous surveillance 48h-7j (Tropical Weather Outlook TWO)
- JTWC (Joint Typhoon Warning Center) :
    * Typhons & Cyclones actifs (jtwc.rss)
    * INVESTs actifs Pacifique Ouest, Pacifique Sud & Océan Indien (ABPW10 & ABIO10)

Génère 'cyclones_actifs.json' pour la carte interactive.
"""

import io
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "MonsieurMeteo-CycloneTracker/2.0 (+https://monsieurmeteo.github.io/gfs-weather-map/)"
}


def parse_kmz_cone(kmz_url):
    """Télécharge et extrait le polygone officiel du cône d'incertitude depuis le KMZ du NHC."""
    if not kmz_url:
        return []
    try:
        req = urllib.request.Request(kmz_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = next((n for n in z.namelist() if n.endswith(".kml")), None)
            if not name:
                return []
            kml = z.read(name).decode("utf-8", errors="ignore")
        m = re.search(r"<coordinates>(.*?)</coordinates>", kml, re.DOTALL)
        if not m:
            return []
        pts = []
        raw_items = m.group(1).strip().split()
        step = max(1, len(raw_items) // 180)
        for item in raw_items[::step]:
            p = item.split(",")
            if len(p) >= 2:
                pts.append([round(float(p[0]), 3), round(float(p[1]), 3)])
        return pts
    except Exception as e:
        print(f"[KMZ Cone] Erreur {kmz_url} : {e}")
        return []


def parse_kmz_track(kmz_url):
    """Télécharge et extrait les points de trajectoire prévisionnelle (3 à 5 jours) depuis le KMZ du NHC."""
    if not kmz_url:
        return []
    try:
        req = urllib.request.Request(kmz_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = next((n for n in z.namelist() if n.endswith(".kml")), None)
            if not name:
                return []
            kml = z.read(name).decode("utf-8", errors="ignore")
        root = ET.fromstring(kml)
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        fcst_pts = []
        seen = set()
        for p in root.findall(".//kml:Placemark", ns):
            desc = p.findtext("kml:description", "", ns)
            coords = p.findtext(".//kml:coordinates", "", ns)
            if not coords:
                continue
            coords = coords.strip()
            if coords in seen:
                continue
            if "Forecast" in desc or "Advisory Information" in desc:
                seen.add(coords)
                m_time = re.search(r"Valid at:\s*(.*?)(?:<|\n)", desc)
                m_wind = re.search(r"Maximum Wind:\s*([0-9]+)\s*knots", desc)
                m_lead = re.search(r"([0-9]+)\s*hr Forecast", desc)
                lead = int(m_lead.group(1)) if m_lead else 0
                parts = coords.split(",")
                if len(parts) >= 2:
                    w_kts = int(m_wind.group(1)) if m_wind else 0
                    w_kmh = round(w_kts * 1.852)
                    cat_short = "TD"
                    if w_kmh >= 252:
                        cat_short = "H5"
                    elif w_kmh >= 209:
                        cat_short = "H4"
                    elif w_kmh >= 178:
                        cat_short = "H3"
                    elif w_kmh >= 154:
                        cat_short = "H2"
                    elif w_kmh >= 119:
                        cat_short = "H1"
                    elif w_kmh >= 63:
                        cat_short = "TS"
                    fcst_pts.append({
                        "lead_hours": lead,
                        "time": m_time.group(1).strip() if m_time else "",
                        "wind_kts": w_kts,
                        "wind_kmh": w_kmh,
                        "cat_short": cat_short,
                        "lon": round(float(parts[0]), 3),
                        "lat": round(float(parts[1]), 3),
                    })
        fcst_pts.sort(key=lambda x: x["lead_hours"])
        return fcst_pts
    except Exception as e:
        print(f"[KMZ Track] Erreur {kmz_url} : {e}")
        return []


def parse_kmz_best_track(kmz_url):
    """Télécharge et extrait la trajectoire historique passée (Best Track) depuis le KMZ du NHC."""
    if not kmz_url:
        return []
    try:
        req = urllib.request.Request(kmz_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = next((n for n in z.namelist() if n.endswith(".kml")), None)
            if not name:
                return []
            kml = z.read(name).decode("utf-8", errors="ignore")
        matches = re.findall(r"<coordinates>(.*?)</coordinates>", kml, re.DOTALL)
        pts = []
        for m in matches:
            for item in m.strip().split():
                parts = item.split(",")
                if len(parts) >= 2:
                    pt = [round(float(parts[0]), 3), round(float(parts[1]), 3)]
                    if not pts or pt != pts[-1]:
                        pts.append(pt)
        return pts
    except Exception as e:
        print(f"[KMZ Best Track] Erreur {kmz_url} : {e}")
        return []


def determine_cyclone_basin(lat, lon, default_basin=None):
    """Détermine le domaine cartographique mondial exact contenant le système selon ses coordonnées."""
    if lat is None or lon is None:
        return default_basin or "antilles"
    lat, lon = float(lat), float(lon)
    # 1. Pacifique Est & Hawaï (-180° à -100°O, 0°N à 45°N)
    if -180.0 <= lon <= -100.0 and 0.0 <= lat <= 45.0:
        return "pacifique_est"
    # 2. États-Unis & Golfe du Mexique (-128° à -66°O, 23°N à 52°N)
    if lat >= 23.0 and ((-128.0 <= lon < -75.0) or (-75.0 <= lon <= -66.0 and lat > 32.0)):
        return "etats_unis"
    # 3. Arc Antillais & Atlantique Tropical (-75° à -20°O, 5°N à 33°N)
    if -75.0 <= lon <= -20.0 and 5.0 <= lat <= 33.0:
        return "antilles"
    # Caraïbes occidentales
    if -95.0 <= lon < -75.0 and 8.0 <= lat < 23.0:
        return "antilles"
    # 4. Océan Indien Sud-Ouest (Madagascar • Réunion • Maurice : lat < 0, 35° à 85°E)
    if lat < 0.0 and 35.0 <= lon <= 85.0:
        return "ocean_indien"
    # 5. Océan Indien Nord (Golfe du Bengale • Mer d'Arabie • Inde : lat >= 0, 50° à 100°E)
    if lat >= 0.0 and 50.0 <= lon <= 100.0:
        return "ocean_indien_nord"
    # 6. Pacifique Sud & Océanie (lat < 0, lon >= 125 ou lon <= -170)
    if lat < 0.0 and (lon >= 125.0 or lon <= -170.0):
        return "pacifique_sud"
    # 7. Pacifique Ouest & Asie (Typhons Chine • Japon • Philippines : lat >= 0, 100° à 180°E)
    if lat >= 0.0 and 100.0 <= lon <= 180.0:
        return "pacifique_ouest"
    return default_basin or "antilles"


def fetch_nhc_storms():
    """Récupère les cyclones et tempêtes baptisés suivis par le National Hurricane Center (NOAA)."""
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

                lat = float(item.get("latitudeNumeric") if item.get("latitudeNumeric") is not None else str(item.get("latitude", 0)).rstrip("NS"))
                lon = float(item.get("longitudeNumeric") if item.get("longitudeNumeric") is not None else str(item.get("longitude", 0)).rstrip("EW"))
                pressure = int(item.get("pressure", 1010))

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

                basin = determine_cyclone_basin(lat, lon, "pacifique_est" if lon < -100 else "antilles")

                cone = parse_kmz_cone(item.get("trackCone", {}).get("kmzFile") if item.get("trackCone") else None)
                fcst_track = parse_kmz_track(item.get("forecastTrack", {}).get("kmzFile") if item.get("forecastTrack") else None)
                past_track = parse_kmz_best_track(item.get("bestTrackGIS", {}).get("kmzFile") if item.get("bestTrackGIS") else None)

                storms.append({
                    "id": item.get("id", f"NHC_{name}"),
                    "name": f"{classification} {name}".strip(),
                    "type": "cyclone",
                    "status_badge": "🔴",
                    "category": cat,
                    "wind_kmh": intensity_kmh,
                    "pressure_hpa": pressure,
                    "lat": round(lat, 2),
                    "lon": round(lon, 2),
                    "basin": basin,
                    "movement": f"{item.get('movementDir', 0)}° à {round(float(item.get('movementSpeed', 0))*1.609)} km/h",
                    "source": "NOAA / NHC",
                    "updated_at": item.get("lastUpdate", datetime.now(timezone.utc).isoformat()),
                    "cone_polygon": cone,
                    "forecast_track": fcst_track,
                    "past_track": past_track,
                })
    except Exception as e:
        print(f"[NHC Storms] Erreur : {e}")

    return storms


def fetch_nhc_disturbances():
    """Récupère les INVESTs et zones sous surveillance du NHC (Outlook Atlantique & Pacifique Est)."""
    invests = []
    targets = [
        ("https://www.nhc.noaa.gov/text/MIATWOAT.shtml", "antilles"),
        ("https://www.nhc.noaa.gov/text/MIATWOEP.shtml", "pacifique_est"),
    ]
    for url, basin_default in targets:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")

            # Nettoyage HTML
            clean = re.sub(r"<!--[\s\S]*?-->", "", raw)
            clean = re.sub(r"<[^>]+>", "", clean)

            # Recherche des paragraphes de perturbations
            blocks = re.split(r"\n(?=[0-9]\.|\b[A-Z][A-Za-z0-9\s]+:)", clean)
            for b in blocks:
                if "Formation chance" in b:
                    lines = [l.strip() for l in b.splitlines() if l.strip()]
                    if not lines:
                        continue
                    first_line = lines[0].rstrip(":")
                    if any(k in first_line for k in ["Special Tropical", "Tropical Weather", "For the North"]):
                        first_line = lines[1].rstrip(":") if len(lines) > 1 else "Zone sous surveillance"

                    m_inv = re.search(r"\(([A-Z]{2}[0-9]{2})\)", b)
                    inv_tag = m_inv.group(1) if m_inv else None
                    name = f"INVEST {inv_tag}" if inv_tag else f"INVEST ({first_line[:22]})"

                    m_48 = re.search(r"Formation chance through 48 hours\.\.\.([a-z]+)\.\.\.(?:near\s+)?([0-9]+)\s*percent", b, re.I)
                    m_7d = re.search(r"Formation chance through 7 days\.\.\.([a-z]+)\.\.\.(?:near\s+)?([0-9]+)\s*percent", b, re.I)

                    probs = []
                    if m_48:
                        probs.append(f"48h: {m_48.group(2)}%")
                    if m_7d:
                        probs.append(f"7j: {m_7d.group(2)}% ({m_7d.group(1).capitalize()})")
                    prob_str = " • ".join(probs) if probs else "En surveillance"

                    # Approximations de coordonnées ou zone
                    lat, lon = None, None
                    m_coords = re.search(r"near\s+latitude\s+([0-9\.]+)\s*([NS])\s*,\s*longitude\s+([0-9\.]+)\s*([EW])", b, re.I)
                    if m_coords:
                        lat = float(m_coords.group(1)) * (-1 if m_coords.group(2).upper() == "S" else 1)
                        lon = float(m_coords.group(3)) * (-1 if m_coords.group(4).upper() == "W" else 1)

                    invests.append({
                        "id": f"NHC_{inv_tag or 'DISTURB_' + str(abs(hash(first_line)) % 10000)}",
                        "name": name,
                        "type": "invest",
                        "status_badge": "🟡",
                        "category": "INVEST (Zone sous surveillance)",
                        "probability": prob_str,
                        "wind_kmh": 45,
                        "pressure_hpa": 1008,
                        "lat": round(lat, 2) if lat is not None else (15.0 if basin_default == "antilles" else 15.0),
                        "lon": round(lon, 2) if lon is not None else (-55.0 if basin_default == "antilles" else -110.0),
                        "basin": determine_cyclone_basin(lat, lon, basin_default),
                        "source": "NOAA / NHC (Outlook)",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })
        except Exception as e:
            print(f"[NHC Disturbances] Erreur : {e}")

    return invests


def fetch_jtwc_data():
    """Récupère à la fois les cyclones actifs et les INVESTs du JTWC (Asie, Océanie, Océan Indien)."""
    items = []
    # 1. Alertes actives
    url_rss = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
    try:
        req = urllib.request.Request(url_rss, headers=HEADERS)
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

                    basin = determine_cyclone_basin(lat, lon, "pacifique_ouest")

                    m_wind = re.search(r"SUSTAINED\s+WINDS\s+([0-9]+)\s*KTS", desc.upper())
                    wind_kmh = round(int(m_wind.group(1)) * 1.852) if m_wind else 100

                    cat = "Cyclone Tropical" if "CYCLONE" in title.upper() else "Typhon"
                    if wind_kmh >= 240:
                        cat = "Super-Typhon (Cat. 5)"
                    elif wind_kmh >= 180:
                        cat = "Typhon Très Violent"

                    clean_name = title.split(" - ")[0].replace("WARNING", "").strip().title()
                    items.append({
                        "id": f"JTWC_{clean_name.replace(' ', '_')}",
                        "name": clean_name,
                        "type": "cyclone",
                        "status_badge": "🔴",
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
        print(f"[JTWC RSS] Erreur : {e}")

    # 2. Bulletins d'investigation ABPW10 (Pacifique Ouest/Sud) et ABIO10 (Océan Indien)
    invest_sources = [
        ("https://www.metoc.navy.mil/jtwc/products/abpwweb.txt", "pacifique_ouest"),
        ("https://www.metoc.navy.mil/jtwc/products/abioweb.txt", "ocean_indien"),
    ]
    for url, def_basin in invest_sources:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8")

            matches = re.finditer(r"\(INVEST\s+([0-9]{2}[A-Z])\)\s+LOCATED\s+NEAR\s+([0-9\.]+)\s*([NS])\s+([0-9\.]+)\s*([EW])", text, re.I)
            for m in matches:
                inv_code = m.group(1).upper()
                lat = float(m.group(2)) * (-1 if m.group(3).upper() == "S" else 1)
                lon = float(m.group(4)) * (-1 if m.group(5).upper() == "W" else 1)

                snippet = text[m.start():m.start() + 500]
                m_pot = re.search(r"POTENTIAL FOR THE DEVELOPMENT OF A SIGNIFICANT TROPICAL CYCLONE\s+IS\s+(LOW|MEDIUM|HIGH)", snippet, re.I)
                pot = m_pot.group(1).upper() if m_pot else "SURVEILLANCE"

                basin = determine_cyclone_basin(lat, lon, def_basin)

                items.append({
                    "id": f"JTWC_INVEST_{inv_code}",
                    "name": f"INVEST {inv_code}",
                    "type": "invest",
                    "status_badge": "🟡",
                    "category": f"INVEST (Potentiel {pot})",
                    "probability": f"Potentiel cyclonique : {pot}",
                    "wind_kmh": 40,
                    "pressure_hpa": 1006,
                    "lat": round(lat, 2),
                    "lon": round(lon, 2),
                    "basin": basin,
                    "source": "US Navy / JTWC (Outlook)",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            print(f"[JTWC INVEST] Erreur {url} : {e}")

    return items


def update_active_cyclones(out_file="cyclones_actifs.json"):
    """Agrège l'ensemble des cyclones, typhons et INVESTs actifs mondialement."""
    all_systems = []
    all_systems.extend(fetch_nhc_storms())
    all_systems.extend(fetch_nhc_disturbances())
    all_systems.extend(fetch_jtwc_data())

    # Dédoublonnage par ID
    unique = {}
    for s in all_systems:
        unique[s["id"]] = s
    final_list = list(unique.values())

    # Tri : cyclones confirmés d'abord, puis INVESTs
    final_list.sort(key=lambda x: (0 if x.get("type") == "cyclone" else 1, -x.get("wind_kmh", 0)))

    cyclone_count = sum(1 for x in final_list if x.get("type") == "cyclone")
    invest_count = sum(1 for x in final_list if x.get("type") == "invest")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_active": len(final_list),
        "cyclones_count": cyclone_count,
        "invests_count": invest_count,
        "storms": final_list,
    }

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_path = os.path.join(base_dir, out_file)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    # Double sauvegarde sécurisée dans output/
    out_dir = os.path.join(base_dir, "output")
    if os.path.exists(out_dir):
        with open(os.path.join(out_dir, out_file), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {cyclone_count} cyclone(s) & {invest_count} INVEST(s) actif(s) mondialement -> {target_path}")
    return result


if __name__ == "__main__":
    update_active_cyclones()
