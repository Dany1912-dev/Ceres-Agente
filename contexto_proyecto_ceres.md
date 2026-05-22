# Contexto del Proyecto — Agente Inteligente de Ventas para Grupo Ceres

## Descripción general

Se trata de un Build Day con fecha 21 de mayo de 2026. El objetivo es construir un **Agente de IA para Ventas** capaz de ayudar o reemplazar parcialmente tareas críticas del proceso comercial. El proyecto se enfoca en una empresa financiera real llamada **Grupo Ceres**, para la cual se construirá un agente de cotización de financiamiento con subagentes especializados.

---

## La empresa: Grupo Ceres

Grupo Ceres es una empresa agrícola que agrupa varias subsidiarias:

- El Valle
- Defersa
- Armes
- Triple T

### Modelo de negocio

Grupo Ceres es un **Intermediario Financiero No Bancario (IFNB)**, probablemente una SOFOM no regulada. Se fondea de **FIRA** (Fideicomisos Instituidos en Relación con la Agricultura), que es banca de segundo piso dependiente de Banco de México. FIRA no presta directo al cliente final, sino a través de intermediarios como Ceres.

**Flujo de fondeo:**
```
FIRA → Grupo Ceres (IFNB) → Cliente final
```

La tasa que cobra Ceres al cliente es:
```
Tasa final = TIIE 28 días + 8 puntos adicionales (spread de Ceres)
```

TIIE 28 días al 19 de mayo de 2026: **6.7458%**
Tasa final actual de referencia: **~14.75% anual**

### Situación actual

Antes financiaban exclusivamente a agricultores, pero por diversificación ahora también atienden:
- Restaurantes
- Comercios
- Negocios rurales
- Cualquier actividad económica lícita en el medio rural

Tienen presencia en:
- Noroeste de México (Sinaloa principalmente)
- Nayarit
- Jalisco
- Guanajuato

**Problema principal:** No pueden visitar físicamente a cada prospecto en los cuatro estados. Quieren digitalizar el proceso de cotización para que los clientes puedan iniciar su solicitud sin necesidad de una visita del ejecutivo.

---

## FIRA — Información relevante

### Qué es FIRA

Cuatro fideicomisos públicos administrados por Banco de México:
- **FONDO** — crédito y garantías agropecuarias
- **FEFA** — financiamientos agropecuarios
- **FOPESCA** — actividades pesqueras
- **FEGA** — garantías de crédito

### Productos de crédito disponibles

| Producto | Para qué | Plazo máximo |
|---|---|---|
| Avío / capital de trabajo | Insumos, materias primas, jornales | 2 años (5 si es permanente) |
| Refaccionario | Inversiones fijas, equipamiento | 15 años (20 forestales) |
| Prendario | Capital de trabajo con inventario pignorado | 180 días |
| Arrendamiento financiero/puro | Bienes muebles e inmuebles | 15 años |
| Factoraje financiero | Adelanto sobre facturas | Corto plazo |
| Quirografario | Sin garantía específica | Variable |

### Sectores elegibles (clave para el cotizador)

- **Sector agropecuario tradicional** — aplica siempre
- **Financiamiento Rural** — cualquier actividad económica lícita en el medio rural, diferente del agro
- **Crédito Orgullo Rural** — hoteles, restaurantes y turismo en poblaciones menores a 50,000 habitantes
- **Del Campo al Plato** — restaurantes en cadena de valor turística (pueden ser ciudad grande si pertenecen a esta cadena)

### Requisitos para IFNB como Ceres

- Ser usuario de una Sociedad de Información Crediticia (SIC / Buró de Crédito)
- Reportar todas las operaciones de crédito al SIC
- Concentración máxima de cartera: **30% personas morales, 10% personas físicas** respecto al capital contable
- Apegarse a Disposiciones CUIFE

### Garantías

- FEGA: cobertura del 40%
- FONAGA: fondo de garantías adicional
- El intermediario puede solicitar garantía FIRA complementaria

---

## El agente a construir

### Objetivo

