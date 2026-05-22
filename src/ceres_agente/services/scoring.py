import random
import numpy as np
from sklearn.ensemble import RandomForestClassifier

GIROS = ["agricola", "restaurante", "comercio", "pecuario", "forestal", "pesquero", "turismo", "otro"]
ESTADOS = ["sinaloa", "nayarit", "jalisco", "guanajuato", "otro"]

_model: RandomForestClassifier = None


def _generar_datos_sinteticos(n: int = 600):
    X, y = [], []
    for _ in range(n):
        giro_idx = random.randint(0, len(GIROS) - 1)
        estado_idx = random.randint(0, len(ESTADOS) - 1)
        monto = random.uniform(50_000, 5_000_000)
        plazo = random.choice([6, 12, 18, 24, 36, 60])
        ratio = random.uniform(0.1, 3.0)
        antiguedad = random.randint(0, 20)
        tipo_persona = random.choice([0, 1])

        prob = 0.5
        if giro_idx in [0, 3, 4, 5]:
            prob += 0.15
        if estado_idx in [0, 1]:
            prob += 0.1
        if monto < 500_000:
            prob += 0.1
        if ratio < 0.5:
            prob += 0.15
        if antiguedad > 5:
            prob += 0.1
        prob = min(max(prob + random.gauss(0, 0.1), 0), 1)

        X.append([giro_idx, estado_idx, monto, plazo, ratio, antiguedad, tipo_persona])
        y.append(1 if prob > 0.55 else 0)
    return np.array(X), np.array(y)


def inicializar_modelo():
    global _model
    X, y = _generar_datos_sinteticos()
    _model = RandomForestClassifier(n_estimators=100, random_state=42)
    _model.fit(X, y)


def calcular_score(giro: str, estado: str, monto: float, plazo: int,
                   ratio_monto_ingresos: float, antiguedad_fiscal: int,
                   tipo_persona: str) -> dict:
    giro_idx = GIROS.index(giro) if giro in GIROS else len(GIROS) - 1
    estado_idx = ESTADOS.index(estado) if estado in ESTADOS else len(ESTADOS) - 1
    tipo_idx = 0 if tipo_persona == "fisica" else 1

    X = np.array([[giro_idx, estado_idx, monto, plazo, ratio_monto_ingresos, antiguedad_fiscal, tipo_idx]])
    prob = float(_model.predict_proba(X)[0][1])

    features = ["giro", "estado", "monto", "plazo", "ratio_ingresos", "antiguedad_fiscal", "tipo_persona"]
    factores = sorted(zip(features, _model.feature_importances_), key=lambda x: x[1], reverse=True)[:3]
    factores_top = [{"factor": f, "importancia": round(float(i), 3)} for f, i in factores]

    if prob >= 0.70:
        decision, accion = "verde", "Solicitar documentación automáticamente"
    elif prob >= 0.40:
        decision, accion = "amarillo", "Escalar a ejecutivo humano"
    else:
        decision, accion = "rojo", "Rechazar con explicación"

    return {
        "score": round(prob, 3),
        "decision": decision,
        "accion": accion,
        "factores_principales": factores_top,
    }
