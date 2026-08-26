#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
domains.py — SOURCE UNIQUE des domaines géographiques et grilles Mercator.
===========================================================================
Tous les modèles (GFS Europe, GFS France, ARPEGE Europe) et le générateur de
fonds utilisent ces domaines. Un seul endroit à modifier.
"""
import numpy as np

# Domaine Europe : projection conique conforme de Lambert (style officiel Météociel GFS/ARPEGE Europe)
# Domaine France : projection Mercator identique au site AROME (métropole + Corse + pays voisins)
DOMAINS = {
    "europe": {
        "projection": "lambert",
        "lat1": 30.0, "lat2": 60.0, "lat0": 50.0, "lon0": -5.0,
        "x_min": -0.5902, "x_max": 0.5902,
        "y_min": -0.4200, "y_max": 0.4600,
        "south": 18.0, "west": -60.0, "north": 75.0, "east": 50.0,
        "width": 2200, "height": 1640,
        "label": "Europe",
    },

    "france": {
        "projection": "mercator",
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


def lambert_conformal_direct(lats, lons, lat1=35.0, lat2=65.0, lat0=50.0, lon0=-5.0):
    r_lat1 = np.radians(lat1)
    r_lat2 = np.radians(lat2)
    r_lat0 = np.radians(lat0)
    r_lon0 = np.radians(lon0)
    n = np.log(np.cos(r_lat1) / np.cos(r_lat2)) / np.log(
        np.tan(np.pi / 4.0 + r_lat2 / 2.0) / np.tan(np.pi / 4.0 + r_lat1 / 2.0)
    )
    F = (np.cos(r_lat1) * (np.tan(np.pi / 4.0 + r_lat1 / 2.0) ** n)) / n
    rho0 = F / (np.tan(np.pi / 4.0 + r_lat0 / 2.0) ** n)
    
    r_lats = np.radians(lats)
    r_lons = np.radians(lons)
    rho = F / (np.tan(np.pi / 4.0 + r_lats / 2.0) ** n)
    theta = n * (r_lons - r_lon0)
    x = rho * np.sin(theta)
    y = rho0 - rho * np.cos(theta)
    return x, y


def lambert_conformal_inverse(xs, ys, lat1=35.0, lat2=65.0, lat0=50.0, lon0=-5.0):
    r_lat1 = np.radians(lat1)
    r_lat2 = np.radians(lat2)
    r_lat0 = np.radians(lat0)
    r_lon0 = np.radians(lon0)
    n = np.log(np.cos(r_lat1) / np.cos(r_lat2)) / np.log(
        np.tan(np.pi / 4.0 + r_lat2 / 2.0) / np.tan(np.pi / 4.0 + r_lat1 / 2.0)
    )
    F = (np.cos(r_lat1) * (np.tan(np.pi / 4.0 + r_lat1 / 2.0) ** n)) / n
    rho0 = F / (np.tan(np.pi / 4.0 + r_lat0 / 2.0) ** n)
    
    rho = np.sign(n) * np.sqrt(xs ** 2 + (rho0 - ys) ** 2)
    theta = np.arctan2(xs, rho0 - ys)
    lons = np.degrees(r_lon0 + theta / n)
    t = (F / rho) ** (1.0 / n)
    lats = np.degrees(2.0 * np.arctan(t) - np.pi / 2.0)
    return lats, lons


class Domain:
    """Grille (2200×1640) précalculée pour un domaine."""

    def __init__(self, name):
        if name not in DOMAINS:
            raise ValueError("Domaine inconnu: %s" % name)
        d = DOMAINS[name]
        self.name = name
        self.projection = d.get("projection", "mercator")
        self.width, self.height = d["width"], d["height"]
        self.south, self.west = d["south"], d["west"]
        self.north, self.east = d["north"], d["east"]
        self.bounds = {"south": self.south, "west": self.west,
                       "north": self.north, "east": self.east,
                       "projection": self.projection}

        if self.projection == "lambert":
            self.lat1, self.lat2 = d["lat1"], d["lat2"]
            self.lat0, self.lon0 = d["lat0"], d["lon0"]
            self.x_min, self.x_max = d["x_min"], d["x_max"]
            self.y_min, self.y_max = d["y_min"], d["y_max"]
            xs = np.linspace(self.x_min, self.x_max, self.width, dtype=np.float64)
            ys = np.linspace(self.y_max, self.y_min, self.height, dtype=np.float64)
            XX, YY = np.meshgrid(xs, ys)
            self.lats, self.lons = lambert_conformal_inverse(
                XX, YY, self.lat1, self.lat2, self.lat0, self.lon0
            )
        else:
            n_y = mercator_y(self.north)
            s_y = mercator_y(self.south)
            lons = np.linspace(self.west, self.east, self.width, dtype=np.float32)
            ys = np.linspace(n_y, s_y, self.height, dtype=np.float32)
            lats = inverse_mercator_y(ys).astype(np.float32)
            self.lons, self.lats = np.meshgrid(lons, lats)

    def project(self, lon, lat):
        """Projette (lon, lat) en pixels (x, y) sur le canvas (2200×1640)."""
        if self.projection == "lambert":
            x, y = lambert_conformal_direct(
                lat, lon, self.lat1, self.lat2, self.lat0, self.lon0
            )
            u = (x - self.x_min) / (self.x_max - self.x_min)
            v = (self.y_max - y) / (self.y_max - self.y_min)
        else:
            ny = mercator_y(self.north)
            sy = mercator_y(self.south)
            u = (lon - self.west) / (self.east - self.west)
            v = (ny - mercator_y(lat)) / (ny - sy)
        return (u * (self.width - 1), v * (self.height - 1))

    def regrid(self, data, src_lats, src_lons):
        """Ré-échantillonne un champ natif (lat/lon) sur la grille du domaine."""
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
        
        # Clamping des coordonnées aux limites de la grille source pour une couverture 100% sans bordures grises
        pts_lat = np.clip(self.lats.ravel(), src_lats[0], src_lats[-1])
        pts_lon = np.clip(self.lons.ravel(), src_lons[0], src_lons[-1])
        pts = np.column_stack((pts_lat, pts_lon))
        
        interp = RegularGridInterpolator(
            (src_lats, src_lons), data, method="linear",
            bounds_error=False, fill_value=None)
        return interp(pts).reshape((self.height, self.width)).astype(np.float32)


# Instances partagées
EUROPE = Domain("europe")
FRANCE = Domain("france")
