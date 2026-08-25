#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline Multi-Modèles Météo — Portées Officielles Complètes
============================================================
 1. AROME HD   (1.3 km) → H+00 à H+51  (pas de 1h)
 2. ICON-EU    (7 km)   → H+00 à H+120 (pas de 1h puis 3h)
 3. ARPEGE     (5 km)   → H+00 à H+114 (pas de 1h puis 3h)
 4. ECMWF IFS  (9 km)   → H+00 à H+240 (pas de 3h puis 6h)
 5. GFS Monde  (13 km)  → H+00 à H+384 (pas de 3h puis 6h)
"""

import os, sys, json, datetime, io, bz2, tempfile, shutil, argparse
import threading, time
import requests, numpy as np, urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from scipy.interpolate import RegularGridInterpolator

urllib3.disable_warnings()

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
WIDTH, HEIGHT = 2200, 1640
BOUNDS = {"south": 39.5, "west": -8.5, "north": 52.5, "east": 13.5}

TOKEN_PATH = os.path.expanduser(
    r"~/.gemini/config/skills/dpclim/config/dpclim_token.txt"
)

def get_mf_token():
    t = os.environ.get("METEOFRANCE_TOKEN", "").strip()
    if t:
        return t
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, encoding="utf-8") as f:
            return f.read().strip()
    return ""

LABELS = {
    "temperature":           ("Temperature a 2 m",               "degC"),
    "temperature_ressentie": ("Temperature ressentie",            "degC"),
    "point_rosee":           ("Point de rosee a 2 m",            "degC"),
    "humidex":               ("Indice Humidex",                   ""),
    "pluie_1h":              ("Pluie horaire",                    "mm"),
    "pluie_cumul":           ("Precipitations cumulees",          "mm"),
    "reflectivite":          ("Reflectivite radar Doppler",       "dBZ"),
    "graupel":               ("Graupel / Gresil",                 "mm"),
    "vent":                  ("Vent moyen a 10 m",                "km/h"),
    "rafales":               ("Rafales maximales",                "km/h"),
    "rafales_cumul":         ("Rafales maximales cumulees",       "km/h"),
    "nebulosite":            ("Nebulosite totale",                "%"),
    "nuages_bas":            ("Couverture nuages bas",            "%"),
    "nuages_moyens":         ("Couverture nuages moyens",         "%"),
    "nuages_eleves":         ("Couverture nuages eleves",         "%"),
    "humidite":              ("Humidite relative a 2 m",          "%"),
    "mucape":                ("Instabilite convective (MUCAPE)",  "J/kg"),
    "neige":                 ("Chutes de neige",                  "cm/h"),
    "neige_au_sol":          ("Epaisseur neige au sol",           "cm"),
    "equivalent_eau_neige":  ("Cumul neigeux equiv. eau",         "mm"),
    "pression":              ("Pression niveau mer",              "hPa"),
    "pression_surface":      ("Pression au sol",                  "hPa"),
}
LAYERS = list(LABELS.keys())

PALETTES = {
    "temperature": [
        (-24.0,(64,0,64,255)),
        (-22.0,(96,0,96,255)),
        (-20.0,(170,0,170,255)),
        (-18.0,(128,16,128,255)),
        (-16.0,(96,0,64,255)),
        (-14.0,(48,51,102,255)),
        (-12.0,(0,51,153,255)),
        (-10.0,(0,0,204,255)),
        (-8.0,(0,0,255,255)),
        (-6.0,(0,85,255,255)),
        (-4.0,(0,153,255,255)),
        (-2.0,(51,204,255,255)),
        (0.0,(102,255,255,255)),
        (2.0,(102,255,153,255)),
        (4.0,(102,255,102,255)),
        (6.0,(102,255,0,255)),
        (8.0,(191,250,14,255)),
        (10.0,(255,255,9,255)),
        (12.0,(255,255,134,255)),
        (14.0,(253,232,81,255)),
        (16.0,(255,204,0,255)),
        (18.0,(255,153,0,255)),
        (20.0,(255,105,0,255)),
        (22.0,(255,77,51,255)),
        (24.0,(255,48,0,255)),
        (26.0,(255,0,0,255)),
        (28.0,(229,0,0,255)),
        (30.0,(178,0,0,255)),
        (32.0,(153,0,0,255)),
        (34.0,(108,0,0,255)),
        (36.0,(128,0,80,255)),
        (38.0,(160,0,119,255)),
        (40.0,(204,0,204,255)),
        (42.0,(255,0,255,255)),
        (44.0,(255,64,255,255)),
        (46.0,(255,128,255,255)),
    ],
    "temperature_ressentie": [
        (-24.0,(64,0,64,255)),
        (-22.0,(96,0,96,255)),
        (-20.0,(170,0,170,255)),
        (-18.0,(128,16,128,255)),
        (-16.0,(96,0,64,255)),
        (-14.0,(48,51,102,255)),
        (-12.0,(0,51,153,255)),
        (-10.0,(0,0,204,255)),
        (-8.0,(0,0,255,255)),
        (-6.0,(0,85,255,255)),
        (-4.0,(0,153,255,255)),
        (-2.0,(51,204,255,255)),
        (0.0,(102,255,255,255)),
        (2.0,(102,255,153,255)),
        (4.0,(102,255,102,255)),
        (6.0,(102,255,0,255)),
        (8.0,(191,250,14,255)),
        (10.0,(255,255,9,255)),
        (12.0,(255,255,134,255)),
        (14.0,(253,232,81,255)),
        (16.0,(255,204,0,255)),
        (18.0,(255,153,0,255)),
        (20.0,(255,105,0,255)),
        (22.0,(255,77,51,255)),
        (24.0,(255,48,0,255)),
        (26.0,(255,0,0,255)),
        (28.0,(229,0,0,255)),
        (30.0,(178,0,0,255)),
        (32.0,(153,0,0,255)),
        (34.0,(108,0,0,255)),
        (36.0,(128,0,80,255)),
        (38.0,(160,0,119,255)),
        (40.0,(204,0,204,255)),
        (42.0,(255,0,255,255)),
        (44.0,(255,64,255,255)),
        (46.0,(255,128,255,255)),
    ],
    "point_rosee": [
        (-24.0,(0,0,16,255)),
        (-22.0,(0,5,32,255)),
        (-20.0,(0,16,64,255)),
        (-18.0,(0,51,102,255)),
        (-16.0,(0,51,153,255)),
        (-14.0,(0,0,204,255)),
        (-12.0,(0,0,255,255)),
        (-10.0,(0,102,255,255)),
        (-8.0,(0,153,255,255)),
        (-6.0,(51,204,255,255)),
        (-4.0,(102,255,255,255)),
        (-2.0,(102,255,153,255)),
        (0.0,(102,255,102,255)),
        (2.0,(102,255,0,255)),
        (4.0,(191,250,14,255)),
        (6.0,(255,255,9,255)),
        (8.0,(255,255,134,255)),
        (10.0,(253,232,81,255)),
        (12.0,(255,204,0,255)),
        (14.0,(255,153,0,255)),
        (16.0,(255,105,0,255)),
        (18.0,(255,77,51,255)),
        (20.0,(255,48,0,255)),
        (22.0,(255,0,0,255)),
        (24.0,(204,0,0,255)),
        (26.0,(153,0,0,255)),
        (28.0,(108,0,0,255)),
        (30.0,(79,0,0,255)),
    ],
    "humidex": [
        (-10.0,(64,0,64,255)),
        (-8.0,(96,0,96,255)),
        (-6.0,(170,0,170,255)),
        (-4.0,(128,16,128,255)),
        (-2.0,(96,0,64,255)),
        (0.0,(48,51,102,255)),
        (2.0,(0,51,153,255)),
        (4.0,(0,0,204,255)),
        (6.0,(0,0,255,255)),
        (8.0,(0,85,255,255)),
        (10.0,(0,153,255,255)),
        (12.0,(51,204,255,255)),
        (14.0,(102,255,255,255)),
        (16.0,(102,255,153,255)),
        (18.0,(102,255,102,255)),
        (20.0,(102,255,0,255)),
        (22.0,(191,250,14,255)),
        (24.0,(255,255,9,255)),
        (26.0,(255,255,134,255)),
        (28.0,(253,232,81,255)),
        (30.0,(255,204,0,255)),
        (32.0,(255,153,0,255)),
        (34.0,(255,105,0,255)),
        (36.0,(255,77,51,255)),
        (38.0,(255,48,0,255)),
        (40.0,(255,0,0,255)),
        (42.0,(229,0,0,255)),
        (44.0,(178,0,0,255)),
        (46.0,(153,0,0,255)),
        (48.0,(108,0,0,255)),
        (50.0,(128,0,80,255)),
        (52.0,(160,0,119,255)),
        (54.0,(204,0,204,255)),
        (56.0,(255,0,255,255)),
        (58.0,(255,64,255,255)),
        (60.0,(255,128,255,255)),
    ],
    "pluie_1h": [
        (0.0,(255,255,255,0)),
        (0.1,(151,230,255,255)),
        (0.2,(51,204,255,255)),
        (0.5,(0,153,255,255)),
        (1.0,(0,255,153,255)),
        (2.0,(51,204,102,255)),
        (3.0,(102,204,51,255)),
        (4.0,(102,255,0,255)),
        (5.0,(164,242,47,255)),
        (6.0,(183,207,14,255)),
        (7.0,(214,240,23,255)),
        (8.0,(204,153,0,255)),
        (9.0,(255,153,0,255)),
        (10.0,(255,153,102,255)),
        (15.0,(204,153,153,255)),
        (20.0,(204,102,51,255)),
        (25.0,(204,51,51,255)),
        (30.0,(255,13,13,255)),
        (40.0,(198,0,0,255)),
        (50.0,(128,0,0,255)),
        (60.0,(128,0,80,255)),
        (70.0,(160,0,119,255)),
        (100.0,(204,0,204,255)),
        (200.0,(255,0,255,255)),
    ],
    "pluie_cumul": [
        (0.0,(255,255,255,0)),
        (0.5,(151,230,255,255)),
        (1.0,(51,204,255,255)),
        (2.0,(0,153,255,255)),
        (5.0,(0,255,153,255)),
        (10.0,(51,204,102,255)),
        (20.0,(102,204,51,255)),
        (30.0,(102,255,0,255)),
        (40.0,(164,242,47,255)),
        (50.0,(183,207,14,255)),
        (60.0,(214,240,23,255)),
        (70.0,(204,153,0,255)),
        (80.0,(255,153,0,255)),
        (400.0,(198,0,0,255)),
        (500.0,(128,0,0,255)),
        (600.0,(128,0,80,255)),
        (700.0,(160,0,119,255)),
        (800.0,(204,0,204,255)),
    ],
    "reflectivite": [
        (5.0,(100,200,255,0)),
        (15.0,(0,0,255,255)),
        (25.0,(0,255,0,255)),
        (35.0,(255,255,0,255)),
        (45.0,(255,165,0,255)),
        (55.0,(255,0,0,255)),
        (65.0,(160,0,160,255)),
    ],
    "geopotentiel_500": [
        (492.0, (120, 0, 140, 255)),
        (496.0, (80, 0, 160, 255)),
        (500.0, (0, 0, 180, 255)),
        (504.0, (0, 40, 220, 255)),
        (508.0, (0, 100, 255, 255)),
        (512.0, (0, 160, 255, 255)),
        (516.0, (0, 210, 255, 255)),
        (520.0, (0, 255, 255, 255)),
        (524.0, (0, 255, 200, 255)),
        (528.0, (0, 255, 140, 255)),
        (532.0, (0, 255, 70, 255)),
        (536.0, (0, 255, 0, 255)),
        (540.0, (70, 255, 0, 255)),
        (544.0, (140, 255, 0, 255)),
        (548.0, (200, 255, 0, 255)),
        (552.0, (255, 255, 0, 255)),
        (556.0, (255, 230, 0, 255)),
        (560.0, (255, 200, 0, 255)),
        (564.0, (255, 170, 0, 255)),
        (568.0, (255, 140, 0, 255)),
        (572.0, (255, 110, 0, 255)),
        (576.0, (255, 80, 0, 255)),
        (580.0, (255, 50, 0, 255)),
        (584.0, (255, 20, 0, 255)),
        (588.0, (240, 0, 0, 255)),
        (592.0, (210, 0, 0, 255)),
        (596.0, (180, 0, 0, 255)),
        (600.0, (150, 0, 0, 255)),
        (604.0, (120, 0, 0, 255)),
        (608.0, (90, 0, 0, 255)),
        (612.0, (60, 0, 0, 255)),
    ],
    "graupel": [
        (0.5,(200,230,255,0)),
        (2.0,(100,200,255,255)),
        (5.0,(255,165,0,255)),
        (15.0,(200,0,200,255)),
    ],
    "vent": [
        (0.0,(255,255,255,0)),
        (5.0,(151,230,255,255)),
        (10.0,(51,204,255,255)),
        (15.0,(0,153,255,255)),
        (20.0,(0,255,153,255)),
        (25.0,(51,204,102,255)),
        (30.0,(102,204,51,255)),
        (35.0,(102,255,0,255)),
        (40.0,(164,242,47,255)),
        (45.0,(183,207,14,255)),
        (50.0,(214,240,23,255)),
        (55.0,(204,153,0,255)),
        (60.0,(255,153,0,255)),
        (65.0,(255,153,102,255)),
        (70.0,(204,153,153,255)),
        (75.0,(204,102,51,255)),
        (80.0,(204,51,51,255)),
        (85.0,(255,13,13,255)),
        (90.0,(198,0,0,255)),
        (95.0,(128,0,0,255)),
        (100.0,(128,0,80,255)),
        (105.0,(160,0,119,255)),
        (110.0,(204,0,204,255)),
        (115.0,(255,0,255,255)),
        (120.0,(255,64,255,255)),
        (125.0,(255,128,255,255)),
        (130.0,(255,160,255,255)),
        (140.0,(255,255,255,255)),
        (150.0,(227,227,227,255)),
        (160.0,(198,198,198,255)),
        (170.0,(170,170,170,255)),
        (180.0,(142,142,142,255)),
    ],
    "rafales": [
        (0.0,(255,255,255,0)),
        (5.0,(151,230,255,255)),
        (10.0,(51,204,255,255)),
        (15.0,(0,153,255,255)),
        (20.0,(0,255,153,255)),
        (25.0,(51,204,102,255)),
        (30.0,(102,204,51,255)),
        (35.0,(102,255,0,255)),
        (40.0,(164,242,47,255)),
        (45.0,(183,207,14,255)),
        (50.0,(214,240,23,255)),
        (55.0,(204,153,0,255)),
        (60.0,(255,153,0,255)),
        (65.0,(255,153,102,255)),
        (70.0,(204,153,153,255)),
        (75.0,(204,102,51,255)),
        (80.0,(204,51,51,255)),
        (85.0,(255,13,13,255)),
        (90.0,(198,0,0,255)),
        (100.0,(128,0,0,255)),
        (110.0,(128,0,80,255)),
        (120.0,(160,0,119,255)),
        (130.0,(204,0,204,255)),
        (140.0,(255,0,255,255)),
        (150.0,(255,64,255,255)),
        (160.0,(255,128,255,255)),
        (180.0,(255,160,255,255)),
        (200.0,(255,255,255,255)),
        (220.0,(227,227,227,255)),
        (240.0,(198,198,198,255)),
    ],
    "rafales_cumul": [
        (0.0,(255,255,255,0)),
        (5.0,(151,230,255,255)),
        (10.0,(51,204,255,255)),
        (15.0,(0,153,255,255)),
        (20.0,(0,255,153,255)),
        (25.0,(51,204,102,255)),
        (30.0,(102,204,51,255)),
        (35.0,(102,255,0,255)),
        (40.0,(164,242,47,255)),
        (45.0,(183,207,14,255)),
        (50.0,(214,240,23,255)),
        (55.0,(204,153,0,255)),
        (60.0,(255,153,0,255)),
        (65.0,(255,153,102,255)),
        (70.0,(204,153,153,255)),
        (75.0,(204,102,51,255)),
        (80.0,(204,51,51,255)),
        (85.0,(255,13,13,255)),
        (90.0,(198,0,0,255)),
        (100.0,(128,0,0,255)),
        (110.0,(128,0,80,255)),
        (120.0,(160,0,119,255)),
        (130.0,(204,0,204,255)),
        (140.0,(255,0,255,255)),
        (150.0,(255,64,255,255)),
        (160.0,(255,128,255,255)),
        (180.0,(255,160,255,255)),
        (200.0,(255,255,255,255)),
        (220.0,(227,227,227,255)),
        (240.0,(198,198,198,255)),
    ],
    "nebulosite": [
        (0.0,(0,0,0,0)),
        (30.0,(102,102,102,255)),
        (60.0,(136,136,136,255)),
        (90.0,(170,170,170,255)),
        (95.0,(204,204,204,255)),
        (99.0,(255,255,255,255)),
    ],
    "nuages_bas": [
        (0.0,(0,0,0,0)),
        (30.0,(102,102,102,255)),
        (60.0,(136,136,136,255)),
        (90.0,(170,170,170,255)),
        (95.0,(204,204,204,255)),
        (99.0,(255,255,255,255)),
    ],
    "nuages_moyens": [
        (0.0,(0,0,0,0)),
        (30.0,(102,102,102,255)),
        (60.0,(136,136,136,255)),
        (90.0,(170,170,170,255)),
        (95.0,(204,204,204,255)),
        (99.0,(255,255,255,255)),
    ],
    "nuages_eleves": [
        (0.0,(0,0,0,0)),
        (30.0,(102,102,102,255)),
        (60.0,(136,136,136,255)),
        (90.0,(170,170,170,255)),
        (95.0,(204,204,204,255)),
        (99.0,(255,255,255,255)),
    ],
    "humidite": [
        (0.0,(0,0,0,255)),
        (5.0,(12,12,12,255)),
        (10.0,(25,25,25,255)),
        (15.0,(38,38,38,255)),
        (20.0,(51,51,51,255)),
        (25.0,(63,63,63,255)),
        (30.0,(76,76,76,255)),
        (35.0,(89,89,89,255)),
        (40.0,(102,102,102,255)),
        (45.0,(114,114,114,255)),
        (50.0,(127,127,127,255)),
        (55.0,(140,140,140,255)),
        (60.0,(153,153,153,255)),
        (65.0,(165,165,165,255)),
        (70.0,(178,178,178,255)),
        (75.0,(191,191,191,255)),
        (80.0,(204,204,204,255)),
        (85.0,(216,216,216,255)),
        (90.0,(229,229,229,255)),
        (95.0,(242,242,242,255)),
        (100.0,(255,255,255,255)),
    ],
    "mucape": [
        (0.0,(0,51,102,0)),
        (100.0,(0,51,153,255)),
        (200.0,(0,0,204,255)),
        (300.0,(0,0,255,255)),
        (400.0,(0,102,255,255)),
        (500.0,(0,153,255,255)),
        (600.0,(51,204,255,255)),
        (700.0,(102,255,255,255)),
        (800.0,(102,255,153,255)),
        (900.0,(102,255,102,255)),
        (1000.0,(102,255,0,255)),
        (1100.0,(191,250,14,255)),
        (1200.0,(255,255,9,255)),
        (1300.0,(255,255,134,255)),
        (1400.0,(253,232,81,255)),
        (1500.0,(255,204,0,255)),
        (1600.0,(255,153,0,255)),
        (1700.0,(255,102,0,255)),
        (1800.0,(255,51,51,255)),
        (1900.0,(255,51,0,255)),
        (2000.0,(255,0,0,255)),
        (2100.0,(229,0,0,255)),
        (2200.0,(178,0,0,255)),
        (2300.0,(178,0,59,255)),
        (2400.0,(178,0,119,255)),
        (2600.0,(178,0,178,255)),
        (2800.0,(204,0,204,255)),
        (3000.0,(229,0,229,255)),
        (3200.0,(255,0,255,255)),
        (3400.0,(255,95,255,255)),
        (3600.0,(255,191,255,255)),
        (4000.0,(255,255,255,255)),
        (4500.0,(170,170,170,255)),
        (5000.0,(128,128,128,255)),
        (6000.0,(64,64,64,255)),
        (7000.0,(0,0,0,255)),
    ],
    "neige": [
        (0.0,(255,255,255,0)),
        (0.1,(151,230,255,255)),
        (0.2,(51,204,255,255)),
        (0.5,(0,153,255,255)),
        (1.0,(0,255,153,255)),
        (2.0,(51,204,102,255)),
        (3.0,(102,204,51,255)),
        (4.0,(102,255,0,255)),
        (5.0,(164,242,47,255)),
        (6.0,(183,207,14,255)),
        (7.0,(214,240,23,255)),
        (8.0,(204,153,0,255)),
        (9.0,(255,153,0,255)),
        (10.0,(255,153,102,255)),
        (15.0,(204,153,153,255)),
        (20.0,(204,102,51,255)),
        (25.0,(204,51,51,255)),
        (30.0,(255,13,13,255)),
        (40.0,(198,0,0,255)),
        (50.0,(128,0,0,255)),
        (60.0,(128,0,80,255)),
        (70.0,(160,0,119,255)),
        (80.0,(204,0,204,255)),
        (90.0,(255,0,255,255)),
        (100.0,(255,64,255,255)),
        (120.0,(255,128,255,255)),
        (140.0,(255,160,255,255)),
        (160.0,(192,192,192,255)),
        (180.0,(144,144,144,255)),
        (200.0,(96,96,96,255)),
        (250.0,(48,48,48,255)),
    ],
    "neige_au_sol": [
        (0.0,(255,255,255,0)),
        (0.1,(151,230,255,255)),
        (0.2,(51,204,255,255)),
        (0.5,(0,153,255,255)),
        (1.0,(0,255,153,255)),
        (2.0,(51,204,102,255)),
        (3.0,(102,204,51,255)),
        (4.0,(102,255,0,255)),
        (5.0,(164,242,47,255)),
        (6.0,(183,207,14,255)),
        (7.0,(214,240,23,255)),
        (8.0,(204,153,0,255)),
        (9.0,(255,153,0,255)),
        (10.0,(255,153,102,255)),
        (15.0,(204,153,153,255)),
        (20.0,(204,102,51,255)),
        (25.0,(204,51,51,255)),
        (30.0,(255,13,13,255)),
        (40.0,(198,0,0,255)),
        (50.0,(128,0,0,255)),
        (60.0,(128,0,80,255)),
        (70.0,(160,0,119,255)),
        (80.0,(204,0,204,255)),
        (90.0,(255,0,255,255)),
        (100.0,(255,64,255,255)),
        (120.0,(255,128,255,255)),
        (140.0,(255,160,255,255)),
        (160.0,(192,192,192,255)),
        (180.0,(144,144,144,255)),
        (200.0,(96,96,96,255)),
        (250.0,(48,48,48,255)),
    ],
    "equivalent_eau_neige": [
        (1.0,(200,230,255,0)),
        (5.0,(100,180,255,255)),
        (15.0,(50,100,200,255)),
        (30.0,(0,0,180,255)),
    ],
    "pression": [
        (960.0,(130,0,130,255)),
        (975.0,(0,0,200,255)),
        (985.0,(0,150,255,255)),
        (995.0,(0,200,150,255)),
        (1005.0,(0,180,0,255)),
        (1013.0,(200,200,200,255)),
        (1020.0,(255,220,100,255)),
        (1030.0,(255,150,0,255)),
        (1040.0,(200,80,0,255)),
    ],
    "pression_surface": [
        (800.0,(130,0,130,255)),
        (900.0,(0,0,200,255)),
        (960.0,(0,180,0,255)),
        (1013.0,(200,200,200,255)),
        (1040.0,(200,80,0,255)),
    ],
}


def apply_palette(data, palette):
    vs = np.array([s[0] for s in palette], dtype=np.float32)
    cs = np.array([list(s[1]) for s in palette], dtype=np.float32)
    rgba = np.zeros((*data.shape, 4), dtype=np.uint8)
    for i in range(len(vs) - 1):
        mask = (data >= vs[i]) & (data < vs[i+1])
        if not np.any(mask): continue
        t = (data[mask] - vs[i]) / (vs[i+1] - vs[i])
        for c in range(4):
            rgba[mask, c] = np.clip(cs[i,c] + t*(cs[i+1,c]-cs[i,c]), 0, 255).astype(np.uint8)
    rgba[data <= vs[0]] = cs[0].astype(np.uint8)
    rgba[data >= vs[-1]] = cs[-1].astype(np.uint8)
    return rgba

def _mercator_y(lat):
    """Y de Mercator (radians) pour une latitude en degrés."""
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def _inverse_mercator_y(y):
    """Latitude (degrés) depuis un Y de Mercator (radians)."""
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def _reproject_to_mercator(img):
    """Re-projette une image WMS EPSG:4326 (équirectangulaire) vers Mercator.

    Rééchelonnage vertical ligne par ligne (la longitude reste linéaire,
    seule la latitude devient Mercator). Nécessaire car le WMS ne fournit
    que du EPSG:4326, alors que le front-end attend du Mercator.
    """
    arr = np.array(img).astype(np.float32)
    h = arr.shape[0]
    north_y = _mercator_y(BOUNDS["north"])
    south_y = _mercator_y(BOUNDS["south"])
    # Latitude de chaque ligne Mercator (nord en haut)
    lat_tgt = _inverse_mercator_y(np.linspace(north_y, south_y, h))
    # Ligne source équirectangulaire correspondante (latitude linéaire)
    src_rows = (BOUNDS["north"] - lat_tgt) / (BOUNDS["north"] - BOUNDS["south"]) * (h - 1)
    src_rows = np.clip(src_rows, 0, h - 1)
    lo = np.floor(src_rows).astype(int)
    hi = np.ceil(src_rows).astype(int)
    frac = (src_rows - lo)[:, None, None]
    out = arr[lo] * (1 - frac) + arr[hi] * frac
    return Image.fromarray(out.astype(np.uint8))


def regrid(data, lats, lons):
    if lats[0] > lats[-1]:
        lats, data = lats[::-1], data[::-1, :]
    # Projection Mercator (comme la référence alertes-meteo.com) :
    # espacement vertical selon la latitude de Mercator, nord en haut.
    lat_out = _inverse_mercator_y(
        np.linspace(_mercator_y(BOUNDS["north"]), _mercator_y(BOUNDS["south"]), HEIGHT)
    )
    lon_out = np.linspace(BOUNDS["west"], BOUNDS["east"], WIDTH)
    lo, la  = np.meshgrid(lon_out, lat_out)
    pts = np.stack([la.ravel(), lo.ravel()], axis=-1)
    pts[:,0] = np.clip(pts[:,0], lats[0], lats[-1])
    pts[:,1] = np.clip(pts[:,1], lons[0], lons[-1])
    fn = RegularGridInterpolator((lats, lons), data, method='linear',
                                  bounds_error=False, fill_value=np.nan)
    return fn(pts).reshape(HEIGHT, WIDTH).astype(np.float32)

def save_webp(data, layer, dst):
    rgba = apply_palette(data, PALETTES.get(layer, PALETTES["temperature"]))
    Image.fromarray(rgba, "RGBA").save(dst, format="WEBP", quality=85, method=4)

def _cleanup_orphans(out_dir, steps):
    """Supprime les dalles .webp non référencées par le manifeste
    (restes d'un pas horaire précédent → évite doublons et trous)."""
    keep = {layer: set() for layer in LAYERS}
    for step in steps:
        for layer, rel in (step.get("files") or {}).items():
            keep.setdefault(layer, set()).add(os.path.basename(rel))
    for layer in LAYERS:
        layer_dir = os.path.join(out_dir, layer)
        if not os.path.isdir(layer_dir):
            continue
        for fn in os.listdir(layer_dir):
            if fn.endswith(".webp") and fn not in keep.get(layer, set()):
                try:
                    os.remove(os.path.join(layer_dir, fn))
                except OSError:
                    pass


def write_manifest(out_dir, steps, meta):
    layers_info = {l: {"label": LABELS[l][0], "unit": LABELS[l][1], "decimals": 1} for l in LAYERS}
    # Ne référencer que les tuiles réellement présentes sur disque
    # (sinon le front-end affiche des images cassées).
    model_root = os.path.dirname(out_dir)
    clean_steps = []
    for step in steps:
        files = {}
        for layer, rel in (step.get("files") or {}).items():
            if os.path.exists(os.path.join(model_root, rel.replace("/", os.sep))):
                files[layer] = rel
        clean_steps.append(dict(step, files=files))
    _cleanup_orphans(out_dir, clean_steps)
    m = {"schema_version": 6, "status": "ok",
         "model_name": meta["name"], "provider": meta["provider"],
         "resolution": meta["resolution"],
         "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "run_time": meta["run_time"], "bounds": BOUNDS,
         "overlay": "maps/frontieres.svg", "places": "maps/communes.json",
         "layers": layers_info, "steps": clean_steps}
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p

# ─── 1. AROME HD (48h) ────────────────────────────────────────────────────────
AROME_WMS_MAP = {
    "temperature":           ("TEMPERATURE__SPECIFIC_HEIGHT_LEVEL_ABOVE_GROUND", "T__HEIGHT__SHADING"),
    "temperature_ressentie": ("TEMPERATURE__SPECIFIC_HEIGHT_LEVEL_ABOVE_GROUND", "T__HEIGHT__SHADING"),
    "point_rosee":           ("DEW_POINT_TEMPERATURE__SPECIFIC_HEIGHT_LEVEL_ABOVE_GROUND", "TD__HEIGHT__SHADING"),
    "humidex":               ("TEMPERATURE__SPECIFIC_HEIGHT_LEVEL_ABOVE_GROUND", "T__HEIGHT__SHADING"),
    "pluie_1h":              ("TOTAL_WATER_PRECIPITATION__GROUND_OR_WATER_SURFACE", "EAU__GROUND__RADAR_SHADING"),
    "pluie_cumul":           ("TOTAL_PRECIPITATION__GROUND_OR_WATER_SURFACE", "PRECIP__GROUND__RADAR_SHADING"),
    "reflectivite":          ("REFLECTIVITY_MAX_DBZ__GROUND_OR_WATER_SURFACE", "RFLCTMAX_DBZ__GROUND__SHADING"),
    "graupel":               ("GRAUPEL__GROUND_OR_WATER_SURFACE", "GRAUPEL__GROUND__SHADING"),
    "vent":                  ("WIND_SPEED__SPECIFIC_HEIGHT_LEVEL_ABOVE_GROUND", "FF__HEIGHT__SHADING"),
    "rafales":               ("WIND_SPEED_GUST__SPECIFIC_HEIGHT_LEVEL_ABOVE_GROUND", "FF_RAF__HEIGHT__SHADING"),
    "rafales_cumul":         ("WIND_SPEED_GUST__SPECIFIC_HEIGHT_LEVEL_ABOVE_GROUND", "FF_RAF__HEIGHT__SHADING"),
    "nebulosite":            ("TOTAL_CLOUD_COVER__GROUND_OR_WATER_SURFACE", "NEBUL__GROUND__SHADING"),
    "nuages_bas":            ("LOW_CLOUD_COVER__GROUND_OR_WATER_SURFACE", "NEBBAS__GROUND__SHADING"),
    "nuages_moyens":         ("MEDIUM_CLOUD_COVER__GROUND_OR_WATER_SURFACE", "NEBMOY__GROUND__SHADING"),
    "nuages_eleves":         ("HIGH_CLOUD_COVER__GROUND_OR_WATER_SURFACE", "NEBHAU__GROUND__SHADING"),
    "humidite":              ("RELATIVE_HUMIDITY__SPECIFIC_HEIGHT_LEVEL_ABOVE_GROUND", "HU__HEIGHT__SHADING"),
    "mucape":                ("CONVECTIVE_AVAILABLE_POTENTIAL_ENERGY__GROUND_OR_WATER_SURFACE", "CAPE_INS__GROUND__SHADING"),
    "neige":                 ("TOTAL_SNOW_PRECIPITATION__GROUND_OR_WATER_SURFACE", "NEIGE__GROUND__RADAR_SHADING"),
    "neige_au_sol":          ("TOTAL_SNOW_PRECIPITATION__GROUND_OR_WATER_SURFACE", "NEIGE__GROUND__RADAR_SHADING"),
    "equivalent_eau_neige":  ("WATER_EQUIVALENT_ACCUMULATED_SNOW__GROUND_OR_WATER_SURFACE", "RESR_NEIGE__GROUND__NO_SHADING"),
    "pression":              ("PRESSURE__MEAN_SEA_LEVEL", "P__SEA__NO_SHADING"),
    "pression_surface":      ("PRESSURE__GROUND_OR_WATER_SURFACE", "P__GROUND__NO_SHADING"),
}
AROME_WMS = "https://public-api.meteofrance.fr/public/arome/1.0/wms/MF-NWP-HIGHRES-AROME-001-FRANCE-WMS/GetMap"
# Endpoint ARPEGE Europe 5 km. Surchargable via ARPEGE_WMS_URL si l'URL officielle
# évolue (convention Météo-France : MF-NWP-GLOBAL-ARPEGE-001-EURAT5-WMS).
ARPEGE_WMS = os.environ.get(
    "ARPEGE_WMS_URL",
    "https://public-api.meteofrance.fr/public/arpege/1.0/wms/MF-NWP-GLOBAL-ARPEGE-001-EURAT5-WMS/GetMap"
)

# Limiteur de débit Météo-France (50 requêtes/minute, sans burst).
# Espace uniformément les requêtes (≈48 req/min) pour éviter les 429/502
# déclenchés par le burst initial des workers en parallèle.
_mf_rate_lock = threading.Lock()
_mf_rate_last = 0.0


def _mf_rate_wait():
    global _mf_rate_last
    with _mf_rate_lock:
        now = time.time()
        if _mf_rate_last and now - _mf_rate_last < 1.25:
            time.sleep(1.25 - (now - _mf_rate_last))
        _mf_rate_last = time.time()


def _fetch_mf_tile(session, token, wms_url, wms_layer, style, time_str, ref_str, dst):
    headers = {"apikey": token, "Authorization": "Bearer " + token,
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
               "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
               "Accept-Language": "fr-FR,fr;q=0.9"}
    params = {"service": "WMS", "version": "1.3.0", "request": "GetMap",
              "layers": wms_layer, "styles": style,
              "crs": "EPSG:4326", "bbox": "38.0,-12.0,53.0,16.0",
              "width": str(WIDTH), "height": str(HEIGHT),
              "format": "image/png", "transparent": "TRUE",
              "time": time_str, "reference_time": ref_str}
    # Réessai jusqu'à 3 fois pour récupérer les erreurs 502/429 ponctuelles.
    for attempt in range(3):
        try:
            _mf_rate_wait()
            r = session.get(wms_url, params=params, headers=headers, timeout=30, verify=False)
            if r.status_code == 200 and len(r.content) > 1000:
                img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                # Le WMS renvoie de l'EPSG:4326 (équirectangulaire) ; on le
                # re-projette en Mercator pour correspondre au front-end.
                img = _reproject_to_mercator(img)
                img.save(dst, format="WEBP", quality=85, method=4)
                return True
            elif r.status_code != 200:
                print("  [WMS] %s -> HTTP %d (essai %d/3)" % (wms_layer, r.status_code, attempt + 1), flush=True)
        except Exception as e:
            print("  [WMS] %s -> erreur (essai %d/3): %s" % (wms_layer, attempt + 1, e), flush=True)
        if attempt < 2:
            time.sleep(1.2)
    return False

def _fetch_arome_tile(session, token, wms_layer, style, time_str, ref_str, dst):
    return _fetch_mf_tile(session, token, AROME_WMS, wms_layer, style, time_str, ref_str, dst)

def compute_physical_cumulative_gusts(model_dir, lead_hours):
    rf_dir = os.path.join(model_dir, "rafales")
    cumul_dir = ensure_dir(os.path.join(model_dir, "rafales_cumul"))
    max_score = None
    max_rgba = None
    
    def _wind_score(r, g, b, a):
        score = np.zeros_like(r, dtype=float)
        valid = a > 30
        m_mag = valid & (r > 110) & (b > 110) & (g < 120)
        score[m_mag] = 110.0 + (r[m_mag].astype(float) + b[m_mag].astype(float)) / 10.0
        m_viol = valid & (b > 150) & (r > 40) & (g < 130) & ~m_mag
        score[m_viol] = 90.0 + (b[m_viol].astype(float) - g[m_viol].astype(float)) / 5.0
        m_bleu = valid & (b > 130) & (r < 90) & (g < 150) & ~m_mag & ~m_viol
        score[m_bleu] = 70.0 + (b[m_bleu].astype(float) - r[m_bleu].astype(float)) / 5.0
        m_cyan = valid & (b > 120) & (g > 120) & (r < 110) & ~m_mag & ~m_viol & ~m_bleu
        score[m_cyan] = 50.0 + (g[m_cyan].astype(float) + b[m_cyan].astype(float)) / 10.0
        m_vert = valid & (g > 120) & (b < 140) & ~m_mag & ~m_viol & ~m_bleu & ~m_cyan
        score[m_vert] = 30.0 + (255.0 - r[m_vert].astype(float)) / 8.0
        m_faible = valid & (score == 0)
        score[m_faible] = 10.0
        return score

    for lh in lead_hours:
        rf_file = os.path.join(rf_dir, "%03d.webp" % lh)
        if os.path.exists(rf_file):
            arr = np.array(Image.open(rf_file).convert("RGBA"))
            curr_score = _wind_score(arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3])
            if max_score is None:
                max_score = curr_score.copy()
                max_rgba = arr.copy()
            else:
                mask = curr_score > max_score
                max_score[mask] = curr_score[mask]
                max_rgba[mask] = arr[mask]
            dst_c = os.path.join(cumul_dir, "%03d.webp" % lh)
            Image.fromarray(max_rgba, "RGBA").save(dst_c, format="WEBP", quality=85)

