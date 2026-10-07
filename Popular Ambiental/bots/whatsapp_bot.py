"""
Bot de WhatsApp para Popular Ambiental via Twilio.

WhatsApp no tiene API publica, por lo que se usa Twilio como intermediario.
Twilio recibe el mensaje del usuario en WhatsApp y hace un POST a este
servidor Flask. Este responde con el texto en formato TwiML y Twilio
se lo envia de vuelta al usuario en WhatsApp.

Flujo completo:
    Usuario en WhatsApp --> Twilio --> este servidor --> Twilio --> Usuario

Funcionalidad identica al bot de Telegram:
    - IA activada: "que pasa" y "que pasa en [barrio]" generan mensajes
      amigables usando la API de Claude (requiere ANTHROPIC_API_KEY).
    - IA inactiva: los mismos comandos responden con formato de texto
      estandar. El bot siempre funciona sin importar si hay API key o no.

Para configurar:
    1. Crear cuenta gratuita en twilio.com
    2. Activar el sandbox de WhatsApp en la consola de Twilio
    3. Agregar las credenciales en .env:
           TWILIO_ACCOUNT_SID=ACxxxxx
           TWILIO_AUTH_TOKEN=tu_token
    4. Configurar el webhook en Twilio: https://tu-url/whatsapp/webhook
    5. Para pruebas locales: ngrok http 5000
"""

import os
import sys
import logging
from dotenv import load_dotenv
from flask import Flask, request, Response

# load_dotenv va antes de cualquier import del proyecto para garantizar
# que las variables de entorno esten listas cuando se cargue telegram_bot,
# que instancia el DataProcessor y lee PRODUCCION al importarse.
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# procesar_comando contiene toda la logica compartida con el bot de Telegram:
# bienvenida, resumen, alertas, top5, barrio, y los comandos de IA
# (que pasa / que pasa en). La IA se activa automaticamente si
# ANTHROPIC_API_KEY esta en el .env, y cae a texto estandar si no.
from bots.telegram_bot import procesar_comando, _tiene_api_ia

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("popular_ambiental.whatsapp")

app = Flask(__name__)


@app.route("/whatsapp/webhook", methods=["POST"])
def webhook():
    """
    Endpoint que recibe mensajes de WhatsApp desde Twilio.

    Twilio hace un POST con el mensaje en el campo Body del formulario.
    La respuesta debe ser XML en formato TwiML para que Twilio pueda
    enviarsela al usuario.

    Los comandos de IA pueden tardar 2-5 segundos. Twilio espera hasta
    15 segundos antes de declarar timeout, suficiente para el prototipo.
    """
    try:
        mensaje_entrante = request.form.get("Body", "").strip()
        remitente = request.form.get("From", "desconocido")

        logger.info(f"WhatsApp de {remitente}: {mensaje_entrante[:40]}")

        if not mensaje_entrante:
            return Response("<Response></Response>", mimetype="text/xml"), 400

        respuesta_texto = procesar_comando(mensaje_entrante)
        return Response(_construir_twiml(respuesta_texto), mimetype="text/xml")

    except Exception as e:
        logger.error(f"Error en webhook WhatsApp: {e}")
        return Response(
            _construir_twiml(
                "Ocurrio un error procesando tu mensaje. "
                "Por favor intenta de nuevo."
            ),
            mimetype="text/xml"
        ), 500


def _construir_twiml(texto: str) -> str:
    """
    Convierte texto plano en XML TwiML que espera Twilio.

    Escapa caracteres especiales para que el XML sea valido incluso
    si el texto generado por la IA contiene simbolos como < o &.
    """
    texto_seguro = (
        texto
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"<Response><Message>{texto_seguro}</Message></Response>"


@app.route("/health", methods=["GET"])
def health():
    """
    Endpoint de salud del servidor.

    Railway, Render y otras plataformas llaman periodicamente a este
    endpoint. Si no responde con 200, la plataforma reinicia el servidor.
    Incluye el estado de la IA para facilitar el diagnostico en produccion.
    """
    return {
        "status":    "ok",
        "servicio":  "Popular Ambiental - WhatsApp Bot",
        "ia_activa": _tiene_api_ia(),
    }, 200


if __name__ == "__main__":
    puerto     = int(os.getenv("PORT", 5000))
    produccion = os.getenv("PRODUCCION", "false").lower() == "true"

    logger.info(
        f"Servidor WhatsApp iniciando en puerto {puerto} | "
        f"IA narrativa: {'activa' if _tiene_api_ia() else 'inactiva (agrega ANTHROPIC_API_KEY en .env)'}"
    )
    app.run(host="0.0.0.0", port=puerto, debug=not produccion)