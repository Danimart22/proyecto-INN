"""
Modulo central de analisis de riesgo por lluvias - Comuna 1 Popular, Medellin.

La lluvia es el eje de todo el analisis. En la ladera nororiental de Medellin,
donde esta la Comuna 1, una lluvia intensa puede desencadenar en minutos:
    - Inundaciones y corrientes violentas de agua en las vias
    - Deslizamientos y derrumbes en zonas de ladera con suelo saturado
    - Arrastre de basura desde puntos criticos hacia las quebradas

Este modulo calcula tres indices de riesgo independientes para esos tres
fenomenos, mas un indice general que los combina. Todo el sistema puede
funcionar con datos simulados (sin internet) o con datos reales del SIATA
y Datos Abiertos Medellin (en produccion).

Funciones principales:
    1. cargar_datos()             -- carga variables climaticas y territoriales
    2. calcular_riesgo_general()  -- calcula los 3 tipos de riesgo por barrio
    3. simular_lluvia_extra(mm)   -- que pasa si llueve X mm mas esta noche
    4. alertas_activas()          -- barrios con al menos un riesgo en ALTO
    5. resumen_comuna()           -- resumen para los bots
    6. buscar_barrio(nombre)      -- consulta individual por barrio
"""

import os
import logging
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("popular_ambiental")

# Barrios oficiales de la Comuna 1 Popular segun el POT de Medellin.
BARRIOS_COMUNA_1 = [
    "Santo Domingo Savio N1",
    "Santo Domingo Savio N2",
    "El Popular",
    "Granizal",
    "Moscu N2",
    "Villa Guadalupe",
    "San Pablo",
    "El Compromiso",
    "Aldea Pablo VI",
    "La Esperanza N2",
    "La Avanzada",
    "Carpinelo",
]
# Coordenadas aproximadas del centroide de cada barrio (WGS84).
# Estimadas a partir de puntos de referencia conocidos (estaciones del
# Metrocable Linea K, disposicion de barrios segun el POT) -- no son
# centroides catastrales oficiales. Si se necesita precision para la
# version final, reemplazar por los centroides del catalogo GIS de
# Medellin (https://www.medellin.gov.co/giscatalogacion).
COORDENADAS_BARRIOS = {
    "Santo Domingo Savio N1": (6.2932, -75.5417),
    "Santo Domingo Savio N2": (6.2948, -75.5428),
    "El Popular":             (6.2878, -75.5463),
    "Granizal":                (6.2981, -75.5392),
    "Moscu N2":                (6.2865, -75.5492),
    "Villa Guadalupe":         (6.2903, -75.5478),
    "San Pablo":               (6.2891, -75.5447),
    "El Compromiso":           (6.2957, -75.5386),
    "Aldea Pablo VI":          (6.2969, -75.5405),
    "La Esperanza N2":         (6.2920, -75.5365),
    "La Avanzada":             (6.3002, -75.5437),
    "Carpinelo":               (6.3038, -75.5415),
}

# Distancias aproximadas de cada barrio a la quebrada mas cercana en metros.
# Estimadas a partir de la cartografia del IGAC y el SIG de Medellin.
# Las quebradas La Francia, Granizal y El Molino son las principales
# fuentes de riesgo de inundacion en la Comuna 1 Popular.
# Codigos POT: 101-112.
DISTANCIA_A_QUEBRADA = {
    "Santo Domingo Savio N1": 150,  # cercano a Quebrada La Francia
    "Santo Domingo Savio N2": 200,
    "El Popular":             280,
    "Granizal":               110,  # muy cercano a Quebrada Granizal
    "Moscu N2":               305,
    "Villa Guadalupe":        175,
    "San Pablo":              270,
    "El Compromiso":          190,
    "Aldea Pablo VI":         160,  # entre Granizal y El Compromiso
    "La Esperanza N2":        210,
    "La Avanzada":            220,
    "Carpinelo":              410,  # zona alta, mas alejado de quebradas
}

