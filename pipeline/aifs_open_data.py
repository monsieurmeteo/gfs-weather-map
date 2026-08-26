#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aifs_open_data.py — Pipeline ECMWF AIFS 0.25° (modèle IA, open data)
====================================================================
  - Source : open data ECMWF (data.ecmwf.int) via le paquet ecmwf-opendata.
  - model="aifs-single" (data-driven), resol="0p25", runs 00/12Z.
  - Échéances H+00 → H+360 (15 jours) : pas 3 h → 6 h → 12 h.
  - Domaines : Europe (Lambert) + France (Mercator) — --domain both/europe/france.
  - Couches : comme les autres modèles (Z500, T850, pression, températures,
    vent, rafales, nuages, humidité, MUCAPE, pluie, neige au sol…).
"""
import os
import sys
import datetime
import tempfile

import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))

from domains import EUROPE, FRANCE  # noqa: E402
from render import (  # noqa: E402
    save_webp, write_hkv, write_places, write_manifest,
    render_z500_with_isobars, render_pression_with_isobars,
    render_temperature850_with_isotherms, ensure_dir,
    dew_point_c, heat_index_c, wind_chill_c, humidex_c,
)

RUN_MATURITY = 21600  # 6 h
MAX_LEAD = 360

SFC_PARAMS = ["2t", "2d", "10u", "10v", "msl", "sp", "tp", "tcc", "cape", "10fg"]
PL_PARAMS = ["z", "t", "r"]
PL_LEVELS = [500, 850]

# Alias cfgrib AIFS/IFS → clés canoniques
ALIASES = {
    "t2m": "T2M", "2t": "T2M",
    "d2m": "DPT", "2d": "DPT",
    "r2": "RH", "r": "RH",
    "u10": "U10", "10u": "U10",
    "v10": "V10", "10v": "V10",
    "fg10": "GUST", "10fg": "GUST",
    "tp": "APCP",
    "cape": "CAPE", "mcape": "MUCAPE",
    "msl": "PRMSL",
    "sp": "PRES",
    "tcc": "TCDC",
    "gh": "HGT", "z": "HGT",
    "t": "T850",
}


def log(msg):
    print("[AIFS] " + msg, flush=True)


def latest_run(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    run_h = 0 if now.hour < 12 else 12
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    if (now - run_dt).total_seconds() < RUN_MATURITY:
        run_dt -= datetime.timedelta(hours=12)
    return run_dt


def compute_leads(max_hours=MAX_LEAD):
    max_h = max(3, min(int(max_hours), MAX_LEAD))
    leads = list(range(0, min(max_h, 121), 3))
    if max_h > 120:
        leads.extend(range(126, min(max_h, 241), 6))
    if max_h > 240:
        leads.extend(range(252, max_h + 1, 12))
    return sorted(set(leads))


def _retrieve(client, run_dt, levtype, params, levels, leads, tmp):
    """Récupère un fichier GRIB AIFS (sfc ou pl) pour la liste d'échéances."""
    kwargs = {
        "model": "aifs-single",
        "resol": "0p25",
        "levtype": levtype,
        "param": params,
        "step": leads,
        "date": run_dt.strftime("%Y-%m-%d"),
        "time": "%02d:00" % run_dt.hour,
        "target": tmp,
    }
    if levtype == "pl":
        kwargs["levelist"] = levels
    client.retrieve(**kwargs)
    return tmp


def decode_file(path, lead_list):
    """Décode un GRIB AIFS → {lead: {KEY: (values 2D, lat 1D, lon 1D)}}."""
    import cfgrib
    out = {}
    for ds in cfgrib.open_datasets(path):
        v = list(ds.data_vars)[0]
        key = ALIASES.get(v.lower())
        if key is None:
            continue
        if "isobaricInhPa" in ds[v].coords:
            levs = np.atleast_1d(ds[v].isobaricInhPa.values)
            for idx, lev_val in enumerate(levs):
                lev_f = float(lev_val)
                if key == "HGT" and lev_f == 500.0:
                    out.setdefault(0, {})["HGT"] = _to2d(ds[v].values[idx], ds)
                elif key == "T850" and lev_f == 850.0:
                    out.setdefault(0, {})["T850"] = _to2d(ds[v].values[idx], ds)
            continue
        if "step" in ds[v].coords:
            steps = np.atleast_1d(ds[v].step.values)
            vals = ds[v].values
            for idx, st in enumerate(steps):
                lead = int(st) if np.isscalar(st) else int(st)
                try:
                    lead = int(float(np.atleast_1d(st)[0]))
                except Exception:
                    lead = 0
                arr = vals[idx] if vals.ndim > 2 else vals
                if arr.ndim != 2:
                    continue
                if key == "HGT":
                    continue  # traité via pressure-level
                if key == "T850":
                    continue
                out.setdefault(lead, {})[key] = _to2d(arr, ds)
        else:
            arr = ds[v].values
            while arr.ndim > 2 and arr.shape[0] == 1:
                arr = arr[0]
            if arr.ndim == 2:
                lead = int(float(np.atleast_1d(ds.step.values)[0])) \
                    if "step" in ds.coords else 0
                out.setdefault(lead, {})[key] = _to2d(arr, ds)
    return out


