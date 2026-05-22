import asyncio
import json
from datetime import datetime
from functools import partial

from sqlmodel import Session, select
from twilio.rest import Client

from src.ceres_agente.config.settings import get_settings
from src.ceres_agente.db.models import Conversacion, Lead
from src.ceres_agente.db.database import engine
from src.ceres_agente.services.scoring import calcular_score
from src.ceres_agente.services.tiie import obtener_tiie, SPREAD_CERES
from src.ceres_agente.services.cotizador import calcular_cuota
from src.ceres_agente import run_agent

PREGUNTAS = {
    "inicio": "👋 Hola, soy *Ceres*, el asistente de crédito de *Grupo Ceres*.\n\n¿A qué se dedica tu negocio? (ej. agricultura, restaurante, ganadería, comercio)",
    "giro":       "📍 ¿En qué municipio y estado se encuentra tu negocio?",
    "ubicacion":  "💰 ¿Cuánto dinero necesitas? (escribe solo el número en pesos)",
    "monto":      "📅 ¿A cuántos meses quieres pagar? (ej. 12, 24, 36)",
    "plazo":      "👤 Por último, ¿cuál es tu nombre completo?",
    "nombre":     "🪪 ¿Cuál es tu RFC? (si no lo tienes a la mano escribe *no tengo*)",
}


def _get_client() -> Client:
    s = get_settings()
    return Client(s.sid_twilo, s.auth_token_twilo)


def _enviar_mensaje(destinatario: str, mensaje: str):
    s = get_settings()
    _get_client().messages.create(
        from_=f"whatsapp:{s.numero_twilo}",
        to=f"whatsapp:{destinatario}",
        body=mensaje,
    )


def _get_o_crear_conversacion(telefono: str, session: Session) -> Conversacion:
    conv = session.exec(select(Conversacion).where(Conversacion.telefono == telefono)).first()
    if not conv:
        conv = Conversacion(telefono=telefono)
        session.add(conv)
        session.commit()
        session.refresh(conv)
    return conv


def _guardar_estado(conv: Conversacion, estado: str, datos: dict, session: Session):
    conv.estado = estado
    conv.datos_recolectados = json.dumps(datos, ensure_ascii=False)
    conv.actualizado_en = datetime.utcnow()
    session.add(conv)
    session.commit()