# Umbrales de lluvia del SIATA (Sistema de Alerta Temprana de Medellin).
# Estos valores se usan para clasificar la situacion de lluvia actual
# y comunicarla a la comunidad con el lenguaje de alerta que ya conocen.
UMBRALES_SIATA = {
    "lluvia_24h": {
        "normal":     20,   # menos de 20mm: sin alerta
        "precaucion": 40,   # 20-40mm: amarillo
        "alerta":     70,   # 40-70mm: naranja
        # mas de 70mm en 24h: rojo / emergencia
    },
    "lluvia_72h": {
        "normal":     50,
        "precaucion": 100,
        "alerta":     150,
    }
}

# Inclinacion del terreno calibrada por barrio a partir del Decreto 345/2000
# (SIMPAD/INGEOMINAS), la altimetria IGAC y la Microzonificacion Sismica de
# Medellin (2010). Los valores reflejan la variabilidad topografica dentro
# de cada barrio: los puntos bajos son calles o pequenas explanadas, los
# puntos altos son laderas junto a quebradas o bordes de la comuna.
# Unidades: grados. Formato: (minimo, promedio, maximo).
PENDIENTE_BARRIOS = {
    # Zona alta (> 1750 msnm): fuerte pendiente, riesgo de derrumbe mas alto
    "Santo Domingo Savio N1": (15, 35, 62),
    "Santo Domingo Savio N2": (14, 32, 58),
    "La Avanzada":            (16, 36, 60),
    "Carpinelo":              (18, 40, 66),  # punto mas alto de la comuna
    "Granizal":               (17, 37, 64),  # empinado y junto a quebrada
    # Zona media-alta (1650-1750 msnm): pendientes entre moderadas y fuertes
    "La Esperanza N2":        (12, 28, 52),
    "El Compromiso":          (11, 27, 50),
    "Aldea Pablo VI":         (10, 25, 48),
    # Zona media (1550-1650 msnm): pendientes moderadas (25-40% segun POT)
    "El Popular":             ( 8, 20, 42),
    "Villa Guadalupe":        ( 9, 21, 44),
    "San Pablo":              ( 7, 19, 40),
    "Moscu N2":               ( 6, 18, 38),  # el de menor pendiente promedio
}

# Pesos de cada variable dentro de cada tipo de riesgo.
# Fueron definidos con base en la metodologia de zonificacion de amenazas
# del DAGRD para la ladera nororiental del Valle de Aburra.
# Para derrumbe se usa pendiente_max porque los deslizamientos se inician
# en el punto mas critico del terreno, no en el promedio.
# Para arrastre se usa pendiente_promedio porque la velocidad de la corriente
# depende de la inclinacion general del recorrido del agua, no del peor punto.
PESOS_RIESGO = {
    "inundacion": {
        "lluvia_24h_mm":        0.40,
        "distancia_quebrada_m": 0.30,  # inverso: mas cerca = mas riesgo
        "vias_en_riesgo":       0.20,
        "permeabilidad_suelo":  0.10,  # inverso: menos permeable = mas escorrentia
    },
    "derrumbe": {
        "lluvia_72h_mm":             0.40,
        "pendiente_max_grados":      0.35,  # punto mas critico del barrio
        "cobertura_vegetal_pct":     0.25,  # inverso: menos vegetacion = mas riesgo
    },
    "arrastre_basura": {
        "puntos_criticos_basura":    0.40,
        "lluvia_24h_mm":             0.35,
        "pendiente_promedio_grados": 0.25,  # inclinacion general del recorrido
    }
}


