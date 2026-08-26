#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arpege_open_data.py — Pipeline ARPEGE Europe 0.1° & France (Météo-France)
==========================================================================
  - Données : https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt/{run}/arpege/01/
    paquets SP1 (surface), SP2 (nuages/CAPE), IP1 (géopotentiel Z500).
  - Produit 01 = ARPEGE Europe 0,1° (~11 km) — le plus fin publié par
    Météo-France pour ARPEGE (le 0,025°/2,5 km n'existe qu'en AROME, pas ARPEGE).
  - ARPEGE France = même produit 01 re-projeté sur le domaine Mercator France
    (vue France + régions, ~2,5× plus net que GFS France 0,25°).
  - Téléchargement direct accéléré (1 requête GET par bloc) puis décodage local.
  - Runs 00/06/12/18Z (maturité ≥ 4 h 30), échéances H+00 → H+102 pas 3 h.
  - Couche maîtresse : GÉOPOTENTIEL 500 hPa + isobares pression au sol (Europe).
  - --domain both : un seul téléchargement, rendu Europe + France (18 groupes CI).
"""
import os
import re
import sys
import time
import datetime
import tempfile

import requests
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))

from domains import EUROPE, FRANCE  # noqa: E402
import gribscan  # noqa: E402
from render import (  # noqa: E402
    save_webp, write_hkv, write_places, write_manifest,
    render_z500_with_isobars, render_pression_with_isobars,
    render_temperature850_with_isotherms, ensure_dir,
    dew_point_c, heat_index_c, wind_chill_c, humidex_c,
)

HEADERS = {"User-Agent": "gfs-weather-map/2.0 (Monsieur Meteo)"}
# Produit S3 Météo-France : 01 = ARPEGE Europe 0,1° (~11 km) — le plus fin
# publié pour ARPEGE. ARPEGE France réutilise ce même produit (re-projection
# sur le domaine Mercator France) : il n'existe pas d'ARPEGE France 0,025°.
GRIB_PRODUCTS = {"europe": "01", "france": "01"}
PKGS = ["SP1", "SP2", "IP1"]
BLOCKS = ["000H012H", "013H024H", "025H036H", "037H048H", "049H060H",
          "061H072H", "073H084H", "085H096H", "097H102H"]
RUN_MATURITY = 16200  # 4 h 30
MAX_LEAD = 102


def grib_url(run, pkg, block, product="01"):
    """URL S3 Météo-France d'un bloc GRIB2 ARPEGE (produit 01 ou 02)."""
    return ("https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt/{run}/arpege/{prod}/"
            "{pkg}/arpege__{prod}__{pkg}__{block}__{run}.grib2"
            .format(run=run, prod=product, pkg=pkg, block=block))


def log(msg):
    print("[ARPEGE] " + msg, flush=True)


