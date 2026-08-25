#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render.py — briques de rendu partagées (GFS / ARPEGE)
=======================================================
Palettes, application couleur, dalles WebP, sondes HKV1, communes (places),
manifeste exact, isobares Z500 + formules physiques (ressentie, humidex).
"""
import os
import gzip
import struct
import json
import datetime

import numpy as np
from PIL import Image

from palettes_data import PALETTES

# ── Métadonnées des couches (libellés, unités, décimales, groupe UI) ────────
LAYER_META = {
    "temperature":           ("Température à 2 m",             "°C",   1, "Températures"),
    "temperature_ressentie": ("Température ressentie",         "°C",   1, "Températures"),
    "point_rosee":           ("Point de rosée à 2 m",          "°C",   1, "Températures"),
    "humidex":               ("Indice Humidex",                "",     1, "Températures"),
    "vent":                  ("Vent moyen à 10 m",             "km/h", 0, "Vent"),
    "rafales":               ("Rafales maximales",             "km/h", 0, "Vent"),
    "rafales_cumul":         ("Rafales maximales cumulées",    "km/h", 0, "Vent"),
    "nebulosite":            ("Nébulosité totale",             "%",    0, "Nuages et humidité"),
    "nuages_bas":            ("Couverture nuages bas",         "%",    0, "Nuages et humidité"),
    "nuages_moyens":         ("Couverture nuages moyens",      "%",    0, "Nuages et humidité"),
    "nuages_eleves":         ("Couverture nuages élevés",      "%",    0, "Nuages et humidité"),
    "humidite":              ("Humidité relative à 2 m",       "%",    0, "Nuages et humidité"),
    "mucape":                ("Instabilité orageuse (MUCAPE)", "J/kg", 0, "Instabilité"),
    "pression":              ("Pression niveau mer",           "hPa",  0, "Pression et géopotentiel"),
    "pression_surface":      ("Pression au sol",               "hPa",  0, "Pression et géopotentiel"),
    "geopotentiel_500":      ("Géopotentiel 500 hPa",          "dam",  0, "Pression et géopotentiel"),
    "pluie_1h":              ("Précipitations sur 3 h",        "mm",   1, "Précipitations"),
    "pluie_cumul":           ("Précipitations cumulées",       "mm",   1, "Précipitations"),
    "neige_au_sol":          ("Épaisseur de neige au sol",     "cm",   1, "Autres"),
}

# Ordre d'affichage des couches dans le sélecteur
LAYER_ORDER = [
    "temperature", "temperature_ressentie", "point_rosee", "humidex",
    "vent", "rafales", "rafales_cumul",
    "nebulosite", "nuages_bas", "nuages_moyens", "nuages_eleves",
    "humidite", "mucape",
    "pression", "pression_surface", "geopotentiel_500",
    "pluie_1h", "pluie_cumul", "neige_au_sol",
]


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p


# ── Couleur ──────────────────────────────────────────────────────────────────
def apply_palette(data, palette):
    """Applique une palette (liste de (seuil, rgba)) à un champ 2D → RGBA."""
    vs = np.array([s[0] for s in palette], dtype=np.float32)
    cs = np.array([list(s[1]) for s in palette], dtype=np.float32)
    rgba = np.zeros((*data.shape, 4), dtype=np.uint8)
    for i in range(len(vs) - 1):
        mask = (data >= vs[i]) & (data < vs[i + 1])
        if not np.any(mask):
            continue
        t = (data[mask] - vs[i]) / (vs[i + 1] - vs[i])
        for c in range(4):
            rgba[mask, c] = np.clip(
                cs[i, c] + t * (cs[i + 1, c] - cs[i, c]), 0, 255).astype(np.uint8)
    rgba[data <= vs[0]] = cs[0].astype(np.uint8)
    rgba[data >= vs[-1]] = cs[-1].astype(np.uint8)
    return rgba


def save_webp(data, layer, dst, quality=85):
    """Dalle WebP RGBA (alpha = zone sans données via NaN → transparent)."""
    pal = PALETTES.get(layer)
    if pal is None:
        pal = PALETTES["temperature"]
    rgba = apply_palette(np.nan_to_num(data, nan=np.nan), pal)
    # NaN → alpha 0 (transparent)
    if np.isnan(data).any():
        rgba[..., 3] = np.where(np.isnan(data), 0, rgba[..., 3])
    ensure_dir(os.path.dirname(dst))
    Image.fromarray(rgba, "RGBA").save(dst, format="WEBP", quality=quality, method=4)


# ── Sondes HKV1 (valeurs au survol) ─────────────────────────────────────────
def write_hkv(grid, dst, probe_w=440, probe_h=328):
    """Grille de valeurs compressée gzip pour la sonde au survol.

    Format : en-tête 'HKV1' + w u16 + h u16 + min f32 + max f32
             + données u16 (65535 = NaN).
    """
    g = np.asarray(grid, dtype=np.float32)
    if g.shape[0] != probe_h or g.shape[1] != probe_w:
        ys = np.linspace(0, g.shape[0] - 1, probe_h).astype(int)
        xs = np.linspace(0, g.shape[1] - 1, probe_w).astype(int)
        g = g[np.ix_(ys, xs)]
    finite = g[np.isfinite(g)]
    if finite.size == 0:
        gmin, gmax = 0.0, 1.0
    else:
        gmin, gmax = float(finite.min()), float(finite.max())
    span = gmax - gmin
    if span <= 0:
        span = 1.0
    q = np.where(np.isfinite(g),
                 np.clip((g - gmin) / span, 0.0, 1.0) * 65534.0, 65535.0)
    q = q.astype(np.uint16)
    ensure_dir(os.path.dirname(dst))
    with gzip.open(dst, "wb") as f:
        f.write(b"HKV1")
        f.write(struct.pack("<HH", probe_w, probe_h))
        f.write(struct.pack("<ff", gmin, gmax))
        f.write(q.tobytes())


# ── Communes (places, pour la couche villes) ────────────────────────────────
def write_places(domain, out_dir):
    """Génère maps/communes.json filtré au domaine (tri par population).

    Format attendu par le front : {"places": [[nom, pop, lat, lon], ...]}
    Source : config/communes-compact.json (34 746 communes).
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(base_dir, "config", "communes-compact.json")
    if not os.path.exists(src):
        return False
    with open(src, encoding="utf-8") as f:
        rows = json.load(f)  # [code, nom, cps[], dept, pop, lat, lon]
    w, e = domain.west, domain.east
    s, n = domain.south, domain.north
    out = []
    for r in rows:
        try:
            lat, lon = float(r[5]), float(r[6])
        except (IndexError, TypeError, ValueError):
            continue
        if w <= lon <= e and s <= lat <= n:
            out.append([r[1], int(r[4]), lat, lon])
    out.sort(key=lambda p: -p[1])
    ensure_dir(out_dir)
    with open(os.path.join(out_dir, "communes.json"), "w", encoding="utf-8") as f:
        json.dump({"places": out}, f, ensure_ascii=False)
    return True


