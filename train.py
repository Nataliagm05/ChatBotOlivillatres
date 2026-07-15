"""
train.py
========
Pipeline TF-IDF + SVM ligero. Sin sentence-transformers.
Funciona en Render y PythonAnywhere gratuitos (~50MB total).
"""

import json
import pickle
import numpy as np
from pathlib import Path
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report
import re


# ── Preprocesamiento ──────────────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    texto = texto.lower().strip()
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
        'ü': 'u', 'ñ': 'n'
    }
    for orig, repl in reemplazos.items():
        texto = texto.replace(orig, repl)
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


# ── Carga de datos ────────────────────────────────────────────────────────────

def cargar_datos(ruta: str):
    with open(ruta, 'r', encoding='utf-8') as f:
        data = json.load(f)

    X, y = [], []
    for intent in data['intents']:
        for patron in intent['patterns']:
            X.append(normalizar(patron))
            y.append(intent['tag'])

    print(f"  Dataset: {len(X)} ejemplos, {len(set(y))} clases")
    return X, y


# ── Entrenamiento ─────────────────────────────────────────────────────────────

def entrenar(ruta_datos: str, ruta_modelo: str):
    print("\n=== ENTRENANDO CHATBOT (TF-IDF + SVM) ===\n")

    X, y = cargar_datos(ruta_datos)

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            analyzer='char_wb',   # n-gramas de caracteres: robusto a typos y variaciones
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,
        )),
        ('svm', SVC(
            kernel='linear',
            C=1.0,
            probability=True,
            class_weight='balanced',
        )),
    ])

    # Validación cruzada solo si hay suficientes ejemplos por clase
    clases_unicas = list(set(y))
    min_ejemplos = min(y.count(c) for c in clases_unicas)
    if min_ejemplos >= 3:
        print("  Validación cruzada (k=3)...")
        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        scores = cross_val_score(pipeline, X, y, cv=cv, scoring='accuracy')
        print(f"  Accuracy: {scores.mean():.3f} ± {scores.std():.3f}")

    pipeline.fit(X, y)

    y_pred = pipeline.predict(X)
    print("\n  Reporte (train):")
    print(classification_report(y, y_pred, zero_division=0))

    Path(ruta_modelo).parent.mkdir(parents=True, exist_ok=True)

    with open(ruta_datos, 'r', encoding='utf-8') as f:
        data = json.load(f)
    respuestas = {i['tag']: i['responses'] for i in data['intents']}

    with open(ruta_modelo, 'wb') as f:
        pickle.dump({
            'pipeline':   pipeline,
            'respuestas': respuestas,
            'clases':     clases_unicas,
        }, f)

    print(f"\n  Modelo guardado en: {ruta_modelo}")
    print("=== ENTRENAMIENTO COMPLETADO ===\n")
    return pipeline


# ── Inferencia ────────────────────────────────────────────────────────────────

def predecir(pipeline, texto: str, umbral: float = 0.22):
    texto_norm = normalizar(texto)
    probs  = pipeline.predict_proba([texto_norm])[0]
    clases = pipeline.classes_

    idx_max   = np.argmax(probs)
    confianza = probs[idx_max]
    intent    = clases[idx_max]

    print(f"[SVM] '{texto}' → {intent} ({confianza:.3f})")

    if confianza < umbral:
        intent = 'desconocido'

    return intent, float(confianza)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    BASE = Path(__file__).parent
    entrenar(
        ruta_datos=str(BASE / 'intents.json'),
        ruta_modelo=str(BASE / 'chatbot_model.pkl')
    )