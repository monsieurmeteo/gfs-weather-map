#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
domains.py — SOURCE UNIQUE des domaines géographiques et grilles Mercator.
===========================================================================
Tous les modèles (GFS Europe, GFS France, ARPEGE Europe) et le générateur de
fonds utilisent ces domaines. Un seul endroit à modifier.
"""
import numpy as np

# Domaine Europe : synoptique Météociel (Groenland, Islande, Europe, Maghreb)
# Domaine France : métropole + Corse (comme AROME / Météo-Climat Pro)
DOMAINS = {
    "europe": {
        "south": 30.0, "west": -30.0, "north": 68.0, "east": 35.0,
        "width": 2200, "height": 1640,
        "label": "Europe",
    },
    "france": {
        "south": 39.5, "west": -8.5, "north": 52.5, "east": 13.5,
        "width": 2200, "height": 1640,
        "label": "France",
    },
}


def mercator_y(lat):
    """Y de Mercator (radians) pour une latitude en degrés (bornée ±85°)."""
    lat = np.clip(np.asarray(lat, dtype=np.float64), -85.0, 85.0)
    return np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0))


def inverse_mercator_y(y):
    """Latitude (degrés) depuis un Y de Mercator (radians)."""
    return np.degrees(2.0 * np.arctan(np.exp(y)) - np.pi / 2.0)


class Domain:
    """Grille Mercator précalculée pour un domaine (2200×1640 par défaut)."""

    def __init__(self, name):
        if name not in DOMAINS:
            raise ValueError("Domaine inconnu: %s (disponibles: %s)" % (
                name, ", ".join(DOMAINS)))
        d = DOMAINS[name]
        self.name = name
        self.south, self.west = d["south"], d["west"]
        self.north, self.east = d["north"], d["east"]
        self.width, self.height = d["width"], d["height"]
        self.bounds = {"south": self.south, "west": self.west,
                       "north": self.north, "east": self.east}

        n_y = mercator_y(self.north)
        s_y = mercator_y(self.south)
        lons = np.linspace(self.west, self.east, self.width, dtype=np.float32)
        ys = np.linspace(n_y, s_y, self.height, dtype=np.float32)
        lats = inverse_mercator_y(ys).astype(np.float32)
        self.lons, self.lats = np.meshgrid(lons, lats)

    def regrid(self, data, src_lats, src_lons):
        """Ré-échantillonne un champ natif (lat/lon) sur la grille Mercator.

        data   : array 2D (ny, nx) dans l'ordre latitudes croissantes (sud→nord).
        src_lats, src_lons : vecteurs 1D associés au champ natif.
        """
        from scipy.interpolate import RegularGridInterpolator

        data = np.asarray(data, dtype=np.float32)
        src_lats = np.asarray(src_lats, dtype=np.float64)
        src_lons = np.asarray(src_lons, dtype=np.float64)
        if src_lats[0] > src_lats[-1]:
            src_lats = src_lats[::-1]
            data = data[::-1, :]
        if src_lons[0] > src_lons[-1]:
            src_lons = src_lons[::-1]
            data = data[:, ::-1]
        interp = RegularGridInterpolator(
            (src_lats, src_lons), data, method="linear",
            bounds_error=False, fill_value=np.nan)
        pts = np.column_stack((self.lats.ravel(), self.lons.ravel()))
        return interp(pts).reshape((self.height, self.width)).astype(np.float32)


# Instances partagées
EUROPE = Domain("europe")
FRANCE = Domain("france")
