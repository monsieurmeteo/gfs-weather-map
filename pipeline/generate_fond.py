#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur du fond de carte (style Positron, comme meteo-npdc.fr)
=================================================================
Produit output/arome/maps/fond.webp : une carte 2200×1640 (Mercator) avec
  - océan bleu-gris (#8FA3B8 ≈ Positron water)
  - terres gris très clair (#ECE9E2 ≈ Positron land)
  - frontières des pays (gris moyen), avec la France mise en évidence
Le tout est ensuite utilisé comme fond par le moteur cartographique.
"""

import os
import json
import math
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "pipeline"))
from fetch_and_render_all import BOUNDS, WIDTH, HEIGHT  # noqa: E402

COUNTRIES_FILE = os.path.join(BASE_DIR, "config", "countries-50m.geojson")
REGIONS_FILE = os.path.join(BASE_DIR, "config", "regions-france.geojson")
DEPARTEMENTS_URL = ("https://raw.githubusercontent.com/gregoiredavid/"
                    "france-geojson/master/departements.geojson")
MASK_FILE = os.path.join(BASE_DIR, "output", "arome", "maps", "mask_france.png")
SVG_FILE = os.path.join(BASE_DIR, "output", "arome", "maps", "frontieres.svg")

# Couleurs style Positron (cartes claires MapLibre, comme meteo-npdc)
OCEAN = (143, 163, 184)        # #8FA3B8
LAND = (237, 234, 226)         # #EDEAE2
LAND_FRANCE = (232, 228, 218)  # France légèrement distincte
BORDER = (160, 165, 170)       # frontières internationales
FRANCE_BORDER = (120, 128, 136)


def _mercator_y(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def _project(coord):
    """Longitude/latitude → pixel (Mercator) dans la grille BOUNDS."""
    lon, lat = coord
    west, east = BOUNDS["west"], BOUNDS["east"]
    north, south = BOUNDS["north"], BOUNDS["south"]
    ny = _mercator_y(north)
    sy = _mercator_y(south)
    u = (lon - west) / (east - west)
    v = (ny - _mercator_y(lat)) / (ny - sy)
    return (u * (WIDTH - 1), v * (HEIGHT - 1))


def _iter_rings(geometry):
    """Itère sur les anneaux (listes de coordonnées) d'une géométrie."""
    t = geometry["type"]
    if t == "Polygon":
        yield from geometry["coordinates"]
    elif t == "MultiPolygon":
        for poly in geometry["coordinates"]:
            yield from poly


def _ring_to_xy(ring):
    pts = [_project(c) for c in ring]
    return [(float(x), float(y)) for x, y in pts]


def generate_fond(out_path):
    """Génère le fond de carte 2200×1640 et l'enregistre en WebP."""
    with open(COUNTRIES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    img = Image.new("RGB", (WIDTH, HEIGHT), OCEAN)
    draw = ImageDraw.Draw(img)

    # 1. Remplissage des terres (pays)
    france_names = {"France", "French Guiana"}
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        name = props.get("NAME") or props.get("ADMIN") or props.get("name") or ""
        geom = feat.get("geometry")
        if not geom:
            continue
        fill = LAND_FRANCE if name in france_names else LAND
        for ring in _iter_rings(geom):
            pts = _ring_to_xy(ring)
            if len(pts) >= 3:
                draw.polygon(pts, fill=fill)

    # 2. Les frontières et côtes sont tracées exclusivement par frontieres.svg
    # (évite les dédoublements de contours entre le fond bitmap et le SVG).

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, format="WEBP", quality=90, method=6)
    print("Fond de carte généré : %s (%dx%d)" % (out_path, WIDTH, HEIGHT))
    return out_path


def generate_france_mask(out_path=None):
    """Masque France précis (255 = France, 0 = extérieur) dans les bornes
    EXACTES des tuiles (BOUNDS). Sans lui, la météo déborde sur les pays
    voisins et la mer."""
    out_path = out_path or MASK_FILE
    try:
        req = urllib.request.urlopen(DEPARTEMENTS_URL, timeout=60)
        data = json.loads(req.read().decode("utf-8"))
    except Exception as e:
        print("WARNING: masque France non généré (%s)" % e)
        return None

    img = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(img)
    for feature in data.get("features", []):
        geom = feature.get("geometry", {})
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])
        if gtype == "Polygon":
            for ring in coords:
                pts = [_project((pt[0], pt[1])) for pt in ring]
                draw.polygon(pts, fill=255)
        elif gtype == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    pts = [_project((pt[0], pt[1])) for pt in ring]
                    draw.polygon(pts, fill=255)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, format="PNG")
    print("Masque France généré : %s" % out_path)
    return out_path


