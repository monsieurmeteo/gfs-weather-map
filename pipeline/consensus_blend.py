#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
consensus_blend.py — Modèle Consensus Multi-Modèles (Météo-Climat Pro)
========================================================================
Calcule la synthèse pondérée multi-modèles (Super-Ensemble) :
- Domaine France : ARPEGE France 0.1° + ICON-EU France + GFS France + AIFS France
- Domaine Europe : ECMWF AIFS + ICON-EU + GFS + ARPEGE

Génération ultra-rapide multi-threadée (ThreadPoolExecutor).
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
from render import (
    LAYER_ORDER, LAYER_META, save_webp, write_hkv, write_manifest, write_places, ensure_dir
)


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


def process_lead_layer(args):
    lead, layer, models_weights, model_steps, out_dir = args
    lead_str = "%03d" % lead

    collected_grids = []
    collected_weights = []

    for m, weight in models_weights.items():
        hkv_path = os.path.join(BASE_DIR, "output", m, "maps", "values", layer, "%s.hkv.gz" % lead_str)
        if not os.path.exists(hkv_path):
            if m in model_steps and model_steps[m]:
                closest_lead = min(model_steps[m], key=lambda x: abs(x - lead))
                if abs(closest_lead - lead) <= 3:
                    hkv_path = os.path.join(BASE_DIR, "output", m, "maps", "values", layer, "%03d.hkv.gz" % closest_lead)

        if os.path.exists(hkv_path):
            grid = read_hkv(hkv_path)
            if grid is not None:
                if grid.shape != (328, 440):
                    im = Image.fromarray(grid.astype(np.float32)).resize((440, 328), resample=Image.BILINEAR)
                    grid = np.array(im)
                collected_grids.append(grid)
                collected_weights.append(weight)

    if not collected_grids:
        return None

    weights_arr = np.array(collected_weights, dtype=np.float32)
    weights_arr = weights_arr / np.sum(weights_arr)

    stack = np.stack(collected_grids, axis=0)
    valid_mask = np.isfinite(stack)

    w_3d = weights_arr[:, None, None] * valid_mask
    sum_w = np.sum(w_3d, axis=0)
    safe_sum_w = np.where(sum_w > 0, sum_w, 1.0)

    weighted_sum = np.sum(np.nan_to_num(stack, nan=0.0) * w_3d, axis=0)
    consensus_grid = np.where(sum_w > 0, weighted_sum / safe_sum_w, np.nan)

    im_full = Image.fromarray(consensus_grid.astype(np.float32)).resize((2200, 1640), resample=Image.BILINEAR)
    grid_full = np.array(im_full)

    webp_dst = os.path.join(out_dir, layer, "%s.webp" % lead_str)
    hkv_dst = os.path.join(out_dir, "values", layer, "%s.hkv.gz" % lead_str)

    save_webp(grid_full, layer, webp_dst)
    write_hkv(consensus_grid, hkv_dst, probe_w=440, probe_h=328)

    rel_webp = "maps/%s/%s.webp" % (layer, lead_str)
    rel_hkv = "maps/values/%s/%s.hkv.gz" % (layer, lead_str)

    return (lead, layer, rel_webp, rel_hkv)


def generate_consensus(domain_key, target_model, models_weights, max_lead=102):
    print("[consensus] Calcul du Consensus %s (H+000 -> H+%03d)..." % (target_model, max_lead), flush=True)
    out_dir = os.path.join(BASE_DIR, "output", target_model, "maps")
    ensure_dir(out_dir)

    model_steps = {}
    for m in models_weights:
        m_dir = os.path.join(BASE_DIR, "output", m, "maps")
        if not os.path.isdir(m_dir):
            continue
        leads = set()
        for f in glob.glob(os.path.join(m_dir, "values", "*", "*.hkv.gz")):
            base = os.path.basename(f)
            mat = re.match(r"^(\d{3})\.hkv\.gz$", base)
            if mat:
                leads.add(int(mat.group(1)))
        model_steps[m] = sorted(leads)

    if not model_steps:
        print("[consensus] Aucun modèle source disponible pour %s" % target_model, flush=True)
        return False

    all_leads = set()
    for l_list in model_steps.values():
        all_leads.update(l_list)
    # Échéances tri-horaires régulières (0, 3, 6, 9, ...) pour rapidité et régularité
    target_leads = sorted([l for l in all_leads if l <= max_lead and l % 3 == 0])
    if not target_leads:
        target_leads = sorted([l for l in all_leads if l <= max_lead])[:24]

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    run_hour = (now_utc.hour // 6) * 6
    run_dt = now_utc.replace(hour=run_hour, minute=0, second=0, microsecond=0)

    tasks = []
    for lead in target_leads:
        for layer in LAYER_ORDER:
            tasks.append((lead, layer, models_weights, model_steps, out_dir))

    layer_files = {}
    probe_files = {}
    rendered_leads = set()

    # Exécution multi-threadée ultra rapide
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(process_lead_layer, tasks)
        for res in results:
            if res is not None:
                lead, layer, rel_webp, rel_hkv = res
                layer_files.setdefault(lead, {})[layer] = rel_webp
                probe_files.setdefault(lead, {})[layer] = rel_hkv
                rendered_leads.add(lead)

    if not rendered_leads:
        print("[consensus] Aucune dalle générée pour %s" % target_model, flush=True)
        return False

    domain_obj = FRANCE if domain_key == "france" else EUROPE
    steps = []
    for lh in sorted(rendered_leads):
        v_dt = run_dt + datetime.timedelta(hours=lh)
        steps.append({
            "lead_hour": lh,
            "valid_time": v_dt.isoformat(),
            "files": layer_files.get(lh, {}),
            "probes": probe_files.get(lh, {}),
        })

    meta = {
        "model_name": "🌟 CONSENSUS France HD" if domain_key == "france" else "🌟 CONSENSUS Europe",
        "provider": "Météo-Climat Pro — Multi-Model Blend (Météo-France, DWD, NOAA, ECMWF)",
        "resolution": "Multi-Résolution HD (Grille 2200×1640)",
        "run_time": run_dt.isoformat(),
    }

    write_places(domain_obj, out_dir)
    write_manifest(out_dir, steps, meta, domain_obj)
    print("✅ [consensus] %s : %d échéances (H+%03d -> H+%03d) générées avec succès !"
          % (target_model, len(steps), sorted(rendered_leads)[0], sorted(rendered_leads)[-1]), flush=True)
    return True


def main():
    france_weights = {
        "arpege_france": 0.35,
        "icon_eu_france": 0.30,
        "aifs_france": 0.20,
        "gfs_france": 0.15,
    }
    generate_consensus("france", "consensus_france", france_weights, max_lead=102)

    europe_weights = {
        "aifs": 0.30,
        "icon_eu": 0.30,
        "gfs": 0.20,
        "arpege": 0.20,
    }
    generate_consensus("europe", "consensus", europe_weights, max_lead=168)


if __name__ == "__main__":
    main()
