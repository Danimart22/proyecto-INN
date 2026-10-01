"""
Modulo de formato de mensajes para los bots de Telegram y WhatsApp.

Centraliza aqui la construccion de todos los mensajes para que si
se cambia el formato en el futuro, se cambia en un solo lugar y
aplica automaticamente a los dos bots.

El texto usa caracteres ASCII solamente para garantizar compatibilidad
con cualquier version de WhatsApp y Telegram, incluyendo dispositivos
mas antiguos que aun usan la app en la ladera de Medellin.
"""


def mensaje_bienvenida() -> str:
    """
    Mensaje de bienvenida que se envia al escribir 'hola' o '/start'.

    Presenta primero los comandos en lenguaje sencillo (IA) y luego
    los tecnicos, para que la comunidad use los primeros por defecto.
    """
    return (
        "Bienvenido a Popular Ambiental\n"
        "Sistema de alertas por lluvias - Comuna 1 Popular, Medellin\n\n"
        "Te cuento sobre el riesgo de inundaciones, derrumbes y arrastre\n"
        "de basura en tu barrio cuando llueve fuerte.\n\n"
        "Para entender que esta pasando (en lenguaje sencillo):\n"
        "  que pasa              -- como esta la comuna ahora mismo\n"
        "  que pasa en [barrio]  -- como esta tu barrio especifico\n"
        "  alertas               -- barrios en peligro en este momento\n\n"
        "Para ver los datos tecnicos:\n"
        "  resumen               -- numeros y niveles de riesgo\n"
        "  top5                  -- los 5 barrios mas criticos\n"
        "  barrio [nombre]       -- detalle completo de un barrio\n\n"
        "Ejemplos:\n"
        "  que pasa en granizal\n"
        "  que pasa en santo domingo\n"
        "  barrio carpinelo"
    )


def mensaje_resumen(datos: dict) -> str:
    """
    Formatea el resumen de la comuna como texto para el chat.

    Recibe el diccionario de resumen_comuna() y lo convierte en un
    mensaje claro organizado por tipo de riesgo. Se muestra el nivel
    de lluvia segun SIATA porque es el lenguaje de alerta que ya
    conoce la comunidad de Medellin.
    """
    lineas = [
        "ESTADO AMBIENTAL - COMUNA 1 POPULAR",
        f"Fecha: {datos['fecha_corte']}",
        "",
        f"Lluvia promedio ultimas 24h : {datos['lluvia_promedio_24h']} mm",
        f"Nivel de alerta SIATA       : {datos['nivel_lluvia_siata']}",
        "",
        "Barrios en riesgo ALTO por tipo:",
        f"  Inundacion / corrientes : {datos['barrios_inundacion_alto']}",
        f"  Derrumbe / deslizamiento: {datos['barrios_derrumbe_alto']}",
        f"  Arrastre de basura      : {datos['barrios_arrastre_alto']}",
        "",
        "Riesgo general por barrios:",
        f"  Alto     : {datos['barrios_general_alto']}",
        f"  Moderado : {datos['barrios_general_moderado']}",
        f"  Bajo     : {datos['barrios_general_bajo']}",
        "",
        f"Barrio mas critico en este momento: {datos['barrio_mas_critico']}",
        f"  Indice de riesgo: {datos['indice_mas_alto']} / 100",
        "",
        f"Puntos criticos de basura en la comuna: {datos['total_puntos_criticos']}",
        f"Actualizacion: {datos['ultima_actualizacion']}"
    ]
    return "\n".join(lineas)


def mensaje_alertas(alertas: list) -> str:
    """
    Formatea la lista de barrios con riesgo ALTO activo.

    Si no hay alertas activas, da un mensaje tranquilizador pero
    recuerda estar atentos a las condiciones climaticas.
    """
    if not alertas:
        return (
            "No hay barrios con riesgo ALTO en este momento.\n"
            "Sigue pendiente del clima. Si las lluvias aumentan,\n"
            "el sistema actualizara las alertas automaticamente."
        )

    lineas = [
        f"ALERTAS ACTIVAS - {len(alertas)} barrio(s) en riesgo ALTO",
        ""
    ]

    for i, alerta in enumerate(alertas, start=1):
        tipos = ", ".join(alerta["tipos_alerta"])
        lineas.append(
            f"{i}. {alerta['barrio']}\n"
            f"   Riesgo: {tipos}\n"
            f"   Lluvia 24h: {alerta['lluvia_24h_mm']} mm\n"
            f"   Indice general: {alerta['indice_general']} / 100"
        )
        if i < len(alertas):
            lineas.append("")

    return "\n".join(lineas)