def run_str(run_dt):
    return run_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def latest_run(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    run_h = (now.hour // 6) * 6
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    if (now - run_dt).total_seconds() < RUN_MATURITY:
        run_dt -= datetime.timedelta(hours=6)
    return run_dt


def _head(session, url):
    r = session.head(url, headers=HEADERS, timeout=30, verify=True)
    if r.status_code != 200:
        return None
    cl = r.headers.get("Content-Length")
    return int(cl) if cl else None


def select_run(now=None, session=None):
    """Dernier run ARPEGE réellement disponible (SP1 000H012H présent)."""
    s = session or requests.Session()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    for _ in range(2):
        run_dt = latest_run(now)
        url = grib_url(run_str(run_dt), "SP1", "000H012H", GRIB_PRODUCTS["europe"])
        if _head(s, url):
            return run_dt
        log("Run %s indisponible, repli sur le précédent" % run_str(run_dt))
        run_dt -= datetime.timedelta(hours=6)
    raise RuntimeError("Aucun run ARPEGE disponible sur le S3 Météo-France")


def fetch_block_full(session, url, max_lead, logf, lead_min=0):
    """Repli : téléchargement complet du bloc puis décodage sélectif local."""
    logf("  téléchargement direct du bloc GRIB…")
    r = session.get(url, headers=HEADERS, timeout=600, verify=True)
    r.raise_for_status()
    if len(r.content) < 1000:
        raise IOError("Bloc vide: %s" % url)
    tmp = os.path.join(tempfile.gettempdir(), "arpege_block.grib2")
    with open(tmp, "wb") as f:
        f.write(r.content)
    out = {}
    with open(tmp, "rb") as f:
        from eccodes import (codes_grib_new_from_file, codes_get,
                             codes_get_array, codes_release)
        while True:
            gid = codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                # Métadonnées du message courant (décodage local complet)
                cat = int(codes_get(gid, "parameterCategory"))
                num = int(codes_get(gid, "parameterNumber"))
                level = int(codes_get(gid, "level"))
                key = gribscan.key_of(cat, num, level)
                if key is None:
                    continue
                step = int(codes_get(gid, "step"))
                end = int(codes_get(gid, "endStep"))
                lead = end if step != end else step
                if not (lead_min <= lead <= max_lead and lead % 3 == 0):
                    continue
                ni = int(codes_get(gid, "Ni"))
                nj = int(codes_get(gid, "Nj"))
                vals = np.asarray(codes_get_array(gid, "values"),
                                  dtype=np.float32).reshape(nj, ni)
                lat2 = np.asarray(codes_get_array(gid, "latitudes"),
                                  dtype=np.float64).reshape(nj, ni)
                lon2 = np.asarray(codes_get_array(gid, "longitudes"),
                                  dtype=np.float64).reshape(nj, ni)
                out.setdefault(lead, {})[key] = (vals, lat2[:, 0], lon2[0, :])
            except Exception as e:
                logf("  !! message ignoré (%s)" % e)
            finally:
                codes_release(gid)
    try:
        os.remove(tmp)
    except OSError:
        pass
    return out


def _block_range(block):
    """'025H036H' → (25, 36)."""
    m = re.match(r"(\d+)H(\d+)H", block)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def collect_fields(session, run_dt, max_lead, product="01", lead_min=0, lead_max=None):
    """Télécharge/extrait tous les champs → {lead: {KEY: (vals, lat, lon)}}."""
    all_fields = {}
    rs = run_str(run_dt)
    n_full_mb = 0
    n_blocks = 0
    eff_max = min(max_lead, lead_max) if lead_max is not None else max_lead
    for pkg in PKGS:
        for block in BLOCKS:
            b0, b1 = _block_range(block)
            if b0 > eff_max or b1 < lead_min:
                continue  # bloc entièrement hors de la portée demandée
            url = grib_url(rs, pkg, block, product)
            size = _head(session, url)
            if size is None:
                log("!! %s %s introuvable" % (pkg, block))
                continue
            t0 = time.time()
            # Téléchargement direct ultra-rapide en 1 seule requête GET (3-5s par bloc au lieu de 60s en HTTP Range)
            try:
                fields = fetch_block_full(session, url, eff_max, log, lead_min=lead_min)
                mode = "direct (rapide)"
                n_full_mb += size // (1024 * 1024)
            except Exception as e:
                log("!! %s %s : téléchargement échoué (%s)" % (pkg, block, e))
                continue
            n_blocks += 1
            for lead, flds in fields.items():
                all_fields.setdefault(lead, {}).update(flds)
            log("  %s %s : %d échéances (%s, %.1f s)" % (
                pkg, block, len(fields), mode, time.time() - t0))
    log("Blocs traités : %d, dont %d Mo téléchargés en repli complet"
        % (n_blocks, n_full_mb))
    return all_fields


def render_lead(fields, lead, run_dt, domain, out_dir, state):
    """Rend toutes les couches d'une échéance ARPEGE (Z500 en priorité)."""
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
        state["counts"][name] = state["counts"].get(name, 0) + 1

    # ★ Couche maîtresse : Z500 (m²/s² → dam) + isobares (Europe ET France)
    hgt = fields.get("HGT")
    prmsl = fields.get("PRMSL")
    if hgt is not None and prmsl is not None:
        z = regrid(hgt, lambda v: v / 98.0665)
        p_hpa = regrid(prmsl, lambda v: v / 100.0)
        if z is not None and p_hpa is not None:
            dst = os.path.join(out_dir, "geopotentiel_500", "%03d.webp" % lead)
            render_z500_with_isobars(z, p_hpa, dst)
            step["files"]["geopotentiel_500"] = \
                "maps/geopotentiel_500/%03d.webp" % lead
            state["counts"]["geopotentiel_500"] = \
                state["counts"].get("geopotentiel_500", 0) + 1

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
            state["counts"]["temperature_850"] = state["counts"].get("temperature_850", 0) + 1

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
        if state.get("max_gust") is None:
            state["max_gust"] = g.copy()
        else:
            state["max_gust"] = np.maximum(state["max_gust"], g)
        save("rafales_cumul", state["max_gust"])

    clouds = []
    for ck, layer in (("LCC", "nuages_bas"),
                      ("MCC", "nuages_moyens"),
                      ("HCC", "nuages_eleves")):
        f = fields.get(ck)
        if f is not None:
            g = regrid(f)
            if g is not None:
                clouds.append(g)
                save(layer, g)
    if clouds:
        save("nebulosite", np.maximum.reduce(clouds))

    cape = fields.get("CAPE")
    if cape is not None:
        val, _, _ = cape
        if np.isfinite(val).any() and float(np.nanmax(val)) > 1.0:
            save("mucape", regrid(cape))
        else:
            log("  CAPE H+%03d incohérent (max=%s), couche ignorée"
                % (lead, float(np.nanmax(val))))

    if prmsl is not None:
        p = regrid(prmsl, lambda v: v / 100.0)
        dst_p = os.path.join(out_dir, "pression", "%03d.webp" % lead)
        render_pression_with_isobars(p, dst_p)
        step["files"]["pression"] = "maps/pression/%03d.webp" % lead
        write_hkv(p, os.path.join(out_dir, "values", "pression", "%03d.hkv.gz" % lead))
        state["counts"]["pression"] = state["counts"].get("pression", 0) + 1

    apcp = fields.get("APCP")
    if apcp is not None:
        a = regrid(apcp)  # cumul depuis le début du run (mm)
        if a is not None:
            prev = state.get("tp_prev")
            if prev is not None:
                # np.isfinite().all() toujours False à cause des NaN de bord → utiliser np.where
                diff = np.where(np.isfinite(a) & np.isfinite(prev), a - prev, np.nan)
                save("pluie_1h", np.clip(diff, 0, None))
            state["tp_prev"] = a
            save("pluie_cumul", a)

    snod = fields.get("SNOD")
    if snod is not None:
        save("neige_au_sol", regrid(snod, lambda v: v * 100.0))

    return step


def render_domain(all_fields, run_dt, domain, out_dir, model_label, resolution,
                  lead_min=0, lead_max=None):
    """Rend toutes les échéances d'un domaine depuis des champs déjà collectés."""
    os.makedirs(out_dir, exist_ok=True)
    leads = sorted([lh for lh in all_fields
                    if lh >= lead_min and (lead_max is None or lh <= lead_max)])
    if not leads:
        log("Aucune échéance dans l'intervalle [%s, %s]" % (lead_min, lead_max))
        return 0

    steps = []
    state = {"counts": {}, "max_gust": None, "tp_prev": None}
    n_ok = 0
    for lh in leads:
        step = render_lead(all_fields[lh], lh, run_dt, domain, out_dir, state)
        steps.append(step)
        n_ok += 1
        log("  H+%03d OK (%d couches)" % (lh, len(step["files"])))

    if n_ok == 0:
        raise RuntimeError("Aucune échéance rendue pour ARPEGE (%s)" % out_dir)
    write_places(domain, out_dir)
    write_manifest(out_dir, steps,
                   {"model_name": model_label,
                    "provider": "Météo-France — open data (data.gouv.fr)",
                    "resolution": resolution,
                    "run_time": run_dt.isoformat()},
                   domain)
    log("Terminé : %d échéances, couches %s" % (
        n_ok, ", ".join("%s=%d" % kv for kv in
                        sorted(state["counts"].items()))))
    return n_ok


def run_all(max_hours=MAX_LEAD, domain="europe", lead_min=0, lead_max=None):
    max_lead = max(3, min(int(max_hours), MAX_LEAD))
    run_dt = select_run()
    log("Run ARPEGE sélectionné : %s" % run_str(run_dt))
    base = os.path.join(BASE_DIR, "output")
    session = requests.Session()
    session.headers.update(HEADERS)
    # Un seul téléchargement (produit 01, Europe 0,1°) → Europe + France
    all_fields = collect_fields(session, run_dt, max_lead,
                                product=GRIB_PRODUCTS["europe"],
                                lead_min=lead_min, lead_max=lead_max)
    if domain in ("both", "europe"):
        render_domain(all_fields, run_dt, EUROPE,
                      os.path.join(base, "arpege", "maps"),
                      "ARPEGE Europe 0.1°", "0.1° (~11 km)",
                      lead_min=lead_min, lead_max=lead_max)
    if domain in ("both", "france"):
        render_domain(all_fields, run_dt, FRANCE,
                      os.path.join(base, "arpege_france", "maps"),
                      "ARPEGE France 0.1°", "0.1° (~11 km)",
                      lead_min=lead_min, lead_max=lead_max)
    print("[ARPEGE] Pipeline terminé avec succès.", flush=True)


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Pipeline ARPEGE Europe 0.1° & France (produit 01)")
    ap.add_argument("--max-hours", type=int, default=MAX_LEAD,
                    help="Échéance max ARPEGE en heures (défaut 102)")
    ap.add_argument("--domain", choices=["both", "europe", "france"],
                    default="europe",
                    help="Domaine(s) à générer : europe (défaut), france, both")
    ap.add_argument("--lead-min", type=int, default=0,
                    help="Échéance de début")
    ap.add_argument("--lead-max", type=int, default=None,
                    help="Échéance de fin")
    args = ap.parse_args()
    run_all(max_hours=args.max_hours, domain=args.domain,
            lead_min=args.lead_min, lead_max=args.lead_max)


if __name__ == "__main__":
    main()
