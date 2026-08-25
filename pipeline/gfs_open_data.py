#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gfs_open_data.py — Pipeline GFS 0.25° (NOAA / NOMADS), open data sans clé
==========================================================================
  - Téléchargement sous-région Europe via filter_gfs_0p25.pl (TLS vérifié,
    timeouts + 3 tentatives, log des erreurs — plus jamais d'échec silencieux).
  - Échéances : H+00 → H+120 pas de 3 h (limite réelle des fichiers 0p25).
  - Rendus : domaine Europe (output/gfs/maps) ET domaine France
    (output/gfs_france/maps) — le téléchargement couvre les deux.
  - Couches physiquement honnêtes : cumuls réels, formules ressentie/humidex,
    humidité & neige au sol décodées correctement (noms cfgrib GFS).
"""
import os
import sys
import json
import time
import tempfile
import datetime
import warnings

import requests
import numpy as np

warnings.filterwarnings("ignore")  # bruit cfgrib/xarray dans les logs CI

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))

from domains import EUROPE, FRANCE  # noqa: E402
from render import (  # noqa: E402
    LAYER_ORDER, save_webp, write_hkv, write_places, write_manifest,
    render_z500_with_isobars, wind_chill_c, heat_index_c, humidex_c,
)

HEADERS = {"User-Agent": "gfs-weather-map/2.0 (Monsieur Meteo)"}
NOMADS = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
GFS_REQ_VARS = ["TMP", "DPT", "UGRD", "VGRD", "GUST", "APCP", "CAPE",
                "SNOD", "PRMSL", "PRES", "RH", "TCDC", "HGT"]
# Niveaux demandés au filtre NOMADS
GFS_LEVS = {
    "lev_2_m_above_ground": "on",
    "lev_10_m_above_ground": "on",
    "lev_surface": "on",
    "lev_mean_sea_level": "on",
    "lev_entire_atmosphere": "on",
    "lev_500_mb": "on",
}

# Alias cfgrib GFS → clés canoniques
ALIASES = {
    "t2m": "T2M", "2t": "T2M",
    "d2m": "DPT", "2d": "DPT",
    "r2": "RH", "2r": "RH",
    "u10": "U10", "10u": "U10",
    "v10": "V10", "10v": "V10",
    "gust": "GUST",
    "tp": "APCP",
    "cape": "CAPE", "mcape": "MUCAPE",
    "sde": "SNOD",
    "msl": "PRMSL", "prmsl": "PRMSL",
    "sp": "PRES",
    "tcc": "TCDC",
    "gh": "HGT",
}


def log(msg):
    print("[GFS] " + msg, flush=True)


def latest_run(now=None):
    """Dernier run GFS (00/06/12/18Z) suffisamment mature (≥ 3 h 45)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    run_h = (now.hour // 6) * 6
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    if (now - run_dt).total_seconds() < 13500:  # 3 h 45
        run_dt -= datetime.timedelta(hours=6)
    return run_dt


def download_lead(run_dt, lead):
    """Télécharge le GRIB filtré d'une échéance (3 tentatives, TLS vérifié)."""
    day = run_dt.strftime("%Y%m%d")
    hh = "%02d" % run_dt.hour
    params = {
        "dir": "/gfs.%s/%s/atmos" % (day, hh),
        "file": "gfs.t%sz.pgrb2.0p25.f%03d" % (hh, lead),
        "subregion": "",
        "leftlon": "-40", "rightlon": "45",
        "toplat": "75", "bottomlat": "22",
    }
    for v in GFS_REQ_VARS:
        params["var_" + v] = "on"
    params.update(GFS_LEVS)

    last_err = None
    for attempt in range(1, 4):
        try:
            r = requests.get(NOMADS, params=params, headers=HEADERS,
                             timeout=120, verify=True)
            if r.status_code == 200 and len(r.content) > 1000:
                return r.content
            last_err = "HTTP %s (%d octets)" % (r.status_code, len(r.content))
        except Exception as e:  # réseau / TLS
            last_err = "%s" % e
        log("  H+%03d tentative %d/3 échouée : %s" % (lead, attempt, last_err))
        time.sleep(5 * attempt)
    raise RuntimeError("H+%03d : téléchargement impossible (%s)" % (lead, last_err))


def decode_grib(grib_bytes):
    """Décode un GRIB GFS → dict {clé canonique: (values 2D, lat, lon)}."""
    import cfgrib
    cached = {}
    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as tf:
        tf.write(grib_bytes)
        tmp = tf.name
    try:
        for ds in cfgrib.open_datasets(tmp):
            for v in ds.data_vars:
                key = ALIASES.get(v.lower())
                if key is None:
                    continue
                # TCDC : ignorer les niveaux isobariques parasites
                if key == "TCDC" and "isobaricInhPa" in ds[v].coords:
                    continue
                val = ds[v].values
                # Réduction des dimensions de niveau si singleton
                while val.ndim > 2 and val.shape[0] == 1:
                    val = val[0]
                if val.ndim != 2:
                    continue
                lat = ds[v].latitude.values
                lon = ds[v].longitude.values
                # HGT : ne garder que le niveau 500 hPa
                if key == "HGT" and "isobaricInhPa" in ds[v].coords:
                    lev = float(ds[v].isobaricInhPa.values)
                    if lev != 500.0:
                        continue
                # Première occurrence conservée (évite les doublons tcc)
                if key not in cached:
                    cached[key] = (val.astype(np.float32), lat, lon)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return cached


def layer_field(key, cached):
    """Extrait (values, lat, lon) pour une clé, ou None."""
    return cached.get(key)


def render_lead(cached, lead, domain, out_dir, steps, state):
    """Rend toutes les couches d'une échéance pour un domaine."""
    step = {"lead_hour": lead, "valid_time": None, "files": {}}
    t2m = layer_field("T2M", cached)
    dpt = layer_field("DPT", cached)
    rh = layer_field("RH", cached)
    u10 = layer_field("U10", cached)
    v10 = layer_field("V10", cached)
    gust = layer_field("GUST", cached)
    apcp = layer_field("APCP", cached)
    cape = layer_field("MUCAPE", cached) or layer_field("CAPE", cached)
    snod = layer_field("SNOD", cached)
    prmsl = layer_field("PRMSL", cached)
    pres = layer_field("PRES", cached)
    tcdc = layer_field("TCDC", cached)
    hgt = layer_field("HGT", cached)

    def save(name, data, extra_hkv=True):
        dst = os.path.join(out_dir, name, "%03d.webp" % lead)
        save_webp(data, name, dst)
        step["files"][name] = "maps/%s/%03d.webp" % (name, lead)
        if extra_hkv:
            write_hkv(data, os.path.join(out_dir, "values", name,
                                         "%03d.hkv.gz" % lead))
        state["counts"][name] = state["counts"].get(name, 0) + 1

    def regrid(field, convert=None):
        if field is None:
            return None
        val, lat, lon = field
        if convert is not None:
            val = convert(val)
        return domain.regrid(val, lat, lon)

    if t2m is not None:
        t_c = regrid(t2m, lambda v: v - 273.15)
        save("temperature", t_c)
        # Ressentie & humidex (ont besoin du vent / point de rosée)
        wind_kmh = None
        if u10 is not None and v10 is not None:
            spd = np.sqrt(u10[0].astype(np.float32) ** 2
                          + v10[0].astype(np.float32) ** 2) * 3.6
            wind_kmh = domain.regrid(spd, u10[1], u10[2])
        if wind_kmh is not None:
            rh_g = regrid(rh) if rh is not None else None
            felt = t_c.copy()
            if rh_g is not None:
                felt = heat_index_c(t_c, rh_g)
                felt = wind_chill_c(felt, wind_kmh)
            save("temperature_ressentie", felt)
        if dpt is not None:
            td_c = regrid(dpt, lambda v: v - 273.15)
            save("point_rosee", td_c)
            save("humidex", humidex_c(t_c, td_c))

    if rh is not None:
        save("humidite", regrid(rh))

    if u10 is not None and v10 is not None:
        spd = np.sqrt(u10[0].astype(np.float32) ** 2
                      + v10[0].astype(np.float32) ** 2) * 3.6
        save("vent", domain.regrid(spd, u10[1], u10[2]))

    if gust is not None:
        g = regrid(gust, lambda v: v * 3.6)
        save("rafales", g)
        if state.get("max_gust") is None:
            state["max_gust"] = g.copy()
        else:
            state["max_gust"] = np.maximum(state["max_gust"], g)
        save("rafales_cumul", state["max_gust"])

    if tcdc is not None:
        # TCDC GFS déjà exprimé en % (0-100)
        save("nebulosite", regrid(tcdc))

    if cape is not None:
        save("mucape", regrid(cape))

    if prmsl is not None:
        p = regrid(prmsl, lambda v: v / 100.0)
        save("pression", p)

    if pres is not None:
        save("pression_surface", regrid(pres, lambda v: v / 100.0))

    if hgt is not None and prmsl is not None:
        z = regrid(hgt, lambda v: v / 10.0)
        p_hpa = regrid(prmsl, lambda v: v / 100.0)
        dst = os.path.join(out_dir, "geopotentiel_500", "%03d.webp" % lead)
        if z is not None and p_hpa is not None:
            render_z500_with_isobars(z, p_hpa, dst)
            step["files"]["geopotentiel_500"] = "maps/geopotentiel_500/%03d.webp" % lead
            state["counts"]["geopotentiel_500"] = state["counts"].get("geopotentiel_500", 0) + 1

    if apcp is not None:
        a = regrid(apcp)  # mm sur 3 h
        save("pluie_1h", a)
        if state.get("cum_precip") is None:
            state["cum_precip"] = a.copy()
        else:
            state["cum_precip"] = state["cum_precip"] + a
        save("pluie_cumul", state["cum_precip"])

    if snod is not None:
        save("neige_au_sol", regrid(snod, lambda v: v * 100.0))

    return step


def run_model(run_dt, domain, out_dir, max_hours, leads):
    """Exécute le rendu complet d'un modèle (un domaine)."""
    ensure = os.makedirs
    ensure(out_dir, exist_ok=True)
    steps = []
    state = {"counts": {}, "max_gust": None, "cum_precip": None}
    n_ok = 0
    for lh in leads:
        try:
            grib = download_lead(run_dt, lh)
        except Exception as e:
            log("!! H+%03d ignoré (%s)" % (lh, e))
            continue
        try:
            cached = decode_grib(grib)
        except Exception as e:
            log("!! H+%03d : décodage échoué (%s)" % (lh, e))
            continue
        if not cached:
            log("!! H+%03d : aucun champ décodé" % lh)
            continue
        step = render_lead(cached, lh, domain, out_dir, steps, state)
        steps.append(step)
        n_ok += 1
        log("  H+%03d OK (%d couches)" % (lh, len(step["files"])))

    if n_ok == 0:
        raise RuntimeError("Aucune échéance rendue pour %s" % out_dir)
    write_places(domain, out_dir)
    write_manifest(out_dir, steps,
                   {"model_name": "GFS 0.25° " + domain.name,
                    "provider": "NOAA (NOMADS) — open data",
                    "resolution": "0.25° (~25 km)",
                    "run_time": run_dt.isoformat()},
                   domain)
    log("Terminé : %d échéances, couches %s" % (
        n_ok, ", ".join("%s=%d" % kv for kv in sorted(state["counts"].items()))))
    return n_ok


def run_all(max_hours=120):
    max_hours = max(3, min(int(max_hours), 120))  # 6 = 3 échéances (mode ajustement)
    leads = list(range(0, max_hours + 1, 3))
    log("Échéances : H+00 → H+%03d (%d pas)" % (max_hours, len(leads)))

    run_dt = latest_run()
    log("Run GFS sélectionné : %s" % run_dt.isoformat())

    base = os.path.join(BASE_DIR, "output")
    run_model(run_dt, EUROPE, os.path.join(base, "gfs", "maps"),
              max_hours, leads)
    run_model(run_dt, FRANCE, os.path.join(base, "gfs_france", "maps"),
              max_hours, leads)
    print("[GFS] Pipeline terminé avec succès.", flush=True)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Pipeline GFS 0.25° Europe & France")
    ap.add_argument("--max-hours", type=int, default=120,
                    help="Échéance max GFS en heures (24-120, défaut 120)")
    args = ap.parse_args()
    run_all(max_hours=args.max_hours)


if __name__ == "__main__":
    main()