def mensaje_barrio(datos: dict) -> str:
    """
    Formatea los datos completos de un barrio como mensaje de chat.

    Muestra los tres tipos de riesgo por separado para que el habitante
    sepa exactamente a que amenaza especifica esta expuesto su barrio
    con las lluvias actuales.
    """
    lineas = [
        f"BARRIO: {datos.get('barrio', 'N/A')}",
        f"Riesgo general: {datos.get('nivel_riesgo_general', 'N/A')} "
        f"({datos.get('indice_riesgo_general', 0)} / 100)",
        "",
        "Riesgo por tipo de evento:",
        f"  Inundacion / corrientes : {datos.get('nivel_inundacion', 'N/A')} "
        f"({datos.get('indice_inundacion', 0)} pts)",
        f"  Derrumbe / deslizamiento: {datos.get('nivel_derrumbe', 'N/A')} "
        f"({datos.get('indice_derrumbe', 0)} pts)",
        f"  Arrastre de basura      : {datos.get('nivel_arrastre_basura', 'N/A')} "
        f"({datos.get('indice_arrastre_basura', 0)} pts)",
        "",
        "Condiciones actuales:",
        f"  Lluvia ultimas 24h : {datos.get('lluvia_24h_mm', 'N/A')} mm",
        f"  Lluvia ultimas 72h : {datos.get('lluvia_72h_mm', 'N/A')} mm",
        f"  Pendiente del suelo: {datos.get('pendiente_grados', 'N/A')} grados",
        f"  Distancia quebrada : {datos.get('distancia_quebrada_m', 'N/A')} metros",
        f"  Puntos criticos    : {datos.get('puntos_criticos_basura', 'N/A')}",
        f"  Cobertura vegetal  : {datos.get('cobertura_vegetal_pct', 'N/A')} %",
        "",
        f"Datos con corte al: {datos.get('fecha_corte', 'N/A')}"
    ]
    return "\n".join(lineas)


def mensaje_top5(df) -> str:
    """
    Muestra los 5 barrios con mayor riesgo general en este momento.

    Para cada barrio incluye el tipo de riesgo predominante para que
    la comunidad sepa cual es la amenaza principal del sector.
    """
    lineas = ["TOP 5 BARRIOS CON MAYOR RIESGO - COMUNA 1", ""]

    for pos, (_, fila) in enumerate(df.head(5).iterrows(), start=1):
        # Determinar cual es el tipo de riesgo mas alto en ese barrio
        riesgos = {
            "inundacion":    fila["indice_inundacion"],
            "derrumbe":      fila["indice_derrumbe"],
            "arrastre":      fila["indice_arrastre_basura"],
        }
        tipo_principal = max(riesgos, key=riesgos.get)

        lineas.append(
            f"{pos}. {fila['barrio']}\n"
            f"   General: {fila['nivel_riesgo_general']} ({fila['indice_riesgo_general']} pts)\n"
            f"   Principal: {tipo_principal} ({riesgos[tipo_principal]:.1f} pts)"
        )

    return "\n".join(lineas)


def mensaje_barrio_no_encontrado(nombre: str) -> str:
    """
    Mensaje de error cuando la busqueda no encuentra el barrio.

    Da una pista practica para que el usuario corrija su busqueda
    en vez de quedarse sin saber que paso.
    """
    return (
        f"No encontre ningun barrio con el nombre '{nombre}'.\n"
        "Intenta con parte del nombre. Ejemplos:\n"
        "  barrio granizal\n"
        "  barrio manrique\n"
        "  barrio popular\n\n"
        "Escribe 'resumen' para ver todos los barrios de la comuna."
    )