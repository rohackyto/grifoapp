"""Piezas HTML de la interfaz. Todo texto que viene de los datos se escapa."""
from __future__ import annotations

import base64
import re
from html import escape

import logica

def _trazo(color: str, cuerpo: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{cuerpo}</svg>')


# st.html elimina <svg> e <img data:>; por eso los íconos van como fondo CSS de un <span>
_SVG_ICONOS = {
    "logo": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" '
             'fill="#F2A93B"/><rect x="5" y="6" width="7" height="13" fill="#0F1416"/><rect x="6.5" '
             'y="8" width="4" height="3" fill="#F2A93B"/><path d="M13 9h3l2 2v7h-2v-6h-3z" '
             'fill="#0F1416"/></svg>'),
    "ubic": _trazo("#F2A93B", '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/>'
                              '<path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>'),
    "mapa": _trazo("#14181B", '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>'),
    "navegar": _trazo("#E9EFF2", '<path d="m3 11 19-9-9 19-2-8-8-2z"/>'),
    "chevron": _trazo("#A3B1B8", '<path d="m6 9 6 6 6-6"/>'),
}
CSS_ICONOS = "".join(
    f'.g-i-{nombre}{{background-image:url("data:image/svg+xml;base64,'
    f'{base64.b64encode(svg.encode()).decode()}")}}'
    for nombre, svg in _SVG_ICONOS.items())


def _icono(nombre: str, extra: str = "") -> str:
    return f'<span class="g-i g-i-{nombre} {extra}" aria-hidden="true"></span>'


ICONO_LOGO = _icono("logo", "g-ico-logo")
ICONO_UBIC = _icono("ubic", "g-ico-ubic")
ICONO_MAPA = _icono("mapa")
ICONO_NAVEGAR = _icono("navegar")
ICONO_CHEVRON = _icono("chevron", "g-chevron")

_PREFIJOS = re.compile(r"^(AV(ENIDA)?|JR|JIRON|JIRÓN|CA(LLE)?|CAL|PROL(ONGACION)?|CARR(ETERA)?|PSJE|PJE|"
                       r"PASAJE|MZ|MZA|LT|ESQ(UINA)?(\s+(DE|CON))?)(\.\s*|\s+)", re.IGNORECASE)


def calle_corta(direccion: str) -> str:
    """'Av. El Sol Nº 697, Esquina…' -> 'El Sol'."""
    texto = re.split(r"[,(]|\bN[º°o]?\.?\s*\d|\d|\bS/N\b|\bCDRA\b|\bCUADRA\b|\bKM\b", direccion, maxsplit=1,
                     flags=re.IGNORECASE)[0]
    texto = texto.strip()
    while (sin_prefijo := _PREFIJOS.sub("", texto, count=1)) != texto:  # "Esquina Av. X" -> "X"
        texto = sin_prefijo
    texto = re.split(r"\s+(?:Y|CON|ESQ\.?|ESQUINA)\s+", texto, maxsplit=1, flags=re.IGNORECASE)[0]
    return texto.strip(" .-")[:28]


def titulo(e: logica.Estacion) -> str:
    """'Repsol Lince' si conocemos la marca; si no, la razón social."""
    return f"{e.marca} {e.distrito}" if e.marca != "Otra" else e.nombre.strip()


def antiguedad(e: logica.Estacion) -> str:
    if not e.fecha:
        return ""
    dias = (logica.ahora() - e.fecha).days
    return "precio de hoy" if dias <= 0 else f"precio de hace {dias} día{'s' if dias > 1 else ''}"


def cabecera_logo() -> str:
    return f'<div class="g-logo">{ICONO_LOGO}GRIFOAPP</div>'


def cabecera_corte(corte) -> str:
    return f'<div class="g-corte"><span class="g-corte-pre">Osinergmin </span>{corte:%d/%m · %H:%M}</div>'


def ubicacion(nombre: str, detalle: str = "") -> str:
    extra = f"<small>{escape(detalle)}</small>" if detalle else ""
    return f'<div class="g-ubic">{ICONO_UBIC}<div>{escape(nombre)}{extra}</div></div>'


def botones(e: logica.Estacion) -> str:
    return (f'<div class="g-botones">'
            f'<a class="g-btn g-btn-claro" href="{logica.enlace_google_maps(e.lat, e.lon)}" target="_blank" '
            f'rel="noopener">{ICONO_MAPA}Google Maps</a>'
            f'<a class="g-btn" href="{logica.enlace_waze(e.lat, e.lon)}" target="_blank" rel="noopener">'
            f'{ICONO_NAVEGAR}Waze</a></div>')


