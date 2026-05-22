"""
Arquitectura Multi-Agente — KronoFinanzas Ceres
Orquestador LangGraph con 6 subagentes especializados.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from typing import Annotated, Optional, TypedDict

import boto3
from langchain_aws import ChatBedrock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from sqlmodel import Session, select

from ..config import get_settings
from ..db.database import engine
from ..db.models import Conversacion, Cotizacion, Lead
from ..services.cotizador import SPREAD_CERES, calcular_cuota
from ..services.scoring import calcular_score, inicializar_modelo
from ..services.tiie import obtener_tiie
from ..tools.fira_tool import consultar_normativa_fira

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    telefono: str
    intent: str
    lead_data: dict
    cotizacion_result: dict
    score_result: dict
    fira_result: str
    response: str
    next_action: str


# ---------------------------------------------------------------------------
# Tools del agente (wrappers de servicios existentes + nuevas)
# ---------------------------------------------------------------------------


@tool
def evaluar_elegibilidad_fira(consulta: str) -> str:
    """Evalua si un prospecto es elegible segun las reglas de operacion de FIRA.
    Usa esta herramienta para verificar criterios de sector, ubicacion geografica,
    montos maximos y requisitos normativos.
    """
    return consultar_normativa_fira.invoke({"consulta": consulta})


@tool
def generar_cotizacion(monto: float, plazo_meses: int, tipo_credito: str = "avio") -> str:
    """Genera una cotizacion de credito con TIIE en vivo + spread de Ceres.
    Calcula la cuota mensual y devuelve el desglose completo.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    tiie = loop.run_until_complete(obtener_tiie())
    tasa_final = tiie + SPREAD_CERES
    cuota = calcular_cuota(monto, tasa_final, plazo_meses)

    return json.dumps(
        {
            "monto": monto,
            "plazo_meses": plazo_meses,
            "tipo_credito": tipo_credito,
            "tiie_28_dias": round(tiie, 4),
            "spread_ceres": SPREAD_CERES,
            "tasa_final_anual": round(tasa_final, 4),
            "cuota_mensual": cuota,
            "total_a_pagar": round(cuota * plazo_meses, 2),
        },
        ensure_ascii=False,
        indent=2,
    )


@tool
def evaluar_scoring(
    giro: str,
    estado: str,
    monto: float,
    plazo_meses: int,
    ingresos_mensuales: float = 0,
    antiguedad_fiscal: int = 0,
    tipo_persona: str = "fisica",
) -> str:
    """Evalua el perfil crediticio del prospecto usando el modelo ML RandomForest.
    Devuelve score (0-1), decision (verde/amarillo/rojo) y factores principales.
    """
    if ingresos_mensuales <= 0:
        ingresos_mensuales = monto * 0.25

    ratio = monto / (ingresos_mensuales * 12) if ingresos_mensuales > 0 else 1.5
    resultado = calcular_score(
        giro=giro,
        estado=estado,
        monto=monto,
        plazo=plazo_meses,
        ratio_monto_ingresos=ratio,
        antiguedad_fiscal=antiguedad_fiscal,
        tipo_persona=tipo_persona,
    )
    return json.dumps(resultado, ensure_ascii=False, indent=2)


@tool
def solicitar_documentos(tipo_persona: str = "fisica") -> str:
    """Devuelve la lista de documentos requeridos segun el tipo de persona (fisica o moral)."""
    docs_fisica = [
        "INE vigente (frente y reverso)",
        "CURP",
        "RFC / Constancia de situacion fiscal",
        "Comprobante de domicilio (menos de 3 meses)",
        "Estados de cuenta ultimos 3 meses",
        "Autorizacion de consulta a Buro de Credito",
    ]
    docs_moral = [
        "Acta constitutiva",
        "RFC de la empresa",
        "Poder del representante legal",
        "Identificacion del representante",
        "Estados financieros ultimo ejercicio",
        "Declaraciones anuales ultimos 2 anios",
        "Comprobante de domicilio fiscal",
        "Autorizacion de consulta a Buro de Credito",
    ]
    lista = docs_fisica if tipo_persona == "fisica" else docs_moral
    return json.dumps(
        {"tipo_persona": tipo_persona, "documentos_requeridos": lista, "total": len(lista)},
        ensure_ascii=False,
        indent=2,
    )