# ── Manifeste exact ─────────────────────────────────────────────────────────
def write_manifest(out_dir, steps, meta, domain):
    """Manifeste index.json : ne référence QUE les couches réellement rendues.

    out_dir : output/{model}/maps
    meta    : {model_name, provider, resolution, run_time}
    domain  : objet Domain (bounds, width, height)
    """
    layers_info = {}
    for step in steps:
        for layer in (step.get("files") or {}):
            if layer in LAYER_META and layer not in layers_info:
                label, unit, dec, group = LAYER_META[layer]
                layers_info[layer] = {"label": label, "unit": unit,
                                      "decimals": dec, "group": group}
    m = {
        "schema_version": 6,
        "status": "ok",
        "model_name": meta["model_name"],
        "provider": meta["provider"],
        "resolution": meta["resolution"],
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "run_time": meta["run_time"],
        "bounds": domain.bounds,
        "width": domain.width,
        "height": domain.height,
        "overlay": "maps/frontieres.svg",
        "mask": "maps/mask_france.png",
        "fond": "maps/fond.webp",
        "places": "maps/communes.json",
        "layers": layers_info,
        "steps": steps,
    }
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
    return m


# ── Z500 + isobares ─────────────────────────────────────────────────────────
def render_z500_with_isobars(z500_grid, prmsl_grid, output_path):
    """Z500 coloré (palette geopotentiel_500) + isobares PRMSL (noir/blanc)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects
    import scipy.ndimage

    pal = PALETTES.get("geopotentiel_500", PALETTES["temperature"])
    base_img = apply_palette(z500_grid, pal)
    h, w = z500_grid.shape
    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.imshow(base_img, origin="upper", extent=[0, w, h, 0])
    if prmsl_grid is not None:
        smooth_p = scipy.ndimage.gaussian_filter(prmsl_grid, sigma=1.8)
        gx = np.linspace(0, w, smooth_p.shape[1])
        gy = np.linspace(0, h, smooth_p.shape[0])
        GX, GY = np.meshgrid(gx, gy)
        levels = np.arange(960, 1055, 5)
        ax.contour(GX, GY, smooth_p, levels=levels, colors="#000000", linewidths=3.6)
        cs = ax.contour(GX, GY, smooth_p, levels=levels, colors="#ffffff", linewidths=2.4)
        labels = ax.clabel(cs, inline=True, fmt="%d", fontsize=16,
                           colors="#ffffff", inline_spacing=15)
        if labels:
            for lbl in labels:
                lbl.set_weight("bold")
                lbl.set_path_effects([
                    matplotlib.patheffects.Stroke(linewidth=3, foreground="#000000"),
                    matplotlib.patheffects.Normal(),
                ])
    ensure_dir(os.path.dirname(output_path))
    fig.savefig(output_path, format="webp", dpi=100, pil_kwargs={"quality": 88})
    plt.close(fig)


def render_pression_with_isobars(prmsl_grid, output_path):
    """Pression niveau mer colorée (palette pression) + isobares continues (hPa)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects
    import scipy.ndimage

    pal = PALETTES.get("pression", PALETTES["temperature"])
    base_img = apply_palette(prmsl_grid, pal)
    h, w = prmsl_grid.shape
    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.imshow(base_img, origin="upper", extent=[0, w, h, 0])
    if prmsl_grid is not None:
        smooth_p = scipy.ndimage.gaussian_filter(prmsl_grid, sigma=1.6)
        gx = np.linspace(0, w, smooth_p.shape[1])
        gy = np.linspace(0, h, smooth_p.shape[0])
        GX, GY = np.meshgrid(gx, gy)
        # Isobares principales tous les 2 ou 5 hPa (970 à 1045 hPa)
        levels = np.arange(960, 1055, 2)
        ax.contour(GX, GY, smooth_p, levels=levels, colors="#0b1220", linewidths=2.2)
        cs = ax.contour(GX, GY, smooth_p, levels=levels, colors="#ffffff", linewidths=1.2)
        labels = ax.clabel(cs, inline=True, fmt="%d", fontsize=14,
                           colors="#ffffff", inline_spacing=12)
        if labels:
            for lbl in labels:
                lbl.set_weight("bold")
                lbl.set_path_effects([
                    matplotlib.patheffects.Stroke(linewidth=2.5, foreground="#0b1220"),
                    matplotlib.patheffects.Normal(),
                ])
    ensure_dir(os.path.dirname(output_path))
    fig.savefig(output_path, format="webp", dpi=100, pil_kwargs={"quality": 88})
    plt.close(fig)


