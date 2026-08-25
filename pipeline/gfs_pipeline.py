#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline GFS 0.25 Europe et France (NOAA / Open Data)
=====================================================
Portee : 10 Jours (H+00 a H+240, pas de 3h puis 6h)
Domaine : Europe Entiere et France (Lat 32-65N, Lon 18W-32E)
Resolution : 2200x1640 Mercator
"""

import os, sys, json, datetime, tempfile, urllib3, time
import requests, numpy as np
from PIL import Image
from scipy.interpolate import RegularGridInterpolator

urllib3.disable_warnings()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "gfs", "maps")
os.makedirs(OUTPUT_DIR, exist_ok=True)

sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))
from fetch_and_render_all import (
    PALETTES, apply_palette, ensure_dir, save_webp, write_manifest
)

WIDTH, HEIGHT = 2200, 1640
# Domaine etendu Europe et France
BOUNDS = {"south": 32.0, "west": -18.0, "north": 65.0, "east": 32.0}

def mercator_y(lat):
    r = np.radians(np.clip(lat, -85.0, 85.0))
    return np.log(np.tan(np.pi / 4.0 + r / 2.0))

N_Y = mercator_y(BOUNDS["north"])
S_Y = mercator_y(BOUNDS["south"])

def get_mercator_grid():
    lons = np.linspace(BOUNDS["west"], BOUNDS["east"], WIDTH, dtype=np.float32)
    ys = np.linspace(N_Y, S_Y, HEIGHT, dtype=np.float32)
    lats = np.degrees(2.0 * np.arctan(np.exp(ys)) - np.pi / 2.0).astype(np.float32)
    return np.meshgrid(lons, lats)

GRID_LONS, GRID_LATS = get_mercator_grid()

def regrid_europe(data, src_lats, src_lons):
    if src_lats[0] > src_lats[-1]:
        src_lats = src_lats[::-1]
        data = data[::-1, :]
    if src_lons[0] > src_lons[-1]:
        src_lons = src_lons[::-1]
        data = data[:, ::-1]
    interp = RegularGridInterpolator(
        (src_lats, src_lons), data, method="linear",
        bounds_error=False, fill_value=None
    )
    pts = np.column_stack((GRID_LATS.ravel(), GRID_LONS.ravel()))
    return interp(pts).reshape((HEIGHT, WIDTH)).astype(np.float32)

def run_gfs_pipeline(max_hours=240):
    try:
        import cfgrib
    except ImportError:
        print("Installation ou import de cfgrib...")
        cfgrib = None

    print(f"🌍 Lancement du Pipeline GFS 0.25° Europe & France (H+00 à H+{max_hours})...")
    now = datetime.datetime.now(datetime.timezone.utc)
    # Détection du dernier run GFS (00Z, 06Z, 12Z, 18Z) disponible
    run_h = (now.hour // 6) * 6
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    # Si le run actuel a moins de 3h45, on prend le précédent
    if (now - run_dt).total_seconds() < 13500:
        run_dt -= datetime.timedelta(hours=6)
    
    day_str = run_dt.strftime("%Y%m%d")
    h_str = "%02d" % run_dt.hour
    print(f"📅 Run GFS sélectionné : {day_str} {h_str}Z")

    lead_hours = list(range(0, min(max_hours + 1, 121), 3)) + list(range(126, max_hours + 1, 6))

    gfs_req_vars = ["TMP", "DPT", "UGRD", "VGRD", "GUST", "APCP", "CAPE", "SNOD", "PRMSL", "PRES", "RH", "TCDC", "HGT"]
    gfs_layer_var = {
        "temperature": "TMP",
        "temperature_ressentie": "TMP",
        "point_rosee": "DPT",
        "humidex": "TMP",
        "pluie_1h": "APCP",
        "pluie_cumul": "APCP",
        "reflectivite": "APCP",
        "graupel": "APCP",
        "vent": "UGRD",
        "rafales": "GUST",
        "rafales_cumul": "GUST",
        "nebulosite": "TCDC",
        "mucape": "CAPE",
        "neige": "SNOD",
        "neige_au_sol": "SNOD",
        "equivalent_eau_neige": "SNOD",
        "pression": "PRMSL",
        "pression_surface": "PRES",
        "humidite": "RH",
        "geopotentiel_500": "HGT"
    }

    LAYERS = list(gfs_layer_var.keys())
    steps = []
    max_gust_field = None

    for lh in lead_hours:
        vt = run_dt + datetime.timedelta(hours=lh)
        fhh = "%03d" % lh
        step = {"lead_hour": lh, "valid_time": vt.isoformat(), "files": {}}
        print(f"  ⚡ [GFS Europe] Traitement échéance H+{lh:03d}...", end="", flush=True)

        params = {
            "dir": f"/gfs.{day_str}/{h_str}/atmos",
            "file": f"gfs.t{h_str}z.pgrb2.0p25.f{fhh}",
            "subregion": "",
            "leftlon": "-18",
            "rightlon": "32",
            "toplat": "65",
            "bottomlat": "32",
        }
        for v in gfs_req_vars:
            params["var_" + v] = "on"
        params.update({
            "lev_2_m_above_ground": "on",
            "lev_10_m_above_ground": "on",
            "lev_surface": "on",
            "lev_mean_sea_level": "on",
            "lev_entire_atmosphere": "on",
            "lev_500_mb": "on"
        })

        grib_bytes = None
        try:
            r = requests.get(
                "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl",
                params=params, timeout=45, verify=False
            )
            if r.status_code == 200 and len(r.content) > 1000:
                grib_bytes = r.content
        except Exception as err:
            pass

        cached = {}
        if grib_bytes and cfgrib is not None:
            with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as tf:
                tf.write(grib_bytes)
                tmp = tf.name
            try:
                for ds in cfgrib.open_datasets(tmp):
                    for v in ds.data_vars:
                        vu = v.upper()
                        if vu not in cached:
                            cached[vu] = (ds[v].values, ds.latitude.values, ds.longitude.values)
            except Exception:
                pass
            finally:
                try: os.remove(tmp)
                except: pass

        for layer in LAYERS:
            dst = os.path.join(OUTPUT_DIR, layer, f"{lh:03d}.webp")
            ensure_dir(os.path.dirname(dst))
            step["files"][layer] = f"maps/{layer}/{lh:03d}.webp"

            if layer == "vent":
                if "UGRD" in cached and "VGRD" in cached:
                    u, la, lo = cached["UGRD"]
                    v = cached["VGRD"][0] if len(cached["VGRD"]) > 0 else u
                    spd = np.sqrt(u.astype(np.float32) ** 2 + v.astype(np.float32) ** 2) * 3.6
                    save_webp(regrid_europe(spd, la, lo), layer, dst)
                continue

            key = gfs_layer_var.get(layer, "TMP")
            if key in cached:
                d, la, lo = cached[key]
                if layer in ("temperature", "temperature_ressentie", "humidex") and d.max() > 200:
                    d = d - 273.15
                elif layer == "point_rosee" and d.max() > 200:
                    d = d - 273.15
                elif layer in ("pression", "pression_surface") and d.max() > 10000:
                    d = d / 100.0
                elif layer in ("rafales", "rafales_cumul") and d.max() < 200:
                    d = d * 3.6
                elif layer == "geopotentiel_500" and d.max() > 1000:
                    d = d / 10.0  # dam

                rf = regrid_europe(d, la, lo)
                if layer == "rafales_cumul":
                    max_gust_field = rf.copy() if max_gust_field is None else np.maximum(max_gust_field, rf)
                    save_webp(max_gust_field, layer, dst)
                else:
                    save_webp(rf, layer, dst)

        print(" OK")
        steps.append(step)

    # Écriture du manifest officiel
    manifest_data = {
        "model": "gfs",
        "model_name": "GFS 0.25° Europe & France",
        "provider": "NOAA (National Oceanic and Atmospheric Administration)",
        "resolution": "0.25° (~25 km)",
        "run_time": run_dt.isoformat(),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bounds": BOUNDS,
        "width": WIDTH,
        "height": HEIGHT,
        "steps": steps,
        "layers": {
            "temperature": {"label": "Température à 2 m", "unit": "°C"},
            "temperature_ressentie": {"label": "Température ressentie", "unit": "°C"},
            "point_rosee": {"label": "Point de rosée à 2 m", "unit": "°C"},
            "humidex": {"label": "Indice Humidex", "unit": ""},
            "pluie_1h": {"label": "Précipitations 3h", "unit": "mm"},
            "pluie_cumul": {"label": "Précipitations cumulées", "unit": "mm"},
            "reflectivite": {"label": "Réflectivité radar", "unit": "dBZ"},
            "graupel": {"label": "Grésil / Graupel", "unit": "mm"},
            "vent": {"label": "Vent moyen à 10 m", "unit": "km/h"},
            "rafales": {"label": "Rafales maximales", "unit": "km/h"},
            "rafales_cumul": {"label": "Rafales maximales cumulées", "unit": "km/h"},
            "nebulosite": {"label": "Nébulosité totale", "unit": "%"},
            "mucape": {"label": "Instabilité orageuse (MUCAPE)", "unit": "J/kg"},
            "neige": {"label": "Chutes de neige", "unit": "cm"},
            "neige_au_sol": {"label": "Épaisseur neige au sol", "unit": "cm"},
            "equivalent_eau_neige": {"label": "Cumul neigeux équiv. eau", "unit": "mm"},
            "pression": {"label": "Pression niveau mer", "unit": "hPa"},
            "pression_surface": {"label": "Pression au sol", "unit": "hPa"},
            "humidite": {"label": "Humidité relative à 2 m", "unit": "%"},
            "geopotentiel_500": {"label": "Géopotentiel Z500", "unit": "dam"}
        }
    }

    manifest_path = os.path.join(OUTPUT_DIR, "index.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)
    print(f"🎉 Manifest GFS enregistré avec succès dans {manifest_path} !")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline GFS Europe & France")
    parser.add_argument("--max-hours", type=int, default=24, help="Échéance max en heures (ex: 24, 48, 120)")
    args = parser.parse_args()
    run_gfs_pipeline(max_hours=args.max_hours)

