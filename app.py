"""
app.py - OliviBot Web (widget flotante para olivillatres.com)
TF-IDF + SVM + intents.json. Sin retriever, ligero para Render free tier.
"""
"""
app.py - OliviBot Web (widget flotante para olivillatres.com)
TF-IDF + SVM + intents.json. Sin retriever, ligero para Render free tier.
"""

import pickle
import random
import json
from pathlib import Path
from flask import Flask, request, jsonify, Response
import sys

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from train import normalizar, predecir, entrenar
from citas_flow import manejar_cita, iniciar_cita
from flask_cors import CORS

app = Flask(__name__)

# Solo el dominio real de la empresa puede llamar a /chat.
# Añade variantes (con/sin www, http local de pruebas) si hace falta.
ALLOWED_ORIGINS = [
    "https://www.olivillatres.com",
    "https://olivillatres.com",
]

CORS(app, resources={r"/chat": {"origins": ALLOWED_ORIGINS}})

# ── Cargar datos ──────────────────────────────────────────────────────────────

MODELO_PATH  = BASE / 'chatbot_model.pkl'
INTENTS_PATH = BASE / 'intents.json'

with open(INTENTS_PATH, 'r', encoding='utf-8') as f:
    intents_data = json.load(f)

entrenar(ruta_datos=str(INTENTS_PATH), ruta_modelo=str(MODELO_PATH))

with open(MODELO_PATH, 'rb') as f:
    modelo_data = pickle.load(f)

pipeline   = modelo_data['pipeline']
respuestas = modelo_data['respuestas']


# ── Lógica de respuesta ───────────────────────────────────────────────────────