def run_arome(max_hours=51):
    token = get_mf_token()
    if not token:
        print("ERROR AROME: token Meteo-France introuvable (env METEOFRANCE_TOKEN)")
        return
    print(f"AROME HD (1.3 km) - H+00 a H+51 (pas de 1h)...")
    out_dir   = ensure_dir(os.path.join(OUTPUT_DIR, "maps"))
    arome_dir = ensure_dir(os.path.join(OUTPUT_DIR, "arome", "maps"))

    now   = datetime.datetime.now(datetime.timezone.utc)
    run_h = (now.hour // 6) * 6
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    if (now - run_dt).total_seconds() < 5400:
        run_dt -= datetime.timedelta(hours=6)
    ref_str = run_dt.strftime("%Y-%m-%dT%H:00:00Z")

    lead_hours = list(range(0, max_hours + 1))
    session = requests.Session()
    steps, futs = [], []

    with ThreadPoolExecutor(max_workers=8) as ex:
        for lh in lead_hours:
            vt = run_dt + datetime.timedelta(hours=lh)
            time_str = vt.strftime("%Y-%m-%dT%H:00:00Z")
            step = {"lead_hour": lh, "valid_time": vt.isoformat(), "files": {}}
            for layer in LAYERS:
                wl, st = AROME_WMS_MAP.get(layer, AROME_WMS_MAP["temperature"])
                dst1 = os.path.join(out_dir,   layer, "%03d.webp" % lh)
                dst2 = os.path.join(arome_dir, layer, "%03d.webp" % lh)
                ensure_dir(os.path.dirname(dst1)); ensure_dir(os.path.dirname(dst2))
                step["files"][layer] = "maps/%s/%03d.webp" % (layer, lh)
                futs.append(ex.submit(_fetch_arome_tile, session, token, wl, st, time_str, ref_str, dst1))
            steps.append(step)
        total = len(futs)
        for i, _ in enumerate(as_completed(futs), 1):
            if i % 50 == 0 or i == total:
                print("  AROME %d/%d (%d%%)" % (i, total, i*100//total))

    # Calcul physique des rafales cumulées
    compute_physical_cumulative_gusts(out_dir, lead_hours)
    compute_physical_cumulative_gusts(arome_dir, lead_hours)

    for layer in LAYERS:
        for lh in lead_hours:
            src = os.path.join(out_dir, layer, "%03d.webp" % lh)
            dst = os.path.join(arome_dir, layer, "%03d.webp" % lh)
            # Toujours écraser pour que output/arome reçoive bien les nouvelles tuiles
            if os.path.exists(src):
                shutil.copy2(src, dst)

    meta = {"name": "AROME HD (1,3 km)", "provider": "Meteo-France",
            "resolution": "1,3 km (0.01 deg)", "run_time": run_dt.isoformat()}
    write_manifest(out_dir, steps, meta)
    write_manifest(arome_dir, steps, meta)
    print("  OK AROME 48h termine")

# ─── ARPEGE Europe (4 Jours / 102h) ──────────────────────────────────────────
def run_arpege(max_hours=114):
    token = get_mf_token()
    if not token:
        print("ERROR ARPEGE: token Meteo-France introuvable (env METEOFRANCE_TOKEN)")
        return
    print("ARPEGE Europe (5 km) - H+00 a H+114...")
    arpege_dir = ensure_dir(os.path.join(OUTPUT_DIR, "arpege", "maps"))

    now = datetime.datetime.now(datetime.timezone.utc)
    run_h = (now.hour // 6) * 6
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    if (now - run_dt).total_seconds() < 5400:
        run_dt -= datetime.timedelta(hours=6)
    ref_str = run_dt.strftime("%Y-%m-%dT%H:00:00Z")

    # ARPEGE = pas de 1h jusqu'à H+48, puis pas de 3h jusqu'à H+114
    lead_hours = list(range(0, 49)) + list(range(51, max_hours + 1, 3))
    session = requests.Session()
    steps = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = []
        for lh in lead_hours:
            vt = run_dt + datetime.timedelta(hours=lh)
            time_str = vt.strftime("%Y-%m-%dT%H:00:00Z")
            step = {"lead_hour": lh, "valid_time": vt.isoformat(), "files": {}}
            for layer in LAYERS:
                wl, st = AROME_WMS_MAP.get(layer, AROME_WMS_MAP["temperature"])
                dst = os.path.join(arpege_dir, layer, "%03d.webp" % lh)
                ensure_dir(os.path.dirname(dst))
                step["files"][layer] = "maps/%s/%03d.webp" % (layer, lh)
                futs.append(ex.submit(_fetch_mf_tile, session, token, ARPEGE_WMS, wl, st, time_str, ref_str, dst))
            steps.append(step)
        total = len(futs)
        for i, _ in enumerate(as_completed(futs), 1):
            if i % 50 == 0 or i == total:
                print("  ARPEGE %d/%d (%d%%)" % (i, total, i * 100 // total))

    compute_physical_cumulative_gusts(arpege_dir, lead_hours)

    meta = {"name": "ARPEGE Europe (5 km)", "provider": "Meteo-France",
            "resolution": "5 km (0.05 deg)", "run_time": run_dt.isoformat()}
    write_manifest(arpege_dir, steps, meta)
    print("  OK ARPEGE 4 Jours termine")

# ─── 2. GFS MONDE (16 Jours / 384h) ──────────────────────────────────────────
def run_gfs(max_hours=384):
    try:
        import cfgrib
    except ImportError:
        print("ERROR GFS: cfgrib non installe")
        return
    print("GFS (13 km) - 16 Jours (H+384)...")
    gfs_dir = ensure_dir(os.path.join(OUTPUT_DIR, "gfs", "maps"))
    now = datetime.datetime.now(datetime.timezone.utc)
    run_h = (now.hour // 6) * 6
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    if (now - run_dt).total_seconds() < 14400:
        run_dt -= datetime.timedelta(hours=6)
    day_str = run_dt.strftime("%Y%m%d")
    h_str = "%02d" % run_dt.hour

    # Pas de 3h jusqu'à 240h, puis pas de 6h jusqu'à 384h
    lead_hours = list(range(0, 241, 3)) + list(range(246, max_hours + 1, 6))

    gfs_req_vars = ["TMP","DPT","UGRD","VGRD","GUST","APCP","CAPE","SNOD","PRMSL","PRES","RH","TCDC","LCDC","MCDC","HCDC"]
    gfs_layer_var = {"temperature":"TMP","temperature_ressentie":"TMP","point_rosee":"DPT",
                     "humidex":"TMP","pluie_1h":"APCP","pluie_cumul":"APCP","reflectivite":"APCP",
                     "graupel":"APCP","vent":"UGRD","rafales":"GUST","rafales_cumul":"GUST",
                     "nebulosite":"TCDC","nuages_bas":"LCDC","nuages_moyens":"MCDC","nuages_eleves":"HCDC",
                     "mucape":"CAPE","neige":"SNOD","neige_au_sol":"SNOD","equivalent_eau_neige":"SNOD",
                     "pression":"PRMSL","pression_surface":"PRES","humidite":"RH"}
    steps = []
    max_gust_field = None

    for lh in lead_hours:
        vt = run_dt + datetime.timedelta(hours=lh)
        fhh = "%03d" % lh
        step = {"lead_hour": lh, "valid_time": vt.isoformat(), "files": {}}
        print("  [GFS] H+%03d" % lh, end="", flush=True)

        params = {
            "dir": "/gfs.%s/%s/atmos" % (day_str, h_str),
            "file": "gfs.t%sz.pgrb2.0p25.f%s" % (h_str, fhh),
            "subregion": "", "leftlon": "-15", "rightlon": "20",
            "toplat": "57", "bottomlat": "35",
        }
        for v in gfs_req_vars:
            params["var_" + v] = "on"
        params.update({"lev_2_m_above_ground": "on", "lev_10_m_above_ground": "on",
                        "lev_surface": "on", "lev_mean_sea_level": "on", "lev_entire_atmosphere": "on"})

        grib_bytes = None
        try:
            r = requests.get("https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl",
                             params=params, timeout=45, verify=False)
            if r.status_code == 200 and len(r.content) > 500:
                grib_bytes = r.content
        except Exception:
            pass

        cached = {}
        if grib_bytes:
            with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as tf:
                tf.write(grib_bytes); tmp = tf.name
            try:
                for ds in cfgrib.open_datasets(tmp):
                    for v in ds.data_vars:
                        vu = v.upper()
                        if vu not in cached:
                            cached[vu] = (ds[v].values, ds.latitude.values, ds.longitude.values)
            except Exception:
                pass
            finally:
                try: os.remove(tmp)
                except: pass

        for layer in LAYERS:
            dst = os.path.join(gfs_dir, layer, "%03d.webp" % lh)
            ensure_dir(os.path.dirname(dst))
            step["files"][layer] = "maps/%s/%03d.webp" % (layer, lh)

            # Vent moyen = module du vecteur (U, V) → km/h (jamais le seul U !)
            if layer == "vent":
                if "UGRD" in cached and "VGRD" in cached:
                    u, la, lo = cached["UGRD"]
                    v = cached["VGRD"][0]
                    spd = np.sqrt(u.astype(np.float32) ** 2 + v.astype(np.float32) ** 2) * 3.6
                    save_webp(regrid(spd, la, lo), layer, dst)
                continue

            key = gfs_layer_var.get(layer, "TMP")
            if key in cached:
                d, la, lo = cached[key]
                if layer in ("temperature","temperature_ressentie","humidex") and d.max() > 200: d = d - 273.15
                elif layer == "point_rosee" and d.max() > 200: d = d - 273.15
                elif layer in ("pression","pression_surface") and d.max() > 10000: d = d / 100.0
                elif layer in ("rafales","rafales_cumul") and d.max() < 200: d = d * 3.6
                rf = regrid(d, la, lo)
                if layer == "rafales_cumul":
                    max_gust_field = rf.copy() if max_gust_field is None else np.maximum(max_gust_field, rf)
                    save_webp(max_gust_field, layer, dst)
                else:
                    save_webp(rf, layer, dst)

        print(" OK")
        steps.append(step)

    write_manifest(gfs_dir, steps, {"name": "GFS Monde (13 km)", "provider": "NOAA Etats-Unis",
                                    "resolution": "13 km (0.25 deg)", "run_time": run_dt.isoformat()})
    print("  OK GFS 16 Jours termine")

# ─── 3. ECMWF IFS (10 Jours / 240h) ──────────────────────────────────────────
def run_ecmwf(max_hours=240):
    try:
        from ecmwf.opendata import Client
        import cfgrib
    except ImportError:
        print("ERROR ECMWF: pip install ecmwf-opendata cfgrib eccodes")
        return
    print("ECMWF IFS (9 km) - 10 Jours (H+240)...")
    ecmwf_dir = ensure_dir(os.path.join(OUTPUT_DIR, "ecmwf", "maps"))
    now = datetime.datetime.now(datetime.timezone.utc)
    run_h = 0 if now.hour < 12 else 12
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    if (now - run_dt).total_seconds() < 18000:
        run_dt -= datetime.timedelta(hours=12)

    # ECMWF open data = pas de 3h jusqu'à H+144, puis pas de 6h jusqu'à H+240
    lead_hours = list(range(0, 145, 3)) + list(range(150, max_hours + 1, 6))
    client = Client("ecmwf", beta=True)
    ecmwf_param_map = {"temperature":"2t","temperature_ressentie":"2t","point_rosee":"2d",
                       "humidex":"2t","pluie_1h":"tp","pluie_cumul":"tp","reflectivite":"tp",
                       "graupel":"tp","vent":"10u","rafales":"10u","rafales_cumul":"10u",
                       "nebulosite":"tcc","nuages_bas":"tcc","nuages_moyens":"tcc","nuages_eleves":"tcc",
                       "mucape":"cape","neige":"tp","neige_au_sol":"tp","equivalent_eau_neige":"tp",
                       "pression":"msl","pression_surface":"sp","humidite":"2d"}
    steps = []
    max_gust_field = None

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_grib = os.path.join(tmp_dir, "ifs.grib2")
        try:
            client.retrieve(step=lead_hours,
                            param=["2t","2d","10u","10v","msl","sp","tp","cape","tcc"],
                            target=tmp_grib,
                            date=run_dt.strftime("%Y%m%d"), time=run_h)
        except Exception as e:
            print("  ECMWF download error:", e)
            return

        try:
            all_ds = cfgrib.open_datasets(tmp_grib)
        except Exception as e:
            print("  ECMWF decode error:", e)
            return

        for lh in lead_hours:
            vt = run_dt + datetime.timedelta(hours=lh)
            step = {"lead_hour": lh, "valid_time": vt.isoformat(), "files": {}}
            print("  [ECMWF] H+%03d" % lh, end="", flush=True)
            for layer in LAYERS:
                dst = os.path.join(ecmwf_dir, layer, "%03d.webp" % lh)
                ensure_dir(os.path.dirname(dst))
                step["files"][layer] = "maps/%s/%03d.webp" % (layer, lh)

                # Vent moyen = module (10u, 10v) → km/h (jamais le seul 10u !)
                if layer == "vent":
                    handled = False
                    for ds in all_ds:
                        if "10u" not in ds.data_vars or "10v" not in ds.data_vars:
                            continue
                        try:
                            sub = ds.sel(step=np.timedelta64(lh, "h"), method="nearest")
                        except Exception:
                            sub = ds.isel(step=0) if "step" in ds.dims else ds
                        u = sub["10u"].values
                        v = sub["10v"].values
                        spd = np.sqrt(u.astype(np.float32) ** 2 + v.astype(np.float32) ** 2) * 3.6
                        save_webp(regrid(spd, ds.latitude.values, ds.longitude.values), layer, dst)
                        handled = True
                        break
                    # Fallback documenté si 10u/10v ne sont pas co-localisés dans un même dataset.
                    if not handled:
                        for ds in all_ds:
                            if "10u" not in ds.data_vars:
                                continue
                            try:
                                sub = ds.sel(step=np.timedelta64(lh, "h"), method="nearest")
                            except Exception:
                                sub = ds.isel(step=0) if "step" in ds.dims else ds
                            d = sub["10u"].values * 3.6
                            save_webp(regrid(d, ds.latitude.values, ds.longitude.values), layer, dst)
                            break
                    continue

                param = ecmwf_param_map.get(layer, "2t")
                for ds in all_ds:
                    if param not in ds.data_vars: continue
                    try:
                        sub = ds.sel(step=np.timedelta64(lh,"h"), method="nearest")
                    except Exception:
                        sub = ds.isel(step=0) if "step" in ds.dims else ds
                    d = sub[param].values
                    la, lo = ds.latitude.values, ds.longitude.values
                    if layer in ("temperature","temperature_ressentie","humidex") and d.max() > 200: d = d - 273.15
                    elif layer == "point_rosee" and d.max() > 200: d = d - 273.15
                    elif layer in ("pression","pression_surface") and d.max() > 10000: d = d / 100.0
                    elif layer in ("rafales","rafales_cumul"): d = d * 3.6
                    elif layer in ("nebulosite","nuages_bas","nuages_moyens","nuages_eleves") and d.max() <= 1.0: d = d * 100.0
                    rf = regrid(d, la, lo)
                    if layer == "rafales_cumul":
                        max_gust_field = rf.copy() if max_gust_field is None else np.maximum(max_gust_field, rf)
                        save_webp(max_gust_field, layer, dst)
                    else:
                        save_webp(rf, layer, dst)
                    break
            print(" OK")
            steps.append(step)

    write_manifest(ecmwf_dir, steps, {"name": "ECMWF IFS (9 km)", "provider": "CEPMMT Europe",
                                      "resolution": "9 km (0.1 deg)", "run_time": run_dt.isoformat()})
    print("  OK ECMWF 10 Jours termine")

# ─── 4. ICON-EU (3 Jours / 78h) ──────────────────────────────────────────────
ICON_VARS = {
    "temperature": "t_2m", "temperature_ressentie": "t_2m",
    "point_rosee": "td_2m", "humidex": "t_2m",
    "pluie_1h": "tot_prec", "pluie_cumul": "tot_prec",
    "reflectivite": "tot_prec", "graupel": "graupel_gsp",
    "vent": "u_10m", "rafales": "vmax_10m", "rafales_cumul": "vmax_10m",
    "nebulosite": "clct", "nuages_bas": "clcl", "nuages_moyens": "clcm", "nuages_eleves": "clch",
    "mucape": "cape_con", "neige": "snow_gsp", "neige_au_sol": "h_snow", "equivalent_eau_neige": "snow_gsp",
    "pression": "pmsl", "pression_surface": "ps", "humidite": "relhum_2m",
}

def run_icon(max_hours=120):
    try:
        import cfgrib
    except ImportError:
        print("ERROR ICON: cfgrib non installe")
        return
    print("ICON-EU (7 km) - H+00 a H+120...")
    icon_dir = ensure_dir(os.path.join(OUTPUT_DIR, "icon", "maps"))
    now = datetime.datetime.now(datetime.timezone.utc)
    run_h = (now.hour // 6) * 6
    run_dt = now.replace(hour=run_h, minute=0, second=0, microsecond=0)
    if (now - run_dt).total_seconds() < 7200:
        run_dt -= datetime.timedelta(hours=6)
    day_str = run_dt.strftime("%Y%m%d")
    h_str = "%02d" % run_dt.hour

    # ICON-EU = pas de 1h jusqu'à H+48, puis pas de 3h jusqu'à H+120
    lead_hours = list(range(0, 49)) + list(range(51, max_hours + 1, 3))
    steps = []
    max_gust_field = None
    for lh in lead_hours:
        vt = run_dt + datetime.timedelta(hours=lh)
        step = {"lead_hour": lh, "valid_time": vt.isoformat(), "files": {}}
        print("  [ICON] H+%02d" % lh, end="", flush=True)
        cached = {}
        for layer in LAYERS:
            var = ICON_VARS.get(layer, "t_2m")
            dst = os.path.join(icon_dir, layer, "%03d.webp" % lh)
            ensure_dir(os.path.dirname(dst))
            step["files"][layer] = "maps/%s/%03d.webp" % (layer, lh)
            if var not in cached:
                fn = "icon-eu_europe_regular-lat-lon_single-level_%s%s_%03d_%s.grib2.bz2" % (day_str, h_str, lh, var.upper())
                url = "https://opendata.dwd.de/weather/nwp/icon-eu/grib/%s/%s/%s" % (h_str, var, fn)
                try:
                    r = requests.get(url, timeout=30, verify=False)
                    if r.status_code == 200:
                        raw = bz2.decompress(r.content)
                        with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as tf:
                            tf.write(raw); tmp = tf.name
                        ds = cfgrib.open_dataset(tmp)
                        vk = list(ds.data_vars)[0]
                        d = ds[vk].values; la = ds.latitude.values; lo = ds.longitude.values
                        os.remove(tmp)
                        if layer in ("temperature","temperature_ressentie","point_rosee","humidex") and d.max() > 100:
                            d = d - 273.15
                        elif layer in ("pression","pression_surface") and d.max() > 10000:
                            d = d / 100.0
                        elif layer in ("vent","rafales","rafales_cumul") and d.max() < 200:
                            d = d * 3.6
                        cached[var] = regrid(d, la, lo)
                    else:
                        cached[var] = None
                except Exception:
                    cached[var] = None
            f = cached.get(var)
            if f is not None:
                if layer == "rafales_cumul":
                    max_gust_field = f.copy() if max_gust_field is None else np.maximum(max_gust_field, f)
                    save_webp(max_gust_field, layer, dst)
                else:
                    save_webp(f, layer, dst)
        print(" OK")
        steps.append(step)

    write_manifest(icon_dir, steps, {"name": "ICON-EU (7 km)", "provider": "DWD Allemagne",
                                     "resolution": "7 km (0.0625 deg)", "run_time": run_dt.isoformat()})
    print("  OK ICON-EU 3 Jours termine")

RUNNERS = {"arome": run_arome, "arpege": run_arpege, "icon": run_icon, "gfs": run_gfs, "ecmwf": run_ecmwf}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["arome","arpege","icon","gfs","ecmwf","all"], default="all")
    args = parser.parse_args()
    targets = list(RUNNERS.keys()) if args.model == "all" else [args.model]
    for model in targets:
        try:
            RUNNERS[model]()
        except Exception as exc:
            print("WARNING %s failed: %s" % (model.upper(), exc))
    print("Pipeline termine.")