No es hacer un chatbot bonito. Es construir algo que el equipo de Grupo Ceres usaría mañana mismo: un sistema que digitalice el proceso de cotización de créditos, desde que el prospecto manda el primer mensaje hasta que el ejecutivo recibe el expediente completo.

### Arquitectura: Multi-agente con subagentes especializados

Un **orquestador principal (LangGraph)** recibe el mensaje, identifica la intención y activa el subagente correcto.

#### Subagentes

1. **Cotizador** — calcula la tasa (TIIE + spread del gerente), determina el tipo de crédito apropiado, valida plazos contra máximos de FIRA
2. **Scoring ML** — predice probabilidad de pago usando RandomForest, genera feature importance para explicar rechazos
3. **RAG FIRA** — consulta reglas de FIRA en OpenSearch para determinar elegibilidad por sector y ubicación
4. **Documentos** — solicita, recibe y organiza la papelería del cliente en S3
5. **Seguimiento** — manda recordatorios automáticos, actualiza estados, notifica al ejecutivo
6. **Insights (Gerente)** — responde preguntas del gerente sobre la cartera, genera reportes, analiza patrones de rechazo

### Flujo de interacción con el cliente

```
1. Cliente escribe por WhatsApp
2. Orquestador detecta intención
3. Subagente RAG FIRA evalúa elegibilidad (sector + ubicación)
   → Si no elegible: explica motivo y cierra
   → Si elegible: continúa
4. Subagente Cotizador genera cotización
   (TIIE en vivo + filtros del gerente)
5. Agente muestra cotización al cliente
6. Cliente confirma que quiere proceder
7. Agente registra datos del cliente (nombre, RFC)
8. Subagente Documentos solicita papelería
9. Cliente manda docs por WhatsApp → van a S3
10. Sistema notifica al ejecutivo por correo (SES) con resumen + score
11. Subagente Seguimiento manda recordatorios si hay docs pendientes
```

### Flujo del gerente

- Configura filtros de aprobación (montos, sectores, regiones) que el agente respeta automáticamente
- Consulta la cartera en lenguaje natural: "¿por qué rechazamos tanto en Jalisco?"
- Recibe expedientes completos con score ML y links a S3
- Recibe reporte semanal automático cada lunes

### Scoring ML

- **Modelo:** RandomForest (scikit-learn)
- **Features:** giro del negocio, municipio/estado, monto solicitado, plazo, ratio monto/ingresos, antigüedad fiscal, tipo de persona (física/moral)
- **Output:** probabilidad de pago (0 a 1) + feature importance (SHAP)
- **Decisión:**
  - Verde (+70%): solicita documentos automáticamente
  - Amarillo (40-70%): escala a ejecutivo humano
  - Rojo (-40%): rechaza con explicación de los factores

### Datos históricos

No existen datos reales todavía. Se generarán **datos sintéticos** usando distribuciones realistas basadas en el perfil de clientes de Ceres (agricultores en Sinaloa, restaurantes rurales, comercios en municipios pequeños).

---

## Documentación requerida por cliente

### Persona física
- INE vigente (frente y reverso)
- CURP
- RFC (constancia de situación fiscal)
- Comprobante de domicilio (menos de 3 meses)
- Estados de cuenta últimos 3 meses
- Autorización de consulta a Buró de Crédito

### Persona moral
- Acta constitutiva
- RFC de la empresa
- Poder del representante legal
- Identificación del representante
- Estados financieros último ejercicio
- Declaraciones anuales últimos 2 años
- Comprobante de domicilio fiscal
- Autorización de consulta a Buró

---

## Stack tecnológico

### AWS (principal)

| Componente | Servicio | Para qué |
|---|---|---|
| LLM | Bedrock — Claude Sonnet 4.5 | Cerebro de los subagentes |
| Base de datos principal | RDS PostgreSQL | Leads, cotizaciones, filtros del gerente |
| Estado de conversaciones | DynamoDB | Clave = número de teléfono |
| Archivos / documentos | S3 | INE, RFC, comprobantes por carpeta RFC |
| Vector DB / RAG | OpenSearch | Reglas FIRA en embeddings |
| Correo | SES | Notificaciones automáticas a Ceres |
| Analytics | Athena | SQL sobre historial en S3 |
| Reporte automático | EventBridge | Dispara Lambda cada lunes 8 AM |
| Deploy | Lambda + API Gateway + Docker | Webhook de WhatsApp |
| Secretos | Secrets Manager | Sin hardcodear credenciales |