def _to2d(arr, ds):
    arr = np.asarray(arr, dtype=np.float32)
    while arr.ndim > 2 and arr.shape[0] == 1:
        arr = arr[0]
    lat = np.asarray(ds.latitude.values, dtype=np.float64)
    lon = np.asarray(ds.longitude.values, dtype=np.float64)
    if arr.ndim == 1:
        # grille scalaire dégénérée : reshaped via lat/lon
        try:
            arr = arr.reshape(lat.shape[0], lon.shape[0])
        except Exception:
            return None
    return (arr, lat, lon)


def collect_fields(client, run_dt, leads):
    """Récupère et décode tous les champs des échéances demandées."""
    all_fields = {}
    with tempfile.TemporaryDirectory() as td:
        sfc_path = os.path.join(td, "aifs_sfc.grib2")
        try:
            _retrieve(client, run_dt, "sfc", SFC_PARAMS, None, leads, sfc_path)
        except Exception as e:
            log("!! récupération sfc échouée (%s)" % e)
            sfc_path = None
        pl_path = os.path.join(td, "aifs_pl.grib2")
        try:
            _retrieve(client, run_dt, "pl", PL_PARAMS, PL_LEVELS, leads, pl_path)
        except Exception as e:
            log("!! récupération pl échouée (%s)" % e)
            pl_path = None

        if sfc_path:
            try:
                fields = decode_file(sfc_path, leads)
                for lead, flds in fields.items():
                    all_fields.setdefault(lead, {}).update(flds)
            except Exception as e:
                log("!! décodage sfc échoué (%s)" % e)
        if pl_path:
            try:
                fields = decode_file(pl_path, leads)
                for lead, flds in fields.items():
                    all_fields.setdefault(lead, {}).update(flds)
            except Exception as e:
                log("!! décodage pl échoué (%s)" % e)
    return all_fields


