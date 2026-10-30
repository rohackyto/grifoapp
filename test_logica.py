"""Pruebas de la lógica (python -m unittest test_logica)."""
import unittest

import logica


class PruebasLogica(unittest.TestCase):
    def test_formula_reproduce_gasolinapp(self):
        # Caso observado en GasolinApp: 21.75 con S/ 1.77 de viaje -> 21.88 por galón.
        e = logica.Estacion("X", "M", "", "", -12.0, -77.0, "PREMIUM", 22.75)
        km = 1.77 / logica.COSTO_POR_KM
        destino_lat = -12.0 + km / 111.195  # 1° de latitud ≈ 111.195 km
        r = logica.ranking([e], (destino_lat, -77.0), "PREMIUM", 5, {"M": 1.0})[0]
        self.assertAlmostEqual(r.precio_final, 21.75)
        self.assertAlmostEqual(round(r.precio_efectivo, 2), 21.88)

    def test_cerca_y_algo_mas_caro_gana_a_barato_y_lejos(self):
        cerca = logica.Estacion("Cerca", "A", "", "", -12.0, -77.0, "REGULAR", 17.00)
        lejos = logica.Estacion("Lejos", "A", "", "", -12.09, -77.0, "REGULAR", 16.95)
        r = logica.ranking([lejos, cerca], (-12.0, -77.0), "REGULAR", 20, {})
        self.assertEqual(r[0].estacion.nombre, "Cerca")

    def test_radio_producto_y_filtro_marca(self):
        datos = logica.datos_demo()
        r = logica.ranking(datos, (-12.1211, -77.0297), "PREMIUM", 5, {}, {"Marca B"})
        self.assertTrue(r)
        self.assertTrue(all(x.distancia_km <= 5 and x.estacion.marca == "Marca B"
                            and x.estacion.producto == "PREMIUM" for x in r))

    def test_oculta_precios_viejos(self):
        from datetime import datetime
        hoy = datetime(2026, 10, 30)
        nuevo = logica.Estacion("Nuevo", "A", "", "", -12.0, -77.0, "REGULAR", 18.0,
                                fecha=datetime(2026, 10, 25))
        viejo = logica.Estacion("Viejo", "A", "", "", -12.0, -77.0, "REGULAR", 15.0,
                                fecha=datetime(2026, 1, 1))
        r = logica.ranking([nuevo, viejo], (-12.0, -77.0), "REGULAR", 5, {}, max_dias=30, hoy=hoy)
        self.assertEqual([x.estacion.nombre for x in r], ["Nuevo"])

    def test_marca_por_razon_social(self):
        import fuente_osinergmin as f
        self.assertEqual(f.marca_por_razon("COESTI S.A."), "Primax")
        self.assertEqual(f.marca_por_razon("REPSOL COMERCIAL S.A.C."), "Repsol")
        self.assertEqual(f.marca_por_razon("PERUANA DE ESTACIONES DE SERVICIOS S.A.C."), "Pecsa")
        self.assertIsNone(f.marca_por_razon("GRIFO PARIAHUANCA"))

    def test_leer_csv_con_alias(self):
        csv_txt = "Razon Social,Bandera,Latitud,Longitud,Combustible,Precio Venta\n" \
                  "Grifo 1,Repsol,-12.1,-77.0,Premium,\"21,90\"\nSin coord,X,,,Premium,20\n"
        e = logica.leer_csv(csv_txt)
        self.assertEqual(len(e), 1)
        self.assertEqual((e[0].marca, e[0].producto, e[0].precio), ("Repsol", "PREMIUM", 21.9))


if __name__ == "__main__":
    unittest.main()
