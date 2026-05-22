import urllib.request
import json

data = json.dumps({
    "nombre": "Juan Perez",
    "telefono": "521234567890",
    "rfc": "JUPR800101",
    "giro": "agricola",
    "ubicacion_raw": "Culiacan, Sinaloa",
    "monto": 500000,
    "plazo": 24,
    "tiie": 6.7458,
    "tasa": 14.75,
    "cuota": 24213.50,
    "elegible": True,
    "dictamen": "ELEGIBLE - Cumple criterios FIRA.",
    "score": 0.82,
    "decision": "verde"
}).encode()

req = urllib.request.Request(
    'http://localhost:8000/notificar',
    data=data,
    headers={'Content-Type': 'application/json'},
    method='POST'
)

try:
    resp = urllib.request.urlopen(req, timeout=15)
    print("Status:", resp.status)
    print(resp.read().decode())
except Exception as e:
    print("Error:", e)
