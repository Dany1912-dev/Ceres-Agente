"""Servicio de notificaciones por correo — Resend."""

import resend
from ..config import get_settings


def enviar_correo_resumen(lead_data: dict) -> dict:
    """Envia un correo a Grupo Ceres con el resumen completo del prospecto:
    datos personales, cotizacion, score ML, dictamen FIRA y documentos requeridos.

    Args:
        lead_data: diccionario con todos los datos del lead recolectados

    Returns:
        dict con el resultado del envio (ok/error)
    """
    settings = get_settings()

    if not settings.resend_api_key:
        return {"ok": False, "error": "RESEND_API_KEY no configurada"}

    resend.api_key = settings.resend_api_key

    nombre = lead_data.get("nombre", "No proporcionado")
    telefono = lead_data.get("telefono", "No proporcionado")
    rfc = lead_data.get("rfc") or "No proporcionado"
    giro = lead_data.get("giro", "No especificado")
    ubicacion = lead_data.get("ubicacion_raw", "No especificada")
    monto = lead_data.get("monto", 0)
    plazo = lead_data.get("plazo", 0)

    tiie = lead_data.get("tiie", 0)
    tasa = lead_data.get("tasa", 0)
    cuota = lead_data.get("cuota", 0)

    elegible = "SI" if lead_data.get("elegible", False) else "NO"
    dictamen = lead_data.get("dictamen", "No disponible")
    score = lead_data.get("score", 0)
    decision = lead_data.get("decision", "pendiente")
    programa = lead_data.get("programa_fira", "Por determinar")

    semaforo = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(decision, "⚪")

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
        <h2 style="color: #1a5276;">📋 Nueva Solicitud — Grupo Ceres</h2>
        <p style="color: #666;">Recibida el {lead_data.get('fecha', 'hoy')}</p>

        <hr style="border: 1px solid #eee;">

        <h3 style="color: #2c3e50;">👤 Datos del Prospecto</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 6px; font-weight: bold;">Nombre</td><td style="padding: 6px;">{nombre}</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">Teléfono</td><td style="padding: 6px;">{telefono}</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">RFC</td><td style="padding: 6px;">{rfc}</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">Giro</td><td style="padding: 6px;">{giro}</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">Ubicación</td><td style="padding: 6px;">{ubicacion}</td></tr>
        </table>

        <h3 style="color: #2c3e50;">💰 Cotización</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 6px; font-weight: bold;">Monto solicitado</td><td style="padding: 6px;">${monto:,.2f} MXN</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">Plazo</td><td style="padding: 6px;">{plazo} meses</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">TIIE 28 días</td><td style="padding: 6px;">{tiie:.4f}%</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">Tasa final</td><td style="padding: 6px;">{tasa:.2f}% anual</td></tr>
            <tr><td style="padding: 6px; font-weight: bold; color: #1a5276;">Cuota mensual</td><td style="padding: 6px; color: #1a5276; font-weight: bold;">${cuota:,.2f}</td></tr>
        </table>

        <h3 style="color: #2c3e50;">📊 Evaluación Crediticia</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 6px; font-weight: bold;">Elegible FIRA</td><td style="padding: 6px;">{elegible}</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">Programa FIRA</td><td style="padding: 6px;">{programa}</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">Score ML</td><td style="padding: 6px;">{score*100:.1f}%</td></tr>
            <tr><td style="padding: 6px; font-weight: bold;">Decisión</td><td style="padding: 6px;">{semaforo} {decision.upper()}</td></tr>
        </table>

        <h3 style="color: #2c3e50;">📄 Documentos Pendientes</h3>
        <ul style="color: #555;">
            <li>INE vigente (frente y reverso)</li>
            <li>CURP</li>
            <li>RFC / Constancia de situación fiscal</li>
            <li>Comprobante de domicilio</li>
            <li>Estados de cuenta últimos 3 meses</li>
            <li>Autorización de consulta a Buró de Crédito</li>
        </ul>

        <hr style="border: 1px solid #eee;">

        <h3 style="color: #2c3e50;">📝 Dictamen FIRA</h3>
        <p style="color: #555; background: #f9f9f9; padding: 12px; border-radius: 6px; white-space: pre-wrap;">{dictamen}</p>

        <hr style="border: 1px solid #eee;">
        <p style="color: #999; font-size: 12px;">Este correo fue generado automáticamente por Ceres, el agente inteligente de Grupo Ceres.</p>
    </div>
    """

    try:
        response = resend.Emails.send({
            "from": settings.correo_remitente,
            "to": settings.correo_destino,
            "subject": f"📋 Nueva solicitud — {nombre} | {semaforo} {decision.upper()} | ${monto:,.0f} MXN",
            "html": html,
        })
        return {"ok": True, "id": response.get("id", ""), "destinatario": settings.correo_destino}
    except Exception as e:
        return {"ok": False, "error": str(e)}
