SPREAD_CERES = 8.0


def calcular_cuota(monto: float, tasa_anual: float, plazo_meses: int) -> float:
    tasa_mensual = tasa_anual / 12 / 100
    if tasa_mensual == 0:
        return round(monto / plazo_meses, 2)
    cuota = monto * (tasa_mensual * (1 + tasa_mensual) ** plazo_meses) / ((1 + tasa_mensual) ** plazo_meses - 1)
    return round(cuota, 2)
