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
import icon_open_data
import aifs_open_data


def assemble_model(model_key, domain, meta):
    out_dir = os.path.join(BASE_DIR, "output", model_key, "maps")
    if not os.path.exists(out_dir):
        print("[assemble] Dossier introuvable : %s" % out_dir, flush=True)
        return False

    # Trouver le run_time le plus récent correspondant exactement au modèle
    if "gfs" in model_key:
        run_dt = gfs_open_data.latest_run()
    elif "icon" in model_key:
        run_dt = icon_open_data.latest_run()
    elif "aifs" in model_key:
        run_dt = aifs_open_data.latest_run()
    else:
        run_dt = arpege_open_data.latest_run()
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
        "model_name": "ARPEGE Europe 0.25°",
        "provider": "Météo-France — Open Data (Licence Etalab)",
        "resolution": "0.25° (~25 km)",
    })
    assemble_model("arpege_france", FRANCE, {
        "model_name": "ARPEGE France 0.1°",
        "provider": "Météo-France — Open Data (Licence Etalab)",
        "resolution": "0.1° (~10 km) • Grille 721×541",
    })
    assemble_model("icon_eu", EUROPE, {
        "model_name": "ICON-EU 7 km Europe",
        "provider": "DWD — open data (opendata.dwd.de)",
        "resolution": "7 km (~0.0625°)",
    })
    assemble_model("icon_eu_france", FRANCE, {
        "model_name": "ICON-EU 7 km France",
        "provider": "DWD — open data (opendata.dwd.de)",
        "resolution": "7 km (~0.0625°)",
    })
    assemble_model("aifs", EUROPE, {
        "model_name": "ECMWF AIFS 0.25° Europe",
        "provider": "ECMWF — open data (data.ecmwf.int)",
        "resolution": "0.25° (~25 km)",
    })
    assemble_model("aifs_france", FRANCE, {
        "model_name": "ECMWF AIFS 0.25° France",
        "provider": "ECMWF — open data (data.ecmwf.int)",
        "resolution": "0.25° (~25 km)",
    })
    try:
        import consensus_blend
        consensus_blend.main()
    except Exception as e:
        print("[assemble] Note : consensus_blend non exécuté : %s" % e, flush=True)

    assemble_model("consensus_france", FRANCE, {
        "model_name": "🌟 CONSENSUS France HD",
        "provider": "Météo-Climat Pro — Multi-Model Blend (ARPEGE + ICON + GFS + AIFS)",
        "resolution": "Multi-Résolution HD (Grille 2200×1640)",
    })
    assemble_model("consensus", EUROPE, {
        "model_name": "🌟 CONSENSUS Europe",
        "provider": "Météo-Climat Pro — Multi-Model Blend (AIFS + ICON + GFS + ARPEGE)",
        "resolution": "Multi-Résolution HD (Grille 2200×1640)",
    })
    try:
        import probabilities_24h
        probabilities_24h.main()
    except Exception as e:
        print("[assemble] Note : probabilities_24h non exécuté : %s" % e, flush=True)

    try:
        import daily_min_max
        daily_min_max.main()
    except Exception as e:
        print("[assemble] Note : daily_min_max non exécuté : %s" % e, flush=True)

    assemble_model("probabilites_france", FRANCE, {
        "model_name": "🎯 PROBABILITÉS France 24h",
        "provider": "Météo-Climat Pro — Risques & Probabilités (4 Modèles)",
        "resolution": "Probabilités 24h HD (0 à 100%)",
    })
    assemble_model("probabilites", EUROPE, {
        "model_name": "🎯 PROBABILITÉS Europe 24h",
        "provider": "Météo-Climat Pro — Risques & Probabilités (4 Modèles)",
        "resolution": "Probabilités 24h HD (0 à 100%)",
    })
    print("[assemble] Assemblage terminé avec succès.", flush=True)


if __name__ == "__main__":
    main()
