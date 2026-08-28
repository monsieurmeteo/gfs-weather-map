#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probabilities_24h.py — Cartes de Probabilités Multi-Modèles sur 24h (Météo-Climat Pro)
========================================================================================
Calcule les probabilités de dépassement de seuils critiques par tranche de 24 heures :
- J+0 (0-24h), J+1 (24-48h), J+2 (48-72h), J+3 (72-96h), J+4 (96-120h), J+5 (120-144h), J+6 (144-168h), J+7 (168-192h)

16 Calques de Probabilités :
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
    """Lit une sonde HKV1 et retourne un array 2D float32 (NaN pour valeurs manquantes)."""
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
    """Calcule le résumé 24h (max, min ou somme) pour un modèle donné."""
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
    return None


def generate_probabilities(domain_key, target_model, models_weights, max_days=7):
    """Génère les cartes de probabilités par tranche de 24h."""
    print("[probabilites] Calcul des Probabilités 24h %s (J+0 -> J+%d)..." % (target_model, max_days), flush=True)
    out_dir = os.path.join(BASE_DIR, "output", target_model, "maps")
    ensure_dir(out_dir)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    run_hour = (now_utc.hour // 6) * 6
    run_dt = now_utc.replace(hour=run_hour, minute=0, second=0, microsecond=0)

    days_steps = []
    layer_files = {}
    probe_files = {}

    indicators = {
        "prob_tmax_25":   ("temperature", "max", lambda x: x >= 25.0),
        "prob_tmax_30":   ("temperature", "max", lambda x: x >= 30.0),
        "prob_tmax_35":   ("temperature", "max", lambda x: x >= 35.0),
        "prob_tmax_40":   ("temperature", "max", lambda x: x >= 40.0),
        "prob_tmin_0":    ("temperature", "min", lambda x: x <= 0.0),
        "prob_tmin_m5":   ("temperature", "min", lambda x: x <= -5.0),
        "prob_vent_60":   ("rafales",     "max", lambda x: x >= 60.0),
        "prob_vent_80":   ("rafales",     "max", lambda x: x >= 80.0),
        "prob_vent_100":  ("rafales",     "max", lambda x: x >= 100.0),
        "prob_vent_120":  ("rafales",     "max", lambda x: x >= 120.0),
        "prob_pluie_10":  ("pluie_1h",    "sum", lambda x: x >= 10.0),
        "prob_pluie_25":  ("pluie_1h",    "sum", lambda x: x >= 25.0),
        "prob_pluie_50":  ("pluie_1h",    "sum", lambda x: x >= 50.0),
        "prob_pluie_70":  ("pluie_1h",    "sum", lambda x: x >= 70.0),
        "prob_neige_1":   ("neige_au_sol","max", lambda x: x >= 1.0),
        "prob_neige_5":   ("neige_au_sol","max", lambda x: x >= 5.0),
        "prob_mucape_500":("mucape",      "max", lambda x: x >= 500.0),
        "prob_mucape_1500":("mucape",     "max", lambda x: x >= 1500.0),
    }

    for d in range(max_days + 1):
        start_h = d * 24
        end_h = (d + 1) * 24
        step_str = "%03d" % (d * 24)

        for p_key, (src_layer, op, cond_fn) in indicators.items():
            prob_hits = []
            weights = []

            for m, weight in models_weights.items():
                daily_val = get_model_daily_summary(m, src_layer, start_h, end_h, operation=op)
                if daily_val is not None:
                    mask = np.where(np.isfinite(daily_val), cond_fn(daily_val).astype(np.float32), np.nan)
                    prob_hits.append(mask)
                    weights.append(weight)

            if not prob_hits:
                continue

            weights_arr = np.array(weights, dtype=np.float32)
            weights_arr = weights_arr / np.sum(weights_arr)

            stack = np.stack(prob_hits, axis=0)
            valid_mask = np.isfinite(stack)
            
            w_3d = weights_arr[:, None, None] * valid_mask
            sum_w = np.sum(w_3d, axis=0)
            safe_sum_w = np.where(sum_w > 0, sum_w, 1.0)

            weighted_prob = np.sum(np.nan_to_num(stack, nan=0.0) * w_3d, axis=0) * 100.0
            prob_grid = np.where(sum_w > 0, weighted_prob / safe_sum_w, np.nan)

            im_full = Image.fromarray(prob_grid.astype(np.float32)).resize((2200, 1640), resample=Image.BILINEAR)
            grid_full = np.array(im_full)

            webp_dst = os.path.join(out_dir, p_key, "%s.webp" % step_str)
            hkv_dst = os.path.join(out_dir, "values", p_key, "%s.hkv.gz" % step_str)

            save_webp(grid_full, "probabilite", webp_dst)
            write_hkv(prob_grid, hkv_dst, probe_w=440, probe_h=328)

            rel_webp = "maps/%s/%s.webp" % (p_key, step_str)
            rel_hkv = "maps/values/%s/%s.hkv.gz" % (p_key, step_str)

            layer_files.setdefault(d * 24, {})[p_key] = rel_webp
            probe_files.setdefault(d * 24, {})[p_key] = rel_hkv

        if d * 24 in layer_files:
            days_steps.append(d * 24)

    if not days_steps:
        print("[probabilites] Aucune dalle générée pour %s" % target_model, flush=True)
        return False

    domain_obj = FRANCE if domain_key == "france" else EUROPE
    steps = []
    for lh in sorted(days_steps):
        day_num = lh // 24
        v_dt = run_dt + datetime.timedelta(days=day_num)
        steps.append({
            "lead_hour": lh,
            "valid_time": v_dt.isoformat(),
            "files": layer_files.get(lh, {}),
            "probes": probe_files.get(lh, {}),
        })

    meta = {
        "model_name": "🎯 PROBABILITÉS France 24h" if domain_key == "france" else "🎯 PROBABILITÉS Europe 24h",
        "provider": "Météo-Climat Pro — Risques & Probabilités Multi-Modèles (4 Modèles)",
        "resolution": "Probabilités 24h HD (0 à 100%)",
        "run_time": run_dt.isoformat(),
    }

    write_places(domain_obj, out_dir)
    write_manifest(out_dir, steps, meta, domain_obj)
    print("✅ [probabilites] %s : %d jours (J+0 -> J+%d) générés avec succès !"
          % (target_model, len(steps), len(steps) - 1), flush=True)
    return True


def main():
    france_weights = {
        "arpege_france": 0.35,
        "icon_eu_france": 0.30,
        "aifs_france": 0.20,
        "gfs_france": 0.15,
    }
    generate_probabilities("france", "probabilites_france", france_weights, max_days=4)

    europe_weights = {
        "aifs": 0.30,
        "icon_eu": 0.30,
        "gfs": 0.20,
        "arpege": 0.20,
    }
    generate_probabilities("europe", "probabilites", europe_weights, max_days=7)


if __name__ == "__main__":
    main()
