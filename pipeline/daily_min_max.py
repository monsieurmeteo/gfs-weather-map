#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_min_max.py — Calcul des Températures Minimales (Tn) et Maximales (Tx) sur 24h
=====================================================================================
Génère pour tous les modèles (ARPEGE, GFS, ICON, AIFS, CONSENSUS) :
- temperature_min_24h : Température la plus basse sur chaque tranche de 24h (°C)
- temperature_max_24h : Température la plus haute sur chaque tranche de 24h (°C)
"""
import os
import sys
import glob
import gzip
import struct
import re
import datetime
import numpy as np
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))

from render import save_webp, write_hkv, ensure_dir


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


def process_model_min_max(model_key):
    out_dir = os.path.join(BASE_DIR, "output", model_key, "maps")
    temp_dir = os.path.join(out_dir, "values", "temperature")
    if not os.path.isdir(temp_dir):
        return

    # Découverte de toutes les échéances de température disponibles
    temp_files = {}
    for f in glob.glob(os.path.join(temp_dir, "*.hkv.gz")):
        m = re.match(r"^(\d{3})\.hkv\.gz$", os.path.basename(f))
        if m:
            lead = int(m.group(1))
            temp_files[lead] = f

    if not temp_files:
        return

    sorted_leads = sorted(temp_files.keys())
    max_lead = sorted_leads[-1]
    max_days = (max_lead // 24) + 1

    print("[daily_min_max] Calcul Tn/Tx 24h pour %s (J+0 -> J+%d)..." % (model_key, max_days - 1), flush=True)

    for d in range(max_days):
        start_h = d * 24
        end_h = (d + 1) * 24

        day_leads = [l for l in sorted_leads if start_h <= l <= end_h]
        if not day_leads:
            continue

        day_grids = []
        for l in day_leads:
            g = read_hkv(temp_files[l])
            if g is not None:
                if g.shape != (328, 440):
                    im = Image.fromarray(g.astype(np.float32)).resize((440, 328), resample=Image.BILINEAR)
                    g = np.array(im)
                day_grids.append(g)

        if not day_grids:
            continue

        stack = np.stack(day_grids, axis=0)
        t_min = np.nanmin(stack, axis=0)
        t_max = np.nanmax(stack, axis=0)

        # Upscaling 2200x1640
        im_min = Image.fromarray(t_min.astype(np.float32)).resize((2200, 1640), resample=Image.BILINEAR)
        im_max = Image.fromarray(t_max.astype(np.float32)).resize((2200, 1640), resample=Image.BILINEAR)
        grid_min_full = np.array(im_min)
        grid_max_full = np.array(im_max)

        # Rendre pour tous les leads de cette journée pour une navigation fluide
        for l in day_leads:
            lead_str = "%03d" % l

            # Sauvegarde Tn (Température minimale)
            save_webp(grid_min_full, "temperature", os.path.join(out_dir, "temperature_min_24h", "%s.webp" % lead_str))
            write_hkv(t_min, os.path.join(out_dir, "values", "temperature_min_24h", "%s.hkv.gz" % lead_str), probe_w=440, probe_h=328)

            # Sauvegarde Tx (Température maximale)
            save_webp(grid_max_full, "temperature", os.path.join(out_dir, "temperature_max_24h", "%s.webp" % lead_str))
            write_hkv(t_max, os.path.join(out_dir, "values", "temperature_max_24h", "%s.hkv.gz" % lead_str), probe_w=440, probe_h=328)


def main():
    models = [
        "arpege_france", "arpege",
        "icon_eu_france", "icon_eu",
        "gfs_france", "gfs",
        "aifs_france", "aifs",
        "consensus_france", "consensus"
    ]
    for m in models:
        process_model_min_max(m)
    print("✅ [daily_min_max] Calcul Tn/Tx 24h terminé pour tous les modèles.", flush=True)


if __name__ == "__main__":
    main()