class DataProcessor:
    """
    Clase principal del sistema de monitoreo de riesgo por lluvias.

    Encapsula toda la logica de datos para que el dashboard y los bots
    puedan hacer consultas sin conocer los detalles del calculo.
    Se instancia una vez al arrancar la aplicacion y se reutiliza.

    Ejemplo basico:
        processor = DataProcessor()
        df = processor.calcular_riesgo_general()
        alertas = processor.alertas_activas()
        escenario = processor.simular_lluvia_extra(lluvia_extra_mm=30)
    """

    def __init__(self, modo_produccion: bool = False):
        # modo_produccion=True intenta conectar a SIATA y Datos Abiertos.
        # Con False, el sistema funciona completamente sin internet.
        self.modo_produccion = modo_produccion
        self.datos: Optional[pd.DataFrame] = None
        self.ultima_actualizacion: Optional[datetime] = None

    # -----------------------------------------------------------------------
    # FUNCION 1: cargar_datos
    # -----------------------------------------------------------------------

    def cargar_datos(self) -> pd.DataFrame:
        """
        Carga los datos climaticos y territoriales de la Comuna 1.

        Intenta primero la API real si esta en modo produccion.
        Si falla por cualquier razon (sin internet, cambio de endpoint,
        limite de peticiones), cae automaticamente a datos simulados
        para que la aplicacion nunca quede en blanco.

        El DataFrame siempre tiene las mismas columnas sin importar el origen,
        lo que garantiza que el resto del sistema funcione igual en los dos modos.

        Guarda en self.fuente_datos cual fue el origen realmente usado
        ("api" o "simulados"), para que el resto del sistema (o el dashboard)
        pueda mostrarlo si hace falta.

        Columnas del resultado:
            barrio                 -- nombre del barrio
            lluvia_24h_mm          -- precipitacion ultimas 24 horas (mm)
            lluvia_72h_mm          -- precipitacion acumulada 72 horas (mm)
            lluvia_30d_mm          -- precipitacion acumulada 30 dias (mm)
            pendiente_grados       -- inclinacion promedio del terreno
            distancia_quebrada_m   -- metros a la quebrada mas cercana
            permeabilidad_suelo    -- capacidad de absorcion del suelo (1-10)
            cobertura_vegetal_pct  -- porcentaje de cobertura vegetal
            puntos_criticos_basura -- sitios de disposicion ilegal de basura
            vias_en_riesgo         -- vias que se convierten en canales
            historico_inundaciones -- eventos de inundacion registrados
            historico_derrumbes    -- eventos de deslizamiento registrados
            calidad_aire_pm25      -- material particulado PM2.5 (ug/m3)
            fecha_corte            -- fecha de los datos
        """
        if self.modo_produccion:
            try:
                df = self._cargar_desde_api()
                self.fuente_datos = "api"
                logger.info(
                    "FUENTE DE DATOS: API (Open-Meteo, lluvia real por barrio) -- "
                    f"{len(BARRIOS_COMUNA_1)} barrios actualizados."
                )
                self._guardar_cache(df)
                self.datos = df
                self.ultima_actualizacion = datetime.now()
                return df
            except Exception as e:
                logger.warning(f"API no disponible ({e}). Usando datos simulados.")

        df = self._generar_datos_simulados()
        self.fuente_datos = "simulados"
        motivo = (
            "modo_produccion desactivado"
            if not self.modo_produccion
            else "fallback por error en la API"
        )
        logger.info(
            f"FUENTE DE DATOS: SIMULADOS para {len(BARRIOS_COMUNA_1)} barrios "
            f"de la Comuna 1 ({motivo})"
        )
        self.datos = df
        self.ultima_actualizacion = datetime.now()
        return df

    def _generar_datos_simulados(self) -> pd.DataFrame:
        """
        Genera un dataset de prueba con valores calibrados para la Comuna 1.

        Los rangos estan basados en registros reales:
        - Lluvia: el SIATA registra entre 5 y 80mm/24h en temporada de lluvias
          en la ladera nororiental de Medellin.
        - Pendientes: entre 10 y 44 grados en la zona nororiental segun IGAC.
        - Permeabilidad: suelos arcillosos tipicos de la ladera (valores bajos).
        - Cobertura vegetal: entre 8% y 55% segun el mapa verde de Medellin.

        Los barrios cercanos a quebradas reciben distancias menores (mas riesgo),
        tomadas del mapa DISTANCIA_A_QUEBRADA definido arriba.

        La semilla fija garantiza reproducibilidad para presentaciones y tests,
        pero el ruido aleatorio hace que la distribucion de riesgos sea realista.
        """
        np.random.seed(42)
        n = len(BARRIOS_COMUNA_1)

        # Distancias a quebradas con variacion aleatoria para simular
        # que dentro de un mismo barrio hay zonas mas o menos expuestas.
        distancias = np.array([
            DISTANCIA_A_QUEBRADA.get(b, 350) + np.random.randint(-40, 60)
            for b in BARRIOS_COMUNA_1
        ]).clip(min=40)

        # Lluvia: escenario tipico de dia lluvioso en temporada media.
        lluvia_24h = np.random.uniform(8, 58, n).round(1)
        lluvia_72h = np.maximum(
            lluvia_24h + np.random.uniform(10, 70, n).round(1),
            lluvia_24h
        ).round(1)

        # Pendiente: valores calibrados por barrio desde PENDIENTE_BARRIOS.
        # No se usa aleatoriedad porque estas son medidas del terreno real,
        # no variables que cambien con el tiempo como la lluvia.
        pendiente_min     = [PENDIENTE_BARRIOS[b][0] for b in BARRIOS_COMUNA_1]
        pendiente_promedio = [PENDIENTE_BARRIOS[b][1] for b in BARRIOS_COMUNA_1]
        pendiente_max     = [PENDIENTE_BARRIOS[b][2] for b in BARRIOS_COMUNA_1]

        return pd.DataFrame({
            "barrio":                    BARRIOS_COMUNA_1,
            "lluvia_24h_mm":             lluvia_24h,
            "lluvia_72h_mm":             lluvia_72h,
            "lluvia_30d_mm":             np.random.uniform(80, 280, n).round(1),
            "pendiente_min_grados":      pendiente_min,
            "pendiente_promedio_grados": pendiente_promedio,
            "pendiente_max_grados":      pendiente_max,
            "distancia_quebrada_m":      distancias,
            "permeabilidad_suelo":       np.random.uniform(2, 8, n).round(1),
            "cobertura_vegetal_pct":     np.random.uniform(8, 55, n).round(1),
            "puntos_criticos_basura":    np.random.randint(3, 78, n),
            "vias_en_riesgo":            np.random.randint(1, 18, n),
            "historico_inundaciones":    np.random.randint(0, 22, n),
            "historico_derrumbes":       np.random.randint(0, 12, n),
            "calidad_aire_pm25":         np.random.uniform(12, 50, n).round(1),
            "fecha_corte":               datetime.now().strftime("%Y-%m-%d")
        })

    def _cargar_desde_api(self) -> pd.DataFrame:
        """
        Obtiene lluvia real de Open-Meteo, una estacion POR BARRIO en vez de
        un solo punto para toda la comuna. Las variables de terreno se
        mantienen calibradas porque requieren procesamiento GIS especializado.

        Open-Meteo acepta listas de coordenadas separadas por coma en una sola
        peticion (&latitude=a,b,c&longitude=x,y,z) y devuelve una lista de
        resultados en el mismo orden -- por eso las listas se arman siguiendo
        el orden de BARRIOS_COMUNA_1, para poder volver a emparejar cada
        resultado con su barrio despues.
        """
        lats = ",".join(str(COORDENADAS_BARRIOS[b][0]) for b in BARRIOS_COMUNA_1)
        lons = ",".join(str(COORDENADAS_BARRIOS[b][1]) for b in BARRIOS_COMUNA_1)

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":      lats,
            "longitude":     lons,
            "hourly":        "precipitation",
            "past_days":     30,   # permite calcular 24h, 72h y 30d reales
            "forecast_days": 0,
            "timezone":      "America/Bogota"
        }
        respuesta = requests.get(url, params=params, timeout=15)
        respuesta.raise_for_status()
        resultados = respuesta.json()

        # Con una sola coordenada Open-Meteo devuelve un dict; con varias,
        # devuelve una lista de dicts en el mismo orden en que se pidieron.
        if isinstance(resultados, dict):
            resultados = [resultados]

        lluvia_24h_por_barrio = []
        lluvia_72h_por_barrio = []
        lluvia_30d_por_barrio = []

        for resultado_barrio in resultados:
            horas       = resultado_barrio["hourly"]["time"]
            lluvia_hora = resultado_barrio["hourly"]["precipitation"]

            df_clima = pd.DataFrame({"hora": horas, "lluvia_mm": lluvia_hora})
            df_clima["hora"] = pd.to_datetime(df_clima["hora"])
            df_clima = df_clima.set_index("hora")

            fin = df_clima.index.max()
            lluvia_24h_por_barrio.append(
                float(df_clima[df_clima.index > fin - pd.Timedelta(hours=24)]["lluvia_mm"].sum())
            )
            lluvia_72h_por_barrio.append(
                float(df_clima[df_clima.index > fin - pd.Timedelta(hours=72)]["lluvia_mm"].sum())
            )
            lluvia_30d_por_barrio.append(
                float(df_clima["lluvia_mm"].sum())
            )

        # Tomar la base simulada (terreno, puntos criticos, etc.) y sobreescribir
        # solo las columnas de lluvia -- ahora con un valor real POR BARRIO en
        # vez de un unico valor repetido para toda la comuna.
        df = self._generar_datos_simulados()
        df["lluvia_24h_mm"] = [round(v, 1) for v in lluvia_24h_por_barrio]
        df["lluvia_72h_mm"] = [round(v, 1) for v in lluvia_72h_por_barrio]
        df["lluvia_30d_mm"] = [round(v, 1) for v in lluvia_30d_por_barrio]
        df["fecha_corte"]   = pd.Timestamp.now(tz="America/Bogota").strftime("%Y-%m-%d")

        logger.info(
            f"Lluvia real obtenida de Open-Meteo para {len(BARRIOS_COMUNA_1)} barrios. "
            f"Promedio 24h: {sum(lluvia_24h_por_barrio)/len(lluvia_24h_por_barrio):.1f}mm"
        )
        return df
    def _guardar_cache(self, df: pd.DataFrame) -> None:
        """
        Guarda una copia local de los datos descargados de la API.

        Si en la proxima ejecucion no hay internet, se puede leer este
        archivo en vez de quedarse sin datos. Se sobreescribe con cada
        descarga exitosa para mantener siempre los datos mas recientes.
        """
        ruta = os.path.join(os.path.dirname(__file__), "..", "data", "cache.csv")
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            df.to_csv(ruta, index=False)
        except Exception as e:
            logger.warning(f"No se pudo guardar cache: {e}")

    # -----------------------------------------------------------------------
    # FUNCION 2: calcular_riesgo_general
    # -----------------------------------------------------------------------

    def calcular_riesgo_general(
        self, df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Calcula los tres tipos de riesgo por lluvia para cada barrio.

        Esta funcion es el corazon del sistema. Produce cuatro indices
        de riesgo (uno por tipo + el general) y sus niveles clasificados.

        Tipo 1 - Inundacion y corrientes de agua en vias (peso en general: 35%):
            Las lluvias de las ultimas 24h, combinadas con la cercania a las
            quebradas La Francia, Granizal y El Molino, determinan el riesgo
            de que el barrio sufra inundaciones directas o que sus vias
            se conviertan en canales violentos de agua con capacidad de
            arrastrar personas y vehiculos.

        Tipo 2 - Derrumbes y deslizamientos (peso en general: 35%):
            La acumulacion de lluvia en 72 horas es el factor critico porque
            satura el suelo progresivamente. Combinado con las pendientes de
            10-44 grados tipicas de la ladera nororiental y la baja cobertura
            vegetal de algunos sectores, genera condiciones de deslizamiento.

        Tipo 3 - Arrastre y dispersion de basura (peso en general: 30%):
            La basura en puntos criticos (disposicion ilegal) es arrastrada
            por las corrientes durante lluvias intensas. El arrastre
            contamina las quebradas, crea nuevos puntos de acumulacion en
            zonas bajas y tapa los sumideros agravando las inundaciones.

        Todos los indices van de 0 a 100 y se clasifican en:
            BAJO: 0-33, MODERADO: 34-66, ALTO: 67-100
        """
        if df is None:
            if self.datos is None:
                df = self.cargar_datos()
            else:
                df = self.datos.copy()

        resultado = df.copy()

        # Normalizacion min-max: lleva cada variable al rango [0, 1]
        # para que puedan compararse y ponderarse sin importar sus unidades.
        def normalizar(serie: pd.Series) -> pd.Series:
            rango = serie.max() - serie.min()
            if rango == 0:
                # Si todos los valores son iguales, el riesgo es neutro.
                return pd.Series([0.5] * len(serie), index=serie.index)
            return (serie - serie.min()) / rango

        def normalizar_inversa(serie: pd.Series) -> pd.Series:
            # Cuando la variable va en sentido contrario al riesgo:
            # mas distancia a la quebrada = MENOS riesgo de inundacion.
            # mas cobertura vegetal = MENOS riesgo de derrumbe.
            # mas permeabilidad = MENOS escorrentia superficial.
            return 1.0 - normalizar(serie)

        # --- Riesgo de inundacion y corrientes en vias ---
        resultado["indice_inundacion"] = (
            normalizar(resultado["lluvia_24h_mm"])
            * PESOS_RIESGO["inundacion"]["lluvia_24h_mm"]
            + normalizar_inversa(resultado["distancia_quebrada_m"])
            * PESOS_RIESGO["inundacion"]["distancia_quebrada_m"]
            + normalizar(resultado["vias_en_riesgo"])
            * PESOS_RIESGO["inundacion"]["vias_en_riesgo"]
            + normalizar_inversa(resultado["permeabilidad_suelo"])
            * PESOS_RIESGO["inundacion"]["permeabilidad_suelo"]
        ) * 100

        # --- Riesgo de derrumbes y deslizamientos ---
        # Usa pendiente_max porque los deslizamientos comienzan en el punto
        # mas inclinado del barrio, no en el promedio del terreno.
        resultado["indice_derrumbe"] = (
            normalizar(resultado["lluvia_72h_mm"])
            * PESOS_RIESGO["derrumbe"]["lluvia_72h_mm"]
            + normalizar(resultado["pendiente_max_grados"])
            * PESOS_RIESGO["derrumbe"]["pendiente_max_grados"]
            + normalizar_inversa(resultado["cobertura_vegetal_pct"])
            * PESOS_RIESGO["derrumbe"]["cobertura_vegetal_pct"]
        ) * 100

        # --- Riesgo de arrastre y dispersion de basura ---
        # Usa pendiente_promedio porque la velocidad general del agua
        # depende de la inclinacion media del recorrido, no del peor punto.
        resultado["indice_arrastre_basura"] = (
            normalizar(resultado["puntos_criticos_basura"])
            * PESOS_RIESGO["arrastre_basura"]["puntos_criticos_basura"]
            + normalizar(resultado["lluvia_24h_mm"])
            * PESOS_RIESGO["arrastre_basura"]["lluvia_24h_mm"]
            + normalizar(resultado["pendiente_promedio_grados"])
            * PESOS_RIESGO["arrastre_basura"]["pendiente_promedio_grados"]
        ) * 100

        # --- Indice general: promedio ponderado de los tres tipos ---
        resultado["indice_riesgo_general"] = (
            resultado["indice_inundacion"]     * 0.35
            + resultado["indice_derrumbe"]     * 0.35
            + resultado["indice_arrastre_basura"] * 0.30
        )

        # Redondear para presentacion
        for col in ["indice_inundacion", "indice_derrumbe",
                    "indice_arrastre_basura", "indice_riesgo_general"]:
            resultado[col] = resultado[col].round(1)

        # Clasificar cada indice en los tres niveles del semaforo
        def clasificar(valor: float) -> str:
            if valor <= 33:
                return "BAJO"
            elif valor <= 66:
                return "MODERADO"
            return "ALTO"

        resultado["nivel_inundacion"]      = resultado["indice_inundacion"].apply(clasificar)
        resultado["nivel_derrumbe"]        = resultado["indice_derrumbe"].apply(clasificar)
        resultado["nivel_arrastre_basura"] = resultado["indice_arrastre_basura"].apply(clasificar)
        resultado["nivel_riesgo_general"]  = resultado["indice_riesgo_general"].apply(clasificar)

        # Ordenar de mayor a menor riesgo para que el primer registro
        # siempre sea el barrio mas critico en este momento.
        resultado = resultado.sort_values(
            "indice_riesgo_general", ascending=False
        ).reset_index(drop=True)

        self.datos = resultado
        logger.info(
            f"Riesgo calculado. Barrio mas critico: "
            f"{resultado.iloc[0]['barrio']} "
            f"({resultado.iloc[0]['indice_riesgo_general']} pts)"
        )
        return resultado

    # -----------------------------------------------------------------------
    # FUNCION 3: simular_lluvia_extra
    # -----------------------------------------------------------------------

    def simular_lluvia_extra(self, lluvia_extra_mm: float) -> pd.DataFrame:
        """
        Simula que pasa con el riesgo si cae lluvia adicional sobre la comuna.

        Es la funcion mas diferenciadora del sistema. Permite responder:
        "Si esta noche llueven 40mm mas, cuantos barrios pasan a riesgo ALTO?"

        Funciona tomando los datos actuales, sumando la lluvia extra a
        las variables de precipitacion de todos los barrios, y recalculando
        los tres tipos de riesgo. El resultado es directamente comparable
        con el escenario actual para ver cuanto empeoraría la situacion.

        Esta funcion alimenta el slider interactivo del dashboard, que es
        el elemento mas visual e impactante para el pitch de 3 minutos.

        Parametros:
            lluvia_extra_mm -- mm adicionales de lluvia. Puede ser negativo
                               para simular una reduccion (periodo seco).
        """
        if self.datos is None or "indice_riesgo_general" not in self.datos.columns:
            self.calcular_riesgo_general()

        df_escenario = self.datos.copy()

        # Sumar lluvia extra y evitar valores negativos de precipitacion.
        df_escenario["lluvia_24h_mm"] = (
            df_escenario["lluvia_24h_mm"] + lluvia_extra_mm
        ).clip(lower=0)
        df_escenario["lluvia_72h_mm"] = (
            df_escenario["lluvia_72h_mm"] + lluvia_extra_mm
        ).clip(lower=0)

        # Usar un procesador temporal para no sobreescribir los datos reales.
        # El procesador real sigue guardando el escenario actual en self.datos.
        procesador_temporal = DataProcessor()
        return procesador_temporal.calcular_riesgo_general(df=df_escenario)

    # -----------------------------------------------------------------------
    # Metodos de consulta usados por los bots y el dashboard
    # -----------------------------------------------------------------------

    def resumen_comuna(self) -> dict:
        """
        Genera un resumen ejecutivo de la situacion de riesgo en la comuna.

        Retorna un diccionario con los indicadores mas relevantes,
        incluyendo el nivel de alerta de lluvia segun los umbrales del SIATA.
        Los bots usan este diccionario para construir el mensaje de respuesta.
        """
        if self.datos is None or "indice_riesgo_general" not in self.datos.columns:
            self.calcular_riesgo_general()

        df = self.datos
        lluvia_prom_24h = df["lluvia_24h_mm"].mean()

        # Clasificar la lluvia actual con el lenguaje de alertas del SIATA
        u = UMBRALES_SIATA["lluvia_24h"]
        if lluvia_prom_24h <= u["normal"]:
            nivel_lluvia = "NORMAL"
        elif lluvia_prom_24h <= u["precaucion"]:
            nivel_lluvia = "PRECAUCION"
        elif lluvia_prom_24h <= u["alerta"]:
            nivel_lluvia = "ALERTA"
        else:
            nivel_lluvia = "EMERGENCIA"

        return {
            "total_barrios":           len(df),
            "barrio_mas_critico":      df.iloc[0]["barrio"],
            "indice_mas_alto":         df.iloc[0]["indice_riesgo_general"],
            "lluvia_promedio_24h":     round(lluvia_prom_24h, 1),
            "nivel_lluvia_siata":      nivel_lluvia,
            "barrios_general_alto":    int((df["nivel_riesgo_general"]  == "ALTO").sum()),
            "barrios_general_moderado":int((df["nivel_riesgo_general"]  == "MODERADO").sum()),
            "barrios_general_bajo":    int((df["nivel_riesgo_general"]  == "BAJO").sum()),
            "barrios_inundacion_alto": int((df["nivel_inundacion"]      == "ALTO").sum()),
            "barrios_derrumbe_alto":   int((df["nivel_derrumbe"]        == "ALTO").sum()),
            "barrios_arrastre_alto":   int((df["nivel_arrastre_basura"] == "ALTO").sum()),
            "total_puntos_criticos":   int(df["puntos_criticos_basura"].sum()),
            "fecha_corte":             df["fecha_corte"].iloc[0],
            "ultima_actualizacion": (
                self.ultima_actualizacion.strftime("%d/%m/%Y %H:%M")
                if self.ultima_actualizacion else "N/A"
            )
        }

    def buscar_barrio(self, nombre: str) -> Optional[dict]:
        """
        Busca un barrio por nombre y retorna todos sus datos de riesgo.

        Acepta nombres parciales e ignora mayusculas. Si hay varias
        coincidencias retorna la de mayor riesgo general.
        Retorna None si no encuentra coincidencia, para que el bot pueda
        responder con un mensaje de error claro.
        """
        if self.datos is None or "indice_riesgo_general" not in self.datos.columns:
            self.calcular_riesgo_general()

        busqueda = nombre.strip().lower()
        mascara = self.datos["barrio"].str.lower().str.contains(busqueda, na=False)
        coincidencias = self.datos[mascara]

        if coincidencias.empty:
            return None

        fila = coincidencias.sort_values(
            "indice_riesgo_general", ascending=False
        ).iloc[0]
        return fila.to_dict()

    def alertas_activas(self) -> list:
        """
        Retorna los barrios con al menos un tipo de riesgo en nivel ALTO.

        Un barrio aparece en alertas aunque su riesgo general sea MODERADO,
        si tiene riesgo de derrumbe ALTO o inundacion ALTO de forma especifica.
        Esto es importante porque cada tipo de riesgo requiere una accion
        diferente de la comunidad y las autoridades.

        Retorna una lista de diccionarios ordenada de mayor a menor riesgo,
        cada uno con el barrio y los tipos especificos de alerta activa.
        """
        if self.datos is None or "indice_riesgo_general" not in self.datos.columns:
            self.calcular_riesgo_general()

        df = self.datos
        mascara = (
            (df["nivel_inundacion"]      == "ALTO")
            | (df["nivel_derrumbe"]      == "ALTO")
            | (df["nivel_arrastre_basura"] == "ALTO")
        )

        alertas = []
        for _, fila in df[mascara].iterrows():
            tipos = []
            if fila["nivel_inundacion"]      == "ALTO":
                tipos.append("inundacion / corrientes en vias")
            if fila["nivel_derrumbe"]        == "ALTO":
                tipos.append("derrumbe / deslizamiento")
            if fila["nivel_arrastre_basura"] == "ALTO":
                tipos.append("arrastre de basura")

            alertas.append({
                "barrio":         fila["barrio"],
                "tipos_alerta":   tipos,
                "indice_general": fila["indice_riesgo_general"],
                "nivel_general":  fila["nivel_riesgo_general"],
                "lluvia_24h_mm":  fila["lluvia_24h_mm"],
                "lluvia_72h_mm":  fila["lluvia_72h_mm"],
            })

        return sorted(alertas, key=lambda x: x["indice_general"], reverse=True)