def _polygon_path(rings, bbox=None):
    """Construit un path SVG 'd' depuis des anneaux projetés (x, y).
    bbox = (xmin, ymin, xmax, ymax) : les anneaux entièrement hors bbox
    sont ignorés (évite des coordonnées gigantesques dans le SVG)."""
    parts = []
    for ring in rings:
        pts = _ring_to_xy(ring)
        if len(pts) < 3:
            continue
        if bbox:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if max(xs) < bbox[0] or min(xs) > bbox[2] or \
                    max(ys) < bbox[1] or min(ys) > bbox[3]:
                continue
        d = "M%.1f %.1f " % pts[0]
        d += "L" + " ".join("%.1f %.1f" % p for p in pts[1:])
        d += "Z"
        parts.append(d)
    return " ".join(parts)


def _load_geojson(path_or_url):
    if path_or_url.startswith("http"):
        req = urllib.request.urlopen(path_or_url, timeout=60)
        return json.loads(req.read().decode("utf-8"))
    with open(path_or_url, encoding="utf-8") as f:
        return json.load(f)


def generate_svg(out_path=None):
    """Régénère frontieres.svg avec des lignes UNIQUES (LineString) pour
    les frontières internationales et les côtes, sans aucune duplication polygonale."""
    import shapely.geometry
    from shapely.ops import unary_union

    out_path = out_path or SVG_FILE
    depts = _load_geojson(DEPARTEMENTS_URL)
    boundaries = _load_geojson(os.path.join(BASE_DIR, "config", "international-boundaries.geojson"))
    coastlines = _load_geojson(os.path.join(BASE_DIR, "config", "coastlines.geojson"))

    bounds_box = shapely.geometry.box(
        BOUNDS["west"] - 0.5, BOUNDS["south"] - 0.5,
        BOUNDS["east"] + 0.5, BOUNDS["north"] + 0.5
    )

    # 1. France : départements et côtes haute précision
    france_shapes = []
    depts_d = []
    for f in depts.get("features", []):
        s = shapely.geometry.shape(f["geometry"])
        france_shapes.append(s)
        rings = list(_iter_rings(f["geometry"]))
        depts_d.append(_polygon_path(rings))

    france_union = unary_union(france_shapes)
    france_mask = france_union.buffer(0.015)

    # 2. Lignes de frontières internationales uniques (hors France)
    def line_to_svg(geom):
        pts = [_project(p) for p in geom.coords]
        if len(pts) < 2:
            return ""
        return "M%.1f %.1f L%s" % (pts[0][0], pts[0][1], " ".join("%.1f %.1f" % p for p in pts[1:]))

    def extract_lines(collection):
        out = []
        for feat in collection.get("features", []):
            geom = feat.get("geometry")
            if not geom:
                continue
            s = shapely.geometry.shape(geom)
            if not s.intersects(bounds_box):
                continue
            # Couper ce qui touche la France pour ne laisser que le département français tracer la frontière
            cleaned = s.intersection(bounds_box).difference(france_mask)
            if cleaned.is_empty:
                continue
            if cleaned.geom_type == "LineString":
                d = line_to_svg(cleaned)
                if d:
                    out.append(d)
            elif cleaned.geom_type == "MultiLineString":
                for ls in cleaned.geoms:
                    d = line_to_svg(ls)
                    if d:
                        out.append(d)
        return " ".join(p for p in out if p)

    foreign_boundaries_d = extract_lines(boundaries)
    foreign_coastlines_d = extract_lines(coastlines)
    all_foreign_d = (foreign_boundaries_d + " " + foreign_coastlines_d).strip()

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 %d %d" width="%d" height="%d">\n'
        '<path d="%s" fill="none" stroke="#0d1117" stroke-width="2.6" '
        'stroke-linejoin="round" stroke-linecap="round"/>\n'
        '<path d="%s" fill="none" stroke="#0d1117" stroke-width="1.6" '
        'stroke-linejoin="round" stroke-linecap="round"/>\n'
        '</svg>\n' % (WIDTH, HEIGHT, WIDTH, HEIGHT, all_foreign_d, " ".join(depts_d))
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print("SVG frontières régénéré (traits plus épais et nets) : %s (%d octets)" % (out_path, len(svg)))
    return out_path


def generate_all():
    """Génère le fond de carte + le masque France + les frontières (projection
    identique aux tuiles → plus aucun décalage)."""
    maps_dir = os.path.join(BASE_DIR, "output", "arome", "maps")
    generate_fond(os.path.join(maps_dir, "fond.webp"))
    generate_france_mask(os.path.join(maps_dir, "mask_france.png"))
    generate_svg(os.path.join(maps_dir, "frontieres.svg"))


if __name__ == "__main__":
    generate_all()
