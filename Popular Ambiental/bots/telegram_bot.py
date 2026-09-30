"""
Bot de Telegram para Popular Ambiental.
Usa python-telegram-bot v21 con asyncio. Compatible con Python 3.14.

Para correr:
    1. Crear bot con @BotFather en Telegram
    2. Poner el token en .env: TELEGRAM_TOKEN=tu_token_aqui
    3. python bots/telegram_bot.py
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("popular_ambiental.telegram")

MODO_PRODUCCION = os.getenv("PRODUCCION", "false").lower() == "true"
processor = DataProcessor(modo_produccion=MODO_PRODUCCION)

CMDS_BIENVENIDA = frozenset({"/start", "hola", "inicio", "start", "ayuda", "/ayuda", "help"})
CMDS_RESUMEN    = frozenset({"resumen", "/resumen"})
CMDS_ALERTAS    = frozenset({"alertas", "/alertas"})
CMDS_TOP5       = frozenset({"top5", "/top5", "top 5"})


def procesar_comando(texto: str) -> str:
    """
    Logica central del bot. Sincrona para que tambien pueda usarla
    whatsapp_bot.py sin cambios.
    """
    t = texto.strip().lower()

    if t in CMDS_BIENVENIDA:
        return mensaje_bienvenida()
    if t in CMDS_RESUMEN:
        return mensaje_resumen(processor.resumen_comuna())
    if t in CMDS_ALERTAS:
        return mensaje_alertas(processor.alertas_activas())
    if t in CMDS_TOP5:
        return mensaje_top5(processor.calcular_riesgo_general())
    if "barrio" in t:
        nombre = t.replace("/barrio", "").replace("barrio", "").strip()
        if not nombre:
            return "Escribe el nombre del barrio despues del comando.\nEjemplo: barrio granizal"
        resultado = processor.buscar_barrio(nombre)
        return mensaje_barrio(resultado) if resultado else mensaje_barrio_no_encontrado(nombre)

    return "No entendi ese comando.\nEscribe 'ayuda' para ver los comandos disponibles."


async def handle_message(update, context) -> None:
    """Handler para mensajes de texto normales (sin slash)."""
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
    ya no crea un loop automaticamente si no hay uno activo.
    La solucion es crearlo explicitamente con new_event_loop() y
    registrarlo con set_event_loop() antes de llamar run_polling().
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
    logger.info("Datos listos. Iniciando bot...")

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    for cmd in ["start", "resumen", "alertas", "top5", "ayuda", "barrio"]:
        app.add_handler(CommandHandler(cmd, handle_command))

    # Crear el event loop explicitamente antes de run_polling().
    # Esto es necesario en Python 3.12+ donde asyncio.get_event_loop()
    # ya no crea un loop automaticamente en el thread principal.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info("Bot de Telegram corriendo. Ctrl+C para detener.")
    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()