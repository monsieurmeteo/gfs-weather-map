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
    render_z500_with_isobars, render_pression_with_isobars,
    render_temperature850_with_isotherms,
    wind_chill_c, heat_index_c, humidex_c,
)

HEADERS = {"User-Agent": "gfs-weather-map/2.0 (Monsieur Meteo)"}
NOMADS = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
GFS_REQ_VARS = ["TMP", "DPT", "UGRD", "VGRD", "GUST", "APCP", "CAPE",
                "SNOD", "PRMSL", "PRES", "RH", "TCDC", "LCDC", "MCDC", "HCDC", "HGT"]
# Niveaux demandés au filtre NOMADS
GFS_LEVS = {
    "lev_2_m_above_ground": "on",
    "lev_10_m_above_ground": "on",
    "lev_surface": "on",
    "lev_mean_sea_level": "on",
    "lev_entire_atmosphere": "on",
    "lev_low_cloud_layer": "on",
    "lev_middle_cloud_layer": "on",
    "lev_high_cloud_layer": "on",
    "lev_500_mb": "on",
    "lev_850_mb": "on",
}

# Alias cfgrib GFS → clés canoniques
ALIASES = {
    "t2m": "T2M", "2t": "T2M", "t": "T2M", "tmp": "T2M",
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
    "lcc": "LCC", "lcdc": "LCC",
    "mcc": "MCC", "mcdc": "MCC",
    "hcc": "HCC", "hcdc": "HCC",
    "gh": "HGT", "hgt": "HGT", "z": "HGT", "gp": "HGT",
}


def log(msg):
    print("[GFS] " + msg, flush=True)


def latest_run(now=None, need_lead=384):
    """Dernier run GFS (00/06/12/18Z) mature ET dont l'échéance need_lead
    est réellement publiée sur NOMADS (GFS publie par vagues : les échéances
    longues f192-f384 n'arrivent que ~5-6 h après le run — un run mature mais
    incomplet rendrait les chunks 150-384 vides).

    Repli automatique sur le run précédent (comme ARPEGE select_run).
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    for _ in range(3):  # au plus 3 runs en arrière (18 h)
        run_h = (now.hour // 6) * 6
        run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
        if (now - run_dt).total_seconds() < 13500:  # 3 h 45 de maturité min
            run_dt -= datetime.timedelta(hours=6)
        if _lead_available(run_dt, need_lead):
            return run_dt
        log("Run %s incomplet (f%03d indisponible), repli sur le précédent"
            % (run_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), need_lead))
        now = run_dt - datetime.timedelta(seconds=1)  # décale d'un cycle de 6 h
    raise RuntimeError("Aucun run GFS avec f%03d disponible sur NOMADS"
                       % need_lead)


def _lead_available(run_dt, lead, timeout=30):
    """HEAD NOMADS : l'échéance lead du run existe-t-elle (fichier présent) ?"""
    day = run_dt.strftime("%Y%m%d")
    hh = "%02d" % run_dt.hour
    url = ("%s?dir=/gfs.%s/%s/atmos&file=gfs.t%sz.pgrb2.0p25.f%03d"
           "&var_GUST=on&var_APCP=on&lev_10_m_above_ground=on&lev_surface=on"
           % (NOMADS, day, hh, hh, lead))
    try:
        r = requests.head(url, headers=HEADERS, timeout=timeout, verify=True)
        return r.status_code == 200
    except Exception:
        return False


def download_lead(run_dt, lead, light=False):
    """Télécharge le GRIB filtré d'une échéance (3 tentatives, TLS vérifié).

    light=True : uniquement GUST + APCP (échauffement des couches cumulatives).
    """
    day = run_dt.strftime("%Y%m%d")
    hh = "%02d" % run_dt.hour
    # Grille 100% GLOBALE mondiale (360°) : aucun découpage ni bordure sur toute la projection Europe/Lambert
    params = {
        "dir": "/gfs.%s/%s/atmos" % (day, hh),
        "file": "gfs.t%sz.pgrb2.0p25.f%03d" % (hh, lead),
    }
    if light:
        params["var_GUST"] = "on"
        params["var_APCP"] = "on"
        params["lev_10_m_above_ground"] = "on"
        params["lev_surface"] = "on"
    else:
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
                lat = ds[v].latitude.values
                lon = ds[v].longitude.values

                # Traitement des niveaux isobariques (HGT Z500, TMP T850)
                if "isobaricInhPa" in ds[v].coords:
                    levs = np.atleast_1d(ds[v].isobaricInhPa.values)
                    for idx, lev_val in enumerate(levs):
                        lev_f = float(lev_val)
                        if key == "HGT" and lev_f == 500.0:
                            val_2d = ds[v].values[idx] if ds[v].ndim == 3 else ds[v].values
                            cached["HGT"] = (val_2d.astype(np.float32), lat, lon)
                        elif key == "T2M" and lev_f == 850.0:
                            val_2d = ds[v].values[idx] if ds[v].ndim == 3 else ds[v].values
                            cached["T850"] = (val_2d.astype(np.float32), lat, lon)
                    continue

                val = ds[v].values
                # Réduction des dimensions de niveau si singleton
                while val.ndim > 2 and val.shape[0] == 1:
                    val = val[0]
                if val.ndim != 2:
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


