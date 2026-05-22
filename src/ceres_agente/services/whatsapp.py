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
from src.ceres_agente.services.notificaciones import enviar_correo_resumen
from src.ceres_agente import run_agent

PREGUNTAS = {
    "inicio": "👋 Hola, soy *Ceres*, el asistente de credito de *Grupo Ceres*.\n\n¿A que se dedica tu negocio? (ej. agricultura, restaurante, ganaderia, comercio)",
    "giro":       "📍 ¿En que municipio y estado se encuentra tu negocio?",
    "ubicacion":  "💰 ¿Cuanto dinero necesitas? (escribe solo el numero en pesos)",
    "monto":      "📅 ¿A cuantos meses quieres pagar? (ej. 12, 24, 36)",
    "plazo":      "👤 Por ultimo, ¿cual es tu nombre completo?",
    "nombre":     "🪪 ¿Cual es tu RFC? (si no lo tienes a la mano escribe *no tengo*)",
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


async def procesar_y_enviar(telefono: str, mensaje: str) -> None:
    """Procesa y envía respuesta via REST API (evita timeout de Twilio)."""
    try:
        respuesta = await procesar_mensaje(telefono, mensaje)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _enviar_mensaje, telefono, respuesta)
    except Exception as e:
        print(f"[Ceres] Error procesando {telefono}: {e}")
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, _enviar_mensaje, telefono,
                "Lo siento, ocurrio un problema. Por favor intenta de nuevo."
            )
        except Exception:
            pass


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
            partes = mensaje.replace(",", " ").split()
            datos["municipio"] = partes[0] if partes else mensaje
            datos["estado"] = partes[-1].lower() if len(partes) > 1 else "otro"
            _guardar_estado(conv, "ubicacion", datos, session)
            return PREGUNTAS["ubicacion"]

        if estado == "ubicacion":
            try:
                datos["monto"] = float(mensaje.replace(",", "").replace("$", "").replace(" ", ""))
            except ValueError:
                return "Por favor escribe solo el numero, sin letras ni simbolos. ¿Cuanto dinero necesitas?"
            _guardar_estado(conv, "monto", datos, session)
            return PREGUNTAS["monto"]

        if estado == "monto":
            try:
                datos["plazo"] = int(mensaje.replace(" ", "").replace("meses", ""))
            except ValueError:
                return "Escribe solo el numero de meses (ej. 12, 24, 36)."
            _guardar_estado(conv, "plazo", datos, session)

            # Evaluar elegibilidad FIRA con el agente multi-agente (orquestador -> subagente FIRA)
            consulta = (
                f"Mi negocio es {datos.get('giro')} en {datos.get('ubicacion_raw')}. "
                f"Quiero un credito de ${datos.get('monto'):,.0f} pesos a {datos.get('plazo')} meses. "
                f"¿Soy elegible segun las reglas de FIRA?"
            )
            loop = asyncio.get_event_loop()
            dictamen = await loop.run_in_executor(None, partial(run_agent, consulta, telefono))
            datos["dictamen"] = dictamen

            elegible = "NO ELEGIBLE" not in dictamen.upper()
            datos["elegible"] = elegible

            if not elegible:
                _guardar_estado(conv, "inicio", {}, session)
                return (
                    f"📋 *Evaluacion FIRA:*\n\n{dictamen}\n\n"
                    "Si tienes otra actividad o proyecto, escribeme y lo evaluamos."
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
                f"📊 *Tu cotizacion:*\n"
                f"• Monto: ${datos['monto']:,.0f}\n"
                f"• Plazo: {datos['plazo']} meses\n"
                f"• TIIE 28 dias: {tiie:.4f}%\n"
                f"• Tasa final: {tasa:.2f}% anual\n"
                f"• *Cuota mensual: ${cuota:,.2f}*\n\n"
                f"¿Quieres continuar con tu solicitud? Responde *SI* o *NO*"
            )

        if estado == "plazo":
            if mensaje.upper() in ("SI", "SÍ", "S", "YES", "1"):
                _guardar_estado(conv, "confirmado", datos, session)
                return PREGUNTAS["plazo"]
            else:
                _guardar_estado(conv, "inicio", {}, session)
                return "Entendido. Si en algun momento quieres retomar tu solicitud, escribeme. 👋"

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

            # Enviar correo de resumen a Grupo Ceres
            datos["score"] = resultado_score["score"]
            datos["decision"] = resultado_score["decision"]
            datos["fecha"] = datetime.utcnow().strftime("%d/%m/%Y %H:%M")
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, enviar_correo_resumen, datos.copy())

            _guardar_estado(conv, "inicio", {}, session)

            docs = (
                "📄 *Documentos requeridos (persona fisica):*\n"
                "• INE vigente (frente y reverso)\n"
                "• CURP\n"
                "• RFC / Constancia de situacion fiscal\n"
                "• Comprobante de domicilio (menos de 3 meses)\n"
                "• Estados de cuenta ultimos 3 meses\n"
                "• Autorizacion de consulta a Buro de Credito"
            )

            return (
                f"🎉 *¡Solicitud registrada exitosamente, {datos['nombre']}!*\n\n"
                f"Un ejecutivo de Grupo Ceres se pondra en contacto contigo pronto.\n\n"
                f"{docs}\n\n"
                f"Puedes enviarme tus documentos por aqui cuando los tengas listos. "
                f"Tambien puedes escribirme *'estatus'* en cualquier momento para consultar tu solicitud."
            )

        # Fallback: si llega un mensaje fuera del flujo, usar el agente multi-agente
        loop = asyncio.get_event_loop()
        respuesta = await loop.run_in_executor(None, partial(run_agent, mensaje, telefono))
        return respuesta
