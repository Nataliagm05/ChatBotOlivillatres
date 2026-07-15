"""
citas_flow.py
=============
Flujo conversacional (slot-filling) para agendar citas.

El estado de "en qué paso va la conversación" NO se guarda en memoria del
proceso Python: se guarda en la propia fila de Supabase (qué campos ya
están rellenos). Así funciona igual aunque Render reinicie el servicio
por inactividad, o si en el futuro hay más de un worker de gunicorn.

Variables de entorno necesarias (configúralas en Render → Environment):
  SUPABASE_URL            (mismo proyecto que FacturaSync)
  SUPABASE_SERVICE_KEY    (service role key, NO la anon key: necesita bypass de RLS)
  RESEND_API_KEY          (opcional, para notificar por email a la empresa)
  CITAS_FROM_EMAIL        (opcional, por defecto citas@olivillatres.es)
  CITAS_NOTIFY_EMAIL      (opcional, por defecto info@olivillatres.com)
"""

import os
from datetime import datetime, timezone
import requests

try:
    import dateparser
except ImportError:
    dateparser = None

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Supabase tiene dos sistemas de claves: las nuevas (sb_secret_..., sb_publishable_...)
# y las antiguas basadas en JWT (service_role/anon, que empiezan por "eyJ...").
# Con las nuevas, la clave va SOLO en la cabecera "apikey"; si además se manda en
# "Authorization: Bearer", Supabase la rechaza como "Invalid JWT". Con las antiguas,
# hay que mandarla en ambas cabeceras. Detectamos cuál es por el prefijo.
if SUPABASE_SERVICE_KEY.startswith("sb_"):
    HEADERS = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }
else:
    HEADERS = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_FROM = os.environ.get("CITAS_FROM_EMAIL", "citas@olivillatres.es")
NOTIFY_TO = os.environ.get("CITAS_NOTIFY_EMAIL", "info@olivillatres.com")


# Orden en el que se piden los datos. El primer campo vacío de la lista
# es "en qué paso está" la conversación en todo momento.
CAMPOS_ORDEN = ["nombre", "telefono", "email", "fecha_texto", "hora_texto", "lugar"]

PREGUNTAS = {
    "nombre":      "¡Perfecto! Para agendar la visita, ¿cuál es tu nombre?",
    "telefono":    "Gracias{coma_nombre}. ¿Qué teléfono de contacto nos dejas?",
    "email":       "¿Y tu email? Así podemos avisarte si hay algún cambio en la cita.",
    "fecha_texto": '¿Qué día te vendría bien? (por ejemplo: "el viernes" o "20 de julio")',
    "hora_texto":  "¿A qué hora te viene mejor?",
    "lugar":       "Por último, ¿en qué dirección o localidad sería la visita?",
}

PALABRAS_CANCELAR = {"cancelar", "olvidalo", "olvídalo", "dejalo", "déjalo", "no quiero", "nada", "para"}


def _activo():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _get_borrador(session_id):
    url = f"{SUPABASE_URL}/rest/v1/citas"
    params = {
        "session_id": f"eq.{session_id}",
        "estado": "eq.borrador",
        "order": "creado_en.desc",
        "limit": "1",
    }
    r = requests.get(url, headers=HEADERS, params=params, timeout=10)
    r.raise_for_status()
    filas = r.json()
    return filas[0] if filas else None