def render_lead(cached, lead, run_dt, domain, out_dir, steps, state):
    """Rend toutes les couches d'une échéance pour un domaine."""
    step = {"lead_hour": lead,
            "valid_time": (run_dt + datetime.timedelta(hours=lead)).isoformat(),
            "files": {},
            "probes": {}}
    t2m = layer_field("T2M", cached)
    t850 = layer_field("T850", cached)
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
            step["probes"][name] = "maps/values/%s/%03d.hkv.gz" % (name, lead)
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

    if t850 is not None:
        t850_c = regrid(t850, lambda v: v - 273.15)
        if t850_c is not None:
            dst_t850 = os.path.join(out_dir, "temperature_850", "%03d.webp" % lead)
            os.makedirs(os.path.dirname(dst_t850), exist_ok=True)
            render_temperature850_with_isotherms(t850_c, dst_t850)
            step["files"]["temperature_850"] = "maps/temperature_850/%03d.webp" % lead
            write_hkv(t850_c, os.path.join(out_dir, "values", "temperature_850",
                                            "%03d.hkv.gz" % lead))
            step["probes"]["temperature_850"] = "maps/values/temperature_850/%03d.hkv.gz" % lead
            state["counts"]["temperature_850"] = state["counts"].get("temperature_850", 0) + 1

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

    lcc = cached.get("LCC")
    if lcc is not None:
        save("nuages_bas", regrid(lcc))

    mcc = cached.get("MCC")
    if mcc is not None:
        save("nuages_moyens", regrid(mcc))

    hcc = cached.get("HCC")
    if hcc is not None:
        save("nuages_eleves", regrid(hcc))

    if cape is not None:
        save("mucape", regrid(cape))

    if prmsl is not None:
        p = regrid(prmsl, lambda v: v / 100.0)
        dst_p = os.path.join(out_dir, "pression", "%03d.webp" % lead)
        render_pression_with_isobars(p, dst_p)
        step["files"]["pression"] = "maps/pression/%03d.webp" % lead
        write_hkv(p, os.path.join(out_dir, "values", "pression", "%03d.hkv.gz" % lead))
        state["counts"]["pression"] = state["counts"].get("pression", 0) + 1

    if pres is not None:
        save("pression_surface", regrid(pres, lambda v: v / 100.0))

    if hgt is not None and prmsl is not None:
        z = regrid(hgt, lambda v: v / 10.0)
        p_hpa = regrid(prmsl, lambda v: v / 100.0)
        if z is not None and p_hpa is not None:
            # Style synoptique (défaut, esprit Météociel) : bandes Z500 4 dam + isobares 5 hPa
            dst = os.path.join(out_dir, "geopotentiel_500", "%03d.webp" % lead)
            render_z500_with_isobars(z, p_hpa, dst, style="synoptique")
            step["files"]["geopotentiel_500"] = "maps/geopotentiel_500/%03d.webp" % lead
            state["counts"]["geopotentiel_500"] = state["counts"].get("geopotentiel_500", 0) + 1
            # Style détaillé (option UI) : isobares 1 hPa fins + 5 hPa épais
            dst2 = os.path.join(out_dir, "geopotentiel_500_meteociel", "%03d.webp" % lead)
            render_z500_with_isobars(z, p_hpa, dst2, style="detail")
            step["files"]["geopotentiel_500_meteociel"] = "maps/geopotentiel_500_meteociel/%03d.webp" % lead
            state["counts"]["geopotentiel_500_meteociel"] = state["counts"].get("geopotentiel_500_meteociel", 0) + 1

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


def warmup_from_cached(cached, domain, state):
    """Applique une échéance antérieure (GUST/APCP) à l'état cumulatif."""
    gust = layer_field("GUST", cached)
    apcp = layer_field("APCP", cached)
    if gust is not None:
        val, lat, lon = gust
        g = domain.regrid(val * 3.6, lat, lon)
        if g is not None:
            state["max_gust"] = (g.copy() if state["max_gust"] is None
                                 else np.maximum(state["max_gust"], g))
    if apcp is not None:
        val, lat, lon = apcp
        a = domain.regrid(val, lat, lon)
        if a is not None:
            state["cum_precip"] = (a.copy() if state["cum_precip"] is None
                                   else state["cum_precip"] + a)
    return state


