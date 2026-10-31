"""Construye la base de grifos con precio y coordenadas a partir de fuentes públicas.

1. Precios: Excel oficial "Últimos precios registrados EVPC" (Osinergmin, SCOP/PRICE).
2. Coordenadas: capa ArcGIS pública de Osinergmin "12_BD_Dash_HL_GrifosEESS_gdb",
   unida por código Osinergmin. Sin coordenada -> centro del distrito (ubicación aproximada).
3. Marca: estación OpenStreetMap (amenity=fuel) a menos de 100 m; si no hay,
   se deduce de la razón social; si tampoco, "Otra".
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
import urllib.parse
import urllib.request
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

import logica

URL_PRECIOS = ("https://www.osinergmin.gob.pe/seccion/centro_documental/hidrocarburos/SCOP/"
               "SCOP-DOCS/{anio}/Registro-precios/Ultimos-Precios-Registrados-EVPC.xlsx")
URL_ARCGIS = ("https://services5.arcgis.com/oAvs2fapEemUpOTy/arcgis/rest/services/"
              "12_BD_Dash_HL_GrifosEESS_gdb/FeatureServer/0/query")
URL_OVERPASS = "https://overpass-api.de/api/interpreter"
AGENTE = "GrifoApp/1.0 (app personal; precios Osinergmin)"

# Producto del Excel -> categoría que se muestra en la app (solo productos en galones)
PRODUCTOS = {
    "GASOHOL REGULAR": "REGULAR", "GASOLINA REGULAR": "REGULAR",
    "GASOHOL PREMIUM": "PREMIUM", "GASOLINA PREMIUM": "PREMIUM",
    "DIESEL B5 S-50 UV": "DIESEL", "DIESEL B5 UV": "DIESEL",
    "GLP - G": "GLP",
}

# Patrones de razón social de operadores conocidos de cada marca
MARCAS_POR_RAZON = [
    (r"\bCOESTI\b|\bPRIMAX\b", "Primax"),
    (r"\bREPSOL\b", "Repsol"),
    (r"PERUANA DE ESTACIONES DE SERVICIOS|\bPECSA\b", "Pecsa"),
    (r"PETROLEOS DEL PERU|PETROPERU", "Petroperú"),
]

# Valores de brand/name en OpenStreetMap -> nombre de marca normalizado
MARCAS_OSM = {
    "primax": "Primax", "repsol": "Repsol", "pecsa": "Pecsa", "petroperu": "Petroperú",
    "mobil": "Mobil", "shell": "Shell", "energigas": "Energigas", "jw oliver": "J.W. Oliver",
    "j.w. oliver": "J.W. Oliver", "puma": "Puma", "petro peru": "Petroperú",
}


URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"
CACHE_CENTROS = Path(__file__).parent / "data" / "centros_distrito.json"

# El Excel de precios y la capa ArcGIS no siempre nombran igual las provincias y distritos
ALIAS_PROVINCIA = {"PROV. CONST. DEL CALLAO": "CALLAO"}
ALIAS_DISTRITO = {("LIMA", "ATE"): "ATE VITARTE"}


def _descargar(url: str, datos: bytes | None = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, data=datos, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


# ---------- 1. Precios ----------
def descargar_precios(anio: int | None = None) -> pd.DataFrame:
    anio = anio or logica.ahora().year
    contenido = _descargar(URL_PRECIOS.format(anio=anio))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # el Excel no trae estilo por defecto
        df = pd.read_excel(io.BytesIO(contenido), dtype=str)
    df["categoria"] = df["PRODUCTO"].str.strip().str.upper().map(PRODUCTOS)
    df["precio"] = pd.to_numeric(df["PRECIO_VENTA"], errors="coerce")
    df = df[(df["categoria"].notna()) & (df["precio"] > 0)
            & (df["PRODUCTO_ACTIVO"] == "SI") & (df["ULT_PRECIO_DIF_CERO"] == "SI")]
    df["fecha"] = pd.to_datetime(df["FCHA_REGISTRO"], errors="coerce")
    # Si un local tiene dos productos de la misma categoría (p. ej. gasohol y gasolina
    # regular), nos quedamos con el más barato.
    df = df.sort_values("precio").drop_duplicates(["CODIGO_OSINERG", "categoria"])
    return df


# ---------- 2. Coordenadas ----------
def descargar_coordenadas() -> pd.DataFrame:
    filas, offset = [], 0
    while True:
        params = urllib.parse.urlencode({
            "where": "1=1", "outFields": "COD_OSINERGMIN,RAZON_SOCIAL,DIRECCION,DISTRITO,"
                                         "PROVINCIA,LATITUD,LONGITUD",
            "returnGeometry": "false", "resultOffset": offset, "resultRecordCount": 2000,
            "orderByFields": "OBJECTID", "f": "json",
        })
        datos = json.loads(_descargar(f"{URL_ARCGIS}?{params}"))
        lote = [f["attributes"] for f in datos.get("features", [])]
        filas.extend(lote)
        if not datos.get("exceededTransferLimit") or not lote:
            break
        offset += len(lote)
    df = pd.DataFrame(filas).dropna(subset=["LATITUD", "LONGITUD"])
    return df.drop_duplicates("COD_OSINERGMIN")


# ---------- 3. Marcas desde OpenStreetMap ----------
def descargar_marcas_osm() -> list[tuple[float, float, str]]:
    consulta = ('[out:json][timeout:120];area["ISO3166-1"="PE"][admin_level=2]->.pe;'
                'nwr["amenity"="fuel"](area.pe);out center tags;')
    datos = json.loads(_descargar(URL_OVERPASS, urllib.parse.urlencode({"data": consulta}).encode(),
                                  timeout=180))
    puntos = []
    for el in datos.get("elements", []):
        etiquetas = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        marca = _marca_de_texto(etiquetas.get("brand", "")) or _marca_de_texto(etiquetas.get("name", ""))
        if lat and lon and marca:
            puntos.append((lat, lon, marca))
    return puntos


def _marca_de_texto(texto: str) -> str | None:
    t = _sin_tildes(texto)
    for clave, marca in MARCAS_OSM.items():
        if clave in t:
            return marca
    return None


def marca_por_razon(razon: str) -> str | None:
    t = _sin_tildes(razon).upper()
    for patron, marca in MARCAS_POR_RAZON:
        if re.search(patron, t):
            return marca
    return None


def _marca_cercana(lat: float, lon: float, celdas: dict, radio_km: float = 0.1) -> str | None:
    clave = (round(lat, 2), round(lon, 2))
    mejor, mejor_d = None, radio_km
    for dlat in (-1, 0, 1):
        for dlon in (-1, 0, 1):
            for plat, plon, marca in celdas.get((round(clave[0] + dlat / 100, 2),
                                                 round(clave[1] + dlon / 100, 2)), []):
                d = logica.distancia_km(lat, lon, plat, plon)
                if d < mejor_d:
                    mejor, mejor_d = marca, d
    return mejor


# ---------- Centro de distrito ----------
def _clave_distrito(provincia: str, distrito: str) -> tuple[str, str]:
    provincia = ALIAS_PROVINCIA.get(provincia, provincia)
    return provincia, ALIAS_DISTRITO.get((provincia, distrito), distrito)


def centros_distrito(coords: pd.DataFrame, faltantes: set[tuple[str, str, str]]) -> dict:
    """Centro de cada distrito: promedio de sus grifos con coordenada; si no tiene ninguno,
    se geocodifica el nombre del distrito con Nominatim (1 consulta/s, con caché en disco)."""
    centros = {_clave_distrito(p, d): (la, lo) for (p, d), (la, lo) in
               coords.groupby(["PROVINCIA", "DISTRITO"])[["LATITUD", "LONGITUD"]].mean().iterrows()}
    cache = json.loads(CACHE_CENTROS.read_text(encoding="utf-8")) if CACHE_CENTROS.exists() else {}
    nuevos = False
    for departamento, provincia, distrito in sorted(faltantes):
        clave = _clave_distrito(provincia, distrito)
        texto = f"{clave[1]}|{clave[0]}|{departamento}"
        if clave in centros:
            continue
        if texto not in cache:
            params = urllib.parse.urlencode({"q": f"{clave[1]}, {clave[0]}, {departamento}, Perú",
                                             "format": "json", "limit": 1, "countrycodes": "pe"})
            try:
                res = json.loads(_descargar(f"{URL_NOMINATIM}?{params}", timeout=30))
                cache[texto] = [float(res[0]["lat"]), float(res[0]["lon"])] if res else None
            except Exception:
                continue  # se reintentará en la próxima construcción
            nuevos = True
            time.sleep(1.1)  # política de uso de Nominatim
        if cache.get(texto):
            centros[clave] = tuple(cache[texto])
    if nuevos:
        CACHE_CENTROS.parent.mkdir(exist_ok=True)
        CACHE_CENTROS.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    return centros


# ---------- Unión ----------
def construir(con_osm: bool = True) -> tuple[list[logica.Estacion], dict]:
    precios = descargar_precios()
    coords = descargar_coordenadas()
    try:
        osm = descargar_marcas_osm() if con_osm else []
    except Exception:
        osm = []  # la marca es un extra: si Overpass falla seguimos sin ella
    celdas: dict = {}
    for p in osm:
        celdas.setdefault((round(p[0], 2), round(p[1], 2)), []).append(p)

    df = precios.merge(coords, how="left", left_on="CODIGO_OSINERG", right_on="COD_OSINERGMIN",
                       suffixes=("", "_geo"))
    sin_coord = df[df["LATITUD"].isna()]
    centros = centros_distrito(coords, set(zip(sin_coord["DEPARTAMENTO"], sin_coord["PROVINCIA"],
                                               sin_coord["DISTRITO"])))
    estaciones, sin_ubicar = [], 0
    for fila in df.itertuples(index=False):
        aprox = pd.isna(fila.LATITUD)
        if aprox:
            centro = centros.get(_clave_distrito(fila.PROVINCIA, fila.DISTRITO))
            if not centro:
                sin_ubicar += 1
                continue
            lat, lon = centro
        else:
            lat, lon = fila.LATITUD, fila.LONGITUD
        # el Excel trae caracteres dañados (�); la capa ArcGIS tiene el texto correcto
        razon = fila.RAZON_SOCIAL if isinstance(fila.RAZON_SOCIAL, str) else fila.RAZON
        direccion = fila.DIRECCION_geo if isinstance(fila.DIRECCION_geo, str) else fila.DIRECCION
        marca = (None if aprox else _marca_cercana(lat, lon, celdas)) or marca_por_razon(razon) or "Otra"
        estaciones.append(logica.Estacion(
            nombre=" ".join(razon.split()).title(), marca=marca,
            direccion=" ".join(direccion.split()).title(), distrito=fila.DISTRITO.strip().title(), lat=float(lat), lon=float(lon),
            producto=fila.categoria, precio=float(fila.precio), ubicacion_aprox=bool(aprox),
            codigo=fila.CODIGO_OSINERG,
            fecha=fila.fecha.to_pydatetime() if pd.notna(fila.fecha) else None,
        ))
    meta = {
        "generado": logica.ahora(),
        "corte": precios["fecha"].max().to_pydatetime(),
        "grifos": precios["CODIGO_OSINERG"].nunique(),
        "con_coordenada": int(df.drop_duplicates("CODIGO_OSINERG")["LATITUD"].notna().sum()),
        "sin_ubicar": sin_ubicar,
        "estaciones_osm": len(osm),
    }
    return estaciones, meta


def guardar_csv(estaciones: list[logica.Estacion], ruta) -> None:
    pd.DataFrame([vars(e) for e in estaciones]).to_csv(ruta, index=False, encoding="utf-8")


if __name__ == "__main__":
    import sys
    from collections import Counter
    est, meta = construir()
    print(meta)
    print(Counter(e.marca for e in est).most_common(12))
    if len(sys.argv) > 1:
        guardar_csv(est, sys.argv[1])
        Path(sys.argv[1]).with_name("meta.json").write_text(json.dumps(meta, default=str), encoding="utf-8")
        print("guardado en", sys.argv[1])