### Externo (sin alternativa en AWS)

| Componente | Servicio | Para qué |
|---|---|---|
| WhatsApp | Twilio | Canal de comunicación con el cliente |
| TIIE en vivo | Banxico SIE API | Calcular tasa del día |
| Ubicación rural/urbano | Google Maps Geocoding | Validar elegibilidad geográfica |
| Score crediticio | Buró de Crédito | Mock en Build Day, real en producción |

### Librerías Python

- FastAPI
- LangGraph
- LangChain AWS
- boto3
- scikit-learn
- SHAP
- psycopg2
- twilio
- Docker
- ngrok (solo desarrollo local)

---

## Estructura de S3

```
ceres-expedientes/
├── {RFC_cliente_1}/
│   ├── ine_frente.jpg
│   ├── ine_reverso.jpg
│   ├── comprobante_domicilio.pdf
│   └── estado_cuenta.pdf
├── {RFC_cliente_2}/
│   └── ...
```

## Estructura de RDS PostgreSQL (tablas principales)

- **leads** — datos del prospecto, estado del expediente, score ML, docs entregados/faltantes, URLs en S3
- **cotizaciones** — monto, plazo, tasa, tipo de crédito, programa FIRA, resultado
- **filtros_gerente** — reglas dinámicas que el gerente configura
- **conversaciones** — historial por número de teléfono (respaldo de DynamoDB)

---

## Correo automático a Grupo Ceres

Cuando el cliente confirma que quiere proceder, el sistema manda automáticamente un correo vía SES a la empresa con:

- Datos del cliente (nombre, RFC, teléfono, giro, municipio)
- Programa FIRA que aplica
- Cotización generada (monto, plazo, tasa, cuota mensual)
- Score ML y factores principales
- Estado del expediente y links a S3
- Link al expediente en el CRM

---

## Reporte semanal automático (EventBridge + Lambda + SES)

Cada lunes 8 AM se genera automáticamente un reporte con:

- Total de solicitudes de la semana
- Tasa de aprobación general y por estado
- Top razones de rechazo con porcentajes
- Monto promedio solicitado vs aprobado
- Perfil del cliente con mayor tasa de aprobación
- Observación automática del agente con recomendación de negocio

---

## Rúbrica de evaluación del Build Day

El proyecto se evalúa con estos criterios:

- Impacto real en negocio
- Creatividad
- Calidad de la experiencia
- Nivel de autonomía
- Integraciones
- Uso inteligente de AI/ML
- Ejecución técnica
- Qué tan rápido hace pensar "necesito esto en mi empresa"

### Requisitos obligatorios del Build Day

1. Activarse desde un canal de comunicación real (WhatsApp vía Twilio)
2. Conectarse a una fuente de datos (RDS PostgreSQL + S3)
3. Integrarse con un CRM (RDS PostgreSQL con vista tipo CRM)
4. Incluir al menos una técnica de Machine Learning (RandomForest scoring + SHAP)

### Punto extra

Integrar embeddings/vector DB — cubierto con OpenSearch para reglas FIRA

---

## Notas importantes

- Para el Build Day, OpenSearch corre localmente con Docker. En producción se migra a OpenSearch Serverless en AWS.
- El Buró de Crédito se mockea en Build Day con una función Python que genera scores realistas (distribución normal, media 650, desv 100).
- Los datos del modelo ML son sintéticos generados con distribuciones realistas basadas en el perfil de clientes de Ceres.
- Todo el desarrollo se hace local primero (FastAPI + ngrok) y se despliega a Lambda en las últimas 2-3 horas del Build Day.
- La TIIE 28 días se consulta en vivo desde la API de Banxico SIE en cada cotización.