def warmup_cumulative(run_dt, prior_leads, domain):
    """État cumulatif réel (max_gust, cum_precip) avant le premier lead du lot."""
    state = {"max_gust": None, "cum_precip": None}
    for lh in prior_leads:
        try:
            grib = download_lead(run_dt, lh, light=True)
            cached = decode_grib(grib)
        except Exception as e:
            log("  échauffement H+%03d ignoré (%s)" % (lh, e))
            continue
        warmup_from_cached(cached, domain, state)
    if state["max_gust"] is not None or state["cum_precip"] is not None:
        log("  échauffement cumulatif : %d échéances antérieures traitées"
            % len(prior_leads))
    return state


def run_model(run_dt, domain, out_dir, max_hours, leads, lead_min=0):
    """Exécute le rendu complet d'un modèle (un domaine).

    lead_min > 0 : échauffement du cumul (rafales_cumul / pluie_cumul) avec les
    échéances antérieures (téléchargement léger GUST+APCP), pour que les couches
    cumulatives restent correctes malgré le découpage en chunks parallèles.
    """
    ensure = os.makedirs
    ensure(out_dir, exist_ok=True)
    steps = []
    state = {"counts": {}, "max_gust": None, "cum_precip": None}
    n_ok = 0
    if int(lead_min) > 0:
        prior_leads = [lh for lh in compute_leads(max_hours) if lh < int(lead_min)]
        if prior_leads:
            state = warmup_cumulative(run_dt, prior_leads, domain)
            state["counts"] = {}
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
        step = render_lead(cached, lh, run_dt, domain, out_dir, steps, state)
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


def compute_leads(max_hours=384, lead_min=0, lead_max=None):
    """Génère la liste des échéances GFS officielles jusqu'à 384 h (16 jours).
    - 0 → 120 h  : pas fin de 3 h (court terme)
    - 126 → 240 h : pas de 6 h (moyen terme)
    - 252 → 384 h : pas de 12 h (long terme)
    """
    max_h = max(3, min(int(max_hours), 384))
    leads = list(range(0, min(max_h, 120) + 1, 3))
    if max_h > 120:
        h_mid = min(max_h, 240)
        leads.extend(range(126, h_mid + 1, 6))
    if max_h > 240:
        leads.extend(range(252, max_h + 1, 12))

    if lead_min is not None:
        leads = [lh for lh in leads if lh >= int(lead_min)]
    if lead_max is not None:
        leads = [lh for lh in leads if lh <= int(lead_max)]
    return sorted(list(set(leads)))


def run_all(max_hours=384, domain="both", lead_min=0, lead_max=None):
    leads = compute_leads(max_hours, lead_min=lead_min, lead_max=lead_max)
    if not leads:
        log("Aucune échéance à traiter dans l'intervalle [%s, %s]" % (lead_min, lead_max))
        return

    log("Échéances : H+%03d → H+%03d (%d pas)" % (leads[0], leads[-1], len(leads)))

    # Le run doit être identique pour TOUS les chunks : on vérifie l'échéance
    # maximale GLOBALE (max_hours), pas le lead_max local du chunk — sinon les
    # chunks courts choisiraient un run récent et les chunks longs un plus vieux.
    run_dt = latest_run(need_lead=max_hours)
    log("Run GFS sélectionné : %s" % run_dt.isoformat())

    base = os.path.join(BASE_DIR, "output")
    if domain in ("both", "europe"):
        run_model(run_dt, EUROPE, os.path.join(base, "gfs", "maps"),
                  leads[-1], leads, lead_min=lead_min)
    if domain in ("both", "france"):
        run_model(run_dt, FRANCE, os.path.join(base, "gfs_france", "maps"),
                  leads[-1], leads, lead_min=lead_min)
    print("[GFS] Pipeline terminé avec succès.", flush=True)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Pipeline GFS 0.25° Europe & France")
    ap.add_argument("--max-hours", type=int, default=384,
                    help="Échéance max GFS en heures (24-384, défaut 384)")
    ap.add_argument("--domain", choices=["both", "europe", "france"], default="both",
                    help="Domaine à générer : both (défaut), europe, france")
    ap.add_argument("--lead-min", type=int, default=0,
                    help="Échéance de début (ex: 0, 39, 75...)")
    ap.add_argument("--lead-max", type=int, default=None,
                    help="Échéance de fin (ex: 36, 72, 108...)")
    args = ap.parse_args()
    run_all(max_hours=args.max_hours, domain=args.domain,
            lead_min=args.lead_min, lead_max=args.lead_max)


if __name__ == "__main__":
    main()
