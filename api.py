from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Form, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from src.ceres_agente.db import engine, init_db, Lead, Cotizacion, Conversacion
from src.ceres_agente.services.whatsapp import procesar_y_enviar
from src.ceres_agente.services import calcular_score, obtener_tiie, calcular_cuota
from src.ceres_agente.services.tiie import SPREAD_CERES
from src.ceres_agente.services.scoring import inicializar_modelo
from src.ceres_agente.agent.graph import generar_reporte_cartera, verificar_expediente
from src.ceres_agente.services.notificaciones import enviar_correo_resumen
from src.ceres_agente import run_agent


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    mensaje: str
    telefono: str = "0000000000"

class ChatResponse(BaseModel):
    respuesta: str

class CotizarRequest(BaseModel):
    telefono: str
    monto: float
    plazo_meses: int
    tipo_credito: str = "avio"

class CotizarResponse(BaseModel):
    tasa_tiie: float
    spread: float
    tasa_final: float
    cuota_mensual: float
    cotizacion_id: int

class LeadCreate(BaseModel):
    nombre: str
    telefono: str
    rfc: Optional[str] = None
    giro: str
    municipio: str
    estado: str
    monto_solicitado: float
    plazo_meses: int
    tipo_credito: str = "avio"
    tipo_persona: str = "fisica"
    ingresos_mensuales: Optional[float] = None
    antiguedad_fiscal: int = 0

class ScoreRequest(BaseModel):
    giro: str
    estado: str
    monto: float
    plazo_meses: int
    ingresos_mensuales: float
    antiguedad_fiscal: int = 0
    tipo_persona: str = "fisica"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    inicializar_modelo()
    yield

