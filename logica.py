"""Lógica de GrifoApp sin dependencias externas (se puede probar sin Streamlit)."""
from __future__ import annotations

import csv
import io
import math
import random
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

COSTO_POR_KM = 0.65      # S/ que cuesta recorrer 1 km (combustible + desgaste aprox.)
GALONES_TANQUE = 14      # tamaño de tanque usado para repartir el costo del viaje

# Nombres de columna aceptados -> nombre interno. Permite usar el CSV de
# datos abiertos u otra fuente sin reescribir el código.
ALIAS_COLUMNAS = {
    "nombre": "nombre", "razon_social": "nombre", "establecimiento": "nombre",
    "marca": "marca", "bandera": "marca",
    "direccion": "direccion",
    "distrito": "distrito",
    "lat": "lat", "latitud": "lat",
    "lon": "lon", "lng": "lon", "longitud": "lon",
    "producto": "producto", "combustible": "producto",
    "precio": "precio", "precio_venta": "precio",
    "ubicacion_aprox": "ubicacion_aprox",
    "codigo": "codigo", "codigo_osinerg": "codigo", "cod_osinergmin": "codigo",
    "fecha": "fecha", "fcha_registro": "fecha",
}


@dataclass
class Estacion:
    nombre: str
    marca: str
    direccion: str
    distrito: str
    lat: float
    lon: float
    producto: str
    precio: float
    ubicacion_aprox: bool = False
    codigo: str = ""
    fecha: datetime | None = None   # cuándo el grifo registró ese precio


@dataclass
class Resultado:
    estacion: Estacion
    distancia_km: float
    descuento: float
    precio_final: float
    costo_llegar: float
    precio_efectivo: float          # precio_final + costo del viaje repartido por galón
    extras: dict = field(default_factory=dict)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return texto.strip().lower().replace(" ", "_")


def leer_csv(contenido: str) -> list[Estacion]:
    """Lee un CSV con columnas compatibles con ALIAS_COLUMNAS."""
    lector = csv.DictReader(io.StringIO(contenido))
    estaciones = []
    for fila in lector:
        datos = {}
        for col, valor in fila.items():
            interno = ALIAS_COLUMNAS.get(_normalizar(col or ""))
            if interno:
                datos[interno] = (valor or "").strip()
        try:
            precio = float(datos["precio"].replace(",", "."))
        except (KeyError, ValueError):
            continue
        lat, lon = datos.get("lat"), datos.get("lon")
        if not lat or not lon:
            continue  # sin coordenadas no podemos medir distancia
        estaciones.append(Estacion(
            nombre=datos.get("nombre", "Sin nombre"),
            marca=datos.get("marca", "Independiente") or "Independiente",
            direccion=datos.get("direccion", ""),
            distrito=datos.get("distrito", ""),
            lat=float(lat), lon=float(lon),
            producto=datos.get("producto", "").upper(),
            precio=precio,
            ubicacion_aprox=datos.get("ubicacion_aprox", "").lower() in ("true", "1", "si"),
            codigo=datos.get("codigo", ""),
            fecha=_leer_fecha(datos.get("fecha", "")),
        ))
    return estaciones


def _leer_fecha(texto: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def datos_demo(semilla: int = 7) -> list[Estacion]:
    """Estaciones ficticias alrededor de Lima para probar la app sin datos reales."""
    rnd = random.Random(semilla)
    marcas = {"Marca A": 0.0, "Marca B": 0.35, "Marca C": -0.2, "Independiente": -0.5}
    distritos = [
        ("Miraflores", -12.1211, -77.0297), ("Barranco", -12.1497, -77.0213),
        ("Santiago de Surco", -12.1350, -76.9920), ("San Isidro", -12.0975, -77.0365),
        ("Lince", -12.0840, -77.0360), ("La Molina", -12.0870, -76.9300),
        ("San Borja", -12.1080, -76.9990), ("Chorrillos", -12.1700, -77.0150),
    ]
    base = {"REGULAR": 17.6, "PREMIUM": 21.9, "DIESEL": 18.4}
    estaciones = []
    for i in range(60):
        distrito, lat, lon = rnd.choice(distritos)
        marca = rnd.choice(list(marcas))
        aprox = rnd.random() < 0.1
        e_lat = lat if aprox else lat + rnd.uniform(-0.02, 0.02)
        e_lon = lon if aprox else lon + rnd.uniform(-0.02, 0.02)
        for producto, precio in base.items():
            estaciones.append(Estacion(
                nombre=f"{marca} {distrito} #{i + 1}", marca=marca,
                direccion=f"Dirección demo {i + 1}", distrito=distrito,
                lat=e_lat, lon=e_lon, producto=producto,
                precio=round(precio + marcas[marca] + rnd.uniform(-0.6, 0.9), 2),
                ubicacion_aprox=aprox,
            ))
    return estaciones


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en línea recta (fórmula de Haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def ranking(
    estaciones: list[Estacion],
    origen: tuple[float, float],
    producto: str,
    radio_km: float,
    descuentos: dict[str, float],
    solo_marcas: set[str] | None = None,
    costo_km: float = COSTO_POR_KM,
    galones: float = GALONES_TANQUE,
    max_dias: int | None = None,
    hoy: datetime | None = None,
) -> list[Resultado]:
    """Ordena por lo que realmente cuesta cargar: precio con descuento + viaje."""
    hoy = hoy or datetime.now()
    resultados = []
    for e in estaciones:
        if e.producto != producto:
            continue
        if solo_marcas and e.marca not in solo_marcas:
            continue
        if max_dias is not None and e.fecha and (hoy - e.fecha).days > max_dias:
            continue  # precio viejo: probablemente ya no es el vigente
        d = distancia_km(origen[0], origen[1], e.lat, e.lon)
        if d > radio_km:
            continue
        desc = descuentos.get(e.marca, 0.0)
        final = round(e.precio - desc, 2)
        viaje = d * costo_km
        resultados.append(Resultado(
            estacion=e, distancia_km=d, descuento=desc, precio_final=final,
            costo_llegar=viaje, precio_efectivo=final + viaje / galones,
        ))
    resultados.sort(key=lambda r: r.precio_efectivo)
    return resultados


def ahorro_por_tanque(resultados: list[Resultado], galones: float = GALONES_TANQUE) -> float:
    """Cuánto ahorras con la mejor opción frente al precio promedio de la zona."""
    if not resultados:
        return 0.0
    promedio = sum(r.estacion.precio for r in resultados) / len(resultados)
    mejor = resultados[0]
    return (promedio - mejor.precio_final) * galones - mejor.costo_llegar


def enlace_google_maps(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"


def enlace_waze(lat: float, lon: float) -> str:
    return f"https://waze.com/ul?ll={lat},{lon}&navigate=yes"
