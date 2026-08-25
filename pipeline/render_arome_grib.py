#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rendu des tuiles AROME à partir des GRIB2 ouverts de Météo-France (data.gouv.fr)
================================================================================
Les paquets GRIB2 AROME 0,01° sont publiés en open data sur data.gouv.fr
(dataset « Paquets Arome - Résolution 0,01° »), gratuitement et sans token.

Packages par échéance : HP1 (vent/humidité multi-niveaux), SP1 (température,
humidité 2m, vent 10m, rafales max), SP2 (CAPE, pression, nuages, graupel,
neige), SP3 (divers).

Ce module télécharge les 4 packages d'un run, décode les champs, les régrid en
projection Mercator (2200×1640) et applique les palettes météociel.
"""

import os, sys, re, shutil, tempfile, datetime
import requests
import numpy as np
from PIL import Image
import warnings

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))
from fetch_and_render_all import (  # noqa: E402
    PALETTES, BOUNDS, WIDTH, HEIGHT, regrid, apply_palette,
)

GRIB_BASE = ("https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt/{run}/arome/001/"
             "{pkg}/arome__001__{pkg}__{lead:02d}H__{run}.grib2")
GRIB_PKGS = ["HP1", "SP1", "SP2", "SP3"]
DATASET_API = ("https://www.data.gouv.fr/api/1/datasets/"
               "paquets-arome-resolution-0-01deg/")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def latest_run():
    """Retourne le run AROME le plus récent disponible sur data.gouv.fr."""
    r = requests.get(DATASET_API, headers=HEADERS, timeout=30)
    r.raise_for_status()
    runs = set()
    for res in r.json().get("resources", []):
        m = re.search(r"__(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\.grib2",
                      res.get("title", ""))
        if m:
            runs.add(m.group(1))
    if not runs:
        raise RuntimeError("Aucun run AROME trouvé sur data.gouv.fr")
    # Le plus récent (tri lexicographique ISO 8601)
    return max(runs)


def run_ready_hint():
    """Échéances disponibles pour le run le plus récent."""
    r = requests.get(DATASET_API, headers=HEADERS, timeout=30)
    r.raise_for_status()
    run = latest_run()
    leads = set()
    for res in r.json().get("resources", []):
        t = res.get("title", "")
        m = re.search(r"__(\d{2})H__" + re.escape(run) + r"\.grib2", t)
        if m:
            leads.add(int(m.group(1)))
    return run, sorted(leads)


def download_packages(run_str, lead, tmpdir):
    """Télécharge les 4 packages GRIB2 d'une échéance."""
    paths = []
    for pkg in GRIB_PKGS:
        url = GRIB_BASE.format(run=run_str, pkg=pkg, lead=lead)
        dst = os.path.join(tmpdir, "%s_%02dH.grib2" % (pkg, lead))
        try:
            r = requests.get(url, headers=HEADERS, timeout=300)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(dst, "wb") as f:
                    f.write(r.content)
                paths.append(dst)
        except Exception:
            pass
    return paths


def _decode(paths, shortname):
    """Retourne (valeurs, dataset) pour un shortName GRIB donné."""
    import cfgrib
    for p in paths:
        try:
            for ds in cfgrib.open_datasets(p):
                for v in ds.data_vars:
                    if v.lower() == shortname.lower():
                        return ds[v].values, ds
        except Exception:
            continue
    return None, None


def _grid(ds):
    lat = ds.latitude.values
    lon = ds.longitude.values
    if lat.ndim == 2:
        return lat[:, 0], lon[0, :]
    return lat, lon


