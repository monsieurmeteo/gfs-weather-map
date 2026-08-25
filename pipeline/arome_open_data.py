#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROGRAMME NEUF v2 — Tuiles AROME HD + Prévisions par commune
==============================================================
  Données   : paquets GRIB2 AROME 0,01° (open data Météo-France, data.gouv.fr)
  Décodage  : eccodes (contrôle total des champs)
  Projection: Mercator (2200×1640) — France non étirée
  Couleurs  : palettes météociel (vives)
  Communes  : extraction par interpolation bilinéaire à la position exacte
              de chaque commune (34 746) + fichiers binaires int16/zlib
              par département (beaucoup plus léger que le JSON de référence)

Corrections apportées vs v1 :
  - tirf/tsnowp/tgrp sont des CUMULS depuis le début du run
    → valeurs horaires = cumul(H+n) − cumul(H+n−1)
  - Réflectivité DIRECTE du modèle (champ 16.193) au lieu de Marshall-Palmer
  - Altitude réelle (SP3 H+0, shortName 'h') → pression MSL correcte
  - Neige au sol = cumul de neige fraîche (si10 n'existe pas dans les paquets)
  - Vent à 20/50/100 m + humidité multi-niveaux (HP1) → cisaillement vertical
    → type d'orage affiné (cellules / multicellulaires / lignes / supercellulaires)
"""

import os
import re
import sys
import zlib
import struct
import shutil
import tempfile
import datetime
import warnings

import requests
import numpy as np
from PIL import Image

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))
from fetch_and_render_all import (  # noqa: E402
    PALETTES, BOUNDS, WIDTH, HEIGHT, regrid, apply_palette,
)

# ── Constantes ──────────────────────────────────────────────────────────────
GRIB_BASE = ("https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt/{run}/arome/001/"
             "{pkg}/arome__001__{pkg}__{lead:02d}H__{run}.grib2")
GRIB_PKGS = ["HP1", "SP1", "SP2", "SP3"]
DATASET_API = ("https://www.data.gouv.fr/api/1/datasets/"
               "paquets-arome-resolution-0-01deg/")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Grille native AROME 0,01° (regular_ll, point 0 en haut à gauche)
NI, NJ = 2801, 1791
LAT0, LON0, STEP = 55.4, -12.0, 0.01

# ── Données ─────────────────────────────────────────────────────────────────
def latest_run():
    r = requests.get(DATASET_API, headers=HEADERS, timeout=30)
    r.raise_for_status()
    runs = set()
    for res in r.json().get("resources", []):
        m = re.search(r"__(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\.grib2",
                      res.get("title", ""))
        if m:
            runs.add(m.group(1))
    if not runs:
        raise RuntimeError("Aucun run AROME sur data.gouv.fr")
    return max(runs)


def available_leads(run_str):
    r = requests.get(DATASET_API, headers=HEADERS, timeout=30)
    r.raise_for_status()
    leads = set()
    for res in r.json().get("resources", []):
        m = re.search(r"__(\d{2})H__" + re.escape(run_str) + r"\.grib2",
                      res.get("title", ""))
        if m:
            leads.add(int(m.group(1)))
    return sorted(leads)


def download_packages(run_str, lead, tmpdir, with_sp3=False):
    """Télécharge les packages. SP3 (altitude) n'est pris qu'à H+0."""
    paths = []
    for pkg in GRIB_PKGS:
        if pkg == "SP3" and not with_sp3:
            continue
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


def read_grib(path):
    """Lit un fichier GRIB2 avec eccodes → dict {clé: array 2D (NJ, NI)}.

    Clés produites selon le package :
      SP1 : t2m, r2, u10, v10, efg10, nfg10
      SP2 : cape, refl, tgrp, sp, lcc, mcc, hcc, tirf, tsnowp
      HP1 : u20,u50,u100, v20,v50,v100, ws20,ws50,ws100, r10,r20,r50,r100
      SP3 : h (altitude)
    """
    from eccodes import codes_grib_new_from_file, codes_get, codes_get_array, codes_release
    out = {}
    with open(path, "rb") as f:
        while True:
            gid = codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                short = str(codes_get(gid, "shortName"))
                disc = int(codes_get(gid, "discipline"))
                cat = int(codes_get(gid, "parameterCategory"))
                num = int(codes_get(gid, "parameterNumber"))
                level = int(codes_get(gid, "level"))
                arr = np.asarray(codes_get_array(gid, "values"),
                                 dtype=np.float64)
                # Grille : le premier point est en haut à gauche (lat LAT0)
                arr = arr.reshape(NJ, NI)
                if short == "2t":
                    out["t2m"] = arr
                elif short == "2r":
                    out["r2"] = arr
                elif short == "10u":
                    out["u10"] = arr
                elif short == "10v":
                    out["v10"] = arr
                elif short == "max_10efg":
                    out["efg10"] = arr
                elif short == "max_10nfg":
                    out["nfg10"] = arr
                elif short == "CAPE_INS":
                    out["cape"] = arr
                elif short == "tgrp":
                    out["tgrp"] = arr
                elif short == "sp":
                    out["sp"] = arr
                elif short == "lcc":
                    out["lcc"] = arr
                elif short == "mcc":
                    out["mcc"] = arr
                elif short == "hcc":
                    out["hcc"] = arr
                elif short == "tirf":
                    out["tirf"] = arr
                elif short == "tsnowp":
                    out["tsnowp"] = arr
                elif short == "h":
                    out["h"] = arr
                elif short == "u" and level == 20:
                    out["u20"] = arr
                elif short == "u" and level == 50:
                    out["u50"] = arr
                elif short == "u" and level == 100:
                    out["u100"] = arr
                elif short == "v" and level == 20:
                    out["v20"] = arr
                elif short == "v" and level == 50:
                    out["v50"] = arr
                elif short == "v" and level == 100:
                    out["v100"] = arr
                elif short == "r" and level == 10:
                    out["r10"] = arr
                elif short == "r" and level == 20:
                    out["r20"] = arr
                elif short == "r" and level == 50:
                    out["r50"] = arr
                elif short == "r" and level == 100:
                    out["r100"] = arr
                # Réflectivité directe : discipline 0, cat 16, param 193
                elif disc == 0 and cat == 16 and num == 193:
                    out["refl"] = arr
            except Exception:
                pass
            codes_release(gid)
    return out


def _clean(arr, missing=9999.0):
    arr = np.asarray(arr, dtype=np.float64)
    arr = np.where((arr >= missing - 1.0) | ~np.isfinite(arr), np.nan, arr)
    return arr


def _clean_sp(arr):
    """La pression surface est en Pa (~100 000) : le seuil 'missing' GRIB
    (9999) ne s'applique pas — on filtre seulement les valeurs aberrantes."""
    arr = np.asarray(arr, dtype=np.float64)
    return np.where((arr < 40000.0) | (arr > 110000.0) | ~np.isfinite(arr),
                    np.nan, arr)


# ── Calculs physiques (grille native) ───────────────────────────────────────
def compute_fields(raw, altitude, previous, lead_hour):
    """Calcule tous les champs sur la grille native. Retourne
    (fields: dict nom → array 2D, state: dict cumuls pour l'échéance suivante)."""
    shape = (NJ, NI)

    def get(name, clip=None, scale=1.0, offset=0.0):
        arr = raw.get(name)
        if arr is None:
            return np.full(shape, np.nan)
        arr = _clean(arr) * scale + offset
        if clip:
            arr = np.clip(arr, *clip)
        return arr

    t2m = get("t2m", scale=1.0, offset=-273.15)          # °C
    r2 = np.clip(get("r2"), 0, 100)                       # %
    u10 = get("u10")
    v10 = get("v10")
    efg_u = get("efg10")
    efg_v = get("nfg10")
    cape = np.maximum(get("cape"), 0.0)
    refl = np.clip(get("refl"), 0, 80)
    sp = _clean_sp(raw.get("sp")) * (1.0 / 100.0)         # hPa
    lcc = np.clip(get("lcc"), 0, 100)
    mcc = np.clip(get("mcc"), 0, 100)
    hcc = np.clip(get("hcc"), 0, 100)
    tgrp_cum = get("tgrp")
    tirf_cum = get("tirf")
    tsnowp_cum = get("tsnowp")
    # Altitude réelle : fournie par l'appelant (SP3 H+0, mis en cache)
    if altitude is not None and np.any(np.isfinite(altitude)):
        h_alt = np.asarray(altitude, dtype=np.float64)
    else:
        h_alt = np.zeros(shape)

    fields = {}

    def put(name, arr):
        if arr is not None:
            fields[name] = arr

    # ── Cumuls → valeurs horaires ────────────────────────────────────────
    prev = previous or {}
    rain_total = np.where(np.isfinite(tirf_cum), np.maximum(tirf_cum, 0.0), np.nan)
    snow_total = np.where(np.isfinite(tsnowp_cum), np.maximum(tsnowp_cum, 0.0), np.nan)
    graupel_total = np.where(np.isfinite(tgrp_cum), np.maximum(tgrp_cum, 0.0), np.nan)
    if lead_hour == 0 and not np.any(np.isfinite(rain_total)):
        rain_total = np.zeros(shape)
    if lead_hour == 0 and not np.any(np.isfinite(snow_total)):
        snow_total = np.zeros(shape)
    if lead_hour == 0 and not np.any(np.isfinite(graupel_total)):
        graupel_total = np.zeros(shape)

    prev_rain = prev.get("rain_total")
    prev_snow = prev.get("snow_total")
    prev_graupel = prev.get("graupel_total")
    rain = np.where(np.isfinite(rain_total),
                    np.maximum(rain_total - (prev_rain if prev_rain is not None else 0.0), 0.0),
                    np.nan)
    snow = np.where(np.isfinite(snow_total),
                    np.maximum(snow_total - (prev_snow if prev_snow is not None else 0.0), 0.0),
                    np.nan)
    graupel = np.where(np.isfinite(graupel_total),
                       np.maximum(graupel_total - (prev_graupel if prev_graupel is not None else 0.0), 0.0),
                       np.nan)
    if prev_rain is None:
        rain[~np.isfinite(rain_total)] = np.nan

    # ── Vent ─────────────────────────────────────────────────────────────
    ws10 = np.hypot(np.nan_to_num(u10, nan=0.0), np.nan_to_num(v10, nan=0.0)) * 3.6
    ws10[~np.isfinite(u10) | ~np.isfinite(v10)] = np.nan
    gust = np.hypot(np.nan_to_num(efg_u, nan=0.0), np.nan_to_num(efg_v, nan=0.0)) * 3.6
    gust[~np.isfinite(efg_u) | ~np.isfinite(efg_v)] = np.nan
    wind_dir = (np.degrees(np.arctan2(-np.nan_to_num(u10, nan=0.0),
                                      -np.nan_to_num(v10, nan=0.0))) % 360.0)
    wind_dir[~np.isfinite(u10) | ~np.isfinite(v10)] = np.nan

    # Vent 20/50/100 m (bonus HP1) + cisaillement vertical
    ws100 = np.full(shape, np.nan)
    shear = np.full(shape, np.nan)
    if "u100" in raw and "v100" in raw:
        ws100 = np.hypot(np.nan_to_num(raw["u100"], nan=0.0),
                         np.nan_to_num(raw["v100"], nan=0.0)) * 3.6
        ws100[~np.isfinite(raw["u100"]) | ~np.isfinite(raw["v100"])] = np.nan
        du = np.nan_to_num(raw["u100"], nan=0.0) - np.nan_to_num(u10, nan=0.0)
        dv = np.nan_to_num(raw["v100"], nan=0.0) - np.nan_to_num(v10, nan=0.0)
        shear = np.hypot(du, dv) * 3.6
        shear[~np.isfinite(raw["u100"]) | ~np.isfinite(u10)] = np.nan

    # ── Point de rosée / ressenti / humidex ──────────────────────────────
    rel = np.clip(r2 / 100.0, 0.01, 1.0)
    gamma = np.log(rel) + 17.625 * t2m / (243.04 + t2m)
    dew = 243.04 * gamma / (17.625 - gamma)
    dew[~np.isfinite(t2m) | ~np.isfinite(r2)] = np.nan

    wind_chill = t2m.copy()
    chill_ok = np.isfinite(t2m) & np.isfinite(ws10) & (t2m <= 10) & (ws10 >= 4.8)
    wf = np.power(np.maximum(np.nan_to_num(ws10, nan=0.0), 0.0), 0.16)
    wind_chill[chill_ok] = (13.12 + 0.6215 * t2m[chill_ok]
                            - 11.37 * wf[chill_ok] + 0.3965 * t2m[chill_ok] * wf[chill_ok])

    td_k = np.clip(dew + 273.15, 173.15, 333.15)
    e = 6.11 * np.exp(5417.7530 * (1.0 / 273.16 - 1.0 / td_k))
    humidex = t2m + 0.5555 * (e - 10.0)

    # ── Nuages totaux (superposition) ────────────────────────────────────
    cloud = 100.0 * (1.0 - (1.0 - lcc / 100.0) * (1.0 - mcc / 100.0) * (1.0 - hcc / 100.0))
    cloud[~np.isfinite(lcc) | ~np.isfinite(mcc) | ~np.isfinite(hcc)] = np.nan

    # ── Pression MSL (réduction hypsométrique avec altitude réelle) ──────
    t_k = np.maximum(t2m + 273.15, 180.0)
    pressure = sp * np.exp(9.80665 * np.maximum(h_alt, -500.0)
                           / (287.05 * (t_k + 0.00325 * np.maximum(h_alt, 0.0))))
    pressure[~np.isfinite(sp) | ~np.isfinite(t2m)] = np.nan
    pressure = np.clip(pressure, 850, 1085)

    # ── Condition code (0-9, comme météociel) ────────────────────────────
    condition = np.zeros(shape, dtype=np.int16)
    condition[np.isfinite(cloud) & (cloud <= 20)] = 1
    condition[np.isfinite(cloud) & (cloud > 20) & (cloud <= 55)] = 2
    condition[np.isfinite(cloud) & (cloud > 55) & (cloud <= 85)] = 3
    condition[np.isfinite(cloud) & (cloud > 85)] = 4
    condition[np.isfinite(gust) & (gust >= 70)] = 9
    condition[np.isfinite(rain) & (rain >= 0.1)] = 5
    condition[np.isfinite(rain) & (rain >= 5.0)] = 6
    condition[np.isfinite(snow) & (snow >= 0.1)] = 7
    # Brouillard : humidité très élevée + nuages bas + vent faible
    fog = (r2 >= 96) & (lcc >= 90) & (ws10 < 10)
    condition[fog & np.isfinite(r2) & np.isfinite(lcc) & np.isfinite(ws10)] = 8

    # ── Diagnostics orageux ──────────────────────────────────────────────
    thunder = np.zeros(shape, dtype=np.int16)
    thunder[(cape >= 100) | (refl >= 30)] = 1
    thunder[(cape >= 500) | (refl >= 40)] = 2
    thunder[(cape >= 1200) | (refl >= 50)] = 3
    thunder[(cape >= 2200) & (refl >= 52)] = 4
    thunder[(refl >= 58) | ((cape >= 1800) & (gust >= 90))] = 4
    thunder[~np.isfinite(cape) & ~np.isfinite(refl)] = 0

    lightning = np.clip(
        np.nan_to_num(cape, nan=0.0) / 30.0
        + np.maximum(np.nan_to_num(refl, nan=0.0) - 25.0, 0) * 1.8,
        0, 100)

    hail = np.zeros(shape, dtype=np.int16)
    hail[(cape >= 500) & (refl >= 42)] = 1
    hail[(cape >= 1200) & (refl >= 50)] = 2
    hail[((cape >= 2200) & (refl >= 55)) | (graupel >= 2)] = 3

    conv_frac = np.clip(np.nan_to_num(cape, nan=0.0) / 1200.0, 0, 1) \
        * np.clip((np.nan_to_num(refl, nan=0.0) - 20.0) / 25.0, 0, 1)
    conv_precip = rain * conv_frac

    # Type d'orage — AMÉLIORÉ : cisaillement vertical 10→100 m inclus
    # 0 = pas d'orage organisé, 1 = cellules isolées, 2 = multicellulaire,
    # 3 = ligne/MCS, 4 = convection très intense / supercellulaire
    storm_type = np.zeros(shape, dtype=np.int16)
    storm_type[thunder == 1] = 1
    storm_type[thunder == 2] = 2
    strong_shear = np.nan_to_num(shear, nan=0.0) >= 40  # > 40 km/h de cisaillement
    storm_type[(thunder >= 3) & (refl >= 50) & strong_shear] = 3
    storm_type[(thunder >= 4) & (cape >= 2000)] = 4
    storm_type[(thunder >= 3) & (refl >= 50) & ~strong_shear] = 3

    # ── Diagnostics neige ────────────────────────────────────────────────
    snow_ratio = np.select(
        [t2m <= -10, t2m <= -5, t2m <= 0, t2m <= 1.5],
        [15.0, 12.0, 10.0, 6.0], default=2.0)
    snow_fresh = np.maximum(snow, 0.0) * snow_ratio / 10.0   # cm

    prev_fresh = prev.get("fresh_snow")
    if prev_fresh is None:
        snow_depth = snow_fresh.copy()
    else:
        snow_depth = np.nan_to_num(prev_fresh, nan=0.0) + np.nan_to_num(snow_fresh, nan=0.0)
        snow_depth[~np.isfinite(snow_fresh) & ~np.isfinite(prev_fresh)] = np.nan

    snow_phase = np.zeros(shape, dtype=np.int16)
    snow_phase[np.isfinite(rain) & (rain >= 0.1)] = 1
    snow_phase[(snow >= 0.03) & (t2m > 0.5)] = 2
    snow_phase[(snow >= 0.03) & (t2m <= 0.5)] = 3

    snow_stick = np.zeros(shape, dtype=np.int16)
    snow_stick[(snow_fresh >= 0.05) & (t2m <= 2.0)] = 1
    snow_stick[(snow_fresh >= 0.2) & (t2m <= 1.0)] = 2
    snow_stick[(snow_fresh >= 0.5) & (t2m <= 0.0)] = 3

    snow_risk = np.zeros(shape, dtype=np.int16)
    snow_risk[(snow >= 0.03) | ((rain >= 0.2) & (t2m <= 1.5))] = 1
    snow_risk[(snow_fresh >= 0.3) | ((rain >= 1.0) & (t2m <= 0.5))] = 2
    snow_risk[(snow_fresh >= 1.0) | ((rain >= 3.0) & (t2m <= 0.0))] = 3
    snow_risk[(snow_fresh >= 3.0) | ((rain >= 8.0) & (t2m <= -1.0))] = 4

    # ── LCL (formule de Lawrence) ────────────────────────────────────────
    lcl = np.clip(125.0 * (t2m - dew), 0, 5000)

    # ── Sortie ───────────────────────────────────────────────────────────
    put("temperature_c", t2m)
    put("wind_chill_c", wind_chill)
    put("dewpoint_c", dew)
    put("humidex", humidex)
    put("humidity_pct", r2)
    put("precipitation_mm", rain)
    put("precipitation_total_mm", rain_total)
    put("snowfall_mm", snow)
    put("snow_mm", snow)
    put("snow_fresh_cm", snow_fresh)
    put("snow_depth_cm", snow_depth)
    put("snow_water_equivalent_mm", snow_total)
    put("snowfall_total_mm", snow_total)
    put("graupel_mm", graupel)
    put("cloud_cover_pct", cloud)
    put("cloud_low_pct", lcc)
    put("cloud_mid_pct", mcc)
    put("cloud_high_pct", hcc)
    put("wind_speed_kmh", ws10)
    put("wind_direction_deg", wind_dir)
    put("wind_gust_kmh", gust)
    put("wind_100m_kmh", ws100)
    put("wind_shear_kmh", shear)
    put("pressure_hpa", pressure)
    put("pressure_surface_hpa", sp)
    put("surface_pressure_hpa", sp)
    put("cape_jkg", cape)
    put("reflectivity_dbz", refl)
    put("lcl_m", lcl)
    put("condition_code", condition)
    put("thunder_risk_code", thunder)
    put("lightning_score", lightning)
    put("hail_risk_code", hail)
    put("convective_precipitation_mm", conv_precip)
    put("storm_type_code", storm_type)
    put("snow_risk_code", snow_risk)
    put("snow_phase_code", snow_phase)
    put("snow_stick_risk_code", snow_stick)
    put("altitude_m", h_alt)

    state = {
        "rain_total": rain_total,
        "snow_total": snow_total,
        "graupel_total": graupel_total,
        "fresh_snow": snow_depth,
    }
    return fields, state


# ── Extraction par commune ──────────────────────────────────────────────────
COMMUNES_FILE = os.path.join(BASE_DIR, "config", "communes-compact.json")

# Colonnes stockées par commune : nom, échelle (int16 = round(v/scale)),
# offset ajouté avant division (pour les valeurs négatives → int16 non signé)
COMMUNE_COLUMNS = [
    # (nom, scale, offset)  → valeur stockée = (v + offset) / scale
    ("temperature_c", 0.1, 600),        # -60..+60 °C → 0..1200
    ("wind_chill_c", 0.1, 600),
    ("dewpoint_c", 0.1, 600),
    ("humidex", 0.1, 600),
    ("humidity_pct", 1.0, 0),
    ("precipitation_mm", 0.01, 0),
    ("precipitation_total_mm", 0.1, 0),
    ("snowfall_mm", 0.01, 0),
    ("snow_fresh_cm", 0.1, 0),
    ("snow_depth_cm", 0.1, 0),
    ("snow_water_equivalent_mm", 0.1, 0),
    ("graupel_mm", 0.01, 0),
    ("cloud_cover_pct", 1.0, 0),
    ("cloud_low_pct", 1.0, 0),
    ("cloud_mid_pct", 1.0, 0),
    ("cloud_high_pct", 1.0, 0),
    ("wind_speed_kmh", 1.0, 0),
    ("wind_direction_deg", 1.0, 0),
    ("wind_gust_kmh", 1.0, 0),
    ("wind_gust_max_kmh", 1.0, 0),   # rafale max depuis le run (comme météociel)
    ("wind_100m_kmh", 1.0, 0),
    ("wind_shear_kmh", 1.0, 0),
    ("pressure_hpa", 0.1, 0),
    ("pressure_surface_hpa", 0.1, 0),
    ("cape_jkg", 1.0, 0),
    ("reflectivity_dbz", 0.1, 0),
    ("lcl_m", 5.0, 0),
    ("condition_code", 1.0, 0),
    ("thunder_risk_code", 1.0, 0),
    ("lightning_score", 1.0, 0),
    ("hail_risk_code", 1.0, 0),
    ("convective_precipitation_mm", 0.01, 0),
    ("storm_type_code", 1.0, 0),
    ("snow_risk_code", 1.0, 0),
    ("snow_phase_code", 1.0, 0),
    ("snow_stick_risk_code", 1.0, 0),
    ("altitude_m", 1.0, 500),           # -500..+5000 m
]

NAN_I16 = -32768


def load_communes():
    """Charge les communes : [[code, nom, postaux[], dept, pop, lat, lon], ...]"""
    import json
    with open(COMMUNES_FILE, encoding="utf-8") as f:
        return json.load(f)


def bilinear_sample(fields, communes):
    """Interpolation bilinéaire de chaque champ aux coordonnées exactes des
    communes. Retourne {nom_champ: array (n_communes,)}."""
    lats = np.array([c[5] for c in communes], dtype=np.float64)
    lons = np.array([c[6] for c in communes], dtype=np.float64)
    rows_f = (LAT0 - lats) / STEP
    cols_f = (lons - LON0) / STEP
    r0 = np.clip(np.floor(rows_f).astype(np.int64), 0, NJ - 2)
    c0 = np.clip(np.floor(cols_f).astype(np.int64), 0, NI - 2)
    fr = (rows_f - r0).astype(np.float64)
    fc = (cols_f - c0).astype(np.float64)
    r1, c1 = r0 + 1, c0 + 1

    out = {}
    for name, arr in fields.items():
        if arr is None:
            continue
        a = np.asarray(arr, dtype=np.float64)
        v00 = a[r0, c0]
        v01 = a[r0, c1]
        v10 = a[r1, c0]
        v11 = a[r1, c1]
        v = (v00 * (1 - fr) * (1 - fc) + v01 * (1 - fr) * fc
             + v10 * fr * (1 - fc) + v11 * fr * fc)
        out[name] = v
    return out


def quantize(values, scale, offset):
    q = np.round((values + offset) / scale)
    q = np.clip(q, -32767, 32767)
    q[~np.isfinite(values)] = NAN_I16
    return q.astype(np.int16)


# ── Grilles de valeurs pour la sonde (format HKV1, comme le front l'attend) ──
PROBE_W, PROBE_H = 440, 328  # grille réduite (facteur 5 vs 2200×1640)

def export_probe(field, out_path):
    """Exporte une grille 2D en format HKV1 gzip pour la sonde au survol.
    Structure : 'HKV1' + width u16 + height u16 + min f32 + max f32 + u16[…]
    (65535 = NaN)."""
    import gzip
    data = np.asarray(field, dtype=np.float64)
    ny, nx = data.shape
    fin = data[np.isfinite(data)]
    if fin.size == 0:
        min_val, max_val = 0.0, 1.0
    else:
        min_val = float(np.min(fin))
        max_val = float(np.max(fin))
    val_range = max_val - min_val if max_val > min_val else 1.0
    normalized = np.full(data.shape, 65535, dtype=np.uint16)
    ok = np.isfinite(data)
    normalized[ok] = np.clip(
        (data[ok] - min_val) / val_range * 65534.0, 0, 65534).astype(np.uint16)
    header = bytearray(b'HKV1')
    header.extend(np.uint16(nx).tobytes())
    header.extend(np.uint16(ny).tobytes())
    header.extend(np.float32(min_val).tobytes())
    header.extend(np.float32(max_val).tobytes())
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with gzip.open(out_path, "wb") as f:
        f.write(bytes(header) + normalized.tobytes())


def save_probes(out_dir, lead, fields, step_files, regridded):
    """Écrit maps/values/{layer}/{lead}.hkv.gz pour chaque paramètre tuilé.
    step_files["probes"] = {layer: rel_path}."""
    probes = {}
    for tile_name, fname in TILE_FIELDS.items():
        data = regridded.get(tile_name)
        if data is None:
            continue
        # Sous-échantillonnage vers PROBE_W × PROBE_H (moyenne de blocs)
        sy = data.shape[0] // PROBE_H
        sx = data.shape[1] // PROBE_W
        if sy >= 1 and sx >= 1:
            small = np.nanmean(
                data[:PROBE_H * sy, :PROBE_W * sx].reshape(
                    PROBE_H, sy, PROBE_W, sx),
                axis=(1, 3))
        else:
            small = data
        rel = "maps/values/%s/%03d.hkv.gz" % (tile_name, lead)
        export_probe(small, os.path.join(out_dir, "..", rel.replace("/", os.sep)))
        probes[tile_name] = rel
    if probes:
        step_files["probes"] = probes


# ── Écriture des fichiers par département ───────────────────────────────────
def write_department_files(out_dir, run_str, leads, per_lead_values, communes):
    """per_lead_values : dict lead → dict champ → array (n_communes,).
    Écrit output/arome/communes/{dept}.bin.gz + index.json."""
    import json
    cdir = os.path.join(out_dir, "communes")
    os.makedirs(cdir, exist_ok=True)

    # Regroupe les communes par département (ordre du fichier)
    by_dept = {}
    for i, c in enumerate(communes):
        by_dept.setdefault(c[3], []).append(i)

    # Cumuls par commune et par échéance (pluie/neige totales déjà fournies)
    leads_sorted = sorted(leads)
    col_names = [c[0] for c in COMMUNE_COLUMNS]
    col_scales = [c[1] for c in COMMUNE_COLUMNS]
    col_offsets = [c[2] for c in COMMUNE_COLUMNS]

    for dept, idxs in by_dept.items():
        idxs = sorted(idxs)
        n = len(idxs)
        # Entête
        header = bytearray()
        header += b"MCV2"
        header += struct.pack("<H", n)                 # nb communes
        header += struct.pack("<H", len(leads_sorted))  # nb échéances
        header += struct.pack("<H", len(col_names))     # nb colonnes
        run_b = run_str.encode("ascii", "replace")[:40].ljust(40, b"\0")
        header += run_b
        # Communes : code(5) + nom variable + lat/lon + population
        for i in idxs:
            code = str(communes[i][0])[:5].encode("ascii", "replace").ljust(5, b"\0")
            nom = str(communes[i][1]).encode("utf-8")[:80]
            header += code
            header += struct.pack("<B", len(nom)) + nom
            header += struct.pack("<f", float(communes[i][5]))   # lat
            header += struct.pack("<f", float(communes[i][6]))   # lon
            header += struct.pack("<I", int(communes[i][4]))     # population
        # Colonnes : nom(32) + échelle + offset
        for cname, scale, offset in COMMUNE_COLUMNS:
            header += cname.encode("ascii", "replace")[:32].ljust(32, b"\0")
            header += struct.pack("<ff", scale, offset)
        # Échéances : heures
        for lh in leads_sorted:
            header += struct.pack("<H", lh)
        # Alignement des données sur 2 octets (exigé par Int16Array côté JS)
        if len(header) % 2 == 1:
            header += b"\0"

        # Données : construction vectorisée par échéance
        # mat[lead] = (n_communes, n_cols) en int16 → concaténation
        mats = []
        for lh in leads_sorted:
            pv = per_lead_values.get(lh)
            if pv is None:
                raise RuntimeError("Valeurs manquantes pour H+%d" % lh)
            n_cols = len(col_names)
            mat = np.empty((n, n_cols), dtype=np.int16)
            for j, (cname, scale, offset) in enumerate(COMMUNE_COLUMNS):
                arr = pv.get(cname)
                if arr is None:
                    mat[:, j] = NAN_I16
                    continue
                q = np.round((np.asarray(arr, dtype=np.float64)[idxs] + offset) / scale)
                q = np.clip(q, -32767, 32767)
                q[~np.isfinite(np.asarray(arr, dtype=np.float64)[idxs])] = NAN_I16
                mat[:, j] = q.astype(np.int16)
            mats.append(mat)
        data = np.concatenate(mats, axis=1).ravel() if mats else \
            np.zeros(0, dtype=np.int16)

        payload = bytes(header) + data.tobytes()
        gz = zlib.compress(payload, 9)
        with open(os.path.join(cdir, "%s.bin.gz" % dept), "wb") as f:
            f.write(gz)

    # index.json
    meta = {
        "format": "MCV2",
        "run_time": run_str,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
        .isoformat().replace("+00:00", "Z"),
        "columns": [c[0] for c in COMMUNE_COLUMNS],
        "leads": leads_sorted,
        "departments": {d: len(v) for d, v in by_dept.items()},
        "communes_total": len(communes),
    }
    with open(os.path.join(cdir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return cdir


# ── Rendu des tuiles ────────────────────────────────────────────────────────
def save_tile(name, arr, lat, lon, out_dir, lead, step_files, regridded):
    if arr is None:
        return
    if name not in regridded:
        try:
            regridded[name] = regrid(arr, lat, lon)
        except Exception as e:
            print("  [%s] regrid: %s" % (name, e))
            return
    data = regridded[name]
    rgba = apply_palette(data, PALETTES.get(name, PALETTES["temperature"]))
    ddir = os.path.join(out_dir, name)
    os.makedirs(ddir, exist_ok=True)
    dst = os.path.join(ddir, "%03d.webp" % lead)
    Image.fromarray(rgba, "RGBA").save(dst, format="WEBP", quality=85, method=4)
    if "files" not in step_files:
        step_files["files"] = {}
    step_files["files"][name] = "maps/%s/%03d.webp" % (name, lead)


# Champs rendus en tuiles (compatibles palettes existantes)
TILE_FIELDS = {
    "temperature": "temperature_c",
    "temperature_ressentie": "wind_chill_c",
    "point_rosee": "dewpoint_c",
    "humidex": "humidex",
    "humidite": "humidity_pct",
    "pluie_1h": "precipitation_mm",
    "pluie_cumul": "precipitation_total_mm",
    "reflectivite": "reflectivity_dbz",
    "graupel": "graupel_mm",
    "vent": "wind_speed_kmh",
    "rafales": "wind_gust_kmh",
    "nebulosite": "cloud_cover_pct",
    "nuages_bas": "cloud_low_pct",
    "nuages_moyens": "cloud_mid_pct",
    "nuages_eleves": "cloud_high_pct",
    "mucape": "cape_jkg",
    "neige": "snow_fresh_cm",
    "neige_au_sol": "snow_depth_cm",
    "equivalent_eau_neige": "snow_water_equivalent_mm",
    "pression": "pressure_hpa",
    "pression_surface": "pressure_surface_hpa",
}


def render_lead(run_str, lead, out_dir, step_files, previous_state, communes,
                per_lead_values, altitude_cache):
    """Télécharge, décode, calcule, rend les tuiles + échantillonne les communes."""
    tmp = tempfile.mkdtemp(prefix="arome_grib_")
    try:
        paths = download_packages(run_str, lead, tmp, with_sp3=(lead == 0))
        if len(paths) < 3:
            print("  H+%02d: packages insuffisants (%d)" % (lead, len(paths)))
            return False

        raw = {}
        for p in paths:
            raw.update(read_grib(p))

        if lead == 0:
            if "h" in raw:
                altitude_cache["h"] = _clean(raw["h"])
                print("  Altitude SP3 chargée (min %.0f m, max %.0f m)"
                      % (np.nanmin(altitude_cache["h"]), np.nanmax(altitude_cache["h"])))
            else:
                print("  WARNING: altitude absente de SP3 H+0")
        altitude = altitude_cache.get("h", np.zeros((NJ, NI)))

        fields, state = compute_fields(raw, altitude, previous_state, lead)
        if not fields:
            print("  H+%02d: aucun champ calculé" % lead)
            return False
        # CRITIQUE : réinjecte l'état des cumuls (rain_total, snow_total,
        # graupel_total, fresh_snow) pour que l'échéance suivante calcule les
        # valeurs HORAIRES par différence (cumul(H+n) − cumul(H+n−1)).
        previous_state.update(state)

        # ── Tuiles ─────────────────────────────────────────────────────
        lats = LAT0 - np.arange(NJ) * STEP
        lons = LON0 + np.arange(NI) * STEP
        regridded = {}
        for tile_name, fname in TILE_FIELDS.items():
            arr = fields.get(fname)
            if arr is not None:
                save_tile(tile_name, arr, lats, lons, out_dir, lead,
                          step_files, regridded)

        # Rafale max cumulée depuis le run (paramètre « rafale max échéance »).
        # NB : à H+0 les rafales sont NaN (pas de max sur un intervalle vide) ;
        # on initialise à 0 pour que le cumul ne soit pas pollué par NaN.
        prev_max = previous_state.get("gust_max")
        cur_gust = fields["wind_gust_kmh"]
        if prev_max is None:
            gust_max = np.where(np.isfinite(cur_gust), cur_gust, 0.0)
        else:
            gust_max = np.maximum(np.nan_to_num(prev_max, nan=0.0),
                                  np.nan_to_num(cur_gust, nan=0.0))
            gust_max[~np.isfinite(prev_max) & ~np.isfinite(cur_gust)] = np.nan
        previous_state["gust_max"] = gust_max
        fields["wind_gust_max_kmh"] = gust_max
        save_tile("rafales_cumul", gust_max, lats, lons, out_dir, lead,
                  step_files, regridded)

        # ── Échantillonnage par commune ────────────────────────────────
        sampled = bilinear_sample(fields, communes)
        per_lead_values[lead] = sampled

        # ── Grilles de valeurs pour la sonde au survol ─────────────────
        save_probes(out_dir, lead, fields, step_files, regridded)

        print("  H+%02d: %d champs, %d tuiles, %d probes, %d communes échantillonnées"
              % (lead, len(fields), len(step_files.get("files", {})),
                 len(step_files.get("probes", {})), len(communes)))
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(max_hours=51):
    """Génère tuiles AROME + prévisions par commune + manifeste."""
    run_str = latest_run()
    leads = available_leads(run_str)
    print("Run AROME: %s | échéances disponibles: %s" % (run_str, len(leads)))
    out_dir = os.path.join(BASE_DIR, "output", "arome", "maps")
    os.makedirs(out_dir, exist_ok=True)

    communes = load_communes()
    print("Communes chargées: %d" % len(communes))

    steps = []
    previous_state = {}
    per_lead_values = {}
    altitude_cache = {}
    for lh in sorted(leads):
        if lh > max_hours:
            break
        step_files = {}
        ok = render_lead(run_str, lh, out_dir, step_files, previous_state,
                         communes, per_lead_values, altitude_cache)
        if ok and step_files:
            vt = datetime.datetime.fromisoformat(run_str.replace("Z", "+00:00")) \
                + datetime.timedelta(hours=lh)
            steps.append({"lead_hour": lh, "valid_time": vt.isoformat(),
                          "files": step_files.get("files", {}),
                          "probes": step_files.get("probes", {})})

    # Fichiers par département + index
    write_department_files(out_dir, run_str,
                           [s["lead_hour"] for s in steps],
                           per_lead_values, communes)

    # Fond de carte (pays voisins inclus) + masque France (bornes correctes)
    try:
        from generate_fond import generate_all
        generate_all()
    except Exception as e:
        print("WARNING: fond de carte non généré (%s)" % e)

    from fetch_and_render_all import write_manifest
    meta = {"name": "AROME HD (1,3 km)", "provider": "Meteo-France",
            "resolution": "1,3 km (0.01°)", "run_time": run_str}
    write_manifest(out_dir, steps, meta)
    print("OK AROME open data : %d échéances, %d communes"
          % (len(steps), len(communes)))


if __name__ == "__main__":
    run()
