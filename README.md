# GrifoApp

Muestra el grifo que realmente te conviene en Perú: **precio − tu descuento + costo de llegar**.
Hace lo mismo que GasolinApp, con datos públicos y oficiales.

## Ejecutar
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py          # http://localhost:8501
```

## De dónde salen los datos
| Dato | Fuente | Cómo se usa |
|---|---|---|
| Precios | Osinergmin SCOP/PRICE, [`Ultimos-Precios-Registrados-EVPC.xlsx`](https://www.osinergmin.gob.pe/empresas/hidrocarburos/scop/documentos-scop), con el último precio de cada grifo y producto | Se descarga y se filtran los productos activos con precio mayor que 0 |
| Coordenadas | Capa ArcGIS pública de Osinergmin `12_BD_Dash_HL_GrifosEESS_gdb` (FeatureServer/0) | Se une por código Osinergmin. Cubre unos 2 600 de 5 640 grifos |
| Grifos sin coordenada | Centro de su distrito: promedio de los grifos del distrito o, si no hay ninguno, Nominatim | Se marcan como "ubic. aprox." |
| Marca | OpenStreetMap (`amenity=fuel`, a menos de 100 m) o la razón social (COESTI → Primax, etc.) | Si no se identifica, queda como "Otra" |
| Direcciones y cruces | Nominatim (OpenStreetMap). Un cruce se calcula como el punto donde se tocan los trazados de las dos calles | Respeta el límite de 1 consulta por segundo |

El Excel de precios **no trae coordenadas y casi nunca trae la marca**. Por eso hay que combinar fuentes.

## Archivos
- `app.py`: interfaz en Streamlit (descuentos guardados en localStorage, GPS, filtros, Top 10, mapa).
- `fuente_osinergmin.py`: descarga y combina precios, coordenadas y marcas. También se puede ejecutar solo:
  `python fuente_osinergmin.py data/estaciones.csv`.
- `geocodificar.py`: convierte direcciones y cruces en coordenadas.
- `logica.py`: distancia, ranking, ahorro y filtro por antigüedad del precio. Es Python puro.
- `data/`: copia local de los datos. Se refresca cada 3 h y se usa como respaldo si Osinergmin no responde.
- `test_logica.py`: `python -m unittest test_logica`.

## Publicar gratis
Sube la carpeta a GitHub (sin `.venv`), entra a https://share.streamlit.io y elige `app.py`.
Incluye la carpeta `data/` para que la primera carga sea inmediata.