def obtener_respuesta(texto: str, session_id: str = None):
    # Si hay una cita a medias para esta sesión, el mensaje se trata como
    # respuesta al siguiente dato pendiente (nombre/teléfono/fecha/hora/lugar),
    # saltándose la clasificación normal de intents.
    if session_id:
        respuesta_cita = manejar_cita(session_id, texto)
        if respuesta_cita is not None:
            return {
                "intent": "cita",
                "nivel": "flujo_cita",
                "confianza": 1.0,
                "respuesta": respuesta_cita,
            }

    texto_norm = normalizar(texto)

    # Nivel 1: coincidencia exacta
    for intent in intents_data["intents"]:
        patrones = [normalizar(p) for p in intent["patterns"]]
        if texto_norm in patrones:
            if intent["tag"] == "cita" and session_id:
                return {
                    "intent": "cita", "nivel": "exacto", "confianza": 1.0,
                    "respuesta": iniciar_cita(session_id),
                }
            return {
                "intent":    intent["tag"],
                "nivel":     "exacto",
                "confianza": 1.0,
                "respuesta": random.choice(intent["responses"])
            }

    # Nivel 2: SVM
    intent, confianza = predecir(pipeline, texto)

    if intent == "cita" and session_id:
        return {
            "intent": "cita", "nivel": "svm", "confianza": round(confianza, 3),
            "respuesta": iniciar_cita(session_id),
        }

    if intent != 'desconocido' and intent in respuestas:
        return {
            'intent':    intent,
            'nivel':     'svm',
            'confianza': round(confianza, 3),
            'respuesta': random.choice(respuestas[intent])
        }

    # Nivel 3: fallback + guardar pregunta
    try:
        UNANSWERED_PATH = BASE / 'unanswered.json'
        preguntas = []
        if UNANSWERED_PATH.exists():
            with open(UNANSWERED_PATH, 'r', encoding='utf-8') as f:
                preguntas = json.load(f)
        if texto not in preguntas and len(texto.strip()) > 3:
            preguntas.append(texto)
            with open(UNANSWERED_PATH, 'w', encoding='utf-8') as f:
                json.dump(preguntas, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error guardando pregunta: {e}")

    return {
        'intent':    'desconocido',
        'nivel':     'fallback',
        'confianza': confianza,
        'respuesta': (
            "Lo siento, no tengo información sobre eso. "
            "Puedes llamarnos al 925 23 34 54 o escribirnos a "
            "info@olivillatres.com y te ayudamos."
        )
    }


# ── Rutas ─────────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return "OliviBot Web backend activo. Endpoints: /chat (POST), /widget.js (GET)."

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json() or {}
    mensaje = data.get('mensaje', '')
    session_id = data.get('session_id')
    if not mensaje:
        return jsonify({'respuesta': 'No he recibido ningún texto.'}), 400
    return jsonify(obtener_respuesta(mensaje, session_id))

@app.route('/widget.js')
def widget():
    return Response(WIDGET_JS, mimetype='application/javascript')


# ── Widget JS embebible ───────────────────────────────────────────────────────
# Se sirve tal cual desde /widget.js. WordPress solo necesita:
# <script src="https://TU-APP.onrender.com/widget.js"></script>
# El backend se autodetecta con el origen del propio script (no hay que
# hardcodear la URL de Render dentro del JS).

WIDGET_JS = """
(function () {
  var currentScript = document.currentScript;
  var API_BASE = new URL(currentScript.src).origin;
  var SESSION_ID = (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : 'ob-' + Date.now() + '-' + Math.random().toString(36).slice(2);

  var css = `
    .ob-btn { position: fixed; bottom: 90px; right: 24px; width: 56px; height: 56px;
      border-radius: 50%; background: #b53987; box-shadow: 0 4px 16px rgba(74,59,104,0.35);
      display: flex; align-items: center; justify-content: center; cursor: pointer;
      z-index: 2147483000; font-size: 26px; border: none; transition: transform .15s ease; }
    .ob-btn:hover { transform: scale(1.06); }
    .ob-window { position: fixed; bottom: 158px; right: 24px; width: 340px; max-width: 90vw;
      height: 480px; max-height: 70vh; background: #fff; border-radius: 16px;
      box-shadow: 0 8px 32px rgba(74,59,104,0.25); display: none; flex-direction: column;
      overflow: hidden; z-index: 2147483000; font-family: 'Inter', system-ui, sans-serif; }
    .ob-window.open { display: flex; }
    .ob-header { background: #4a3b68; color: #fff; padding: 14px 16px; display: flex;
      align-items: center; gap: 10px; border-bottom: 3px solid #b53987; }
    .ob-avatar { width: 30px; height: 30px; background: rgba(255,255,255,.2); border-radius: 50%;
      display: flex; align-items: center; justify-content: center; font-size: 15px; }
    .ob-title { font-size: 14px; font-weight: 600; line-height: 1.3; }
    .ob-sub { font-size: 11px; opacity: .75; }
    .ob-close { margin-left: auto; cursor: pointer; opacity: .8; background: none; border: none;
      color: #fff; font-size: 16px; }
    .ob-messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column;
      gap: 8px; background: #f4f2f8; }
    .ob-msg { max-width: 85%; padding: 8px 12px; border-radius: 14px; font-size: 13px; line-height: 1.45; }
    .ob-msg.bot { align-self: flex-start; background: #fff; color: #4a3b68; border-radius: 3px 14px 14px 14px; }
    .ob-msg.user { align-self: flex-end; background: #4a3b68; color: #fff; border-radius: 14px 3px 14px 14px; }
    .ob-input-area { padding: 10px; border-top: 1px solid rgba(74,59,104,.12); display: flex; gap: 6px;
      background: #fff; }
    .ob-input { flex: 1; padding: 8px 12px; border: 1.5px solid rgba(74,59,104,.2); border-radius: 20px;
      outline: none; font-size: 13px; }
    .ob-input:focus { border-color: #b53987; }
    .ob-send { background: #b53987; color: #fff; border: none; padding: 8px 14px; border-radius: 20px;
      cursor: pointer; font-size: 13px; font-weight: 500; }
    .ob-send:hover { background: #922f6d; }
  `;
  var style = document.createElement('style');
  style.innerHTML = css;
  document.head.appendChild(style);

  var btn = document.createElement('button');
  btn.className = 'ob-btn';
  btn.innerHTML = '💬';
  document.body.appendChild(btn);

  var win = document.createElement('div');
  win.className = 'ob-window';
  win.innerHTML =
    '<div class="ob-header"><div class="ob-avatar">🤖</div>' +
    '<div><div class="ob-title">OliviBot</div><div class="ob-sub">Asistente de Olivilla Tres</div></div>' +
    '<button class="ob-close">✕</button></div>' +
    '<div class="ob-messages" id="ob-messages"></div>' +
    '<div class="ob-input-area"><input class="ob-input" id="ob-input" type="text" ' +
    'placeholder="Escribe tu pregunta..."/><button class="ob-send" id="ob-send">Enviar</button></div>';
  document.body.appendChild(win);

  var messagesEl = win.querySelector('#ob-messages');
  var inputEl = win.querySelector('#ob-input');
  var sendBtn = win.querySelector('#ob-send');
  var closeBtn = win.querySelector('.ob-close');

  function addMsg(texto, from) {
    var d = document.createElement('div');
    d.className = 'ob-msg ' + from;
    d.textContent = texto;
    messagesEl.appendChild(d);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  var greeted = false;
  btn.addEventListener('click', function () {
    win.classList.toggle('open');
    if (!greeted) {
      addMsg('¡Hola! Soy OliviBot, el asistente de Olivilla Tres. ¿En qué puedo ayudarte?', 'bot');
      greeted = true;
    }
  });
  closeBtn.addEventListener('click', function () { win.classList.remove('open'); });

  function send() {
    var texto = inputEl.value.trim();
    if (!texto) return;
    inputEl.value = '';
    addMsg(texto, 'user');
    fetch(API_BASE + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensaje: texto, session_id: SESSION_ID })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) { addMsg(data.respuesta, 'bot'); })
      .catch(function () { addMsg('Error al conectar con el servidor.', 'bot'); });
  }
  sendBtn.addEventListener('click', send);
  inputEl.addEventListener('keydown', function (e) { if (e.key === 'Enter') send(); });
})();
"""

if __name__ == '__main__':
    app.run(debug=True, port=5000)