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
    "geopotentiel_500_meteociel": ("Géopotentiel 500 hPa (contours Météociel)", "dam", 0, "Pression et géopotentiel"),
    "temperature_850":       ("Température à 850 hPa (~1 500 m)", "°C", 1, "Pression et géopotentiel"),
    "pluie_1h":              ("Précipitations sur 3 h",        "mm",   1, "Précipitations"),
    "pluie_cumul":           ("Précipitations cumulées",       "mm",   1, "Précipitations"),
    "neige_au_sol":          ("Épaisseur de neige au sol",     "cm",   1, "Autres"),
}

# Ordre d'affichage des couches dans le sélecteur
LAYER_ORDER = [
    "geopotentiel_500", "temperature_850", "pression", "pression_surface",
    "temperature", "temperature_ressentie", "point_rosee", "humidex",
    "vent", "rafales", "rafales_cumul",
    "nebulosite", "nuages_bas", "nuages_moyens", "nuages_eleves",
    "humidite", "mucape",
    "pluie_1h", "pluie_cumul", "neige_au_sol",
]


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p


# ── Couleur ──────────────────────────────────────────────────────────────────
def apply_palette(data, palette, discrete=False):
    """Applique une palette (liste de (seuil, rgba)) à un champ 2D → RGBA.

    discrete=True : bandes de couleurs PLEINES (chaque classe = couleur de son
    seuil, sans interpolation) — nécessaire pour le Z500 par classes de 4 dam
    (style Météociel). False : dégradé linéaire continu (autres couches).
    """
    vs = np.array([s[0] for s in palette], dtype=np.float32)
    cs = np.array([list(s[1]) for s in palette], dtype=np.float32)
    rgba = np.zeros((*data.shape, 4), dtype=np.uint8)
    if discrete:
        # Chaque classe [vs[i], vs[i+1]) reçoit la couleur PLEINE de son seuil bas
        for i in range(len(vs) - 1):
            mask = (data >= vs[i]) & (data < vs[i + 1])
            if np.any(mask):
                rgba[mask] = cs[i].astype(np.uint8)
        rgba[data <= vs[0]] = cs[0].astype(np.uint8)
        rgba[data >= vs[-1]] = cs[-1].astype(np.uint8)
        return rgba
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


