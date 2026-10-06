"""
Tests de las funciones principales del sistema.

Se usa unittest de la libreria estandar para no requerir instalaciones
adicionales (unittest.mock, incluido en la libreria estandar, se usa para
simular las respuestas de Open-Meteo sin depender de internet). Cada test
verifica una condicion concreta y tiene un mensaje de error que explica
exactamente que fallo y por que importa.

Para correr:
    python tests/test_core.py
    python -m pytest tests/ -v
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import utils.data_processor as dp_module
from utils.data_processor import (
    DataProcessor,
    BARRIOS_COMUNA_1,
    COORDENADAS_BARRIOS,
    PESOS_RIESGO,
    UMBRALES_SIATA
)


class TestCargarDatos(unittest.TestCase):
    """
    Tests para la Funcion 1: cargar_datos() (ruta simulada, sin internet).

    Verifica que los datos tengan el formato correcto y los rangos
    de valores esperados para la realidad de la Comuna 1.
    """

    def setUp(self):
        self.processor = DataProcessor(modo_produccion=False)

    def test_retorna_dataframe(self):
        """cargar_datos debe retornar un DataFrame, nunca None ni una lista."""
        resultado = self.processor.cargar_datos()
        self.assertIsInstance(resultado, pd.DataFrame)

    def test_tiene_todos_los_barrios(self):
        """Debe haber exactamente un registro por cada barrio de la lista oficial."""
        df = self.processor.cargar_datos()
        self.assertEqual(
            len(df), len(BARRIOS_COMUNA_1),
            f"Se esperaban {len(BARRIOS_COMUNA_1)} barrios, se obtuvieron {len(df)}"
        )

    def test_columnas_de_lluvia_presentes(self):
        """Las tres variables de lluvia son obligatorias para el calculo de riesgo."""
        df = self.processor.cargar_datos()
        for col in ["lluvia_24h_mm", "lluvia_72h_mm", "lluvia_30d_mm"]:
            self.assertIn(col, df.columns, f"Falta la columna de lluvia: {col}")

    def test_columnas_de_terreno_presentes(self):
        """
        Las variables del terreno son necesarias para derrumbe e inundacion.
        La pendiente se guarda como tres columnas (min/promedio/max), no una
        sola "pendiente_grados", porque derrumbe usa el punto mas critico
        (max) y arrastre usa la inclinacion general del recorrido (promedio).
        """
        df = self.processor.cargar_datos()
        for col in ["pendiente_min_grados", "pendiente_promedio_grados",
                    "pendiente_max_grados", "distancia_quebrada_m",
                    "permeabilidad_suelo", "cobertura_vegetal_pct"]:
            self.assertIn(col, df.columns, f"Falta columna de terreno: {col}")

    def test_columnas_de_uso_territorio_presentes(self):
        """Las variables de uso del territorio son necesarias para arrastre de basura."""
        df = self.processor.cargar_datos()
        for col in ["puntos_criticos_basura", "vias_en_riesgo",
                    "historico_inundaciones", "historico_derrumbes"]:
            self.assertIn(col, df.columns, f"Falta columna de uso: {col}")

    def test_sin_valores_nulos(self):
        """Ningun campo critico puede tener nulos porque romperian el calculo."""
        df = self.processor.cargar_datos()
        criticas = ["barrio", "lluvia_24h_mm", "lluvia_72h_mm",
                    "pendiente_min_grados", "pendiente_promedio_grados",
                    "pendiente_max_grados", "distancia_quebrada_m",
                    "puntos_criticos_basura"]
        for col in criticas:
            nulos = df[col].isnull().sum()
            self.assertEqual(nulos, 0, f"La columna '{col}' tiene {nulos} valores nulos")

    def test_lluvia_72h_mayor_que_24h(self):
        """
        La lluvia acumulada en 72h siempre debe ser >= a la de 24h.
        Si no, el calculo de riesgo de derrumbe seria incoherente.
        """
        df = self.processor.cargar_datos()
        violaciones = (df["lluvia_72h_mm"] < df["lluvia_24h_mm"]).sum()
        self.assertEqual(
            violaciones, 0,
            f"{violaciones} barrios tienen lluvia_72h menor que lluvia_24h"
        )

    def test_distancias_a_quebrada_positivas(self):
        """La distancia a una quebrada no puede ser negativa ni cero."""
        df = self.processor.cargar_datos()
        self.assertTrue(
            (df["distancia_quebrada_m"] > 0).all(),
            "Hay barrios con distancia_quebrada_m <= 0"
        )

    def test_pendientes_en_rango_real(self):
        """
        Las pendientes de la ladera nororiental estan entre 5 y 70 grados,
        y dentro de cada barrio el minimo <= promedio <= maximo siempre.
        """
        df = self.processor.cargar_datos()
        for col in ["pendiente_min_grados", "pendiente_promedio_grados",
                    "pendiente_max_grados"]:
            self.assertTrue(
                (df[col].between(5, 70)).all(),
                f"Hay valores de {col} fuera del rango real de la ladera nororiental"
            )
        self.assertTrue(
            (df["pendiente_min_grados"] <= df["pendiente_promedio_grados"]).all(),
            "Hay barrios con pendiente_min_grados > pendiente_promedio_grados"
        )
        self.assertTrue(
            (df["pendiente_promedio_grados"] <= df["pendiente_max_grados"]).all(),
            "Hay barrios con pendiente_promedio_grados > pendiente_max_grados"
        )

    def test_datos_guardados_en_instancia(self):
        """
        Despues de cargar, self.datos debe estar disponible para que
        los bots puedan consultar sin recargar en cada mensaje. Tambien
        debe quedar registrado el origen de los datos (api o simulados).
        """
        self.processor.cargar_datos()
        self.assertIsNotNone(self.processor.datos)
        self.assertIsNotNone(self.processor.ultima_actualizacion)
        self.assertEqual(
            self.processor.fuente_datos, "simulados",
            "Con modo_produccion=False, fuente_datos deberia quedar en 'simulados'"
        )

    def test_guardar_cache_crea_carpeta_si_no_existe(self):
        """
        _guardar_cache debe crear la carpeta data/ sola si no existe, en vez
        de fallar en silencio con 'No se pudo guardar cache'.
        """
        ruta_data  = os.path.join(os.path.dirname(dp_module.__file__), "..", "data")
        ruta_cache = os.path.join(ruta_data, "cache.csv")

        if os.path.exists(ruta_cache):
            os.remove(ruta_cache)

        df = self.processor._generar_datos_simulados()
        self.processor._guardar_cache(df)

        self.assertTrue(
            os.path.exists(ruta_cache),
            "_guardar_cache no creo el archivo de cache; la carpeta data/ deberia crearse sola"
        )

        os.remove(ruta_cache)


class TestCargarDesdeAPI(unittest.TestCase):
    """
    Tests para _cargar_desde_api(): la lluvia real de Open-Meteo, una
    coordenada por barrio en una sola peticion.

    Usan unittest.mock para no depender de internet. Las respuestas falsas
    siguen el formato real documentado por Open-Meteo para multiples
    coordenadas: una lista de resultados en el mismo orden en que se
    pidieron las coordenadas.
    """

    def setUp(self):
        self.processor = DataProcessor(modo_produccion=True)

    def test_coordenadas_cubren_todos_los_barrios(self):
        """
        _cargar_desde_api arma las listas de lat/lon recorriendo
        BARRIOS_COMUNA_1; si a algun barrio le falta coordenada, revienta
        con KeyError al construir la peticion.
        """
        faltantes = [b for b in BARRIOS_COMUNA_1 if b not in COORDENADAS_BARRIOS]
        self.assertEqual(
            faltantes, [],
            f"Barrios sin coordenadas en COORDENADAS_BARRIOS: {faltantes}"
        )

    @patch("utils.data_processor.requests.get")
    def test_resultados_se_asignan_al_barrio_correcto(self, mock_get):
        """
        Cada barrio debe terminar con SU propio dato de lluvia (no el de
        otro barrio, ni un promedio de toda la comuna), respetando el orden
        en que Open-Meteo devuelve la lista de resultados.
        """
        horas_totales = 80
        horas = pd.date_range("2026-09-01", periods=horas_totales, freq="h")
        horas_iso = [h.strftime("%Y-%m-%dT%H:%M") for h in horas]

        resultados_falsos = []
        for i, barrio in enumerate(BARRIOS_COMUNA_1):
            precip = [0.1] * horas_totales
            # Marca las ultimas 24h con un valor unico por barrio, para
            # poder verificar que cada uno recibe su propio dato.
            for h in range(horas_totales - 24, horas_totales):
                precip[h] = float(i + 1)
            resultados_falsos.append({
                "latitude":  COORDENADAS_BARRIOS[barrio][0],
                "longitude": COORDENADAS_BARRIOS[barrio][1],
                "hourly": {"time": horas_iso, "precipitation": precip}
            })

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = resultados_falsos
        mock_get.return_value = mock_resp

        df = self.processor._cargar_desde_api()

        for i, barrio in enumerate(BARRIOS_COMUNA_1):
            fila = df.iloc[i]
            self.assertEqual(fila["barrio"], barrio)
            self.assertAlmostEqual(
                fila["lluvia_24h_mm"], float(i + 1) * 24, places=1,
                msg=f"{barrio} no recibio su propio dato de lluvia 24h"
            )

    @patch("utils.data_processor.requests.get")
    def test_ventana_24h_cuenta_exactamente_24_horas(self, mock_get):
        """
        Regresion: la ventana de 24h no debe incluir una hora de mas.
        Un slice con .loc[fin-24h:] es inclusivo en ambos extremos y
        terminaba sumando 25 horas en vez de 24 (se corrigio filtrando
        con index > fin-24h).
        """
        horas = pd.date_range("2026-09-01", periods=48, freq="h")
        horas_iso = [h.strftime("%Y-%m-%dT%H:%M") for h in horas]
        precip = [1.0] * 48  # 1mm cada hora: facil de verificar a mano

        resultados_falsos = [{
            "latitude":  COORDENADAS_BARRIOS[b][0],
            "longitude": COORDENADAS_BARRIOS[b][1],
            "hourly": {"time": horas_iso, "precipitation": precip}
        } for b in BARRIOS_COMUNA_1]

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = resultados_falsos
        mock_get.return_value = mock_resp

        df = self.processor._cargar_desde_api()

        self.assertTrue(
            (df["lluvia_24h_mm"] == 24.0).all(),
            f"La ventana de 24h no sumo exactamente 24 horas: {df['lluvia_24h_mm'].tolist()}"
        )

    @patch("utils.data_processor.requests.get")
    def test_fallback_a_simulados_si_api_falla(self, mock_get):
        """
        Si Open-Meteo no responde (sin internet, timeout, error HTTP),
        cargar_datos() debe caer a datos simulados en vez de propagar la
        excepcion, y marcar self.fuente_datos como 'simulados'.
        """
        mock_get.side_effect = Exception("Sin conexion a internet")

        df = self.processor.cargar_datos()

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), len(BARRIOS_COMUNA_1))
        self.assertEqual(self.processor.fuente_datos, "simulados")


class TestCalcularRiesgoGeneral(unittest.TestCase):
    """
    Tests para la Funcion 2: calcular_riesgo_general().

    Verifica la correctitud matematica del calculo y la coherencia
    entre los indices numericos y las clasificaciones textuales.
    """

    def setUp(self):
        self.processor = DataProcessor(modo_produccion=False)

    def test_agrega_indices_de_riesgo(self):
        """calcular_riesgo_general debe agregar los cuatro indices al DataFrame."""
        df = self.processor.calcular_riesgo_general()
        for col in ["indice_inundacion", "indice_derrumbe",
                    "indice_arrastre_basura", "indice_riesgo_general"]:
            self.assertIn(col, df.columns, f"Falta la columna de indice: {col}")

    def test_agrega_niveles_de_riesgo(self):
        """calcular_riesgo_general debe agregar los cuatro niveles clasificados."""
        df = self.processor.calcular_riesgo_general()
        for col in ["nivel_inundacion", "nivel_derrumbe",
                    "nivel_arrastre_basura", "nivel_riesgo_general"]:
            self.assertIn(col, df.columns, f"Falta la columna de nivel: {col}")

    def test_todos_los_indices_en_rango_0_100(self):
        """Ningun indice puede salir del rango 0-100."""
        df = self.processor.calcular_riesgo_general()
        for col in ["indice_inundacion", "indice_derrumbe",
                    "indice_arrastre_basura", "indice_riesgo_general"]:
            self.assertTrue(
                (df[col].between(0, 100)).all(),
                f"{col} tiene valores fuera del rango [0, 100]"
            )

    def test_niveles_solo_valores_validos(self):
        """Los niveles solo pueden ser BAJO, MODERADO o ALTO."""
        df = self.processor.calcular_riesgo_general()
        validos = {"BAJO", "MODERADO", "ALTO"}
        for col in ["nivel_inundacion", "nivel_derrumbe",
                    "nivel_arrastre_basura", "nivel_riesgo_general"]:
            encontrados = set(df[col].unique())
            invalidos = encontrados - validos
            self.assertFalse(invalidos, f"{col} tiene niveles invalidos: {invalidos}")

    def test_clasificacion_coherente_con_indice(self):
        """
        La clasificacion no puede estar invertida: un barrio con indice 80
        no puede tener nivel BAJO. Se verifica que los umbrales sean correctos.
        """
        df = self.processor.calcular_riesgo_general()
        altos    = df[df["nivel_riesgo_general"] == "ALTO"]
        moderados = df[df["nivel_riesgo_general"] == "MODERADO"]
        bajos    = df[df["nivel_riesgo_general"] == "BAJO"]

        if not altos.empty:
            self.assertTrue(
                (altos["indice_riesgo_general"] > 66).all(),
                "Un barrio clasificado ALTO tiene indice <= 66"
            )
        if not moderados.empty:
            self.assertTrue(
                ((moderados["indice_riesgo_general"] > 33)
                 & (moderados["indice_riesgo_general"] <= 66)).all(),
                "Un barrio MODERADO tiene indice fuera del rango 34-66"
            )
        if not bajos.empty:
            self.assertTrue(
                (bajos["indice_riesgo_general"] <= 33).all(),
                "Un barrio BAJO tiene indice > 33"
            )

    def test_ordenado_de_mayor_a_menor_riesgo(self):
        """
        El primer registro siempre debe ser el mas critico.
        Los bots dependen de este orden para encontrar el barrio mas riesgoso.
        """
        df = self.processor.calcular_riesgo_general()
        indices = df["indice_riesgo_general"].tolist()
        self.assertEqual(
            indices, sorted(indices, reverse=True),
            "El DataFrame no esta ordenado de mayor a menor riesgo general"
        )

    def test_pesos_inundacion_suman_uno(self):
        """Los pesos deben sumar exactamente 1.0 para que el indice este en [0,100]."""
        suma = sum(PESOS_RIESGO["inundacion"].values())
        self.assertAlmostEqual(suma, 1.0, places=10,
                               msg=f"Pesos inundacion suman {suma}")

    def test_pesos_derrumbe_suman_uno(self):
        suma = sum(PESOS_RIESGO["derrumbe"].values())
        self.assertAlmostEqual(suma, 1.0, places=10,
                               msg=f"Pesos derrumbe suman {suma}")

    def test_pesos_arrastre_suman_uno(self):
        suma = sum(PESOS_RIESGO["arrastre_basura"].values())
        self.assertAlmostEqual(suma, 1.0, places=10,
                               msg=f"Pesos arrastre_basura suman {suma}")


class TestSimularLluviaExtra(unittest.TestCase):
    """
    Tests para simular_lluvia_extra().

    Verifica que la simulacion sea monotona: mas lluvia siempre debe
    producir igual o mayor riesgo, nunca menor.
    """

    def setUp(self):
        self.processor = DataProcessor(modo_produccion=False)
        self.processor.calcular_riesgo_general()

    def test_retorna_dataframe_con_estructura_correcta(self):
        """La simulacion debe retornar un DataFrame con los mismos indices."""
        df_escenario = self.processor.simular_lluvia_extra(lluvia_extra_mm=20)
        self.assertIsInstance(df_escenario, pd.DataFrame)
        self.assertIn("indice_riesgo_general", df_escenario.columns)

    def test_mas_lluvia_produce_igual_o_mayor_riesgo_promedio(self):
        """
        El indice de riesgo general promedio con lluvia extra no puede ser
        menor que el actual. Si lo fuera, la logica estaria invertida.
        """
        df_actual = self.processor.datos
        df_escenario = self.processor.simular_lluvia_extra(lluvia_extra_mm=30)

        promedio_actual   = df_actual["indice_riesgo_general"].mean()
        promedio_escenario = df_escenario["indice_riesgo_general"].mean()

        self.assertGreaterEqual(
            promedio_escenario, promedio_actual - 0.1,
            "Con mas lluvia el riesgo promedio bajo, lo cual es incorrecto"
        )

    def test_lluvia_negativa_no_rompe_el_sistema(self):
        """
        Simular lluvia negativa (periodo seco) no debe producir valores
        negativos de precipitacion ni errores de calculo.
        """
        df_escenario = self.processor.simular_lluvia_extra(lluvia_extra_mm=-10)
        self.assertFalse(
            (df_escenario["lluvia_24h_mm"] < 0).any(),
            "La simulacion con lluvia negativa produjo precipitacion negativa"
        )
        self.assertFalse(
            df_escenario["indice_riesgo_general"].isnull().any(),
            "La simulacion con lluvia negativa produjo indices nulos"
        )

    def test_no_modifica_datos_originales(self):
        """
        La simulacion no debe modificar los datos reales guardados en
        self.datos. Los datos originales deben ser identicos antes y despues.
        """
        indice_original = self.processor.datos.iloc[0]["indice_riesgo_general"]
        self.processor.simular_lluvia_extra(lluvia_extra_mm=50)
        indice_despues = self.processor.datos.iloc[0]["indice_riesgo_general"]
        self.assertEqual(
            indice_original, indice_despues,
            "simular_lluvia_extra modifico los datos originales del procesador"
        )


class TestConsultasParaBots(unittest.TestCase):
    """
    Tests para los metodos de consulta que usan los bots.

    Verifica que las respuestas tengan el formato que espera el bot
    para construir los mensajes de Telegram y WhatsApp.
    """

    def setUp(self):
        self.processor = DataProcessor(modo_produccion=False)
        self.processor.calcular_riesgo_general()

    def test_resumen_tiene_claves_requeridas(self):
        """El diccionario de resumen debe tener todas las claves que usan los bots."""
        resumen = self.processor.resumen_comuna()
        claves_requeridas = [
            "total_barrios", "barrio_mas_critico", "indice_mas_alto",
            "lluvia_promedio_24h", "nivel_lluvia_siata",
            "barrios_inundacion_alto", "barrios_derrumbe_alto",
            "barrios_arrastre_alto", "total_puntos_criticos"
        ]
        for clave in claves_requeridas:
            self.assertIn(clave, resumen, f"Falta la clave '{clave}' en resumen_comuna()")

    def test_nivel_lluvia_siata_es_valido(self):
        """El nivel de lluvia SIATA solo puede ser uno de los cuatro valores definidos."""
        resumen = self.processor.resumen_comuna()
        validos = {"NORMAL", "PRECAUCION", "ALERTA", "EMERGENCIA"}
        self.assertIn(
            resumen["nivel_lluvia_siata"], validos,
            f"Nivel SIATA invalido: {resumen['nivel_lluvia_siata']}"
        )

    def test_buscar_barrio_coincidencia_parcial(self):
        """'santo domingo' debe encontrar 'Santo Domingo Savio N1' o 'N2'."""
        resultado = self.processor.buscar_barrio("santo domingo")
        self.assertIsNotNone(resultado, "No encontro ningun barrio con 'santo domingo'")
        self.assertIn("Santo Domingo", resultado["barrio"])

    def test_buscar_barrio_insensible_a_mayusculas(self):
        """'GRANIZAL', 'granizal' y 'Granizal' deben encontrar el mismo barrio."""
        r1 = self.processor.buscar_barrio("GRANIZAL")
        r2 = self.processor.buscar_barrio("granizal")
        self.assertIsNotNone(r1)
        self.assertIsNotNone(r2)
        self.assertEqual(r1["barrio"], r2["barrio"])

    def test_buscar_barrio_retorna_none_si_no_existe(self):
        """Un nombre que no existe debe retornar None, no lanzar excepcion."""
        resultado = self.processor.buscar_barrio("barrio_que_no_existe_xyz_123")
        self.assertIsNone(resultado)

    def test_alertas_activas_retorna_lista(self):
        """alertas_activas siempre debe retornar una lista, nunca None."""
        alertas = self.processor.alertas_activas()
        self.assertIsInstance(alertas, list)

    def test_cada_alerta_tiene_tipos_de_riesgo(self):
        """Cada alerta debe especificar que tipo de riesgo la activo."""
        alertas = self.processor.alertas_activas()
        for alerta in alertas:
            self.assertIn("tipos_alerta", alerta)
            self.assertGreater(
                len(alerta["tipos_alerta"]), 0,
                f"El barrio {alerta['barrio']} esta en alertas pero no tiene tipos"
            )

    def test_todas_las_alertas_tienen_riesgo_alto(self):
        """
        Un barrio en la lista de alertas debe tener al menos un tipo en ALTO.
        Si no, el filtro de alertas_activas esta roto.
        """
        self.processor.calcular_riesgo_general()
        df = self.processor.datos
        alertas = self.processor.alertas_activas()

        for alerta in alertas:
            nombre = alerta["barrio"]
            fila = df[df["barrio"] == nombre].iloc[0]
            tiene_alto = (
                fila["nivel_inundacion"]      == "ALTO"
                or fila["nivel_derrumbe"]     == "ALTO"
                or fila["nivel_arrastre_basura"] == "ALTO"
            )
            self.assertTrue(
                tiene_alto,
                f"{nombre} esta en alertas pero ninguno de sus riesgos es ALTO"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)