def render_lead_par(fields, lead, run_dt, domain, out_dir):
    """Rend les couches d'une échéance AIFS (sauf cumulatifs/horaires)."""
    step = {"lead_hour": lead,
            "valid_time": (run_dt + datetime.timedelta(hours=lead)).isoformat(),
            "files": {},
            "probes": {}}

    def regrid(field, convert=None):
        if field is None:
            return None
        val, lat, lon = field
        if convert is not None:
            val = convert(val)
        return domain.regrid(val, lat, lon)

    def save(name, data):
        dst = os.path.join(out_dir, name, "%03d.webp" % lead)
        save_webp(data, name, dst)
        step["files"][name] = "maps/%s/%03d.webp" % (name, lead)
        write_hkv(data, os.path.join(out_dir, "values", name,
                                     "%03d.hkv.gz" % lead))
        step["probes"][name] = "maps/values/%s/%03d.hkv.gz" % (name, lead)

    gust_g = None
    apcp_g = None
    hgt = fields.get("HGT")
    prmsl = fields.get("PRMSL")
    if hgt is not None and prmsl is not None:
        z_raw = regrid(hgt)
        p_hpa = regrid(prmsl, lambda v: v / 100.0)
        if z_raw is not None and p_hpa is not None:
            z = z_raw / 98.0665  # m²/s² → dam
            dst = os.path.join(out_dir, "geopotentiel_500", "%03d.webp" % lead)
            render_z500_with_isobars(z, p_hpa, dst, style="dense")
            step["files"]["geopotentiel_500"] = "maps/geopotentiel_500/%03d.webp" % lead
            dst2 = os.path.join(out_dir, "geopotentiel_500_meteociel", "%03d.webp" % lead)
            render_z500_with_isobars(z, p_hpa, dst2, style="meteociel")
            step["files"]["geopotentiel_500_meteociel"] = "maps/geopotentiel_500_meteociel/%03d.webp" % lead

    t850 = fields.get("T850")
    if t850 is not None:
        t850_c = regrid(t850, lambda v: v - 273.15)
        if t850_c is not None:
            dst_t850 = os.path.join(out_dir, "temperature_850", "%03d.webp" % lead)
            ensure_dir(os.path.dirname(dst_t850))
            render_temperature850_with_isotherms(t850_c, dst_t850)
            step["files"]["temperature_850"] = "maps/temperature_850/%03d.webp" % lead
            write_hkv(t850_c, os.path.join(out_dir, "values", "temperature_850",
                                            "%03d.hkv.gz" % lead))
            step["probes"]["temperature_850"] = "maps/values/temperature_850/%03d.hkv.gz" % lead

    t2m = fields.get("T2M")
    rh = fields.get("RH")
    u10 = fields.get("U10")
    v10 = fields.get("V10")

    if t2m is not None:
        t_c = regrid(t2m, lambda v: v - 273.15)
        save("temperature", t_c)
        td_c = None
        if rh is not None:
            rh_g = regrid(rh)
            if rh_g is not None:
                td_c = dew_point_c(t_c, rh_g)
                save("point_rosee", td_c)
                save("humidex", humidex_c(t_c, td_c))
        if u10 is not None and v10 is not None:
            spd = np.sqrt(u10[0].astype(np.float32) ** 2
                          + v10[0].astype(np.float32) ** 2) * 3.6
            wind_kmh = domain.regrid(spd, u10[1], u10[2])
            if wind_kmh is not None:
                if rh is not None and td_c is not None:
                    felt = heat_index_c(t_c, rh_g)
                    felt = wind_chill_c(felt, wind_kmh)
                else:
                    felt = wind_chill_c(t_c, wind_kmh)
                save("temperature_ressentie", felt)

    if rh is not None:
        save("humidite", regrid(rh))

    if u10 is not None and v10 is not None:
        spd = np.sqrt(u10[0].astype(np.float32) ** 2
                      + v10[0].astype(np.float32) ** 2) * 3.6
        save("vent", domain.regrid(spd, u10[1], u10[2]))

    gust = fields.get("GUST")
    if gust is not None:
        g = regrid(gust, lambda v: v * 3.6)
        save("rafales", g)
        gust_g = g

    tcdc = fields.get("TCDC")
    if tcdc is not None:
        save("nebulosite", regrid(tcdc))

    cape = fields.get("CAPE")
    if cape is not None:
        val, _, _ = cape
        if np.isfinite(val).any() and float(np.nanmax(val)) > 1.0:
            save("mucape", regrid(cape))

    if prmsl is not None:
        p = regrid(prmsl, lambda v: v / 100.0)
        dst_p = os.path.join(out_dir, "pression", "%03d.webp" % lead)
        render_pression_with_isobars(p, dst_p)
        step["files"]["pression"] = "maps/pression/%03d.webp" % lead
        write_hkv(p, os.path.join(out_dir, "values", "pression", "%03d.hkv.gz" % lead))

    if fields.get("PRES") is not None:
        save("pression_surface", regrid(fields["PRES"], lambda v: v / 100.0))

    apcp = fields.get("APCP")
    if apcp is not None:
        a = regrid(apcp)  # tp = cumul depuis le début du run
        if a is not None:
            apcp_g = a

    return step, gust_g, apcp_g


def _save_cumulative(out_dir, name, data, lead, step):
    dst = os.path.join(out_dir, name, "%03d.webp" % lead)
    save_webp(data, name, dst)
    step["files"][name] = "maps/%s/%03d.webp" % (name, lead)
    write_hkv(data, os.path.join(out_dir, "values", name,
                                 "%03d.hkv.gz" % lead))
    step["probes"][name] = "maps/values/%s/%03d.hkv.gz" % (name, lead)


def _apply_cumulative(state, out_dir, lead, step, gust_g, apcp_g):
    if gust_g is not None:
        if state.get("max_gust") is None:
            state["max_gust"] = gust_g.copy()
        else:
            state["max_gust"] = np.maximum(state["max_gust"], gust_g)
        _save_cumulative(out_dir, "rafales_cumul", state["max_gust"], lead, step)
    if apcp_g is not None:
        prev = state.get("tp_prev")
        if prev is not None:
            diff = np.where(np.isfinite(apcp_g) & np.isfinite(prev),
                            apcp_g - prev, np.nan)
            _save_cumulative(out_dir, "pluie_1h", np.clip(diff, 0, None), lead, step)
        state["tp_prev"] = apcp_g
        _save_cumulative(out_dir, "pluie_cumul", apcp_g, lead, step)
    for name in step["files"]:
        state["counts"][name] = state["counts"].get(name, 0) + 1