# ── Communes & Villes Européennes (places) ──────────────────────────────────
def write_places(domain, out_dir):
    """Génère maps/communes.json filtré au domaine (tri par population)."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_fr = os.path.join(base_dir, "config", "communes-compact.json")
    src_eu = os.path.join(base_dir, "config", "cities_europe.json")
    
    out = []
    w, e = domain.west, domain.east
    s, n = domain.south, domain.north

    # Villes européennes majeures pour le domaine Europe
    if os.path.exists(src_eu) and domain.projection == "lambert":
        with open(src_eu, encoding="utf-8") as f:
            cities_eu = json.load(f)
            for c in cities_eu:
                out.append(c)

    if os.path.exists(src_fr):
        with open(src_fr, encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            try:
                lat, lon = float(r[5]), float(r[6])
                pop = int(r[4])
            except (IndexError, TypeError, ValueError):
                continue
            if w <= lon <= e and s <= lat <= n:
                out.append([r[1], pop, lat, lon])

    # Dédoublonnage et tri décroissant par population
    seen = set()
    unique_out = []
    out.sort(key=lambda p: -p[1])
    for p in out:
        key = p[0].lower()
        if key not in seen:
            seen.add(key)
            unique_out.append(p)

    ensure_dir(out_dir)
    with open(os.path.join(out_dir, "communes.json"), "w", encoding="utf-8") as f:
        json.dump({"places": unique_out}, f, ensure_ascii=False)
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



# ── T850 + isothermes ────────────────────────────────────────────────────────
def render_temperature850_with_isotherms(t850_grid, output_path):
    """T850 coloré (palette temperature_850) + isothermes tous les 4°C style Météociel.
    Isotherme 0°C en noir épais — niveau de congélation bien visible.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects
    import scipy.ndimage

    pal = PALETTES.get("temperature_850", PALETTES["temperature"])
    base_img = apply_palette(np.nan_to_num(t850_grid, nan=np.nan), pal)
    if np.isnan(t850_grid).any():
        base_img[np.isnan(t850_grid), 3] = 0

    h, w = t850_grid.shape
    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    try:
        fig.patch.set_alpha(0)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.set_facecolor((0, 0, 0, 0))
        ax.imshow(base_img, origin="upper", extent=[0, w, h, 0])

        nan_mask = np.isnan(t850_grid)
        if nan_mask.any():
            weights = scipy.ndimage.gaussian_filter((~nan_mask).astype(float), sigma=1.5)
            vals = scipy.ndimage.gaussian_filter(np.where(nan_mask, 0.0, t850_grid), sigma=1.5)
            with np.errstate(invalid="ignore", divide="ignore"):
                smooth_t = np.where(weights > 0.1, vals / np.maximum(weights, 1e-6), np.nan)
            smooth_t = np.ma.masked_invalid(smooth_t)
        else:
            smooth_t = scipy.ndimage.gaussian_filter(t850_grid, sigma=1.5)

        gx = np.linspace(0, w, t850_grid.shape[1])
        gy = np.linspace(0, h, t850_grid.shape[0])
        GX, GY = np.meshgrid(gx, gy)

        # Isothermes fines tous les 4°C (-40 à +40°C)
        levels_4 = np.arange(-40, 44, 4)
        # Halo blanc pour contraste
        ax.contour(GX, GY, smooth_t, levels=levels_4,
                   colors="#ffffff", linewidths=3.0, alpha=0.65)
        cs4 = ax.contour(GX, GY, smooth_t, levels=levels_4,
                         colors="#222222", linewidths=1.3, alpha=0.85)
        labels4 = ax.clabel(cs4, inline=True, fmt="%d", fontsize=16,
                            colors="#111111", inline_spacing=6)
        if labels4:
            for lbl in labels4:
                lbl.set_weight("bold")
                lbl.set_path_effects([
                    matplotlib.patheffects.Stroke(linewidth=3.5, foreground="#ffffff"),
                    matplotlib.patheffects.Normal(),
                ])

        # Isotherme 0°C — niveau de congélation, noir épais bien visible
        ax.contour(GX, GY, smooth_t, levels=[0],
                   colors="#ffffff", linewidths=7.0)
        cs0 = ax.contour(GX, GY, smooth_t, levels=[0],
                         colors="#000000", linewidths=3.5)
        labels0 = ax.clabel(cs0, inline=True, fmt="0°C", fontsize=18,
                            colors="#000000", inline_spacing=10)
        if labels0:
            for lbl in labels0:
                lbl.set_weight("black")
                lbl.set_path_effects([
                    matplotlib.patheffects.Stroke(linewidth=4.5, foreground="#ffffff"),
                    matplotlib.patheffects.Normal(),
                ])

        ensure_dir(os.path.dirname(output_path))
        fig.savefig(output_path, format="webp", dpi=100, transparent=True,
                    pil_kwargs={"quality": 88})
    finally:
        plt.close(fig)