# ── Formules physiques ──────────────────────────────────────────────────────
def wind_chill_c(t_c, wind_kmh):
    """Refroidissement éolien (°C) — valable si T ≤ 10 °C et vent > 4,8 km/h."""
    t = np.asarray(t_c, dtype=np.float32)
    v = np.asarray(wind_kmh, dtype=np.float32)
    out = t.copy()
    mask = (t <= 10.0) & (v > 4.8)
    if np.any(mask):
        out[mask] = (13.12 + 0.6215 * t[mask]
                     - 11.37 * np.power(v[mask], 0.16)
                     + 0.3965 * t[mask] * np.power(v[mask], 0.16))
    return out


def heat_index_c(t_c, rh_pct):
    """Indice de chaleur (°C) — valable si T ≥ 27 °C et HR ≥ 40 % (Rothfusz)."""
    t = np.asarray(t_c, dtype=np.float32)
    rh = np.asarray(rh_pct, dtype=np.float32)
    out = t.copy()
    mask = (t >= 27.0) & (rh >= 40.0)
    if np.any(mask):
        T = t[mask]
        R = rh[mask]
        out[mask] = (-8.784695 + 1.61139411 * T + 2.33854889 * R
                     - 0.14611605 * T * R - 1.2308094e-2 * T * T
                     - 1.6424828e-2 * R * R + 2.211732e-3 * T * T * R
                     + 7.2546e-4 * T * R * R - 3.582e-6 * T * T * R * R)
    return out


def dew_point_c(t_c, rh_pct):
    """Point de rosée (°C) calculé depuis T et HR (formule Magnus)."""
    t = np.asarray(t_c, dtype=np.float32)
    rh = np.asarray(rh_pct, dtype=np.float32)
    a, b = 17.67, 243.5
    gamma = np.log(np.clip(rh, 1.0, 100.0) / 100.0) + a * t / (b + t)
    return (b * gamma) / (a - gamma)


def humidex_c(t_c, td_c):
    """Indice humidex (confort) à partir de T et du point de rosée."""
    t = np.asarray(t_c, dtype=np.float32)
    td = np.asarray(td_c, dtype=np.float32)
    e = 6.11 * np.exp(5417.7530 * (1.0 / 273.16 - 1.0 / (273.15 + td)))
    return t + 0.5555 * (e - 10.0)


def felt_temperature_c(t_c, td_c, wind_kmh, rh_pct):
    """Température ressentie : indice de chaleur si T≥27 °C, sinon refroid. éolien."""
    hi = heat_index_c(t_c, rh_pct)
    wc = wind_chill_c(t_c, wind_kmh)
    # Sélection : heat index quand il s'applique (sinon il vaut T),
    # wind chill quand il s'applique (sinon il vaut T).
    t = np.asarray(t_c, dtype=np.float32)
    out = hi.copy()
    mask_wc = (t <= 10.0)
    out[mask_wc] = wc[mask_wc]
    return out
