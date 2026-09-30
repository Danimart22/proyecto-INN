"""
Bot de WhatsApp para Popular Ambiental via Twilio.

WhatsApp no tiene API publica, por lo que se usa Twilio como intermediario.
Twilio recibe el mensaje del usuario en WhatsApp y hace un POST a este
servidor Flask. Este responde con el texto en formato TwiML y Twilio
se lo envia de vuelta al usuario en WhatsApp.

Flujo completo:
    Usuario en WhatsApp --> Twilio --> este servidor --> Twilio --> Usuario

Para configurar:
    1. Crear cuenta gratuita en twilio.com
    2. Activar el sandbox de WhatsApp en la consola de Twilio
    3. Agregar las credenciales en .env
    4. Configurar el webhook en Twilio apuntando a /whatsapp/webhook
    5. Para pruebas locales usar ngrok: ngrok http 5000

En produccion se despliega en Railway o Render (plan gratuito disponible).
"""

import os
import sys
import logging
from flask import Flask, request, Response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Importar la misma funcion de logica que usa el bot de Telegram.
# Esto garantiza que los dos bots siempre tengan exactamente las mismas
# respuestas sin duplicar codigo.
from bots.telegram_bot import procesar_comando

logger = logging.getLogger("popular_ambiental.whatsapp")
MODO_PRODUCCION = os.getenv("PRODUCCION", "false").lower() == "true"

app = Flask(__name__)


@app.route("/whatsapp/webhook", methods=["POST"])
def webhook():
    """
    Endpoint que recibe mensajes de WhatsApp desde Twilio.

    Twilio hace un POST con el mensaje en el campo 'Body' del formulario.
    La respuesta debe ser XML en formato TwiML para que Twilio pueda
    enviarsela al usuario. Sin ese formato, el mensaje no se entrega.
    """
    try:
        mensaje_entrante = request.form.get("Body", "").strip()
        remitente = request.form.get("From", "desconocido")

        logger.info(f"WhatsApp de {remitente}: {mensaje_entrante[:40]}")

        if not mensaje_entrante:
            return Response("<Response></Response>", mimetype="text/xml"), 400

        respuesta_texto = procesar_comando(mensaje_entrante)
        return Response(
            _construir_twiml(respuesta_texto),
            mimetype="text/xml"
        )

    except Exception as e:
        logger.error(f"Error en webhook WhatsApp: {e}")
        return Response(
            _construir_twiml("Error al procesar el mensaje. Intenta de nuevo."),
            mimetype="text/xml"
        ), 500


def _construir_twiml(texto: str) -> str:
    """
    Convierte texto plano en el formato XML que espera Twilio (TwiML).

    Escapa los caracteres especiales para que el XML sea valido
    incluso si el texto del usuario contiene simbolos como < o &.
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
    Endpoint de verificacion de salud del servidor.

    Railway, Render y otras plataformas de hosting llaman periodicamente
    a este endpoint para verificar que el servidor esta activo.
    Si no responde con 200, la plataforma reinicia el servidor.
    """
    return {"status": "ok", "servicio": "Popular Ambiental - WhatsApp Bot"}, 200


if __name__ == "__main__":
    puerto = int(os.getenv("PORT", 5000))
    debug_mode = not MODO_PRODUCCION
    logger.info(f"Servidor WhatsApp iniciando en puerto {puerto}")
    app.run(host="0.0.0.0", port=puerto, debug=debug_mode)