def tarjeta_principal(r: logica.Resultado, ahorro: float) -> str:
    e = r.estacion
    sub = " · ".join(x for x in [escape(calle_corta(e.direccion)) or escape(e.distrito),
                                 f"{r.distancia_km:.1f} km", "ubic. aprox." if e.ubicacion_aprox else "",
                                 antiguedad(e)] if x)
    desc = f"<span>{escape(e.marca)} −S/ {r.descuento:.2f}</span>" if r.descuento else "<span></span>"
    tachado = f"<s>S/ {e.precio:.2f}</s>" if r.descuento else ""
    return (
        '<div class="g-sep"></div>'
        '<div class="g-label">Mejor opción cerca de ti</div>'
        f'<div class="g-nombre">{escape(titulo(e))}</div>'
        f'<div class="g-sub">{sub}</div>'
        f'<div class="g-precio"><div class="g-precio-top"><span>Galón</span>{desc}</div>'
        f'<div class="g-precio-num"><span class="g-sol">S/</span>{r.precio_final:.2f}{tachado}</div></div>'
        '<div class="g-metricas">'
        f'<div><small>DISTANCIA</small><b>{r.distancia_km:.1f} km</b></div>'
        f'<div><small>LLEGAR CUESTA</small><b>S/ {r.costo_llegar:.2f}</b></div>'
        f'<div><small>AHORRO/TANQUE</small><b class="g-verde">S/ {ahorro:.2f}</b></div>'
        '</div>' + botones(e)
    )


def _fila(pos: int, r: logica.Resultado) -> str:
    e = r.estacion
    marca_o_aprox = (f" · <em>{escape(e.marca)} −S/ {r.descuento:.2f}</em>" if r.descuento
                     else (" · ubic. aprox." if e.ubicacion_aprox else ""))
    calle = calle_corta(e.direccion)
    tachado = f"<s>S/ {e.precio:.2f}</s>" if r.descuento else ""
    clase = ' class="g-con-desc"' if r.descuento else ""
    return (
        '<details class="g-fila"><summary>'
        f'<span class="g-pos">{pos}</span>'
        f'<div class="g-info"><div class="g-linea1"><b>{escape(titulo(e))}</b> '
        f'<span class="g-calle">{escape(calle)}</span></div>'
        f'<small><strong>{r.distancia_km:.1f} km</strong>{marca_o_aprox}</small></div>'
        f'<div class="g-precio-chico"><b{clase}>{r.precio_final:.2f}</b>{tachado}</div>{ICONO_CHEVRON}'
        '</summary><div class="g-detalle">'
        f'{escape(e.nombre)} · {escape(e.direccion)} · {escape(e.distrito)}<br>'
        f'Llegar cuesta <strong>S/ {r.costo_llegar:.2f}</strong> ({r.distancia_km:.1f} km) · '
        f'equivale a <strong>S/ {r.precio_efectivo:.2f}</strong> el galón · {antiguedad(e)}'
        f'{botones(e)}</div></details>'
    )


def top10(resultados: list[logica.Resultado], visibles: int = 4) -> str:
    filas = [_fila(i, r) for i, r in enumerate(resultados[1:10], start=2)]
    html = "".join(filas[:visibles])
    if len(filas) > visibles:
        html += (f'<details class="g-mas"><summary>+{len(filas) - visibles} MÁS ⌄</summary>'
                 + "".join(filas[visibles:]) + "</details>")
    return (
        '<div class="g-titulo-lista"><span class="g-label">Top 10 cerca de ti</span>'
        '<span class="g-label">Precio final</span></div>'
        f'<div class="g-nota">Orden por <b>precio + lo que cuesta llegar</b> '
        f'(≈ S/ {logica.COSTO_POR_KM} por km).</div>'
        f'<div class="g-lista">{html}</div>'
    )


def pie(meta: dict) -> str:
    return (
        '<div class="g-como"><div class="g-label">Cómo ordenamos</div>'
        '<p>Por lo que te cuesta cargar de verdad: el precio con tu descuento más el viaje, unos '
        f'S/ {logica.COSTO_POR_KM} por kilómetro repartidos en un tanque de {logica.GALONES_TANQUE} '
        'galones. Por eso un grifo barato pero lejos puede quedar debajo de otro un poco más caro y '
        'cerca.</p></div>'
        '<div class="g-pie">'
        f'<p>Datos de <b>Osinergmin (EVPC)</b> del {meta["corte"]:%d/%m/%Y · %H:%M} (hora de Perú) · '
        f'{meta.get("grifos", 0):,} grifos.</p>'
        '<p>Coordenadas de la capa pública de Osinergmin; las estaciones sin coordenada exacta se '
        'ubican en el centro de su distrito. Marcas según OpenStreetMap y razón social.</p>'
        '<p>Precios referenciales reportados por cada grifo. Los descuentos dependen de las '
        'condiciones vigentes de cada marca.</p></div>'
    )


def aviso(titulo_aviso: str, texto: str) -> str:
    return f'<div class="g-aviso"><b>{escape(titulo_aviso)}</b>{escape(texto)}</div>'
