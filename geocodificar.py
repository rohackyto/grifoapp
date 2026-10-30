"""Convierte direcciones y cruces de calles ("Av. X con Av. Y, distrito") en coordenadas.

Usa Nominatim (OpenStreetMap). Para un cruce pide el trazado de cada calle y toma el
punto donde ambas líneas quedan más cerca, porque Nominatim no entiende intersecciones.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

import logica

URL = "https://nominatim.openstreetmap.org"
AGENTE = "GrifoApp/1.0 (app personal; precios Osinergmin)"
SEPARADOR_CRUCE = re.compile(r"\s+(?:esquina\s+con|esq\.?|con|y|&|/)\s+", re.IGNORECASE)
MAX_DISTANCIA_CRUCE_KM = 0.15
_ultima = 0.0


def _pedir(ruta: str, **params) -> list | dict:
    global _ultima
    espera = 1.05 - (time.time() - _ultima)   # máximo 1 consulta por segundo
    if espera > 0:
        time.sleep(espera)
    params.update(format="json", countrycodes="pe", **{"accept-language": "es"})
    req = urllib.request.Request(f"{URL}/{ruta}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=20) as resp:
        _ultima = time.time()
        return json.loads(resp.read())


def _puntos(resultado: dict) -> list[tuple[float, float]]:
    geo = resultado.get("geojson") or {}
    coords = geo.get("coordinates", [])
    if geo.get("type") == "LineString":
        lineas = [coords]
    elif geo.get("type") == "MultiLineString":
        lineas = coords
    else:
        return [(float(resultado["lat"]), float(resultado["lon"]))]
    return [(lat, lon) for linea in lineas for lon, lat in linea]


def _nombre(resultado: dict) -> str:
    """Nombre corto y legible: 'Avenida Larco 345 · Miraflores'."""
    d = resultado.get("address", {})
    calle = " ".join(x for x in (d.get("road"), d.get("house_number")) if x)
    lugar = calle or resultado.get("name") or resultado.get("display_name", "").split(",")[0]
    zona = d.get("city_district") or d.get("suburb") or d.get("city") or d.get("town")
    return f"{lugar} · {zona}" if zona and zona != lugar else lugar


def buscar_cruce(calle_a: str, calle_b: str, zona: str) -> tuple[str, float, float] | None:
    trazos = []
    for calle in (calle_a, calle_b):
        q = ", ".join(x for x in (calle, zona, "Perú") if x)
        res = _pedir("search", q=q, limit=40, polygon_geojson=1)  # una calle = muchos tramos
        trazos.append([p for r in res for p in _puntos(r)])
    if not all(trazos):
        return None
    mejor = min(((logica.distancia_km(*a, *b), a, b) for a in trazos[0] for b in trazos[1]),
                key=lambda t: t[0])
    distancia, a, b = mejor
    if distancia > MAX_DISTANCIA_CRUCE_KM:
        return None  # las calles no se cruzan (o no son las que buscaba el usuario)
    nombre = f"{calle_a.strip()} con {calle_b.strip()}" + (f" · {zona.strip()}" if zona else "")
    return nombre, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def buscar(texto: str) -> tuple[str, float, float] | None:
    """Acepta 'Av. Larco 345, Miraflores' o 'Av. Benavides con Av. Larco, Miraflores'."""
    calles, _, zona = texto.partition(",")
    partes = SEPARADOR_CRUCE.split(calles, maxsplit=1)
    if len(partes) == 2:
        cruce = buscar_cruce(partes[0], partes[1], zona)
        if cruce:
            return cruce
    res = _pedir("search", q=f"{texto}, Perú", limit=1, addressdetails=1)
    if not res:
        return None
    return _nombre(res[0]), float(res[0]["lat"]), float(res[0]["lon"])


def nombre_de_lugar(lat: float, lon: float) -> str:
    res = _pedir("reverse", lat=lat, lon=lon, zoom=17, addressdetails=1)
    return _nombre(res) if isinstance(res, dict) and "lat" in res else "Mi ubicación"