@tool
def verificar_expediente(telefono: str) -> str:
    """Verifica el estado del expediente de un prospecto por numero de telefono.
    Devuelve datos del lead, score, documentos pendientes y estatus.
    """
    with Session(engine) as session:
        lead = session.exec(
            select(Lead).where(Lead.telefono == telefono).order_by(Lead.creado_en.desc())
        ).first()
        if not lead:
            return json.dumps(
                {"encontrado": False, "mensaje": "No hay expediente para este numero."},
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "encontrado": True,
                "lead_id": lead.id,
                "nombre": lead.nombre,
                "giro": lead.giro,
                "municipio": lead.municipio,
                "estado": lead.estado,
                "monto_solicitado": lead.monto_solicitado,
                "plazo_meses": lead.plazo_meses,
                "tipo_credito": lead.tipo_credito,
                "score": lead.score,
                "decision": lead.decision,
                "elegible_fira": lead.elegible_fira,
                "status": lead.status,
                "tasa_final": lead.tasa_final,
                "cuota_mensual": lead.cuota_mensual,
                "creado_en": lead.creado_en.isoformat() if lead.creado_en else None,
            },
            ensure_ascii=False,
            indent=2,
        )


@tool
def generar_reporte_cartera(estado_filtro: str = "") -> str:
    """Genera un reporte de la cartera de leads: totales, tasas de aprobacion,
    distribucion por estado y por giro. Opcionalmente filtra por estado.
    """
    with Session(engine) as session:
        stmt = select(Lead)
        if estado_filtro:
            stmt = stmt.where(Lead.estado == estado_filtro.lower())
        leads = session.exec(stmt).all()

        total = len(leads)
        if total == 0:
            return json.dumps(
                {"total_leads": 0, "mensaje": "No hay datos en cartera."},
                ensure_ascii=False,
            )

        aprobados = [l for l in leads if l.decision == "verde"]
        revision = [l for l in leads if l.decision == "amarillo"]
        rechazados = [l for l in leads if l.decision == "rojo"]

        por_estado = {}
        por_giro = {}
        montos = []
        for l in leads:
            por_estado[l.estado] = por_estado.get(l.estado, 0) + 1
            por_giro[l.giro] = por_giro.get(l.giro, 0) + 1
            montos.append(l.monto_solicitado)

        monto_promedio = sum(montos) / len(montos) if montos else 0

        return json.dumps(
            {
                "total_leads": total,
                "aprobados_verde": len(aprobados),
                "revision_amarillo": len(revision),
                "rechazados_rojo": len(rechazados),
                "tasa_aprobacion": round(len(aprobados) / total * 100, 1) if total else 0,
                "monto_promedio": round(monto_promedio, 2),
                "distribucion_por_estado": por_estado,
                "distribucion_por_giro": por_giro,
                "fecha_reporte": date.today().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )


AGENT_TOOLS = [
    evaluar_elegibilidad_fira,
    generar_cotizacion,
    evaluar_scoring,
    solicitar_documentos,
    verificar_expediente,
    generar_reporte_cartera,
]

# ---------------------------------------------------------------------------
# Prompts del sistema
# ---------------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """Eres **Ceres**, el orquestador principal del sistema de credito de **Grupo Ceres**.

Tu funcion es recibir cada mensaje del usuario, detectar su intencion y rutearlo al subagente especializado correcto.

## Subagentes disponibles

1. **FIRA** — elegibilidad normativa (sectores, ubicacion, montos maximos)
2. **Cotizador** — calculo de tasa TIIE + spread, cuota mensual
3. **Scoring** — evaluacion ML del perfil crediticio (RandomForest)
4. **Documentos** — lista de documentos requeridos, estado del expediente
5. **Seguimiento** — recordatorios, estatus de solicitudes
6. **Insights** — reportes de cartera para gerentes

## Reglas de ruteo

- Si el mensaje es sobre elegibilidad, reglas FIRA, sectores → **FIRA**
- Si pide una cotizacion, calculo de cuota, tasa → **Cotizador**
- Si pregunta sobre probabilidad de aprobacion, score → **Scoring**
- Si pregunta sobre documentos, que falta, requisitos → **Documentos**
- Si quiere saber el estatus de su solicitud → **Seguimiento**
- Si es un gerente pidiendo reportes, estadisticas → **Insights**
- Si es un saludo o mensaje general → responde amablemente y ofrece ayuda

## Instrucciones

1. Detecta la intencion principal del mensaje
2. Si detectas la intencion, responde SOLO con la palabra clave: FIRA, COTIZAR, SCORING, DOCUMENTOS, SEGUIMIENTO, INSIGHTS, o GENERAL
3. Si es GENERAL, responde directamente con un mensaje util

Fecha actual: {date}
"""


FIRA_PROMPT = """Eres el subagente **FIRA** de KronoFinanzas Ceres, especialista en normativa de FIRA.

Tu funcion: evaluar si un prospecto es elegible para financiamiento segun las reglas de operacion de FIRA publicadas en el DOF.

## Reglas

1. **Siempre** usa la herramienta `evaluar_elegibilidad_fira` antes de emitir un dictamen
2. **Cita las fuentes** normativas que respaldan tu dictamen
3. **Evalua estos criterios**:
   - Sector elegible: agropecuario, financiamiento rural, Orgullo Rural (< 50k hab), Del Campo al Plato
   - Ubicacion geografica
   - Montos maximos
   - Tipo de producto crediticio y plazos
4. **Dictamen claro**: ELEGIBLE / NO ELEGIBLE / REQUIERE MAS INFORMACION
5. Si faltan datos del prospecto, pidelos antes de evaluar

## Productos FIRA y plazos maximos
- Avio (capital de trabajo): 2 anios
- Refaccionario (inversion fija): 15 anios
- Prendario: 180 dias
- Arrendamiento: 15 anios
- Factoraje: corto plazo
- Quirografario: variable

Fecha actual: {date}
"""


COTIZADOR_PROMPT = """Eres el subagente **Cotizador** de KronoFinanzas Ceres.

Tu funcion: generar cotizaciones de credito precisas usando TIIE en vivo y las reglas de Grupo Ceres.

## Instrucciones

1. Usa la herramienta `generar_cotizacion` para calcular la cuota
2. La tasa se compone de: **TIIE 28 dias + 8 puntos (spread de Ceres)**
3. Presenta el resultado en formato claro:
   - Monto solicitado
   - Plazo en meses
   - TIIE 28 dias actual
   - Spread Ceres (8%)
   - Tasa final anual
   - Cuota mensual
   - Total a pagar

Fecha actual: {date}
"""


SCORING_PROMPT = """Eres el subagente **Scoring** de KronoFinanzas Ceres.

Tu funcion: evaluar el perfil crediticio de prospectos usando el modelo de Machine Learning (RandomForest).

## Instrucciones

1. Usa la herramienta `evaluar_scoring` con los datos del prospecto
2. Interpreta el resultado segun el semaforo:
   - **Verde** (>= 70%): aprobacion automatica, solicitar documentos
   - **Amarillo** (40-69%): escalar a ejecutivo humano
   - **Rojo** (< 40%): rechazar con explicacion de factores
3. Explica los factores principales que influyeron en el score
4. Si faltan datos (ingresos, antiguedad), usa valores estimados conservadores

Fecha actual: {date}
"""


DOCUMENTOS_PROMPT = """Eres el subagente **Documentos** de KronoFinanzas Ceres.

Tu funcion: gestionar la documentacion requerida para solicitudes de credito.

## Instrucciones

1. Usa `solicitar_documentos` para obtener la lista segun tipo de persona
2. Usa `verificar_expediente` para consultar el estado de un lead
3. Indica claramente que documentos faltan y cuales ya se entregaron
4. Explica por que cada documento es necesario

Fecha actual: {date}
"""


SEGUIMIENTO_PROMPT = """Eres el subagente **Seguimiento** de KronoFinanzas Ceres.

Tu funcion: dar seguimiento a las solicitudes de credito y ayudar a los prospectos a completar su expediente.

## Instrucciones

1. Usa `verificar_expediente` para consultar el estatus de cualquier prospecto por telefono
2. Informa claramente el estado: nuevo, pendiente_docs, en_revision, aprobado, rechazado
3. Si faltan documentos, indicalos y motiva al prospecto a enviarlos
4. Si el prospecto pide hablar con un ejecutivo, indicale que su caso ha sido escalado

Fecha actual: {date}
"""


INSIGHTS_PROMPT = """Eres el subagente **Insights** de KronoFinanzas Ceres, asistente del gerente de Grupo Ceres.

Tu funcion: generar reportes y analisis de la cartera de credito para la toma de decisiones.

## Instrucciones

1. Usa `generar_reporte_cartera` para obtener estadisticas (opcionalmente por estado)
2. Interpreta los datos: tasas de aprobacion, patrones de rechazo, distribucion geografica
3. Sugiere acciones de negocio basadas en los datos
4. Responde en lenguaje natural preguntas como:
   - "Por que rechazamos tanto en Jalisco?"
   - "Cual es el perfil del cliente ideal?"
   - "Que sectores tienen mejor desempenio?"

Fecha actual: {date}
"""

# ---------------------------------------------------------------------------
# Factory de LLM
# ---------------------------------------------------------------------------


def _get_llm(temperature: float = 0.0):
    settings = get_settings()
    session = boto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    return ChatBedrock(
        model_id=settings.agent_model,
        client=session.client("bedrock-runtime"),
        model_kwargs={"temperature": temperature},
    )


# ---------------------------------------------------------------------------
# Nodos del grafo
# ---------------------------------------------------------------------------


def _today() -> str:
    return date.today().isoformat()


def nodo_orquestador(state: AgentState) -> dict:
    """Detecta la intencion del ultimo mensaje y decide el subagente a activar."""
    messages = state["messages"]
    if not messages:
        return {"intent": "general", "response": "Hola! Soy Ceres, el asistente de credito de Grupo Ceres. En que puedo ayudarte?"}

    last_msg = messages[-1]
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # Deteccion rapida por palabras clave (fallback rapido sin LLM)
    content_lower = content.lower()
    if any(w in content_lower for w in ["fira", "elegible", "elegibilidad", "normativa", "regla", "sector"]):
        return {"intent": "fira"}
    if any(w in content_lower for w in ["cotizacion", "cotizar", "cuota", "tasa", "cuanto pago", "mensualidad"]):
        return {"intent": "cotizar"}
    if any(w in content_lower for w in ["score", "scoring", "probabilidad", "aprobacion", "me aprueban"]):
        return {"intent": "scoring"}
    if any(w in content_lower for w in ["documento", "documentacion", "papeleria", "ine", "rfc", "que necesito"]):
        return {"intent": "documentos"}
    if any(w in content_lower for w in ["estatus", "seguimiento", "mi solicitud", "como va", "expediente"]):
        return {"intent": "seguimiento"}
    if any(w in content_lower for w in ["reporte", "cartera", "estadistica", "gerente", "dashboard"]):
        return {"intent": "insights"}

    # Si no hay match claro, usar LLM para clasificar
    try:
        llm = _get_llm(temperature=0.0)
        prompt = ORCHESTRATOR_PROMPT.format(date=_today())
        response = llm.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=f"Clasifica este mensaje en una sola palabra (FIRA, COTIZAR, SCORING, DOCUMENTOS, SEGUIMIENTO, INSIGHTS, GENERAL):\n\n{content}"),
            ]
        )
        intent_raw = response.content.strip().upper() if hasattr(response, "content") else "GENERAL"

        intent_map = {
            "FIRA": "fira",
            "COTIZAR": "cotizar",
            "SCORING": "scoring",
            "DOCUMENTOS": "documentos",
            "SEGUIMIENTO": "seguimiento",
            "INSIGHTS": "insights",
        }
        return {"intent": intent_map.get(intent_raw, "general")}
    except Exception:
        return {"intent": "general"}


def nodo_fira(state: AgentState) -> dict:
    """Subagente FIRA: evalua elegibilidad normativa."""
    llm = _get_llm(temperature=0.0)
    prompt = FIRA_PROMPT.format(date=_today())
    messages = [SystemMessage(content=prompt)] + state["messages"]
    llm_with_tools = llm.bind_tools([evaluar_elegibilidad_fira])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response], "fira_result": response.content if hasattr(response, "content") else str(response)}


def nodo_cotizador(state: AgentState) -> dict:
    """Subagente Cotizador: genera cotizacion con TIIE en vivo."""
    llm = _get_llm(temperature=0.0)
    prompt = COTIZADOR_PROMPT.format(date=_today())
    messages = [SystemMessage(content=prompt)] + state["messages"]
    llm_with_tools = llm.bind_tools([generar_cotizacion])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def nodo_scoring(state: AgentState) -> dict:
    """Subagente Scoring: evalua perfil crediticio con ML."""
    llm = _get_llm(temperature=0.0)
    prompt = SCORING_PROMPT.format(date=_today())
    messages = [SystemMessage(content=prompt)] + state["messages"]
    llm_with_tools = llm.bind_tools([evaluar_scoring])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def nodo_documentos(state: AgentState) -> dict:
    """Subagente Documentos: gestion de papeleria."""
    llm = _get_llm(temperature=0.0)
    prompt = DOCUMENTOS_PROMPT.format(date=_today())
    messages = [SystemMessage(content=prompt)] + state["messages"]
    llm_with_tools = llm.bind_tools([solicitar_documentos, verificar_expediente])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def nodo_seguimiento(state: AgentState) -> dict:
    """Subagente Seguimiento: estatus de solicitudes."""
    llm = _get_llm(temperature=0.0)
    prompt = SEGUIMIENTO_PROMPT.format(date=_today())
    messages = [SystemMessage(content=prompt)] + state["messages"]
    llm_with_tools = llm.bind_tools([verificar_expediente])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def nodo_insights(state: AgentState) -> dict:
    """Subagente Insights: reportes para gerentes."""
    llm = _get_llm(temperature=0.0)
    prompt = INSIGHTS_PROMPT.format(date=_today())
    messages = [SystemMessage(content=prompt)] + state["messages"]
    llm_with_tools = llm.bind_tools([generar_reporte_cartera])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def nodo_general(state: AgentState) -> dict:
    """Respuesta general cuando no se detecta intencion especifica."""
    llm = _get_llm(temperature=0.3)
    prompt = f"""Eres Ceres, el asistente virtual de Grupo Ceres, una financiera agricola mexicana.
Ofrecemos creditos con respaldo FIRA para agricultores, restaurantes, comercios y negocios rurales en Sinaloa, Nayarit, Jalisco y Guanajuato.

Responde de forma amable y concisa. Si el usuario necesita algo especifico, ofrecele:
- Consultar elegibilidad FIRA
- Generar una cotizacion
- Revisar requisitos de documentacion
- Dar seguimiento a su solicitud

Fecha actual: {_today()}"""
    messages = [SystemMessage(content=prompt)] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def router(state: AgentState) -> str:
    """Rutea al subagente segun la intencion detectada."""
    intent = state.get("intent", "general")
    route_map = {
        "fira": "fira",
        "cotizar": "cotizador",
        "scoring": "scoring",
        "documentos": "documentos",
        "seguimiento": "seguimiento",
        "insights": "insights",
    }
    return route_map.get(intent, "general")


# ---------------------------------------------------------------------------
# Construccion del grafo
# ---------------------------------------------------------------------------


def build_graph():
    """Construye y compila el grafo multi-agente."""
    workflow = StateGraph(AgentState)

    # Nodos
    workflow.add_node("orquestador", nodo_orquestador)
    workflow.add_node("fira", nodo_fira)
    workflow.add_node("cotizador", nodo_cotizador)
    workflow.add_node("scoring", nodo_scoring)
    workflow.add_node("documentos", nodo_documentos)
    workflow.add_node("seguimiento", nodo_seguimiento)
    workflow.add_node("insights", nodo_insights)
    workflow.add_node("general", nodo_general)

    # Flujo
    workflow.set_entry_point("orquestador")

    workflow.add_conditional_edges("orquestador", router, {
        "fira": "fira",
        "cotizador": "cotizador",
        "scoring": "scoring",
        "documentos": "documentos",
        "seguimiento": "seguimiento",
        "insights": "insights",
        "general": "general",
    })

    workflow.add_edge("fira", END)
    workflow.add_edge("cotizador", END)
    workflow.add_edge("scoring", END)
    workflow.add_edge("documentos", END)
    workflow.add_edge("seguimiento", END)
    workflow.add_edge("insights", END)
    workflow.add_edge("general", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# Singleton del grafo
# ---------------------------------------------------------------------------

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


def build_agent():
    """Compatibilidad con codigo existente. Devuelve el grafo multi-agente."""
    return get_graph()


def run_agent(query: str, telefono: str = "") -> str:
    """Ejecuta el grafo multi-agente para un mensaje dado."""
    graph = get_graph()
    result = graph.invoke({
        "messages": [HumanMessage(content=query)],
        "telefono": telefono,
        "lead_data": {},
    })
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        return last.content if hasattr(last, "content") else str(last)
    return "Lo siento, no pude procesar tu solicitud en este momento."
