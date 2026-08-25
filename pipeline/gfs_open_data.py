#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline GFS 0.25 Europe & France (NOAA / Open Data)
====================================================
Génère les cartes 2D HD (2200x1640 Mercator) pour chaque paramètre météo GFS,
et compile le manifest index.json pour le visualiseur cartographique.
"""

import os
import sys
import json
import datetime
import requests
import numpy as np
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "gfs", "maps")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BOUNDS = {
    "north": 65.0,
    "south": 32.0,
    "west": -18.0,
    "east": 32.0,
}
WIDTH, HEIGHT = 2200, 1640

def main():
    print("🚀 Pipeline GFS Europe & France initialisé !")
    print(f"📂 Répertoire de sortie: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