app = FastAPI(title="KronoFinanzas Ceres API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@app.get("/")
def health():
    return {"status": "ok", "proyecto": "KronoFinanzas Ceres", "version": "2.0.0", "agentes": 6}


@app.get("/tiie")
async def tiie_actual():
    tiie = await obtener_tiie()
    return {
        "tiie_28_dias": tiie,
        "spread_ceres": SPREAD_CERES,
        "tasa_referencia": round(tiie + SPREAD_CERES, 4),
        "fecha": date.today().isoformat(),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Chat general con el agente multi-agente. El orquestador detecta la intencion
    y rutea al subagente correcto (FIRA, Cotizador, Scoring, Documentos, Seguimiento, Insights)."""
    try:
        respuesta = run_agent(req.mensaje, telefono=req.telefono)
        return ChatResponse(respuesta=respuesta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cotizar", response_model=CotizarResponse)
async def cotizar(req: CotizarRequest):
    tiie = await obtener_tiie()
    tasa_final = tiie + SPREAD_CERES
    cuota = calcular_cuota(req.monto, tasa_final, req.plazo_meses)

    cotizacion = Cotizacion(
        telefono=req.telefono,
        monto=req.monto,
        plazo_meses=req.plazo_meses,
        tipo_credito=req.tipo_credito,
        tasa_tiie=tiie,
        spread=SPREAD_CERES,
        tasa_final=tasa_final,
        cuota_mensual=cuota,
    )
    with Session(engine) as session:
        session.add(cotizacion)
        session.commit()
        session.refresh(cotizacion)

    return CotizarResponse(
        tasa_tiie=round(tiie, 4),
        spread=SPREAD_CERES,
        tasa_final=round(tasa_final, 4),
        cuota_mensual=cuota,
        cotizacion_id=cotizacion.id,
    )


@app.post("/score")
def score(req: ScoreRequest):
    ratio = req.monto / (req.ingresos_mensuales * 12)
    return calcular_score(
        giro=req.giro,
        estado=req.estado,
        monto=req.monto,
        plazo=req.plazo_meses,
        ratio_monto_ingresos=ratio,
        antiguedad_fiscal=req.antiguedad_fiscal,
        tipo_persona=req.tipo_persona,
    )


@app.post("/leads")
def crear_lead(req: LeadCreate):
    ratio = req.monto_solicitado / (req.ingresos_mensuales * 12) if req.ingresos_mensuales else 1.5
    resultado_score = calcular_score(
        giro=req.giro,
        estado=req.estado,
        monto=req.monto_solicitado,
        plazo=req.plazo_meses,
        ratio_monto_ingresos=ratio,
        antiguedad_fiscal=req.antiguedad_fiscal,
        tipo_persona=req.tipo_persona,
    )

    lead = Lead(
        nombre=req.nombre,
        telefono=req.telefono,
        rfc=req.rfc,
        giro=req.giro,
        municipio=req.municipio,
        estado=req.estado,
        monto_solicitado=req.monto_solicitado,
        plazo_meses=req.plazo_meses,
        tipo_credito=req.tipo_credito,
        tipo_persona=req.tipo_persona,
        score=resultado_score["score"],
        decision=resultado_score["decision"],
    )
    with Session(engine) as session:
        session.add(lead)
        session.commit()
        session.refresh(lead)

    return {**lead.model_dump(), "score_detalle": resultado_score}


@app.get("/leads")
def listar_leads():
    with Session(engine) as session:
        return session.exec(select(Lead).order_by(Lead.creado_en.desc())).all()


@app.get("/leads/{lead_id}")
def obtener_lead(lead_id: int):
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead no encontrado")
        return lead


@app.patch("/leads/{lead_id}/status")
def actualizar_status(lead_id: int, status: str):
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead no encontrado")
        lead.status = status
        session.add(lead)
        session.commit()
        session.refresh(lead)
        return lead


# ---------------------------------------------------------------------------
# Notificaciones (Resend)
# ---------------------------------------------------------------------------

class NotificarRequest(BaseModel):
    nombre: str = "Prospecto de prueba"
    telefono: str = "521234567890"
    rfc: str = "XXXX000000XXX"
    giro: str = "agricola"
    ubicacion_raw: str = "Culiacan, Sinaloa"
    monto: float = 500000.0
    plazo: int = 24
    tiie: float = 6.7458
    tasa: float = 14.75
    cuota: float = 24213.50
    elegible: bool = True
    dictamen: str = "ELEGIBLE — El prospecto cumple con los criterios de FIRA para credito agricola."
    score: float = 0.82
    decision: str = "verde"

@app.post("/notificar")
def notificar(req: NotificarRequest):
    """Endpoint de prueba para enviar correo de resumen via Resend."""
    resultado = enviar_correo_resumen(req.model_dump())
    return resultado


# ---------------------------------------------------------------------------
# Webhook WhatsApp
# ---------------------------------------------------------------------------

@app.post("/webhook/whatsapp")
async def webhook_whatsapp(
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    Body: str = Form(...),
):
    """Webhook de Twilio. Retorna TwiML vacío inmediatamente para evitar
    el timeout de 15s de Twilio y procesa en background via REST API."""
    telefono = From.replace("whatsapp:", "")
    background_tasks.add_task(procesar_y_enviar, telefono, Body)
    return PlainTextResponse(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


# ---------------------------------------------------------------------------
# Endpoints nuevos — Gerente / Reportes / Seguimiento
# ---------------------------------------------------------------------------

@app.get("/reporte/cartera")
def reporte_cartera(estado: str = ""):
    """Reporte de cartera para gerentes. Filtra opcionalmente por estado
    (sinaloa, nayarit, jalisco, guanajuato)."""
    import json
    resultado = generar_reporte_cartera.invoke({"estado_filtro": estado})
    return json.loads(resultado)


@app.get("/expediente/{telefono}")
def consultar_expediente(telefono: str):
    """Consulta el expediente completo de un prospecto por numero de telefono."""
    import json
    resultado = verificar_expediente.invoke({"telefono": telefono})
    return json.loads(resultado)


@app.get("/dashboard")
def dashboard():
    """Dashboard resumido para gerentes: KPIs principales de la cartera."""
    import json
    resultado = generar_reporte_cartera.invoke({"estado_filtro": ""})
    data = json.loads(resultado)

    with Session(engine) as session:
        leads_pendientes = session.exec(
            select(Lead).where(Lead.status == "pendiente_docs")
        ).all()

    return {
        **data,
        "pendientes_documentos": len(leads_pendientes),
        "tasa_conversion": round(
            data["aprobados_verde"] / data["total_leads"] * 100, 1
        ) if data["total_leads"] else 0,
        "ultima_actualizacion": date.today().isoformat(),
    }
