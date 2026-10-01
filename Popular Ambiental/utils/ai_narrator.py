"""
Modulo de narracion inteligente para la comunidad de la Comuna 1.

Usa la API de Claude para convertir los numeros del sistema en mensajes
claros y cercanos, como si los escribiera el presidente de la JAC para
el chat del barrio. Sin terminos tecnicos, sin indices, sin jerga.

Si ANTHROPIC_API_KEY no esta en el .env, las funciones retornan None
y el bot cae automaticamente al formato de texto estandar, asi que
el sistema siempre funciona independientemente de si hay API key o no.

Costo estimado por mensaje: ~$0.004 USD (menos de 2 pesos colombianos).
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("popular_ambiental.ai_narrator")

# Instruccion base que define el tono y restricciones para todos los mensajes.
# Se incluye en todos los prompts para mantener consistencia sin repetir
# la misma instruccion en cada funcion.
_INSTRUCCION_BASE = """
Eres el sistema de alertas ambientales de la Comuna 1 Popular de Medellin, Colombia.
Tu trabajo es hablarle a la comunidad en su propio lenguaje, como vecino a vecino.

Reglas que nunca puedes romper:
- Jamas uses estas palabras: indice, normalizacion, variable, algoritmo, modelo,
  puntaje, PM2.5, permeabilidad, escorrentia, dataset, dataframe, threshold.
- Si el riesgo es ALTO dilo con urgencia pero sin generar panico.
- Si el riesgo es BAJO tranquiliza pero recuerda estar atentos.
- Habla en colombiano cuando sea natural (parcero, listo, ojo con eso).
- Maximo 4 parrafos cortos. La gente lo va a leer en el celular.
- Siempre termina con una recomendacion concreta de que hacer ahora mismo.
""".strip()


def _llamar_api(prompt: str, max_tokens: int = 500) -> Optional[str]:
    """
    Hace la llamada a la API de Claude y retorna el texto generado.

    Centraliza el manejo de errores para que las funciones que llaman
    a esta no tengan que preocuparse por ImportError ni por excepciones
    de red. Siempre retorna None en caso de fallo para que el bot pueda
    usar el formato de texto estandar como alternativa.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic
        cliente = anthropic.Anthropic(api_key=api_key)
        respuesta = cliente.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return respuesta.content[0].text

    except ImportError:
        logger.warning(
            "Libreria anthropic no instalada. "
            "Ejecuta: python -m pip install anthropic"
        )
        return None
    except Exception as e:
        logger.error(f"Error llamando a la API de Claude: {e}")
        return None


def narrar_resumen_comuna(datos: dict) -> Optional[str]:
    """
    Genera un mensaje amigable con el estado general de la comuna.

    Recibe el diccionario de resumen_comuna() y produce un texto como
    el que enviaria el presidente de la JAC al chat del barrio cuando
    hay lluvia fuerte o cuando la situacion es critica.

    Retorna None si no hay API key o si la llamada falla, para que
    el bot use el mensaje formateado estandar como fallback.
    """
    nivel_lluvia   = datos.get("nivel_lluvia_siata", "NORMAL")
    lluvia         = datos.get("lluvia_promedio_24h", 0)
    barrio_critico = datos.get("barrio_mas_critico", "")
    barrios_alto   = datos.get("barrios_general_alto", 0)
    total          = datos.get("total_barrios", 12)
    inund_alto     = datos.get("barrios_inundacion_alto", 0)
    derrumbe_alto  = datos.get("barrios_derrumbe_alto", 0)
    arrastre_alto  = datos.get("barrios_arrastre_alto", 0)
    fecha          = datos.get("fecha_corte", "hoy")

    prompt = f"""
{_INSTRUCCION_BASE}

Situacion actual de la Comuna 1 Popular al {fecha}:
- En las ultimas 24 horas ha llovido {lluvia} mm en promedio (nivel de alerta: {nivel_lluvia}).
- El barrio que mas atencion necesita ahora mismo es {barrio_critico}.
- De los 12 barrios de la comuna, {barrios_alto} estan en situacion critica.
- {inund_alto} barrios tienen riesgo de que el agua baje fuerte por las calles o se desborde la quebrada.
- {derrumbe_alto} barrios tienen riesgo de que se caiga un talude o deslice tierra.
- {arrastre_alto} barrios tienen puntos de basura que la lluvia puede arrastrar hacia las quebradas.

Escribe el mensaje para el chat de la JAC de la comunidad. Explica que esta pasando
en el territorio hoy, cuales son los peligros concretos y que deben hacer los vecinos
ahora mismo para protegerse. Sé directo y claro.
""".strip()

    return _llamar_api(prompt, max_tokens=500)


