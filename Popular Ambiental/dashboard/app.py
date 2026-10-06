"""
Dashboard visual para Popular Ambiental.

Construido con Streamlit para poder mostrar datos interactivos en Python puro.
La caracteristica principal es el simulador de lluvia: un slider que permite
ver en tiempo real como cambian los niveles de riesgo de cada barrio si
llegan lluvias adicionales esta noche.

Para correr localmente:
    streamlit run dashboard/app.py

Para desplegar gratis:
    1. Subir el repositorio a GitHub
    2. Conectarlo en share.streamlit.io
    3. Apuntar al archivo dashboard/app.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
from utils.data_processor import DataProcessor, UMBRALES_SIATA

st.set_page_config(
    page_title="Popular Ambiental - Alertas por Lluvia",
    page_icon="PA",
    layout="wide"
)

# Colores del semaforo de riesgo usados en toda la interfaz
COLOR_NIVEL = {
    "ALTO":     "#e63946",
    "MODERADO": "#f4a261",
    "BAJO":     "#2a9d8f"
}

# Colores para los niveles de alerta de lluvia del SIATA
COLOR_LLUVIA = {
    "NORMAL":     "#2a9d8f",
    "PRECAUCION": "#f4d03f",
    "ALERTA":     "#f4a261",
    "EMERGENCIA": "#e63946"
}


@st.cache_resource
def obtener_processor() -> DataProcessor:
    """
    Crea el DataProcessor una sola vez y lo reutiliza en toda la sesion.

    El decorador cache_resource de Streamlit garantiza que esta funcion
    corre una sola vez sin importar cuantas veces el usuario interactue
    con la pagina. Sin esto, cada click recargaria todos los datos.
    """
    modo = os.getenv("PRODUCCION", "false").lower() == "true"
    p = DataProcessor(modo_produccion=modo)
    p.calcular_riesgo_general()
    return p


def colorear_nivel(val: str) -> str:
    """
    Retorna el estilo CSS para colorear una celda segun su nivel de riesgo.

    Streamlit acepta estilos CSS como strings en el metodo Styler.map.
    """
    color = COLOR_NIVEL.get(val, "#888888")
    return (
        f"background-color: {color}; color: white; "
        f"font-weight: bold; border-radius: 3px; padding: 2px 6px"
    )


def mostrar_alerta_lluvia(resumen: dict):
    """
    Muestra el banner de nivel de lluvia actual segun umbrales SIATA.

    Va en la parte superior del dashboard para que sea lo primero que
    ve el usuario al abrir la pagina. Un banner rojo significa que
    ya se superaron los umbrales de emergencia del SIATA.
    """
    nivel = resumen["nivel_lluvia_siata"]
    lluvia = resumen["lluvia_promedio_24h"]
    color = COLOR_LLUVIA.get(nivel, "#888888")

    st.markdown(
        f"<div style='background-color:{color}; padding:12px 20px; "
        f"border-radius:6px; margin-bottom:10px;'>"
        f"<span style='color:white; font-size:18px; font-weight:bold;'>"
        f"NIVEL DE LLUVIA: {nivel}</span>"
        f"<span style='color:white; font-size:14px; margin-left:20px;'>"
        f"Promedio comunal ultimas 24h: {lluvia} mm</span>"
        f"</div>",
        unsafe_allow_html=True
    )


def mostrar_metricas_riesgo(resumen: dict):
    """
    Muestra los contadores de barrios por tipo de riesgo en columnas.

    Tres columnas para los tres tipos de riesgo, mas una para el total
    de puntos criticos de basura que estan expuestos a ser arrastrados.
    """
    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Barrios: Inundacion ALTO",
        resumen["barrios_inundacion_alto"],
        delta=f"de {resumen['total_barrios']} barrios",
        delta_color="inverse"
    )
    col2.metric(
        "Barrios: Derrumbe ALTO",
        resumen["barrios_derrumbe_alto"],
        delta=f"de {resumen['total_barrios']} barrios",
        delta_color="inverse"
    )
    col3.metric(
        "Barrios: Arrastre basura ALTO",
        resumen["barrios_arrastre_alto"],
        delta=f"de {resumen['total_barrios']} barrios",
        delta_color="inverse"
    )
    col4.metric(
        "Puntos criticos de basura",
        resumen["total_puntos_criticos"],
        delta="en riesgo de arrastre"
    )


def mostrar_simulador_lluvia(processor: DataProcessor, df_actual: pd.DataFrame):
    """
    Simulador interactivo: que pasa si llueve X mm mas esta noche.

    El slider permite mover la lluvia extra de 0 a 80mm.
    Al moverlo, se recalculan todos los riesgos y se muestra cuantos
    barrios cambian de nivel. Este es el elemento mas impactante para
    el pitch porque demuestra el valor predictivo del sistema.
    """
    st.subheader("Simulador de lluvia adicional")
    st.caption(
        "Mueve el slider para ver como cambian los niveles de riesgo "
        "si cae lluvia adicional sobre la comuna"
    )

    lluvia_extra = st.slider(
        label="Lluvia adicional a simular (mm en las proximas horas)",
        min_value=0,
        max_value=80,
        value=0,
        step=5,
        key="slider_lluvia"
    )

    if lluvia_extra > 0:
        df_escenario = processor.simular_lluvia_extra(lluvia_extra_mm=lluvia_extra)

        # Contar cuantos barrios cambian de nivel comparando los dos escenarios
        cambios_alto = (
            (df_escenario["nivel_riesgo_general"] == "ALTO").sum()
            - (df_actual["nivel_riesgo_general"] == "ALTO").sum()
        )

        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Barrios en ALTO (actual)",
            int((df_actual["nivel_riesgo_general"]   == "ALTO").sum())
        )
        col2.metric(
            f"Barrios en ALTO con +{lluvia_extra}mm",
            int((df_escenario["nivel_riesgo_general"] == "ALTO").sum()),
            delta=int(cambios_alto),
            delta_color="inverse"
        )
        col3.metric(
            "Barrio mas critico en escenario",
            df_escenario.iloc[0]["barrio"]
        )

        # Mostrar la tabla del escenario con los nuevos niveles
        mostrar_tabla_riesgos(df_escenario, titulo=f"Riesgos con +{lluvia_extra}mm de lluvia")
    else:
        st.info("Mueve el slider para simular lluvia adicional sobre la comuna.")


def mostrar_tabla_riesgos(df: pd.DataFrame, titulo: str = "Riesgos por barrio"):
    """
    Muestra la tabla de todos los barrios con sus tres tipos de riesgo.

    Las columnas de nivel se colorean con el semaforo para que de un
    vistazo se identifiquen los barrios criticos sin leer los numeros.
    """
    st.subheader(titulo)

    columnas = [
        "barrio", "lluvia_24h_mm",
        "nivel_inundacion",    "indice_inundacion",
        "nivel_derrumbe",      "indice_derrumbe",
        "nivel_arrastre_basura", "indice_arrastre_basura",
        "nivel_riesgo_general", "indice_riesgo_general"
    ]

    nombres = {
        "barrio":                "Barrio",
        "lluvia_24h_mm":         "Lluvia 24h (mm)",
        "nivel_inundacion":      "Inundacion",
        "indice_inundacion":     "Pts. Inundacion",
        "nivel_derrumbe":        "Derrumbe",
        "indice_derrumbe":       "Pts. Derrumbe",
        "nivel_arrastre_basura": "Arrastre basura",
        "indice_arrastre_basura":"Pts. Arrastre",
        "nivel_riesgo_general":  "General",
        "indice_riesgo_general": "Pts. General"
    }

    df_tabla = df[columnas].rename(columns=nombres)

    columnas_nivel = ["Inundacion", "Derrumbe", "Arrastre basura", "General"]
    columnas_pts = ["Pts. Inundacion", "Pts. Derrumbe", "Pts. Arrastre", "Pts. General"]

    formato = {col: "{:.1f}" for col in columnas_pts}
    formato["Lluvia 24h (mm)"] = "{:.1f}"

    tabla_estilizada = df_tabla.style.map(
        colorear_nivel, subset=columnas_nivel
    ).format(formato)

    st.dataframe(tabla_estilizada, width="stretch", hide_index=True)

def mostrar_alertas_activas(processor: DataProcessor):
    """
    Muestra la seccion de alertas activas con sus tipos especificos.

    Cada alerta muestra el barrio, los tipos de riesgo en ALTO y
    la lluvia actual del sector para dar contexto inmediato.
    """
    st.subheader("Alertas activas")
    alertas = processor.alertas_activas()

    if not alertas:
        st.success("No hay barrios con riesgo ALTO en este momento.")
        return

    for alerta in alertas:
        # El borde usa el color del nivel real del barrio.
        # El fondo y el texto tienen colores fijos para que sean legibles
        # tanto en modo claro como en modo oscuro de Streamlit.
        nivel  = alerta["nivel_general"]
        color  = COLOR_NIVEL.get(nivel, "#888888")
        tipos_str = " | ".join(alerta["tipos_alerta"])
        st.markdown(
            f"<div style='"
            f"border-left: 4px solid {color}; "
            f"padding: 10px 16px; margin-bottom: 8px; "
            f"background-color: #1e1e2e; "
            f"border-radius: 4px;'>"
            f"<span style='color:#ffffff; font-weight:bold; font-size:15px;'>"
            f"{alerta['barrio']}</span>"
            f"&nbsp;&nbsp;"
            f"<span style='color:{color}; font-weight:bold;'>"
            f"Riesgo {nivel}</span><br>"
            f"<span style='color:#cccccc; font-size:13px;'>"
            f"Tipos: {tipos_str} &nbsp;|&nbsp; "
            f"Lluvia 24h: {alerta['lluvia_24h_mm']} mm &nbsp;|&nbsp; "
            f"Indice: {alerta['indice_general']} / 100"
            f"</span>"
            f"</div>",
            unsafe_allow_html=True
        )


def mostrar_consulta_barrio(processor: DataProcessor):
    """
    Campo de busqueda para consultar el detalle de un barrio especifico.

    Muestra los tres tipos de riesgo y las variables clave del barrio
    para que el habitante entienda exactamente a que esta expuesto.
    """
    st.subheader("Consulta por barrio")
    nombre = st.text_input(
        "Escribe el nombre del barrio",
        placeholder="Ej: granizal, manrique, la francia...",
        key="busqueda_barrio"
    )

    if not nombre:
        return

    resultado = processor.buscar_barrio(nombre)

    if resultado is None:
        st.error(
            f"No se encontro el barrio '{nombre}'. "
            "Intenta con parte del nombre."
        )
        return

    st.markdown(f"### {resultado['barrio']}")

    col1, col2, col3, col4 = st.columns(4)
    for col, tipo, idx in [
        (col1, "General",  "indice_riesgo_general"),
        (col2, "Inundacion", "indice_inundacion"),
        (col3, "Derrumbe",   "indice_derrumbe"),
        (col4, "Arrastre",   "indice_arrastre_basura"),
    ]:
        nivel_key = tipo.lower().replace(" ", "_")
        nivel_key = f"nivel_{nivel_key}" if tipo != "General" else "nivel_riesgo_general"
        nivel_val = resultado.get(nivel_key, "N/A")
        color = COLOR_NIVEL.get(nivel_val, "#888888")
        col.metric(
            label=tipo,
            value=f"{resultado.get(idx, 0):.1f} pts",
            delta=nivel_val,
            delta_color="off"
        )

    st.write("")
    c1, c2, c3 = st.columns(3)
    c1.metric("Lluvia 24h", f"{resultado.get('lluvia_24h_mm', 'N/A')} mm")
    c2.metric("Lluvia 72h", f"{resultado.get('lluvia_72h_mm', 'N/A')} mm")
    c3.metric("Dist. Quebrada", f"{resultado.get('distancia_quebrada_m', 'N/A')} m")

    c4, c5, c6 = st.columns(3)
    c4.metric("Pendiente promedio", f"{resultado.get('pendiente_promedio_grados', 'N/A')} grados")
    c5.metric("Pendiente maxima",   f"{resultado.get('pendiente_max_grados', 'N/A')} grados")
    c6.metric("Pendiente minima",   f"{resultado.get('pendiente_min_grados', 'N/A')} grados")

    c7, c8, _ = st.columns(3)
    c7.metric("Cobertura vegetal",     f"{resultado.get('cobertura_vegetal_pct', 'N/A')} %")
    c8.metric("Puntos criticos basura", resultado.get("puntos_criticos_basura", "N/A"))


def main():
    """
    Funcion principal que ensambla el dashboard completo.

    Streamlit ejecuta este archivo de arriba a abajo cada vez que el
    usuario interactua. El orden de las llamadas es el orden visual.
    """
    st.title("Popular Ambiental")
    st.markdown(
        "Sistema de monitoreo de riesgo por lluvias -- "
        "**Comuna 1 Popular, Medellin** -- Proyecto Territorio INN 2026"
    )
    st.divider()

    processor = obtener_processor()
    resumen   = processor.resumen_comuna()
    df        = processor.datos

    mostrar_alerta_lluvia(resumen)
    mostrar_metricas_riesgo(resumen)

    st.divider()
    mostrar_alertas_activas(processor)

    st.divider()
    mostrar_simulador_lluvia(processor, df)

    st.divider()
    mostrar_tabla_riesgos(df, titulo="Estado actual de todos los barrios")

    st.divider()
    mostrar_consulta_barrio(processor)

    st.caption(
        f"Datos con corte al {resumen['fecha_corte']} | "
        f"Actualizacion: {resumen['ultima_actualizacion']} | "
        "ITM - Presupuesto Participativo Comuna 1"
    )


if __name__ == "__main__":
    main()