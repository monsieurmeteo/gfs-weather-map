#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble.py — Assemble les dalles et génère index.json après parallélisation en 15 groupes.
========================================================================================
Scanne output/gfs/maps, output/gfs_france/maps, output/arpege/maps :
1. Découvre tous les fichiers .webp et .hkv.gz
2. Reconstruit la liste ordonnée des steps (H+00 à H+384) avec valid_time calculé
3. Génère index.json et communes.json pour chaque modèle
"""
import os
import re
import sys
import glob
import json
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))

from domains import EUROPE, FRANCE
from render import LAYER_META, write_manifest, write_places
import gfs_open_data
import arpege_open_data


def assemble_model(model_key, domain, meta):
    out_dir = os.path.join(BASE_DIR, "output", model_key, "maps")
    if not os.path.exists(out_dir):
        print("[assemble] Dossier introuvable : %s" % out_dir, flush=True)
        return False

    # Trouver le run_time le plus récent ou par défaut
    run_dt = gfs_open_data.latest_run() if "gfs" in model_key else arpege_open_data.latest_run()
    meta["run_time"] = run_dt.isoformat()

    # Découvrir toutes les échéances et couches rendues
    # Structure : maps/<layer>/<lead:03d>.webp
    leads = set()
    layer_files = {}  # {lead: {layer: rel_path}}
    probe_files = {}  # {lead: {layer: rel_path}}

    for webp_path in glob.glob(os.path.join(out_dir, "*", "*.webp")):
        layer_dir = os.path.basename(os.path.dirname(webp_path))
        if layer_dir in ("fond", "values") or not os.path.isdir(os.path.dirname(webp_path)):
            continue
        fname = os.path.basename(webp_path)
        m = re.match(r"^(\d{3})\.webp$", fname)
        if not m:
            continue
        lh = int(m.group(1))
        leads.add(lh)
        rel = "maps/%s/%s" % (layer_dir, fname)
        layer_files.setdefault(lh, {})[layer_dir] = rel

    for hkv_path in glob.glob(os.path.join(out_dir, "values", "*", "*.hkv.gz")):
        layer_dir = os.path.basename(os.path.dirname(hkv_path))
        fname = os.path.basename(hkv_path)
        m = re.match(r"^(\d{3})\.hkv\.gz$", fname)
        if not m:
            continue
        lh = int(m.group(1))
        rel = "maps/values/%s/%s" % (layer_dir, fname)
        probe_files.setdefault(lh, {})[layer_dir] = rel

    if not leads:
        print("[assemble] Aucune dalle trouvée dans %s" % out_dir, flush=True)
        return False

    sorted_leads = sorted(leads)
    steps = []
    for lh in sorted_leads:
        valid_dt = run_dt + datetime.timedelta(hours=lh)
        steps.append({
            "lead_hour": lh,
            "valid_time": valid_dt.isoformat(),
            "files": layer_files.get(lh, {}),
            "probes": probe_files.get(lh, {}),
        })

    write_places(domain, out_dir)
    write_manifest(out_dir, steps, meta, domain)
    print("✅ [assemble] %s : %d échéances (H+%03d → H+%03d) assemblées dans %s"
          % (model_key, len(steps), sorted_leads[0], sorted_leads[-1], out_dir),
          flush=True)
    return True


def main():
    print("[assemble] Début de l'assemblage multi-modèles...", flush=True)
    assemble_model("gfs", EUROPE, {
        "model_name": "GFS 0.25° Europe",
        "provider": "NOAA (NOMADS) — open data",
        "resolution": "0.25° (~25 km)",
    })
    assemble_model("gfs_france", FRANCE, {
        "model_name": "GFS 0.25° France",
        "provider": "NOAA (NOMADS) — open data",
        "resolution": "0.25° (~25 km)",
    })
    assemble_model("arpege", EUROPE, {
        "model_name": "ARPEGE Europe 0.1°",
        "provider": "Météo-France — open data (data.gouv.fr)",
        "resolution": "0.1° (~11 km)",
    })
    assemble_model("arpege_france", FRANCE, {
        "model_name": "ARPEGE France 0.1°",
        "provider": "Météo-France — open data (data.gouv.fr)",
        "resolution": "0.1° (~11 km)",
    })
    print("[assemble] Assemblage terminé avec succès.", flush=True)


if __name__ == "__main__":
    main()