def narrar_barrio(datos: dict) -> Optional[str]:
    """
    Genera un mensaje amigable con el estado de un barrio especifico.

    Recibe el diccionario de buscar_barrio() y produce un texto pensado
    para un habitante de ese barrio que pregunto por WhatsApp como esta
    su sector. Debe ser especifico con las caracteristicas de ese barrio.

    Retorna None si no hay API key o si la llamada falla.
    """
    barrio          = datos.get("barrio", "tu barrio")
    nivel_general   = datos.get("nivel_riesgo_general", "BAJO")
    nivel_inund     = datos.get("nivel_inundacion", "BAJO")
    nivel_derrumbe  = datos.get("nivel_derrumbe", "BAJO")
    nivel_arrastre  = datos.get("nivel_arrastre_basura", "BAJO")
    lluvia_24h      = datos.get("lluvia_24h_mm", 0)
    lluvia_72h      = datos.get("lluvia_72h_mm", 0)
    distancia_q     = datos.get("distancia_quebrada_m", 0)
    pendiente_max   = datos.get("pendiente_max_grados", 0)
    pendiente_prom  = datos.get("pendiente_promedio_grados", 0)
    puntos_basura   = datos.get("puntos_criticos_basura", 0)
    cobertura       = datos.get("cobertura_vegetal_pct", 0)

    # Traducir niveles a lenguaje cotidiano para el prompt
    _nivel = {"ALTO": "critica", "MODERADO": "media", "BAJO": "tranquila"}
    _inund = {"ALTO": "hay riesgo real de que el agua baje fuerte por las calles",
               "MODERADO": "hay que estar ojo con las calles si sigue lloviendo",
               "BAJO": "las calles estan bien por ahora"}
    _derr  = {"ALTO": "hay peligro de que se caiga un talude o deslice tierra",
               "MODERADO": "los taludes hay que vigilarlos si sigue lloviendo",
               "BAJO": "los taludes estan estables por ahora"}
    _arr   = {"ALTO": "la lluvia puede arrastrar la basura a la quebrada y taparla",
               "MODERADO": "los puntos de basura pueden contaminarse si llueve mas",
               "BAJO": "los puntos de basura estan bajo control"}

    prompt = f"""
{_INSTRUCCION_BASE}

Estado actual del barrio {barrio}:
- Situacion general: {_nivel.get(nivel_general, nivel_general)}
- Con el agua: {_inund.get(nivel_inund, nivel_inund)}
- Con los taludes: {_derr.get(nivel_derrumbe, nivel_derrumbe)}
- Con la basura: {_arr.get(nivel_arrastre, nivel_arrastre)}
- Ha llovido {lluvia_24h} mm en las ultimas 24 horas y {lluvia_72h} mm en los ultimos 3 dias
- La parte mas inclinada del barrio tiene {pendiente_max} grados de pendiente
  (el promedio del barrio es {pendiente_prom} grados)
- Hay {puntos_basura} puntos donde se bota basura de manera ilegal
- Solo el {cobertura}% del barrio tiene arboles o plantas que retienen el suelo
- La quebrada mas cercana esta a {distancia_q} metros

Escribe un mensaje para un vecino de {barrio} que pregunto como esta su barrio hoy.
Se especifico con {barrio}: menciona las calles inclinadas, la cercania a la quebrada
si aplica, y los puntos de basura. Dile exactamente que debe hacer o no hacer hoy.
""".strip()

    return _llamar_api(prompt, max_tokens=500)


def narrar_alertas(alertas: list) -> Optional[str]:
    """
    Genera un mensaje de alerta amigable cuando hay barrios en riesgo ALTO.

    Recibe la lista de alertas_activas() y produce un texto urgente
    pero claro, que llame a la accion sin generar panico desmedido.

    Retorna None si no hay API key, si la lista esta vacia o si falla.
    """
    if not alertas:
        return None

    # Resumir las alertas en texto plano para el prompt
    resumen_alertas = []
    for a in alertas[:5]:  # maximo 5 alertas para no saturar el prompt
        tipos = ", ".join(a.get("tipos_alerta", []))
        resumen_alertas.append(
            f"- {a['barrio']}: {tipos} "
            f"(llovio {a.get('lluvia_24h_mm', 0)} mm en las ultimas 24h)"
        )

    prompt = f"""
{_INSTRUCCION_BASE}

En este momento hay {len(alertas)} barrios de la Comuna 1 en situacion critica:

{chr(10).join(resumen_alertas)}

Escribe un mensaje de alerta para el chat comunitario. Debe:
- Nombrar los barrios afectados y explicar brevemente que peligro tiene cada uno
- Dar instrucciones claras de que hacer ahora mismo (no salir si llueve, alejarse de
  quebradas, no botar basura, revisar techos, avisar a vecinos mayores, etc.)
- Tener urgencia sin generar panico
- No ser mas de 3 parrafos
""".strip()

    return _llamar_api(prompt, max_tokens=450)