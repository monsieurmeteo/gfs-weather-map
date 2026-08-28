#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probabilities_24h.py — Cartes de Probabilités Multi-Modèles sur 24h (Météo-Climat Pro)
========================================================================================
Calcule les probabilités de dépassement de seuils critiques par tranche de 24 heures :
- J+0 (0-24h), J+1 (24-48h), J+2 (48-72h), J+3 (72-96h), J+4 (96-120h), J+5 (120-144h), J+6 (144-168h), J+7 (168-192h)

18 Calques de Probabilités calculés en parallèle :
- Chaleur : P(Tmax >= 25°C), P(Tmax >= 30°C), P(Tmax >= 35°C), P(Tmax >= 40°C)
- Gelée   : P(Tmin <= 0°C), P(Tmin <= -5°C)
- Vent    : P(Rafales >= 60 km/h), P(Rafales >= 80 km/h), P(Rafales >= 100 km/h), P(Rafales >= 120 km/h)
- Pluie   : P(Cumul 24h >= 10 mm), P(Cumul 24h >= 25 mm), P(Cumul 24h >= 50 mm), P(Cumul 24h >= 70 mm)
- Neige   : P(Neige 24h >= 1 cm), P(Neige 24h >= 5 cm)
- Orages  : P(MUCAPE max >= 500 J/kg), P(MUCAPE max >= 1500 J/kg)
"""
import os
import sys
import glob
import gzip
import struct
import json
import re
import datetime
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))

from domains import EUROPE, FRANCE
from render import save_webp, write_hkv, write_manifest, write_places, ensure_dir


PROB_LAYERS = {
    "prob_tmax_25":   ("Probabilité Tmax ≥ 25 °C (24h)",   "%", 0, "🔥 Chaleur & Canicule"),
    "prob_tmax_30":   ("Probabilité Tmax ≥ 30 °C (24h)",   "%", 0, "🔥 Chaleur & Canicule"),
    "prob_tmax_35":   ("Probabilité Tmax ≥ 35 °C (24h)",   "%", 0, "🔥 Chaleur & Canicule"),
    "prob_tmax_40":   ("Probabilité Tmax ≥ 40 °C (24h)",   "%", 0, "🔥 Chaleur & Canicule"),
    "prob_tmin_0":    ("Probabilité Gelée Tmin ≤ 0 °C (24h)", "%", 0, "❄️ Gel & Hiver"),
    "prob_tmin_m5":   ("Probabilité Forte Gelée ≤ -5 °C",  "%", 0, "❄️ Gel & Hiver"),
    "prob_vent_60":   ("Probabilité Rafales ≥ 60 km/h (24h)", "%", 0, "💨 Vent & Tempêtes"),
    "prob_vent_80":   ("Probabilité Rafales ≥ 80 km/h (24h)", "%", 0, "💨 Vent & Tempêtes"),
    "prob_vent_100":  ("Probabilité Rafales ≥ 100 km/h (24h)","%", 0, "💨 Vent & Tempêtes"),
    "prob_vent_120":  ("Probabilité Rafales ≥ 120 km/h (24h)","%", 0, "💨 Vent & Tempêtes"),
    "prob_pluie_10":  ("Probabilité Pluie 24h ≥ 10 mm",    "%", 0, "🌧️ Fortes Pluies"),
    "prob_pluie_25":  ("Probabilité Pluie 24h ≥ 25 mm",    "%", 0, "🌧️ Fortes Pluies"),
    "prob_pluie_50":  ("Probabilité Pluie 24h ≥ 50 mm",    "%", 0, "🌧️ Fortes Pluies"),
    "prob_pluie_70":  ("Probabilité Pluie 24h ≥ 70 mm",    "%", 0, "🌧️ Fortes Pluies"),
    "prob_neige_1":   ("Probabilité Neige 24h ≥ 1 cm",     "%", 0, "❄️ Gel & Hiver"),
    "prob_neige_5":   ("Probabilité Neige 24h ≥ 5 cm",     "%", 0, "❄️ Gel & Hiver"),
    "prob_mucape_500":("Probabilité Risque Orageux (24h)", "%", 0, "⚡ Orages & Instabilité"),
    "prob_mucape_1500":("Probabilité Orages Violents (24h)","%", 0, "⚡ Orages & Instabilité"),
}


def read_hkv(path):
    try:
        with gzip.open(path, "rb") as gz:
            magic = gz.read(4)
            if magic != b"HKV1":
                return None
            w, h = struct.unpack("<HH", gz.read(4))
            gmin, gmax = struct.unpack("<ff", gz.read(8))
            raw = np.frombuffer(gz.read(), dtype=np.uint16)
            if len(raw) != w * h:
                return None
            vals = np.where(
                raw == 65535,
                np.nan,
                gmin + (raw.astype(np.float32) / 65534.0) * (gmax - gmin)
            ).reshape((h, w))
            return vals
    except Exception:
        return None


def get_model_daily_summary(model_key, layer_key, start_hour, end_hour, operation="max"):
    m_dir = os.path.join(BASE_DIR, "output", model_key, "maps", "values", layer_key)
    if not os.path.isdir(m_dir):
        return None

    grids = []
    for f in glob.glob(os.path.join(m_dir, "*.hkv.gz")):
        m = re.match(r"^(\d{3})\.hkv\.gz$", os.path.basename(f))
        if m:
            lead = int(m.group(1))
            if start_hour <= lead <= end_hour:
                g = read_hkv(f)
                if g is not None:
                    if g.shape != (328, 440):
                        im = Image.fromarray(g.astype(np.float32)).resize((440, 328), resample=Image.BILINEAR)
                        g = np.array(im)
                    grids.append(g)

    if not grids:
        return None

    stack = np.stack(grids, axis=0)
    if operation == "max":
        return np.nanmax(stack, axis=0)
    elif operation == "min":
        return np.nanmin(stack, axis=0)
    elif operation == "sum":
        return np.nansum(stack, axis=0)
    return np.nanmean(stack, axis=0)


def calc_prob(grids, operator, threshold):
    if not grids:
        return None
    counts = np.zeros(grids[0].shape, dtype=np.float32)
    valid_models = np.zeros(grids[0].shape, dtype=np.float32)

    for g in grids:
        valid = np.isfinite(g)
        valid_models += valid.astype(np.float32)
        if operator == ">=":
            counts += ((g >= threshold) & valid).astype(np.float32)
        elif operator == "<=":
            counts += ((g <= threshold) & valid).astype(np.float32)

    safe_valid = np.where(valid_models > 0, valid_models, 1.0)
    prob_pct = (counts / safe_valid) * 100.0
    return np.where(valid_models > 0, prob_pct, np.nan)


def process_day_prob(args):
    d, models, out_dir = args
    start_h = d * 24
    end_h = (d + 1) * 24
    lead_str = "%03d" % start_h

    # Récupérer les données pour chaque modèle une seule fois
    tmax_list, tmin_list, gust_list, rain_list, snow_list, cape_list = [], [], [], [], [], []

    for m in models:
        tmax = get_model_daily_summary(m, "temperature", start_h, end_h, "max")
        if tmax is not None: tmax_list.append(tmax)

        tmin = get_model_daily_summary(m, "temperature", start_h, end_h, "min")
        if tmin is not None: tmin_list.append(tmin)

        gust = get_model_daily_summary(m, "rafales_10m", start_h, end_h, "max")
        if gust is not None: gust_list.append(gust)

        rain = get_model_daily_summary(m, "precipitations_cumulees", start_h, end_h, "max")
        if rain is not None: rain_list.append(rain)

        snow = get_model_daily_summary(m, "neige_sol", start_h, end_h, "max")
        if snow is not None: snow_list.append(snow)

        cape = get_model_daily_summary(m, "mucape", start_h, end_h, "max")
        if cape is not None: cape_list.append(cape)

    prob_maps = {
        "prob_tmax_25":   calc_prob(tmax_list, ">=", 25.0),
        "prob_tmax_30":   calc_prob(tmax_list, ">=", 30.0),
        "prob_tmax_35":   calc_prob(tmax_list, ">=", 35.0),
        "prob_tmax_40":   calc_prob(tmax_list, ">=", 40.0),
        "prob_tmin_0":    calc_prob(tmin_list, "<=", 0.0),
        "prob_tmin_m5":   calc_prob(tmin_list, "<=", -5.0),
        "prob_vent_60":   calc_prob(gust_list, ">=", 60.0),
        "prob_vent_80":   calc_prob(gust_list, ">=", 80.0),
        "prob_vent_100":  calc_prob(gust_list, ">=", 100.0),
        "prob_vent_120":  calc_prob(gust_list, ">=", 120.0),
        "prob_pluie_10":  calc_prob(rain_list, ">=", 10.0),
        "prob_pluie_25":  calc_prob(rain_list, ">=", 25.0),
        "prob_pluie_50":  calc_prob(rain_list, ">=", 50.0),
        "prob_pluie_70":  calc_prob(rain_list, ">=", 70.0),
        "prob_neige_1":   calc_prob(snow_list, ">=", 1.0),
        "prob_neige_5":   calc_prob(snow_list, ">=", 5.0),
        "prob_mucape_500":calc_prob(cape_list, ">=", 500.0),
        "prob_mucape_1500":calc_prob(cape_list, ">=", 1500.0),
    }

    day_files = {}
    day_probes = {}

    for prob_key, grid in prob_maps.items():
        if grid is not None:
            im_full = Image.fromarray(grid.astype(np.float32)).resize((2200, 1640), resample=Image.BILINEAR)
            grid_full = np.array(im_full)

            webp_dst = os.path.join(out_dir, prob_key, "%s.webp" % lead_str)
            hkv_dst = os.path.join(out_dir, "values", prob_key, "%s.hkv.gz" % lead_str)

            save_webp(grid_full, prob_key, webp_dst)
            write_hkv(grid, hkv_dst, probe_w=440, probe_h=328)

            day_files[prob_key] = "maps/%s/%s.webp" % (prob_key, lead_str)
            day_probes[prob_key] = "maps/values/%s/%s.hkv.gz" % (prob_key, lead_str)

    return (d, start_h, day_files, day_probes)


def generate_probabilities_dataset(domain_key, target_model, models, max_days=8):
    print("[probabilites] Calcul des Probabilités 24h %s (J+0 -> J+%d)..." % (target_model, max_days - 1), flush=True)
    out_dir = os.path.join(BASE_DIR, "output", target_model, "maps")
    ensure_dir(out_dir)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    run_hour = (now_utc.hour // 6) * 6
    run_dt = now_utc.replace(hour=run_hour, minute=0, second=0, microsecond=0)

    tasks = [(d, models, out_dir) for d in range(max_days)]
    steps = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(process_day_prob, tasks)
        for res in sorted(results, key=lambda x: x[0]):
            d, start_h, day_files, day_probes = res
            if day_files:
                valid_dt = run_dt + datetime.timedelta(hours=start_h)
                steps.append({
                    "lead_hour": start_h,
                    "valid_time": valid_dt.isoformat(),
                    "files": day_files,
                    "probes": day_probes,
                })

    if not steps:
        print("[probabilites] Aucune dalle générée pour %s" % target_model, flush=True)
        return False

    domain_obj = FRANCE if domain_key == "france" else EUROPE
    meta = {
        "model_name": "🎯 PROBABILITÉS France 24h" if domain_key == "france" else "🎯 PROBABILITÉS Europe 24h",
        "provider": "Météo-Climat Pro — Risques & Probabilités (ARPEGE, ICON, GFS, AIFS)",
        "resolution": "Probabilités 24h HD (0 à 100%)",
        "run_time": run_dt.isoformat(),
    }

    write_places(domain_obj, out_dir)
    write_manifest(out_dir, steps, meta, domain_obj)
    print("✅ [probabilites] %s : %d jours (J+0 -> J+%d) générés avec succès !"
          % (target_model, len(steps), len(steps) - 1), flush=True)
    return True


def main():
    france_models = ["arpege_france", "icon_eu_france", "gfs_france", "aifs_france"]
    generate_probabilities_dataset("france", "probabilites_france", france_models, max_days=5)

    europe_models = ["aifs", "icon_eu", "gfs", "arpege"]
    generate_probabilities_dataset("europe", "probabilites", europe_models, max_days=8)


if __name__ == "__main__":
    main()
