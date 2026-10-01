"""
Bot de Telegram para Popular Ambiental.
Usa python-telegram-bot v21 con asyncio. Compatible con Python 3.14.

Comandos disponibles:
    hola / ayuda            -- bienvenida y lista de comandos
    resumen                 -- estado tecnico de la comuna (datos y numeros)
    que pasa                -- explicacion amigable del estado de la comuna (IA)
    alertas                 -- barrios en riesgo ALTO con explicacion amigable (IA)
    top5                    -- los 5 barrios mas criticos
    barrio [nombre]         -- datos tecnicos de un barrio
    que pasa en [nombre]    -- explicacion amigable de un barrio (IA)

Los comandos con IA requieren ANTHROPIC_API_KEY en el .env.
Si no esta configurada, el bot usa el formato de texto estandar como fallback.
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.data_processor import DataProcessor
from utils.messages import (
    mensaje_bienvenida,
    mensaje_resumen,
    mensaje_alertas,
    mensaje_barrio,
    mensaje_top5,
    mensaje_barrio_no_encontrado
)
from utils.ai_narrator import (
    narrar_resumen_comuna,
    narrar_barrio,
    narrar_alertas
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("popular_ambiental.telegram")

MODO_PRODUCCION = os.getenv("PRODUCCION", "false").lower() == "true"
processor = DataProcessor(modo_produccion=MODO_PRODUCCION)

# Conjuntos para lookup O(1)
CMDS_BIENVENIDA = frozenset({"/start", "hola", "inicio", "start", "ayuda", "/ayuda", "help"})
CMDS_RESUMEN    = frozenset({"resumen", "/resumen"})
CMDS_ALERTAS    = frozenset({"alertas", "/alertas"})
CMDS_TOP5       = frozenset({"top5", "/top5", "top 5"})
CMDS_QUE_PASA   = frozenset({"que pasa", "qué pasa", "/quepasa"})

# Prefijos que activan la explicacion amigable de un barrio especifico.
# Se detectan por startswith para soportar "que pasa en granizal" etc.
PREFIJOS_QUE_PASA_EN = ("que pasa en ", "qué pasa en ", "/quepasaen ")


def _tiene_api_ia() -> bool:
    """Verifica si esta disponible la API de IA para mensajes amigables."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def procesar_comando(texto: str) -> str:
    """
    Logica central del bot. Recibe texto y retorna la respuesta.

    Sincrona para que whatsapp_bot.py pueda importarla sin cambios.
    Los comandos de IA llaman la API de Claude si hay API key disponible;
    si no, usan el formato de texto estandar como fallback automatico.

    Jerarquia de comandos:
        1. Bienvenida y ayuda
        2. Comandos de IA (que pasa / que pasa en)
        3. Comandos tecnicos estandar (resumen, alertas, top5, barrio)
    """
    t = texto.strip().lower()

    # --- Bienvenida ---
    if t in CMDS_BIENVENIDA:
        return mensaje_bienvenida()

    # --- Explicacion amigable con IA: estado general de la comuna ---
    if t in CMDS_QUE_PASA:
        logger.info("Generando explicacion amigable de la comuna con IA...")
        datos = processor.resumen_comuna()
        respuesta_ia = narrar_resumen_comuna(datos)
        if respuesta_ia:
            return respuesta_ia
        # Fallback si no hay API key o falla la llamada
        logger.info("IA no disponible, usando formato estandar.")
        return mensaje_resumen(datos)

    # --- Explicacion amigable con IA: barrio especifico ---
    for prefijo in PREFIJOS_QUE_PASA_EN:
        if t.startswith(prefijo):
            nombre = t[len(prefijo):].strip()
            if not nombre:
                return (
                    "Escribe el nombre del barrio despues del comando.\n"
                    "Ejemplo: que pasa en granizal"
                )
            resultado = processor.buscar_barrio(nombre)
            if not resultado:
                return mensaje_barrio_no_encontrado(nombre)
            logger.info(f"Generando explicacion amigable de {nombre} con IA...")
            respuesta_ia = narrar_barrio(resultado)
            if respuesta_ia:
                return respuesta_ia
            # Fallback si no hay API key o falla la llamada
            logger.info("IA no disponible, usando formato estandar.")
            return mensaje_barrio(resultado)

    # --- Alertas (con IA si esta disponible) ---
    if t in CMDS_ALERTAS:
        alertas = processor.alertas_activas()
        if _tiene_api_ia() and alertas:
            logger.info("Generando mensaje de alertas con IA...")
            respuesta_ia = narrar_alertas(alertas)
            if respuesta_ia:
                return respuesta_ia
        return mensaje_alertas(alertas)

    # --- Comandos tecnicos estandar ---
    if t in CMDS_RESUMEN:
        return mensaje_resumen(processor.resumen_comuna())
    if t in CMDS_TOP5:
        return mensaje_top5(processor.calcular_riesgo_general())
    if "barrio" in t:
        nombre = t.replace("/barrio", "").replace("barrio", "").strip()
        if not nombre:
            return (
                "Escribe el nombre del barrio despues del comando.\n"
                "Ejemplo: barrio granizal"
            )
        resultado = processor.buscar_barrio(nombre)
        return mensaje_barrio(resultado) if resultado else mensaje_barrio_no_encontrado(nombre)

    return (
        "No entendi ese comando.\n"
        "Escribe 'ayuda' para ver los comandos disponibles."
    )


async def handle_message(update, context) -> None:
    """
    Handler para mensajes de texto normales (sin slash).

    Los comandos de IA pueden tardar 2-5 segundos en responder porque
    hacen una llamada a la API de Claude. El indicador de 'escribiendo...'
    de Telegram se muestra automaticamente mientras el handler procesa.
    """
    texto = update.message.text or ""
    logger.info(f"Mensaje de {update.effective_user.first_name}: {texto[:40]}")
    try:
        await update.message.reply_text(procesar_comando(texto))
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        await update.message.reply_text("Ocurrio un error. Por favor intenta de nuevo.")


async def handle_command(update, context) -> None:
    """Handler para comandos con slash (/start, /resumen, etc)."""
    try:
        await update.message.reply_text(procesar_comando(update.message.text))
    except Exception as e:
        logger.error(f"Error en comando {update.message.text}: {e}")
        await update.message.reply_text("Ocurrio un error. Por favor intenta de nuevo.")


def main() -> None:
    """
    Construye y arranca el bot en modo polling.

    Python 3.14 cambio el comportamiento de asyncio.get_event_loop():
    ya no crea un loop automaticamente. Se crea explicitamente antes de
    llamar run_polling() para evitar el RuntimeError.
    """
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error(
            "Falta TELEGRAM_TOKEN en las variables de entorno.\n"
            "Crealo con @BotFather en Telegram y pegalo en el archivo .env"
        )
        return

    try:
        from telegram.ext import Application, MessageHandler, CommandHandler, filters
    except ImportError:
        logger.error("Instala: python -m pip install python-telegram-bot==21.6")
        return

    logger.info("Cargando datos iniciales...")
    processor.calcular_riesgo_general()

    tiene_ia = _tiene_api_ia()
    logger.info(
        f"Datos listos. IA narrativa: {'activa' if tiene_ia else 'inactiva (agrega ANTHROPIC_API_KEY en .env)'}. "
        "Iniciando bot..."
    )

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    for cmd in ["start", "resumen", "alertas", "top5", "ayuda", "barrio", "quepasa"]:
        app.add_handler(CommandHandler(cmd, handle_command))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info("Bot de telegram corriendo ctrl+C para detener.")
    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()