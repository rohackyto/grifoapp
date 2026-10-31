"""GrifoApp: encuentra el grifo que realmente te conviene según precio, descuento y distancia."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_js_eval import streamlit_js_eval

import fuente_osinergmin
import geocodificar
import logica
import vista

st.set_page_config(page_title="GrifoApp", page_icon="⛽", layout="centered")

CARPETA = Path(__file__).parent
SNAPSHOT = CARPETA / "data" / "estaciones.csv"
META = CARPETA / "data" / "meta.json"
HORAS_REFRESCO = 3
ORIGEN_POR_DEFECTO = ("Plaza San Martín, Lima", -12.0517, -77.0347)
ORDEN_PRODUCTOS = ["REGULAR", "PREMIUM", "DIESEL", "GLP"]
MARCAS_DESCUENTO = ["Primax", "Repsol", "Pecsa", "Petroperú"]
CLAVE_LS = "grifoapp"
# Pide la ubicación al navegador y se rinde a los 20 s: si el usuario ignora el aviso de
# permiso, getCurrentPosition puede no responder nunca (su "timeout" no cuenta esa espera).
JS_UBICACION = """new Promise(responder => {
  if (!navigator.geolocation) { responder({error: {code: 0}}); return; }
  const limite = setTimeout(() => responder({error: {code: 3}}), 20000);
  navigator.geolocation.getCurrentPosition(
    p => { clearTimeout(limite); responder({coords: {latitude: p.coords.latitude, longitude: p.coords.longitude}}); },
    e => { clearTimeout(limite); responder({error: {code: e.code}}); },
    {enableHighAccuracy: false, timeout: 15000, maximumAge: 300000});
})"""

st.html(f"<style>{(CARPETA / 'estilos.css').read_text(encoding='utf-8')}{vista.CSS_ICONOS}</style>")


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
productos = [p for p in ORDEN_PRODUCTOS if any(e.producto == p for e in estaciones)]
marcas = [m for m in MARCAS_DESCUENTO if any(e.marca == m for e in estaciones)] or \
    sorted({e.marca for e in estaciones})

# ---------- Preferencias guardadas en el navegador (localStorage) ----------
if "prefs" not in st.session_state:
    crudo = streamlit_js_eval(js_expressions=f"localStorage.getItem('{CLAVE_LS}') || '{{}}'",
                              key="leer_prefs")
    if crudo is None:  # el componente aún no responde: esperamos al siguiente ciclo
        st.stop()
    try:
        prefs = json.loads(crudo)
    except json.JSONDecodeError:
        prefs = {}
    st.session_state.prefs = prefs
    st.session_state.origen = tuple(prefs.get("origen") or ORIGEN_POR_DEFECTO)
    # Primera visita (sin ubicación guardada): pedimos la del navegador, como GasolinApp
    st.session_state.pedir_gps = not prefs.get("origen")
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
with st.container(key="cabecera"):
    c_logo, c_corte, c_cfg = st.columns([5, 4, 1.6])
    c_logo.html(vista.cabecera_logo())
    c_corte.html(vista.cabecera_corte(meta["corte"]))
    with c_cfg.popover(":material/tune:", help="Mis descuentos y ajustes", use_container_width=True):
        st.html('<div class="g-label">Mis descuentos</div>')
        st.caption("Lo que te descuenta cada marca por galón. Déjalo en 0 si no lo tienes y "
                   "desaparece de los filtros. Queda guardado en este navegador.")
        for m in marcas:
            st.number_input(m, min_value=0.0, max_value=5.0, step=0.10, format="%.2f", key=f"desc_{m}")
        st.html('<div class="g-label" style="margin-top:.6rem">Ajustes</div>')
        st.toggle("Ocultar precios con más de 30 días sin actualizar", value=True, key="recientes")
descuentos = {m: st.session_state[f"desc_{m}"] for m in marcas}
if meta.get("aviso"):
    st.html(vista.aviso("Aviso", meta["aviso"]))

# ---------- Ubicación ----------
nombre_origen, lat0, lon0 = st.session_state.origen
with st.container(key="ubicacion"):
    c_ubic, c_gps = st.columns([8, 1.3])
    buscando = st.session_state.get("pedir_gps")
    c_ubic.html(vista.ubicacion(nombre_origen, "Buscando tu ubicación…" if buscando else ""))
    if c_gps.button(":material/my_location:", help="Usar mi ubicación actual", use_container_width=True):
        st.session_state.pedir_gps = True
        st.session_state.gps_error = False
        st.session_state.gps_intento = st.session_state.get("gps_intento", 0) + 1
        st.rerun()
if st.session_state.get("pedir_gps"):
    # una clave nueva por intento, para que el botón vuelva a preguntar al navegador
    pos = streamlit_js_eval(js_expressions=JS_UBICACION,
                            key=f"gps_{st.session_state.get('gps_intento', 0)}")
    if pos and "coords" in pos:
        st.session_state.pedir_gps = False
        la, lo = pos["coords"]["latitude"], pos["coords"]["longitude"]
        st.session_state.origen = (nombre_de_lugar(la, lo), la, lo)
        st.rerun()
    elif pos and "error" in pos:
        st.session_state.pedir_gps = False
        st.session_state.gps_error = True
        st.rerun()
if st.session_state.get("gps_error"):
    st.html(vista.aviso("No pudimos usar tu ubicación",
                        "Permite Ubicación en el candado de la barra de direcciones y toca el botón "
                        "de ubicación, o escribe tu dirección abajo."))


def buscar_direccion() -> None:
    texto = st.session_state.busqueda.strip()
    if not texto:
        return
    try:
        encontrado = buscar_lugar(texto)
    except Exception as e:
        st.session_state.error_busqueda = f"Error del buscador de direcciones: {e}"
        return
    if encontrado:
        st.session_state.origen = encontrado
        st.session_state.error_busqueda = None
        st.session_state.pedir_gps = False
        st.session_state.gps_error = False
    else:
        st.session_state.error_busqueda = "No encontré esa dirección. Prueba 'Av. X con Av. Y, distrito'."
    st.session_state.busqueda = ""


st.text_input("Cambiar ubicación", key="busqueda", on_change=buscar_direccion,
              placeholder="Cambiar: escribe una dirección o un cruce", label_visibility="collapsed")
if st.session_state.get("error_busqueda"):
    st.html(vista.aviso("Dirección no encontrada", st.session_state.error_busqueda))

# ---------- Filtros ----------
producto = st.segmented_control("Combustible", productos, default=productos[0], key="producto",
                                label_visibility="collapsed") or productos[0]
radio = st.segmented_control("Radio", [5, 10, 20], default=5, format_func=lambda k: f"{k} KM",
                             key="radio", label_visibility="collapsed") or 5
con_descuento = [m for m, d in descuentos.items() if d > 0]
filtro = set()
if con_descuento:
    with st.container(key="marcas"):
        filtro = set(st.pills("Solo marcas", con_descuento, selection_mode="multi",
                              format_func=lambda m: f"{m.upper()} −S/ {descuentos[m]:.2f}",
                              label_visibility="collapsed") or [])

guardar_prefs()
resultados = logica.ranking(estaciones, (lat0, lon0), producto, radio, descuentos, filtro,
                            max_dias=30 if st.session_state.get("recientes", True) else None)

if not resultados:
    st.html(vista.aviso("Sin resultados", "No hay grifos con esos filtros. Aumenta el radio o quita filtros."))
    st.stop()

# ---------- Resultados ----------
st.html(vista.tarjeta_principal(resultados[0], logica.ahorro_por_tanque(resultados)))
st.html(vista.top10(resultados))

with st.expander(f"Ver los {min(10, len(resultados))} grifos en el mapa"):
    puntos = [{"lat": r.estacion.lat, "lon": r.estacion.lon, "color": "#F2A93B"} for r in resultados[:10]]
    puntos.append({"lat": lat0, "lon": lon0, "color": "#4DA3FF"})
    st.map(pd.DataFrame(puntos), color="color", size=40)

st.html(vista.pie(meta))