async def procesar_mensaje(telefono: str, mensaje: str) -> str:
    with Session(engine) as session:
        conv = _get_o_crear_conversacion(telefono, session)
        estado = conv.estado
        datos = json.loads(conv.datos_recolectados or "{}")
        mensaje = mensaje.strip()

        # --- FLUJO PASO A PASO ---

        if estado == "inicio":
            datos["giro"] = mensaje
            _guardar_estado(conv, "giro", datos, session)
            return PREGUNTAS["giro"]

        if estado == "giro":
            datos["ubicacion_raw"] = mensaje
            # Intentar separar municipio y estado
            partes = mensaje.replace(",", " ").split()
            datos["municipio"] = partes[0] if partes else mensaje
            datos["estado"] = partes[-1].lower() if len(partes) > 1 else "otro"
            _guardar_estado(conv, "ubicacion", datos, session)
            return PREGUNTAS["ubicacion"]

        if estado == "ubicacion":
            try:
                datos["monto"] = float(mensaje.replace(",", "").replace("$", "").replace(" ", ""))
            except ValueError:
                return "Por favor escribe solo el número, sin letras ni símbolos. ¿Cuánto dinero necesitas?"
            _guardar_estado(conv, "monto", datos, session)
            return PREGUNTAS["monto"]

        if estado == "monto":
            try:
                datos["plazo"] = int(mensaje.replace(" ", "").replace("meses", ""))
            except ValueError:
                return "Escribe solo el número de meses (ej. 12, 24, 36)."
            _guardar_estado(conv, "plazo", datos, session)

            # Evaluar elegibilidad FIRA con el agente RAG (en thread para no bloquear async)
            consulta = (
                f"Mi negocio es {datos.get('giro')} en {datos.get('ubicacion_raw')}. "
                f"Quiero un crédito de ${datos.get('monto'):,.0f} pesos a {datos.get('plazo')} meses. "
                f"¿Soy elegible según las reglas de FIRA?"
            )
            loop = asyncio.get_event_loop()
            dictamen = await loop.run_in_executor(None, partial(run_agent, consulta))
            datos["dictamen"] = dictamen

            elegible = "NO ELEGIBLE" not in dictamen.upper()
            datos["elegible"] = elegible

            if not elegible:
                _guardar_estado(conv, "inicio", {}, session)
                return (
                    f"📋 *Evaluación FIRA:*\n\n{dictamen}\n\n"
                    "Si tienes otra actividad o proyecto, escríbeme y lo evaluamos."
                )

            tiie = await obtener_tiie()
            tasa = tiie + SPREAD_CERES
            cuota = calcular_cuota(datos["monto"], tasa, datos["plazo"])
            datos["tiie"] = tiie
            datos["tasa"] = tasa
            datos["cuota"] = cuota

            _guardar_estado(conv, "plazo", datos, session)
            return (
                f"✅ *¡Buenas noticias! Tu actividad es elegible para financiamiento FIRA.*\n\n"
                f"📊 *Tu cotización:*\n"
                f"• Monto: ${datos['monto']:,.0f}\n"
                f"• Plazo: {datos['plazo']} meses\n"
                f"• TIIE 28 días: {tiie:.4f}%\n"
                f"• Tasa final: {tasa:.2f}% anual\n"
                f"• *Cuota mensual: ${cuota:,.2f}*\n\n"
                f"¿Quieres continuar con tu solicitud? Responde *SÍ* o *NO*"
            )

        if estado == "plazo":
            if mensaje.upper() in ("SI", "SÍ", "S", "YES", "1"):
                _guardar_estado(conv, "confirmado", datos, session)
                return PREGUNTAS["plazo"]
            else:
                _guardar_estado(conv, "inicio", {}, session)
                return "Entendido. Si en algún momento quieres retomar tu solicitud, escríbeme. 👋"

        if estado == "confirmado":
            datos["nombre"] = mensaje
            _guardar_estado(conv, "nombre", datos, session)
            return PREGUNTAS["nombre"]

        if estado == "nombre":
            datos["rfc"] = None if "no tengo" in mensaje.lower() else mensaje.upper()
            _guardar_estado(conv, "rfc", datos, session)

            # Calcular score ML y guardar lead
            ratio = datos["monto"] / (datos["monto"] * 0.3 * 12)
            resultado_score = calcular_score(
                giro=datos.get("giro", "otro"),
                estado=datos.get("estado", "otro"),
                monto=datos["monto"],
                plazo=datos["plazo"],
                ratio_monto_ingresos=ratio,
                antiguedad_fiscal=3,
                tipo_persona="fisica",
            )

            lead = Lead(
                nombre=datos["nombre"],
                telefono=telefono,
                rfc=datos.get("rfc"),
                giro=datos.get("giro", "otro"),
                municipio=datos.get("municipio", ""),
                estado=datos.get("estado", "otro"),
                monto_solicitado=datos["monto"],
                plazo_meses=datos["plazo"],
                tipo_credito="avio",
                elegible_fira=datos.get("elegible", True),
                tasa_final=datos.get("tasa"),
                cuota_mensual=datos.get("cuota"),
                score=resultado_score["score"],
                decision=resultado_score["decision"],
                status="pendiente_docs",
            )
            session.add(lead)
            session.commit()

            _guardar_estado(conv, "inicio", {}, session)

            docs = (
                "📄 *Documentos requeridos (persona física):*\n"
                "• INE vigente (frente y reverso)\n"
                "• CURP\n"
                "• RFC / Constancia de situación fiscal\n"
                "• Comprobante de domicilio (menos de 3 meses)\n"
                "• Estados de cuenta últimos 3 meses\n"
                "• Autorización de consulta a Buró de Crédito"
            )

            return (
                f"🎉 *¡Solicitud registrada exitosamente, {datos['nombre']}!*\n\n"
                f"Un ejecutivo de Grupo Ceres se pondrá en contacto contigo pronto.\n\n"
                f"{docs}\n\n"
                f"Tu número de folio es *#{lead.id}*. Guárdalo para dar seguimiento. ✅"
            )

        # Fallback
        _guardar_estado(conv, "inicio", {}, session)
        return PREGUNTAS["inicio"]