def _crear_borrador(session_id):
    url = f"{SUPABASE_URL}/rest/v1/citas"
    r = requests.post(
        url,
        headers={**HEADERS, "Prefer": "return=representation"},
        json={"session_id": session_id, "estado": "borrador"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()[0]


def _actualizar(cita_id, campos):
    url = f"{SUPABASE_URL}/rest/v1/citas"
    campos = {**campos, "actualizado_en": datetime.now(timezone.utc).isoformat()}
    r = requests.patch(
        url,
        headers={**HEADERS, "Prefer": "return=representation"},
        params={"id": f"eq.{cita_id}"},
        json=campos,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()[0]


def _siguiente_campo_vacio(cita):
    for campo in CAMPOS_ORDEN:
        if not cita.get(campo):
            return campo
    return None


def _parsear_fecha(texto):
    if not dateparser:
        return None
    dt = dateparser.parse(texto, languages=["es"], settings={"PREFER_DATES_FROM": "future"})
    return dt.date().isoformat() if dt else None


def _parsear_hora(texto):
    if not dateparser:
        return None
    dt = dateparser.parse(texto, languages=["es"])
    return dt.time().isoformat(timespec="minutes") if dt else None


def _notificar_empresa(cita):
    if not RESEND_API_KEY:
        return
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": NOTIFY_FROM,
                "to": [NOTIFY_TO],
                "subject": f"Nueva solicitud de cita — {cita.get('nombre', 'cliente web')}",
                "html": (
                    "<p>Nueva solicitud de cita desde el chatbot de la web:</p><ul>"
                    f"<li><b>Nombre:</b> {cita.get('nombre', '-')}</li>"
                    f"<li><b>Teléfono:</b> {cita.get('telefono', '-')}</li>"
                    f"<li><b>Email:</b> {cita.get('email', '-')}</li>"
                    f"<li><b>Día solicitado:</b> {cita.get('fecha_texto', '-')} "
                    f"(interpretado: {cita.get('fecha') or 'revisar en el panel'})</li>"
                    f"<li><b>Hora solicitada:</b> {cita.get('hora_texto', '-')} "
                    f"(interpretado: {cita.get('hora') or 'revisar en el panel'})</li>"
                    f"<li><b>Lugar:</b> {cita.get('lugar', '-')}</li>"
                    "</ul><p>Confírmala o cámbiala desde el panel de citas.</p>"
                ),
            },
            timeout=10,
        )
    except Exception as e:
        print(f"Error enviando email de notificación de cita: {e}")


def manejar_cita(session_id: str, mensaje: str):
    """
    Si hay una cita en curso para esta sesión, procesa el mensaje como
    respuesta al campo pendiente y devuelve la siguiente pregunta (o el
    resumen final). Devuelve None si no hay ninguna cita en curso, para
    que el mensaje siga el flujo normal de intents.
    """
    if not _activo():
        return None

    cita = _get_borrador(session_id)
    if cita is None:
        return None

    if mensaje.strip().lower() in PALABRAS_CANCELAR:
        _actualizar(cita["id"], {"estado": "cancelada"})
        return "Vale, no sigo con la solicitud de cita. Si cambias de idea, solo tienes que decírmelo."

    campo_pendiente = _siguiente_campo_vacio(cita)
    valor = mensaje.strip()
    updates = {campo_pendiente: valor}
    if campo_pendiente == "fecha_texto":
        fecha = _parsear_fecha(valor)
        if fecha:
            updates["fecha"] = fecha
    elif campo_pendiente == "hora_texto":
        hora = _parsear_hora(valor)
        if hora:
            updates["hora"] = hora

    cita = _actualizar(cita["id"], updates)

    campo_siguiente = _siguiente_campo_vacio(cita)
    if campo_siguiente:
        pregunta = PREGUNTAS[campo_siguiente]
        if campo_siguiente == "telefono":
            coma_nombre = f", {cita.get('nombre')}" if cita.get("nombre") else ""
            pregunta = pregunta.format(coma_nombre=coma_nombre)
        return pregunta

    _actualizar(cita["id"], {"estado": "pendiente"})
    _notificar_empresa(cita)
    return (
        f"¡Listo, {cita.get('nombre')}! He apuntado tu solicitud de visita para "
        f"{cita.get('fecha_texto')} a las {cita.get('hora_texto')} en {cita.get('lugar')}. "
        "En breve te confirmamos por teléfono. Si necesitas cambiar algo mientras tanto, "
        "llámanos al 925 23 34 54."
    )


def iniciar_cita(session_id: str):
    """Crea el borrador inicial y devuelve la primera pregunta (nombre)."""
    if not _activo():
        return (
            "Ahora mismo no puedo agendar citas automáticamente. "
            "Llámanos al 925 23 34 54 o escribe a info@olivillatres.com y te atendemos."
        )
    _crear_borrador(session_id)
    return PREGUNTAS["nombre"]