# ── Z500 + isobares ─────────────────────────────────────────────────────────
def render_z500_with_isobars(z500_grid, prmsl_grid, output_path, style="synoptique"):
    """Z500 en bandes de couleurs (palette geopotentiel_500, classes 4 dam)
    + isobares PRMSL niveau mer en hPa.

    style="synoptique" (DÉFAUT, esprit Météociel) : bandes Z500 4 dam
        + isobares blanches tous les 5 hPa UNIQUEMENT (épaisses, étiquettes
        blanches avec halo sombre) — lecture synoptique claire, zéro spaghetti.
    style="detail" : mêmes bandes Z500 + isobares 1 hPa très fines + 5 hPa
        épaisses (étiquettes sur les 5 hPa uniquement) — analyse avancée.
    style="dense"   : ancien rendu (1 hPa + 5 hPa) — conservé pour compat.
    style="meteociel": ancien rendu Météociel (5/10 hPa + isolignes Z500).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects
    import scipy.ndimage

    pal = PALETTES.get("geopotentiel_500", PALETTES["temperature"])
    # BANDES DISCRÈTES 4 dam (pas de dégradé continu)
    base_img = apply_palette(np.nan_to_num(z500_grid, nan=np.nan), pal, discrete=True)
    if np.isnan(z500_grid).any():
        base_img[np.isnan(z500_grid), 3] = 0

    h, w = z500_grid.shape
    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    try:
        fig.patch.set_alpha(0)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.set_facecolor((0, 0, 0, 0))
        ax.imshow(base_img, origin="upper", extent=[0, w, h, 0])
        if prmsl_grid is not None:
            nan_mask = np.isnan(prmsl_grid)
            if nan_mask.any():
                weights = scipy.ndimage.gaussian_filter((~nan_mask).astype(float), sigma=2.0)
                vals = scipy.ndimage.gaussian_filter(np.where(nan_mask, 0.0, prmsl_grid), sigma=2.0)
                with np.errstate(invalid="ignore", divide="ignore"):
                    smooth_p = np.where(weights > 0.1, vals / np.maximum(weights, 1e-6), np.nan)
                smooth_p = np.ma.masked_invalid(smooth_p)
            else:
                smooth_p = scipy.ndimage.gaussian_filter(prmsl_grid, sigma=2.0)

            gx = np.linspace(0, w, prmsl_grid.shape[1])
            gy = np.linspace(0, h, prmsl_grid.shape[0])
            GX, GY = np.meshgrid(gx, gy)

            levels_5hpa = np.arange(935, 1065, 5)
            levels_10hpa = np.arange(930, 1070, 10)

            if style == "synoptique":
                # ── MODE SYNOPTIQUE (défaut, esprit Météociel) ─────────────
                # Isobares blanches tous les 5 hPa UNIQUEMENT : épaisses,
                # fluides, étiquettes blanches avec halo sombre.
                ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                           colors="#000000", linewidths=4.2, alpha=0.75)
                cs5 = ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                                 colors="#ffffff", linewidths=2.0)
                labels = ax.clabel(cs5, inline=True, fmt="%d", fontsize=17,
                                   colors="#ffffff", inline_spacing=8)
                if labels:
                    for lbl in labels:
                        lbl.set_weight("bold")
                        lbl.set_path_effects([
                            matplotlib.patheffects.Stroke(linewidth=3.2, foreground="#000000"),
                            matplotlib.patheffects.Normal(),
                        ])
            elif style == "detail":
                # ── MODE DÉTAILLÉ : 1 hPa fins très discrets + 5 hPa épais ──
                levels_1hpa = np.arange(935, 1065, 1)
                ax.contour(GX, GY, smooth_p, levels=levels_1hpa,
                           colors="#000000", linewidths=1.8, alpha=0.35)
                ax.contour(GX, GY, smooth_p, levels=levels_1hpa,
                           colors="#ffffff", linewidths=0.8, alpha=0.5)
                ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                           colors="#000000", linewidths=4.2, alpha=0.75)
                cs5 = ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                                 colors="#ffffff", linewidths=2.0)
                labels = ax.clabel(cs5, inline=True, fmt="%d", fontsize=17,
                                   colors="#ffffff", inline_spacing=8)
                if labels:
                    for lbl in labels:
                        lbl.set_weight("bold")
                        lbl.set_path_effects([
                            matplotlib.patheffects.Stroke(linewidth=3.2, foreground="#000000"),
                            matplotlib.patheffects.Normal(),
                        ])
            elif style == "meteociel":
                # ── Style Météociel (ancien) : isobares 5 hPa + principales 10 hPa ──
                ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                           colors="#000000", linewidths=3.2, alpha=0.65)
                cs5 = ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                                 colors="#ffffff", linewidths=1.6)
                labels = ax.clabel(cs5, inline=True, fmt="%d", fontsize=17,
                                   colors="#ffffff", inline_spacing=8)
                if labels:
                    for lbl in labels:
                        lbl.set_weight("bold")
                        lbl.set_path_effects([
                            matplotlib.patheffects.Stroke(linewidth=3.2, foreground="#000000"),
                            matplotlib.patheffects.Normal(),
                        ])
                ax.contour(GX, GY, smooth_p, levels=levels_10hpa,
                           colors="#000000", linewidths=5.5, alpha=0.55)
                ax.contour(GX, GY, smooth_p, levels=levels_10hpa,
                           colors="#ffffff", linewidths=2.8, alpha=0.9)

                # Isolignes Z500 discrètes tous les 6 dam (gris sombre, fines)
                if z500_grid is not None:
                    if np.isnan(z500_grid).any():
                        zm = np.isnan(z500_grid)
                        zw = scipy.ndimage.gaussian_filter((~zm).astype(float), sigma=2.0)
                        zv = scipy.ndimage.gaussian_filter(np.where(zm, 0.0, z500_grid), sigma=2.0)
                        with np.errstate(invalid="ignore", divide="ignore"):
                            smooth_z = np.where(zw > 0.1, zv / np.maximum(zw, 1e-6), np.nan)
                        smooth_z = np.ma.masked_invalid(smooth_z)
                    else:
                        smooth_z = scipy.ndimage.gaussian_filter(z500_grid, sigma=2.0)
                    levels_6dam = np.arange(480, 620, 6)
                    ax.contour(GX, GY, smooth_z, levels=levels_6dam,
                               colors="#222222", linewidths=1.1, alpha=0.40)
            else:
                # ── Style dense (ancien défaut) : isobares fines 1 hPa + épaisses 5 hPa ──
                levels_1hpa = np.arange(935, 1065, 1)

                # Isobares fines 1 hPa : ligne NOIRE (halo blanc pour détacher du fond)
                ax.contour(GX, GY, smooth_p, levels=levels_1hpa,
                           colors="#ffffff", linewidths=3.0, alpha=0.85)
                ax.contour(GX, GY, smooth_p, levels=levels_1hpa,
                           colors="#000000", linewidths=1.4, alpha=0.9)

                # Isobares épaisses 5 hPa + labels blancs
                ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                           colors="#ffffff", linewidths=5.5)
                cs5 = ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                                 colors="#000000", linewidths=2.8)
                labels = ax.clabel(cs5, inline=True, fmt="%d", fontsize=18,
                                   colors="#ffffff", inline_spacing=8)
                if labels:
                    for lbl in labels:
                        lbl.set_weight("bold")
                        lbl.set_path_effects([
                            matplotlib.patheffects.Stroke(linewidth=3.5, foreground="#000000"),
                            matplotlib.patheffects.Normal(),
                        ])
        ensure_dir(os.path.dirname(output_path))
        # Légende Z500 intégrée (30 rectangles 492→612 dam) — mode synoptique/détail
        if style in ("synoptique", "detail"):
            _draw_z500_legend(ax, w, h)
        fig.savefig(output_path, format="webp", dpi=100, transparent=True, pil_kwargs={"quality": 88})
    finally:
        plt.close(fig)


def _draw_z500_legend(ax, w, h):
    """Légende horizontale en bas : 30 rectangles adjacents (classes de 4 dam)
    + bornes 492→612, couleurs identiques à la palette geopotentiel_500."""
    import matplotlib.patches as mpatches
    import matplotlib.patheffects as pe

    levels = list(range(492, 616, 4))  # 492..612 → 31 bornes → 30 classes
    colors = [
        "#400040", "#600060", "#AA00AA", "#801080", "#600040",
        "#303366", "#003399", "#0000CC", "#0000FF", "#0055FF",
        "#0099FF", "#33CCFF", "#66FFFF", "#66FF99", "#66FF66",
        "#66FF00", "#BFFA0E", "#FFFF09", "#FFFF86", "#FDE851",
        "#FFCC00", "#FF9900", "#FF6900", "#FF4D33", "#FF3000",
        "#FF0000", "#CC0000", "#990000", "#6C0000", "#4F0000",
    ]
    n = len(colors)               # 30 classes
    lw = w * 0.90                 # largeur barre : 90 % de la carte
    lx0 = (w - lw) / 2.0
    ly0 = h - 104                 # bas de la barre (marge 24 px en bas)
    bh = 34                       # hauteur des rectangles
    sw = lw / n                   # largeur d'un rectangle

    # Fond sombre semi-transparent derrière la légende
    ax.add_patch(mpatches.Rectangle((lx0 - 20, ly0 - 12), lw + 40, bh + 58,
                                    facecolor=(7 / 255.0, 11 / 255.0, 20 / 255.0, 0.55),
                                    edgecolor="none"))
    # 30 rectangles adjacents
    for i in range(n):
        ax.add_patch(mpatches.Rectangle((lx0 + i * sw, ly0), sw + 0.4, bh,
                                        facecolor=colors[i], edgecolor="none"))
    # Bornes au-dessus des rectangles (492, 496, ... 612)
    for i, v in enumerate(levels):
        x = lx0 + i * sw
        ax.text(x, ly0 + bh + 4, "%d" % v, fontsize=12, ha="center",
                va="bottom", color="#ffffff", fontweight="bold",
                path_effects=[pe.Stroke(linewidth=2.2, foreground="#000000"),
                              pe.Normal()])


def render_pression_with_isobars(prmsl_grid, output_path):
    """Pression niveau mer colorée (palette pression) + isobares continues (hPa)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects
    import scipy.ndimage

    pal = PALETTES.get("pression", PALETTES["temperature"])
    base_img = apply_palette(np.nan_to_num(prmsl_grid, nan=np.nan), pal)
    if np.isnan(prmsl_grid).any():
        base_img[np.isnan(prmsl_grid), 3] = 0

    h, w = prmsl_grid.shape
    fig = plt.figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    try:
        fig.patch.set_alpha(0)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.set_facecolor((0, 0, 0, 0))
        ax.imshow(base_img, origin="upper", extent=[0, w, h, 0])
        if prmsl_grid is not None:
            nan_mask = np.isnan(prmsl_grid)
            # Lissage modéré (sigma=2) pour conserver les gradients serrés
            if nan_mask.any():
                weights = scipy.ndimage.gaussian_filter((~nan_mask).astype(float), sigma=2.0)
                vals = scipy.ndimage.gaussian_filter(np.where(nan_mask, 0.0, prmsl_grid), sigma=2.0)
                with np.errstate(invalid="ignore", divide="ignore"):
                    smooth_p = np.where(weights > 0.1, vals / np.maximum(weights, 1e-6), np.nan)
                smooth_p = np.ma.masked_invalid(smooth_p)
            else:
                smooth_p = scipy.ndimage.gaussian_filter(prmsl_grid, sigma=2.0)

            gx = np.linspace(0, w, prmsl_grid.shape[1])
            gy = np.linspace(0, h, prmsl_grid.shape[0])
            GX, GY = np.meshgrid(gx, gy)

            # ── Isobares fines tous les 1 hPa (style Météociel) ──────────────
            levels_1hpa = np.arange(935, 1065, 1)
            levels_5hpa = np.arange(935, 1065, 5)

            # Halo blanc pour les lignes fines (1 hPa) + ligne NOIRE
            ax.contour(GX, GY, smooth_p, levels=levels_1hpa,
                       colors="#ffffff", linewidths=2.6, alpha=0.75)
            ax.contour(GX, GY, smooth_p, levels=levels_1hpa,
                       colors="#000000", linewidths=1.2, alpha=0.85)

            # ── Isobares épaisses tous les 5 hPa + labels ─────────────────────
            ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                       colors="#ffffff", linewidths=5.5, alpha=0.9)
            cs5 = ax.contour(GX, GY, smooth_p, levels=levels_5hpa,
                             colors="#000000", linewidths=2.8)
            labels = ax.clabel(cs5, inline=True, fmt="%d", fontsize=18,
                               colors="#000000", inline_spacing=8)
            if labels:
                for lbl in labels:
                    lbl.set_weight("bold")
                    lbl.set_path_effects([
                        matplotlib.patheffects.Stroke(linewidth=4.0, foreground="#ffffff"),
                        matplotlib.patheffects.Normal(),
                    ])
        ensure_dir(os.path.dirname(output_path))
        fig.savefig(output_path, format="webp", dpi=100, transparent=True, pil_kwargs={"quality": 88})
    finally:
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
