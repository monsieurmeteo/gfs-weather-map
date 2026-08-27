#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all.py — Orchestrateur multi-modèles (un seul point d'entrée pour la CI)
============================================================================
1. Fonds de carte alignés (domaine Europe + France) — copiés vers GFS et ARPEGE
2. GFS 0.25° Europe (output/gfs/maps) + France (output/gfs_france/maps)
3. ARPEGE Europe 0.1° (output/arpege/maps)
Chaque modèle produit son propre manifest index.json exact.
"""
import os
import sys
import time
import shutil
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))

FOND_FILES = ("fond.webp", "mask_france.png", "frontieres.svg")


def sync_fond(src_maps, dst_maps):
    os.makedirs(dst_maps, exist_ok=True)
    for name in FOND_FILES:
        s = os.path.join(src_maps, name)
        if os.path.exists(s):
            shutil.copy(s, os.path.join(dst_maps, name))


def main():
    ap = argparse.ArgumentParser(description="Pipeline météo multi-modèles")
    ap.add_argument("--max-hours", type=int, default=384,
                    help="Échéance GFS max (24-384, défaut 384)")
    ap.add_argument("--models", default="gfs,arpege",
                    help="Modèles à lancer : gfs,arpege (défaut: les deux)")
    ap.add_argument("--domain", default="both",
                    choices=["both", "europe", "france"],
                    help="Domaine GFS : both (défaut), europe, france")
    ap.add_argument("--skip-fonds", action="store_true",
                    help="Ne pas régénérer les fonds de carte")
    args = ap.parse_args()

    t0 = time.time()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    if not args.skip_fonds:
        import generate_fond_gfs
        generate_fond_gfs.generate("europe")
        generate_fond_gfs.generate("france")
        # ARPEGE partage les fonds Europe et France
        sync_fond(os.path.join(BASE_DIR, "output", "gfs", "maps"),
                  os.path.join(BASE_DIR, "output", "arpege", "maps"))
        sync_fond(os.path.join(BASE_DIR, "output", "gfs_france", "maps"),
                  os.path.join(BASE_DIR, "output", "arpege_france", "maps"))
        print("[run_all] Fonds de carte générés.", flush=True)

    if "gfs" in models:
        import gfs_open_data
        gfs_open_data.run_all(max_hours=args.max_hours, domain=args.domain)

    if "arpege" in models:
        import arpege_open_data
        arpege_open_data.run_all(max_hours=args.max_hours, domain=args.domain)

    print("[run_all] Terminé en %.1f min." % ((time.time() - t0) / 60.0),
          flush=True)


if __name__ == "__main__":
    main()
