import os
import httpx

TIIE_FALLBACK = 6.7458
SPREAD_CERES = 8.0


async def obtener_tiie() -> float:
    try:
        token = os.getenv("BANXICO_TOKEN", "")
        headers = {"Bmx-Token": token} if token else {}
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                "https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF43783/datos/oportuno",
                headers=headers,
            )
            data = r.json()
            valor = data["bmx"]["series"][0]["datos"][0]["dato"]
            return float(valor)
    except Exception:
        return TIIE_FALLBACK
