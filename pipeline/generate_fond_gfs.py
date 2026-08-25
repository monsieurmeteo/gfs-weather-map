#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, math, urllib.request
import shapely.geometry
from shapely.ops import unary_union
from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output', 'gfs', 'maps')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Domaine synoptique officiel Météociel ARPEGE/GFS Europe (Groenland, Islande, Europe, Maghreb)
BOUNDS = {'south': 28.0, 'west': -38.0, 'north': 70.0, 'east': 32.0}
WIDTH, HEIGHT = 2200, 1640

OCEAN = (143, 163, 184)
LAND = (237, 234, 226)
BORDER = (160, 165, 170)

def mercator_y(lat):
    lat = max(-85.0, min(85.0, lat))
    return math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))

ny = mercator_y(BOUNDS['north'])
sy = mercator_y(BOUNDS['south'])

def project(lon, lat):
    u = (lon - BOUNDS['west']) / (BOUNDS['east'] - BOUNDS['west'])
    v = (ny - mercator_y(lat)) / (ny - sy)
    return (u * (WIDTH - 1), v * (HEIGHT - 1))

def iter_rings(geom):
    t = geom['type']
    if t == 'Polygon':
        for ring in geom['coordinates']: yield ring
    elif t == 'MultiPolygon':
        for poly in geom['coordinates']:
            for ring in poly: yield ring

def polygon_path(rings):
    parts = []
    for ring in rings:
        pts = [project(p[0], p[1]) for p in ring]
        if len(pts) < 3: continue
        d = 'M%.1f %.1f ' % pts[0] + 'L' + ' '.join('%.1f %.1f' % p for p in pts[1:]) + 'Z'
        parts.append(d)
    return ' '.join(parts)

def line_to_svg(geom):
    if geom is None or geom.is_empty:
        return ''
    if geom.geom_type == 'LineString':
        pts = [project(p[0], p[1]) for p in geom.coords]
        if len(pts) < 2: return ''
        return 'M%.1f %.1f L%s' % (pts[0][0], pts[0][1], ' '.join('%.1f %.1f' % p for p in pts[1:]))
    elif geom.geom_type == 'MultiLineString':
        return ' '.join(line_to_svg(g) for g in geom.geoms if not g.is_empty)
    return ''

def main():
    print('Chargement des fichiers GeoJSON haute précision...')
    with open(os.path.join(BASE_DIR, 'config', 'international-boundaries.geojson'), encoding='utf-8') as f:
        boundaries = json.load(f)
    with open(os.path.join(BASE_DIR, 'config', 'coastlines.geojson'), encoding='utf-8') as f:
        coastlines = json.load(f)
    with open(os.path.join(BASE_DIR, 'config', 'countries-50m.geojson'), encoding='utf-8') as f:
        countries = json.load(f)

    dept_url = 'https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements.geojson'
    req = urllib.request.Request(dept_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        depts = json.loads(r.read().decode('utf-8'))

    # 1. Génération de fond.webp et mask_france.png
    img = Image.new('RGB', (WIDTH, HEIGHT), OCEAN)
    draw = ImageDraw.Draw(img)
    mask_img = Image.new('L', (WIDTH, HEIGHT), 0)
    mask_draw = ImageDraw.Draw(mask_img)

    for feat in countries.get('features', []):
        geom = feat.get('geometry')
        if not geom: continue
        for ring in iter_rings(geom):
            pts = [project(p[0], p[1]) for p in ring]
            if len(pts) >= 3:
                draw.polygon(pts, fill=LAND)
                mask_draw.polygon(pts, fill=255)

    for feat in countries.get('features', []):
        geom = feat.get('geometry')
        if not geom: continue
        for ring in iter_rings(geom):
            pts = [project(p[0], p[1]) for p in ring]
            if len(pts) >= 2:
                draw.line(pts, fill=BORDER, width=2)

    img.save(os.path.join(OUTPUT_DIR, 'fond.webp'), 'WEBP', quality=90)
    mask_img.save(os.path.join(OUTPUT_DIR, 'mask_france.png'), 'PNG')
    print('✅ fond.webp et mask_france.png générés !')

    # 2. Génération de frontieres.svg HD
    bounds_box = shapely.geometry.box(BOUNDS['west'] - 0.5, BOUNDS['south'] - 0.5, BOUNDS['east'] + 0.5, BOUNDS['north'] + 0.5)

    france_shapes = []
    depts_d = []
    for feat in depts.get('features', []):
        geom = feat.get('geometry')
        if not geom: continue
        france_shapes.append(shapely.geometry.shape(geom))
        rings = list(iter_rings(geom))
        depts_d.append(polygon_path(rings))

    france_union = unary_union(france_shapes)
    france_mask = france_union.buffer(0.015)

    def extract_lines(collection):
        out = []
        for feat in collection.get('features', []):
            geom = feat.get('geometry')
            if not geom: continue
            s = shapely.geometry.shape(geom)
            if not s.intersects(bounds_box): continue
            cleaned = s.intersection(bounds_box).difference(france_mask)
            if cleaned.is_empty: continue
            if cleaned.geom_type == 'LineString':
                d = line_to_svg(cleaned)
                if d: out.append(d)
            elif cleaned.geom_type == 'MultiLineString':
                for ls in cleaned.geoms:
                    d = line_to_svg(ls)
                    if d: out.append(d)
        return ' '.join(p for p in out if p)

    foreign_boundaries_d = extract_lines(boundaries)
    foreign_coastlines_d = extract_lines(coastlines)
    france_border_d = line_to_svg(france_union.boundary)
    national_lines = (foreign_boundaries_d + ' ' + foreign_coastlines_d + ' ' + france_border_d).strip()
    depts_combined = ' '.join(depts_d)

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">\n'
        '<!-- Côtes et frontières nationales en noir franc style Météociel GFS -->\n'
        '<path d="%s" fill="none" stroke="#0b1220" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>\n'
        '<!-- Départements français fins et discrets en gris style Météociel GFS -->\n'
        '<path d="%s" fill="none" stroke="#7a828e" stroke-width="0.8" stroke-opacity="0.85" stroke-linejoin="round" stroke-linecap="round"/>\n'
        '</svg>\n' % (WIDTH, HEIGHT, WIDTH, HEIGHT, national_lines, depts_combined)
    )

    with open(os.path.join(OUTPUT_DIR, 'frontieres.svg'), 'w', encoding='utf-8') as f:
        f.write(svg)

    print('✅ frontieres.svg style Météociel GFS (national noir + départements gris fins) généré avec succès !')

if __name__ == '__main__':
    main()
