"""GrifoApp: encuentra el grifo que realmente te conviene según precio, descuento y distancia."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_js_eval import get_geolocation, streamlit_js_eval

import fuente_osinergmin
import geocodificar
import logica

st.set_page_config(page_title="GrifoApp", page_icon="⛽", layout="centered")

CARPETA = Path(__file__).parent
SNAPSHOT = CARPETA / "data" / "estaciones.csv"
META = CARPETA / "data" / "meta.json"
HORAS_REFRESCO = 3
ORIGEN_POR_DEFECTO = ("Plaza San Martín, Lima", -12.0517, -77.0347)
ORDEN_PRODUCTOS = ["REGULAR", "PREMIUM", "DIESEL", "GLP"]
MARCAS_DESCUENTO = ["Primax", "Repsol", "Pecsa", "Petroperú"]
CLAVE_LS = "grifoapp"

st.markdown("""
<style>
.precio-grande {font-size: 4.5rem; font-weight: 800; color: #F2A93B; line-height: 1;}
.precio-tachado {text-decoration: line-through; opacity: .6; margin-left: .5rem;}
.etiqueta {font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; opacity: .7;}
.tarjeta {border-top: 3px solid #F2A93B; padding: .8rem 1rem; background: #15191d;}
iframe[title="streamlit_js_eval.streamlit_js_eval"] {display: none;}
</style>
""", unsafe_allow_html=True)


# ---------- Datos ----------
def _leer_snapshot() -> tuple[list[logica.Estacion], dict]:
    meta = json.loads(META.read_text(encoding="utf-8"))
    for campo in ("corte", "generado"):
        if meta.get(campo):
            meta[campo] = datetime.fromisoformat(meta[campo])
    return logica.leer_csv(SNAPSHOT.read_text(encoding="utf-8")), meta


def _snapshot_reciente() -> bool:
    # Se usa la hora guardada en meta.json y no la del archivo: al clonar el repo
    # (p. ej. en Streamlit Cloud) los archivos parecen nuevos aunque los datos no lo sean.
    if not (SNAPSHOT.exists() and META.exists()):
        return False
    generado = json.loads(META.read_text(encoding="utf-8")).get("generado")
    return bool(generado) and (logica.ahora() - datetime.fromisoformat(generado)).total_seconds() \
        < HORAS_REFRESCO * 3600


@st.cache_data(ttl=HORAS_REFRESCO * 3600, show_spinner="Descargando precios de Osinergmin…")
def cargar_estaciones() -> tuple[list[logica.Estacion], dict]:
    """Usa la copia local si tiene menos de HORAS_REFRESCO; si no, reconstruye desde Osinergmin.
    Si la descarga falla, vuelve a la última copia buena; si no hay ninguna, usa datos demo."""
    if _snapshot_reciente():
        return _leer_snapshot()
    try:
        estaciones, meta = fuente_osinergmin.construir()
        if not meta["estaciones_osm"] and SNAPSHOT.exists():
            # OpenStreetMap no respondió: conservamos las marcas de la copia anterior
            previas = {e.codigo: e.marca for e in logica.leer_csv(SNAPSHOT.read_text(encoding="utf-8"))}
            for e in estaciones:
                if e.marca == "Otra":
                    e.marca = previas.get(e.codigo, "Otra")
        fuente_osinergmin.guardar_csv(estaciones, SNAPSHOT)
        META.write_text(json.dumps(meta, default=str), encoding="utf-8")
        return estaciones, meta
    except Exception as e:
        if SNAPSHOT.exists() and META.exists():
            estaciones, meta = _leer_snapshot()
            meta["aviso"] = f"No se pudo actualizar ({e}); se muestra la última copia."
            return estaciones, meta
        return logica.datos_demo(), {"corte": logica.ahora(), "grifos": 0,
                                     "aviso": f"Sin conexión a Osinergmin ({e}). DATOS DEMO."}


@st.cache_data(ttl=86400, show_spinner="Buscando dirección…")
def buscar_lugar(texto: str) -> tuple[str, float, float] | None:
    return geocodificar.buscar(texto)


@st.cache_data(ttl=86400)
def nombre_de_lugar(lat: float, lon: float) -> str:
    try:
        return geocodificar.nombre_de_lugar(lat, lon)
    except Exception:
        return "Mi ubicación"


estaciones, meta = cargar_estaciones()
if meta.get("aviso"):
    st.warning(meta["aviso"])

productos = [p for p in ORDEN_PRODUCTOS if any(e.producto == p for e in estaciones)]
marcas = [m for m in MARCAS_DESCUENTO if any(e.marca == m for e in estaciones)] or \
    sorted({e.marca for e in estaciones})

# ---------- Preferencias guardadas en el navegador (localStorage) ----------
if "prefs" not in st.session_state:
    crudo = streamlit_js_eval(js_expressions=f"localStorage.getItem('{CLAVE_LS}') || '{{}}'",
                              key="leer_prefs")
    if crudo is None:  # el componente aún no responde: esperamos al siguiente ciclo
        st.caption("Cargando tus preferencias…")
        st.stop()
    try:
        prefs = json.loads(crudo)
    except json.JSONDecodeError:
        prefs = {}
    st.session_state.prefs = prefs
    st.session_state.origen = tuple(prefs.get("origen") or ORIGEN_POR_DEFECTO)
    for m in marcas:
        st.session_state[f"desc_{m}"] = float(prefs.get("descuentos", {}).get(m, 0.0))


def guardar_prefs() -> None:
    prefs = {"descuentos": {m: st.session_state[f"desc_{m}"] for m in marcas},
             "origen": list(st.session_state.origen)}
    if prefs != st.session_state.prefs:
        st.session_state.prefs = prefs
        texto = json.dumps(prefs).replace("\\", "\\\\").replace("'", "\\'")
        streamlit_js_eval(js_expressions=f"localStorage.setItem('{CLAVE_LS}', '{texto}')",
                          key=f"guardar_{hash(texto)}")


# ---------- Cabecera ----------
col_logo, col_corte, col_cfg = st.columns([3, 2, 1], vertical_alignment="center")
col_logo.markdown("## ⛽ GRIFOAPP")
col_corte.caption(f"OSINERGMIN {meta['corte']:%d/%m · %H:%M}")
with col_cfg.popover("⚙️", help="Mis descuentos"):
    st.markdown('<div class="etiqueta">Mis descuentos</div>', unsafe_allow_html=True)
    st.caption("Lo que te descuenta cada marca por galón. Déjalo en 0 si no lo tienes y desaparece "
               "de los filtros. Queda guardado en este navegador.")
    for m in marcas:
        st.number_input(m, min_value=0.0, max_value=5.0, step=0.10, format="%.2f", key=f"desc_{m}")
descuentos = {m: st.session_state[f"desc_{m}"] for m in marcas}

# ---------- Ubicación ----------
nombre_origen, lat0, lon0 = st.session_state.origen
c_ubic, c_gps = st.columns([5, 1], vertical_alignment="center")
c_ubic.markdown(f"📍 **{nombre_origen}**")
if c_gps.button("📡", help="Usar mi ubicación actual"):
    st.session_state.pedir_gps = True
if st.session_state.get("pedir_gps"):
    pos = get_geolocation()
    if pos and "coords" in pos:
        st.session_state.pedir_gps = False
        la, lo = pos["coords"]["latitude"], pos["coords"]["longitude"]
        st.session_state.origen = (nombre_de_lugar(la, lo), la, lo)
        st.rerun()
    elif pos and "error" in pos:
        st.session_state.pedir_gps = False
        st.warning("El navegador no compartió la ubicación. Escribe una dirección.")


def buscar_direccion() -> None:
    texto = st.session_state.busqueda.strip()
    if not texto:
        return
    try:
        encontrado = buscar_lugar(texto)
    except Exception as e:
        st.session_state.error_busqueda = f"Error del geocodificador: {e}"
        return
    if encontrado:
        st.session_state.origen = encontrado
        st.session_state.error_busqueda = None
    else:
        st.session_state.error_busqueda = "No encontré esa dirección. Prueba 'Av. X con Av. Y, distrito'."
    st.session_state.busqueda = ""


st.text_input("Cambiar ubicación", key="busqueda", on_change=buscar_direccion,
              placeholder="Cambiar: escribe una dirección o un cruce", label_visibility="collapsed")
if st.session_state.get("error_busqueda"):
    st.warning(st.session_state.error_busqueda)

# ---------- Filtros ----------
c1, c2 = st.columns([1.2, 1])
producto = c1.segmented_control("Combustible", productos, default=productos[0], key="producto",
                                label_visibility="collapsed") or productos[0]
radio = c2.segmented_control("Radio", [5, 10, 20], default=5, format_func=lambda k: f"{k} KM",
                             key="radio", label_visibility="collapsed") or 5

con_descuento = [m for m, d in descuentos.items() if d > 0]
filtro = set()
if con_descuento:
    filtro = set(st.pills("Solo marcas", con_descuento, selection_mode="multi",
                          format_func=lambda m: f"{m.upper()} −S/ {descuentos[m]:.2f}",
                          label_visibility="collapsed") or [])
solo_recientes = st.toggle("Ocultar precios con más de 30 días sin actualizar", value=True)

guardar_prefs()
resultados = logica.ranking(estaciones, (lat0, lon0), producto, radio, descuentos, filtro,
                            max_dias=30 if solo_recientes else None)

if not resultados:
    st.info("No hay grifos con esos filtros. Aumenta el radio o quita filtros.")
    st.stop()


def titulo(e: logica.Estacion) -> str:
    """'Repsol Lince' si conocemos la marca; si no, la razón social."""
    return f"{e.marca} {e.distrito}" if e.marca != "Otra" else e.nombre.strip()


def detalle_fecha(e: logica.Estacion) -> str:
    if not e.fecha:
        return ""
    dias = (logica.ahora() - e.fecha).days
    return "precio de hoy" if dias == 0 else f"precio de hace {dias} día{'s' if dias > 1 else ''}"


# ---------- Mejor opción ----------
mejor = resultados[0]
e = mejor.estacion
st.divider()
st.markdown('<div class="etiqueta">Mejor opción cerca de ti</div>', unsafe_allow_html=True)
st.markdown(f"### {titulo(e)}")
st.caption(" · ".join(x for x in [e.nombre if e.marca != "Otra" else e.distrito,
                                  f"{mejor.distancia_km:.1f} km",
                                  "ubic. aprox." if e.ubicacion_aprox else "", detalle_fecha(e)] if x))
tachado = f'<span class="precio-tachado">S/ {e.precio:.2f}</span>' if mejor.descuento else ""
etiqueta_desc = f' · {e.marca.upper()} −S/ {mejor.descuento:.2f}' if mejor.descuento else ""
st.markdown(f'<div class="tarjeta"><div class="etiqueta">Galón{etiqueta_desc}</div>'
            f'<span class="precio-grande">S/ {mejor.precio_final:.2f}</span>{tachado}</div>',
            unsafe_allow_html=True)
m1, m2, m3 = st.columns(3)
m1.metric("Distancia", f"{mejor.distancia_km:.1f} km")
m2.metric("Llegar cuesta", f"S/ {mejor.costo_llegar:.2f}")
m3.metric("Ahorro/tanque", f"S/ {logica.ahorro_por_tanque(resultados):.2f}",
          help="Frente al precio promedio de la zona, ya restado el costo de llegar.")
b1, b2 = st.columns(2)
b1.link_button("🗺️ Google Maps", logica.enlace_google_maps(e.lat, e.lon), use_container_width=True)
b2.link_button("🧭 Waze", logica.enlace_waze(e.lat, e.lon), use_container_width=True)

# ---------- Top 10 ----------
st.markdown('<div class="etiqueta">Top 10 cerca de ti</div>', unsafe_allow_html=True)
st.caption(f"Orden por precio + lo que cuesta llegar (≈ S/ {logica.COSTO_POR_KM} por km).")
for i, r in enumerate(resultados[1:10], start=2):
    s = r.estacion
    extra = f" · {s.marca} −S/ {r.descuento:.2f}" if r.descuento else (" · ubic. aprox." if s.ubicacion_aprox else "")
    with st.expander(f"{i}. **{titulo(s)}** — {r.distancia_km:.1f} km{extra} — **S/ {r.precio_final:.2f}**"):
        st.write(f"{s.nombre.strip()} · {s.direccion} · {s.distrito}")
        st.write(f"Llegar cuesta **S/ {r.costo_llegar:.2f}** ({r.distancia_km:.1f} km) · equivale a "
                 f"**S/ {r.precio_efectivo:.2f}** el galón · {detalle_fecha(s)}")
        k1, k2 = st.columns(2)
        k1.link_button("Google Maps", logica.enlace_google_maps(s.lat, s.lon), use_container_width=True)
        k2.link_button("Waze", logica.enlace_waze(s.lat, s.lon), use_container_width=True)

with st.expander(f"Ver los {min(10, len(resultados))} grifos en el mapa"):
    puntos = [{"lat": r.estacion.lat, "lon": r.estacion.lon, "color": "#F2A93B"} for r in resultados[:10]]
    puntos.append({"lat": lat0, "lon": lon0, "color": "#4DA3FF"})
    st.map(pd.DataFrame(puntos), color="color", size=40)

st.info(f"**Cómo ordenamos:** por lo que te cuesta cargar de verdad: el precio con tu descuento más "
        f"el viaje, unos S/ {logica.COSTO_POR_KM} por km repartidos en un tanque de "
        f"{logica.GALONES_TANQUE} galones. Por eso un grifo barato pero lejos puede quedar debajo de "
        "otro un poco más caro y cerca.")
st.caption(f"Datos de Osinergmin (EVPC) del {meta['corte']:%d/%m/%Y · %H:%M} · "
           f"{meta.get('grifos', 0):,} grifos. Coordenadas: capa pública de Osinergmin; las estaciones "
           "sin coordenada se ubican en el centro de su distrito. Marcas: OpenStreetMap y razón social. "
           "Precios referenciales reportados por cada grifo.")