def render_domain(all_fields, run_dt, domain, out_dir, model_label, resolution,
                  lead_min=0, lead_max=None, init_state=None):
    os.makedirs(out_dir, exist_ok=True)
    leads = sorted([lh for lh in all_fields
                    if lh >= lead_min and (lead_max is None or lh <= lead_max)])
    if not leads:
        log("Aucune échéance dans l'intervalle [%s, %s]" % (lead_min, lead_max))
        return 0
    state = {"counts": {}, "max_gust": None, "tp_prev": None}
    if init_state:
        if init_state.get("max_gust") is not None:
            state["max_gust"] = init_state["max_gust"]
        if init_state.get("cum_precip") is not None:
            state["tp_prev"] = init_state["cum_precip"]
    steps = []
    n_ok = 0
    for lh in leads:
        step, gust_g, apcp_g = render_lead_par(all_fields[lh], lh, run_dt,
                                               domain, out_dir)
        _apply_cumulative(state, out_dir, lh, step, gust_g, apcp_g)
        steps.append(step)
        n_ok += 1
        log("  H+%03d OK (%d couches)" % (lh, len(step["files"])))
    if n_ok == 0:
        raise RuntimeError("Aucune échéance rendue pour AIFS (%s)" % out_dir)
    write_places(domain, out_dir)
    write_manifest(out_dir, steps,
                   {"model_name": model_label,
                    "provider": "ECMWF — open data (data.ecmwf.int)",
                    "resolution": resolution,
                    "run_time": run_dt.isoformat()},
                   domain)
    log("Terminé : %d échéances, couches %s" % (
        n_ok, ", ".join("%s=%d" % kv for kv in
                        sorted(state["counts"].items()))))
    return n_ok


def run_all(max_hours=MAX_LEAD, domain="europe", lead_min=0, lead_max=None):
    from ecmwf.opendata import Client
    max_lead = max(3, min(int(max_hours), MAX_LEAD))
    run_dt = latest_run()
    log("Run AIFS sélectionné : %s" % run_dt.isoformat())
    all_leads = compute_leads(max_lead)
    chunk_leads = [lh for lh in all_leads
                   if lh >= lead_min and (lead_max is None or lh <= lead_max)]
    if not chunk_leads:
        log("Aucune échéance dans l'intervalle [%s, %s]" % (lead_min, lead_max))
        return

    client = Client()
    # Échauffement cumulatif : échéances antérieures (rafales + pluie)
    state_warm = {"max_gust": None, "cum_precip": None}
    prior = [lh for lh in all_leads if lh < lead_min]
    if prior:
        try:
            warm = collect_fields(client, run_dt, prior)
            for lh in sorted(warm):
                f = warm[lh]
                gust = f.get("GUST")
                apcp = f.get("APCP")
                if gust is not None:
                    val, lat, lon = gust
                    g = EUROPE.regrid(val * 3.6, lat, lon)
                    if g is not None:
                        state_warm["max_gust"] = (g if state_warm["max_gust"] is None
                                                  else np.maximum(state_warm["max_gust"], g))
                if apcp is not None:
                    val, lat, lon = apcp
                    a = EUROPE.regrid(val, lat, lon)
                    if a is not None:
                        state_warm["cum_precip"] = a
        except Exception as e:
            log("!! échauffement ignoré (%s)" % e)

    all_fields = collect_fields(client, run_dt, chunk_leads)
    base = os.path.join(BASE_DIR, "output")
    if domain in ("both", "europe"):
        render_domain(all_fields, run_dt, EUROPE,
                      os.path.join(base, "aifs", "maps"),
                      "ECMWF AIFS 0.25° Europe", "0.25° (~25 km)",
                      lead_min=lead_min, lead_max=lead_max,
                      init_state=state_warm)
    if domain in ("both", "france"):
        render_domain(all_fields, run_dt, FRANCE,
                      os.path.join(base, "aifs_france", "maps"),
                      "ECMWF AIFS 0.25° France", "0.25° (~25 km)",
                      lead_min=lead_min, lead_max=lead_max,
                      init_state=state_warm)
    print("[AIFS] Pipeline terminé avec succès.", flush=True)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Pipeline ECMWF AIFS 0.25°")
    ap.add_argument("--max-hours", type=int, default=MAX_LEAD,
                    help="Échéance max en heures (défaut 360)")
    ap.add_argument("--domain", choices=["both", "europe", "france"],
                    default="europe", help="Domaine(s) à générer")
    ap.add_argument("--lead-min", type=int, default=0)
    ap.add_argument("--lead-max", type=int, default=None)
    args = ap.parse_args()
    run_all(max_hours=args.max_hours, domain=args.domain,
            lead_min=args.lead_min, lead_max=args.lead_max)


if __name__ == "__main__":
    main()
