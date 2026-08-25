#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gribscan.py — Extraction sélective de messages GRIB2 via requêtes HTTP Range
=============================================================================
Lit les en-têtes (sections 0-4) de chaque message GRIB2 et ne télécharge que
les messages utiles. Pour ARPEGE EURAT01 (SP1/SP2/IP1), le volume passe de
~3,7 Go à ~0,5 Go par run.

Paramètres Météo-France (discipline 0) constatés sur les produits ARPEGE 0,1° :
  (0,0,2)  2t        → T2M      (0,2,2)@10 10u → U10
  (0,1,1)@2 2r       → RH       (0,2,3)@10 10v → V10
  (0,1,52)@0 tp      → APCP     (0,2,23)@10 max_10efg → GUST
  (0,1,60)@0 sd      → SNOD     (0,3,1)@0   prmsl → PRMSL
  (0,1,64)@0 (local) → CAPE     (0,3,4)@500 z    → HGT (Z500)
  (0,6,3/4/5)@0 lcc/mcc/hcc → nuages
"""
import os
import struct
import tempfile
import time

import numpy as np
import requests

from eccodes import (codes_grib_new_from_file, codes_get,
                     codes_get_array, codes_release)

# Octets d'en-tête suffisants pour lire les sections 0-4 d'un message
HEADER_FETCH = 2064


def msg_length(sec0):
    """Longueur totale du message (section 0, octets 8-15)."""
    return struct.unpack(">Q", sec0[8:16])[0]


def _level(stype, sscale, sval):
    if stype == 100:            # isobarique — scaledValue en PASCALS
        return (sval // (10 ** sscale)) // 100
    if stype == 103:            # hauteur au-dessus du sol (m) : 2t, 10u…
        return sval // (10 ** sscale)
    if stype in (1, 101, 255):  # sol / niveau moyen de la mer
        return 0
    return -1


def parse_product(b):
    """Sections 0-4 → dict(cat, num, level, start, end, tpl) ou None."""
    if len(b) < 16 or b[:4] != b"GRIB":
        return None
    pos = 16
    try:
        # Section 1 (Identification) — obligatoire
        if len(b) < pos + 5:
            return None
        slen = struct.unpack(">I", b[pos:pos + 4])[0]
        if b[pos + 4] != 1 or len(b) < pos + slen:
            return None
        pos += slen
        # Sections 2 (facultative), 3 (grille) puis 4 (produit)
        while True:
            if len(b) < pos + 5:
                return None
            slen = struct.unpack(">I", b[pos:pos + 4])[0]
            sec = b[pos + 4]
            if sec == 4:
                break
            if sec not in (2, 3) or len(b) < pos + slen:
                return None
            pos += slen
        if len(b) < pos + 9:
            return None
        tpl = struct.unpack(">H", b[pos + 7:pos + 9])[0]
        t = pos + 9
        if tpl == 0:            # Analyse / prévision instantanée
            cat, num = b[t], b[t + 1]
            ft = struct.unpack(">i", b[t + 9:t + 13])[0]
            stype, sscale = b[t + 13], b[t + 14]
            sval = struct.unpack(">i", b[t + 15:t + 19])[0]
            return dict(cat=cat, num=num, level=_level(stype, sscale, sval),
                        start=ft, end=ft, tpl=tpl)
        if tpl == 8:            # Accumulation / moyenne (layout local MF)
            cat, num = b[t], b[t + 1]
            ft = struct.unpack(">i", b[t + 9:t + 13])[0]
            # Layout local Météo-France : surfaces AVANT les infos statistiques
            stype, sscale = b[t + 13], b[t + 14]
            sval = struct.unpack(">i", b[t + 15:t + 19])[0]
            return dict(cat=cat, num=num, level=_level(stype, sscale, sval),
                        start=ft, end=ft, tpl=tpl)
    except Exception:
        return None
    return None


def key_of(cat, num, level):
    """(parameterCategory, parameterNumber, level) → clé canonique ou None."""
    if (cat, num) == (0, 0) and level == 2:
        return "T2M"
    if (cat, num) == (1, 1) and level == 2:
        return "RH"
    if (cat, num) == (2, 2) and level == 10:
        return "U10"
    if (cat, num) == (2, 3) and level == 10:
        return "V10"
    if (cat, num) == (2, 23) and level == 10:
        return "GUST"
    if (cat, num) == (3, 1) and level == 0:
        return "PRMSL"
    if (cat, num) == (1, 52) and level == 0:
        return "APCP"
    if (cat, num) == (1, 60) and level == 0:
        return "SNOD"
    if (cat, num) == (1, 64) and level == 0:
        return "CAPE"
    if (cat, num) == (3, 4) and level == 500:
        return "HGT"
    if (cat, num) == (6, 3) and level == 0:
        return "LCC"
    if (cat, num) == (6, 4) and level == 0:
        return "MCC"
    if (cat, num) == (6, 5) and level == 0:
        return "HCC"
    return None


def _range(session, url, offset, length, timeout=90, retries=4):
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url,
                            headers={"Range": "bytes=%d-%d"
                                     % (offset, offset + length - 1)},
                            timeout=timeout)
            if r.status_code == 206 and len(r.content) == length:
                return r.content
            last = "HTTP %s" % r.status_code
        except Exception as e:
            last = "%s" % e
        time.sleep(1.5 * attempt)
    raise IOError("Range %d+%d échoué (%s)" % (offset, length, last))


def scan(url, size, max_lead=102, session=None, progress=None):
    """Scanne un fichier GRIB2.

    Retourne (found, candidates, n_msgs) :
      found      : {lead: {KEY: (offset, longueur, cat, num, level)}}
                   pour les champs INSTANTANÉS (template 0), lead validé.
      candidates : [(offset, longueur, cat, num, level, key)] pour les
                   ACCUMULATIONS (template 8, layout local Météo-France) —
                   l'échéance de fin n'est validée qu'au décodage (endStep).
    """
    s = session or requests.Session()
    found = {}
    candidates = []
    cursor = 0
    n_msgs = 0
    while cursor < size:
        head = _range(s, url, cursor, min(HEADER_FETCH, size - cursor))
        if len(head) < 16 or head[:4] != b"GRIB":
            raise IOError("En-tête GRIB introuvable à l'offset %d" % cursor)
        length = msg_length(head)
        info = parse_product(head[:min(HEADER_FETCH, length)])
        n_msgs += 1
        if info is not None:
            key = key_of(info["cat"], info["num"], info["level"])
            if key is not None:
                if info["tpl"] == 8:
                    candidates.append((cursor, length, info["cat"],
                                       info["num"], info["level"], key))
                else:
                    lead = info["start"]
                    if 0 <= lead <= max_lead and lead % 3 == 0:
                        found.setdefault(lead, {})[key] = (
                            cursor, length, info["cat"], info["num"],
                            info["level"])
        cursor += length
        if progress is not None and n_msgs % 200 == 0:
            progress(n_msgs, cursor, size)
    return found, candidates, n_msgs


def fetch_message(session, url, offset, length):
    return _range(session, url, offset, length)


def _decode_handle(gid, expect=None):
    """Décode un message GRIB déjà ouvert.

    Retourne (values 2D, lat 1D, lon 1D, end_step).
    """
    if expect is not None:
        cat = int(codes_get(gid, "parameterCategory"))
        num = int(codes_get(gid, "parameterNumber"))
        lev = int(codes_get(gid, "level"))
        if (cat, num, lev) != expect:
            raise ValueError("Attendu %s, lu (%d,%d,%d)"
                             % (expect, cat, num, lev))
    ni = int(codes_get(gid, "Ni"))
    nj = int(codes_get(gid, "Nj"))
    vals = np.asarray(codes_get_array(gid, "values"),
                      dtype=np.float32).reshape(nj, ni)
    lat2 = np.asarray(codes_get_array(gid, "latitudes"),
                      dtype=np.float64).reshape(nj, ni)
    lon2 = np.asarray(codes_get_array(gid, "longitudes"),
                      dtype=np.float64).reshape(nj, ni)
    end_step = int(codes_get(gid, "endStep"))
    return vals, lat2[:, 0], lon2[0, :], end_step


def _decode_blobs(blobs, log):
    """blobs : [(lead, key, expect, data)] → {lead: {KEY: (vals, lat, lon)}}."""
    if not blobs:
        return {}
    tmp = os.path.join(tempfile.gettempdir(), "gribscan_sel.grib2")
    with open(tmp, "wb") as f:
        for _, _, _, data in blobs:
            f.write(data)
    out = {}
    try:
        with open(tmp, "rb") as f:
            for lead, key, expect, _ in blobs:
                gid = codes_grib_new_from_file(f)
                if gid is None:
                    break
                try:
                    vals, lat, lon, _end = _decode_handle(gid, expect)
                except Exception as e:
                    log("  !! %s décodage échoué (%s)" % (key, e))
                    continue
                finally:
                    codes_release(gid)
                out.setdefault(lead, {})[key] = (vals, lat, lon)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return out


def fetch_block(session, url, size, max_lead, log=None):
    """Extraction sélective d'un bloc : {lead: {KEY: (values, lat, lon)}}."""
    log = log or (lambda *a: None)
    found, candidates, n_msgs = scan(url, size, max_lead=max_lead,
                                     session=session)
    log("  scan %d messages → %d échéances instantanées, %d accumulations"
        % (n_msgs, len(found), len(candidates)))
    # Messages instantanés (lead déjà validé par l'en-tête)
    blobs = []
    for lead in sorted(found):
        for key, (off, length, cat, num, lev) in found[lead].items():
            data = fetch_message(session, url, off, length)
            blobs.append((lead, key, (cat, num, lev), data))
    out = _decode_blobs(blobs, log)
    # Accumulations : échéance validée au décodage (endStep % 3 == 0)
    cblobs = []
    for off, length, cat, num, lev, key in candidates:
        data = fetch_message(session, url, off, length)
        cblobs.append((0, key, (cat, num, lev), data))
    if cblobs:
        tmp = os.path.join(tempfile.gettempdir(), "gribscan_acc.grib2")
        with open(tmp, "wb") as f:
            for _, _, _, data in cblobs:
                f.write(data)
        try:
            with open(tmp, "rb") as f:
                for _, key, expect, _ in cblobs:
                    gid = codes_grib_new_from_file(f)
                    if gid is None:
                        break
                    try:
                        vals, lat, lon, end_step = _decode_handle(gid, expect)
                    except Exception as e:
                        log("  !! %s décodage échoué (%s)" % (key, e))
                        continue
                    finally:
                        codes_release(gid)
                    if not (0 <= end_step <= max_lead and end_step % 3 == 0):
                        continue
                    out.setdefault(end_step, {})[key] = (vals, lat, lon)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    if not out:
        raise IOError("Aucun champ utile décodé (bloc %s)" % url)
    return out
