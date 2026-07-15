# OliviBot Web — chatbot para olivillatres.com

Chatbot de intents (TF-IDF + SVM) para la web corporativa de Olivilla Tres
(construcción, reformas, rehabilitación). Se sirve como widget flotante
embebible en WordPress.

## Estructura

- `train.py` — entrenamiento del pipeline TF-IDF + SVM (idéntico al de FacturaSync/OliviBot original)
- `intents.json` — intents propios de esta web: presupuestos, reformas, cubiertas,
  impermeabilización, rehabilitación, proyectos, contacto, horario, financiación, etc.
- `app.py` — backend Flask. Reentrena al arrancar y expone:
  - `POST /chat` — recibe `{ "mensaje": "..." }`, devuelve la respuesta
  - `GET /widget.js` — script embebible que pinta la burbuja de chat
  - `GET /` — healthcheck simple
- `requirements.txt`, `Procfile` — igual que el bot original, deploy con gunicorn

## Desplegar en Render

1. Sube esta carpeta a un repo de GitHub (nuevo repo, o subcarpeta si prefieres monorepo).
2. En Render: New → Web Service → conecta el repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: ya está en el `Procfile` (`gunicorn app:app`), Render lo detecta solo.
5. Plan free está bien para empezar (mismo cold-start que el bot original;
   si quieres evitarlo, el truco de UptimeRobot que usasteis en el otro bot sirve igual aquí).
6. Copia la URL que te da Render, ej: `https://olivibot-web.onrender.com`

**Importante:** en `app.py`, `ALLOWED_ORIGINS` está restringido a
`https://www.olivillatres.com` y `https://olivillatres.com`. Si pruebas en local
o desde otro dominio, añade esa URL a la lista o el navegador bloqueará el `fetch`.

## Integrar en WordPress (olivillatres.com)

No hace falta tocar el theme ni el código de WordPress:

1. Instala el plugin gratuito **WPCode** ("Insert Headers and Footers") desde
   Plugins → Añadir nuevo.
2. Ve a WPCode → Configuración de encabezado y pie de página → **Footer**.
3. Pega una sola línea:
   ```html
   <script src="https://TU-APP.onrender.com/widget.js"></script>
   ```
   (cambia la URL por la que te dé Render)
4. Guarda. La burbuja de chat aparecerá abajo a la derecha en todas las páginas.

### Con WP Rocket (lo tenéis activo)

WP Rocket puede minificar/diferir scripts y romper el widget. En
WP Rocket → Archivos → JavaScript, añade el dominio de Render (o `widget.js`)
a la lista de **exclusiones** de minificación/carga diferida, para asegurarte
de que se ejecuta tal cual.

## Ajustar el bot con el tiempo

Igual que con el OliviBot original: revisa periódicamente `unanswered.json`
en el servidor (preguntas que cayeron en fallback) para detectar temas que
faltan en `intents.json` y añadir patrones nuevos.

Si con el tiempo el % de fallback sigue siendo alto pese a ampliar patrones,
el siguiente paso natural es migrar a embeddings semánticos
(`paraphrase-multilingual-MiniLM-L12-v2`), como hicisteis en el bot del almacén.
Con TF-IDF + SVM y pocos ejemplos por clase las probabilidades salen bajas
de forma natural (por eso el umbral está en 0.22 en vez de 0.40); no hace
falta reentrenar todo el enfoque salvo que la cobertura real de preguntas
se quede corta.