def render_lead(run_str, lead, out_dir, step_files):
    """Télécharge, décode et rend les tuiles d'une échéance."""
    tmp = tempfile.mkdtemp(prefix="arome_grib_")
    try:
        paths = download_packages(run_str, lead, tmp)
        if len(paths) < 3:
            print("  H+%02d: packages insuffisants (%d)" % (lead, len(paths)))
            return

        # ── Extraction des champs bruts ────────────────────────────────
        t2m, ds_t = _decode(paths, "2t")
        r2, _ = _decode(paths, "2r")
        u10, ds_u = _decode(paths, "10u")
        v10, _ = _decode(paths, "10v")
        efg, _ = _decode(paths, "max_10efg")
        cape, _ = _decode(paths, "CAPE_INS")
        sp, _ = _decode(paths, "sp")
        lcc, _ = _decode(paths, "lcc")
        mcc, _ = _decode(paths, "mcc")
        hcc, _ = _decode(paths, "hcc")
        tgrp, _ = _decode(paths, "tgrp")
        tsnowp, _ = _decode(paths, "tsnowp")
        si10, _ = _decode(paths, "10si")

        ds = ds_t or ds_u
        if ds is None:
            print("  H+%02d: aucun dataset décodé" % lead)
            return
        lats, lons = _grid(ds)

        def save(name, arr, scale=1.0, offset=0.0):
            if arr is None:
                return
            d = arr.astype(np.float32) * scale + offset
            d = np.where(np.isfinite(d), d, np.nan)
            try:
                data = regrid(d, lats, lons)
            except Exception as e:
                print("  [%s] regrid erreur: %s" % (name, e))
                return
            rgba = apply_palette(data, PALETTES.get(name, PALETTES["temperature"]))
            dst_dir = os.path.join(out_dir, name)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, "%03d.webp" % lead)
            Image.fromarray(rgba, "RGBA").save(dst, format="WEBP", quality=85, method=4)
            step_files[name] = "maps/%s/%03d.webp" % (name, lead)

        # ── Champs physiques (conversions d'unités) ────────────────────
        save("temperature", t2m, 1.0, -273.15)          # K -> °C
        save("humidite", r2)                              # %
        if u10 is not None and v10 is not None:
            ws = np.sqrt(u10.astype(np.float32) ** 2 + v10.astype(np.float32) ** 2)
            save("vent", ws, 3.6)                        # m/s -> km/h
        save("rafales", efg, 3.6)                        # m/s -> km/h
        save("mucape", cape)
        save("pression_surface", sp, 1.0 / 100.0)        # Pa -> hPa
        save("nuages_bas", lcc)
        save("nuages_moyens", mcc)
        save("nuages_eleves", hcc)
        save("graupel", tgrp)
        save("neige", tsnowp)
        save("neige_au_sol", si10)
        if lcc is not None and mcc is not None and hcc is not None:
            tot = np.maximum(np.maximum(lcc, mcc), hcc)
            save("nebulosite", tot)

        print("  H+%02d: %d couches rendues" % (lead, len(step_files)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_arome_grib(max_hours=51):
    """Génère toutes les tuiles AROME depuis les GRIB2 ouverts."""
    run_str = latest_run()
    print("Run AROME sélectionné : %s" % run_str)
    _, leads = run_ready_hint()
    lead_hours = [lh for lh in range(0, max_hours + 1) if lh in leads or lh <= 48]
    out_dir = os.path.join(BASE_DIR, "output", "arome", "maps")
    os.makedirs(out_dir, exist_ok=True)
    steps = []
    for lh in lead_hours:
        step_files = {}
        render_lead(run_str, lh, out_dir, step_files)
        if step_files:
            vt = datetime.datetime.fromisoformat(run_str.replace("Z", "+00:00")) \
                + datetime.timedelta(hours=lh)
            steps.append({
                "lead_hour": lh,
                "valid_time": vt.isoformat(),
                "files": step_files,
            })
    # Manifeste
    from fetch_and_render_all import write_manifest
    meta = {"name": "AROME HD (1,3 km)", "provider": "Meteo-France",
            "resolution": "1,3 km (0.01°)", "run_time": run_str}
    write_manifest(out_dir, steps, meta)
    print("OK AROME GRIB : %d échéances rendues" % len(steps))


if __name__ == "__main__":
    run_arome_grib()
