# Arquitectura y Documentación Técnica: KronoFinanzas Ceres

Este documento contiene la especificación completa de la arquitectura, configuración de infraestructura en la nube (AWS), solución de problemas estructurales y la integración del backend para el prototipo del Hackatón de Agentes Inteligentes. 

---

## 1. Visión General del Proyecto
**KronoFinanzas Ceres** es un sistema inteligente de precalificación de crédito automatizado diseñado para el sector agrícola y agropecuario. El núcleo de la aplicación utiliza una arquitectura **RAG (Retrieval-Augmented Generation)** conectada de forma directa a las reglas de operación y normativas de **FIRA** (Fideicomisos Instituidos en Relación con la Agricultura) publicadas en el Diario Oficial de la Federación (DOF). 

El sistema evalúa de forma paramétrica si un perfil de productor o solicitante cumple con los criterios específicos geográficos (ej. restricciones en poblaciones menores a 50,000 habitantes), económicos, montos máximos en UDIS y sectores permitidos, emitiendo un dictamen financiero inmediato y citando las fuentes normativas exactas.

---

## 2. Stack Tecnológico General

| Capa | Tecnología / Servicio | Notas |
| :--- | :--- | :--- |
| **Frontend** | React + TypeScript + Vite | Interfaz responsiva, scannable y tipada, optimizada para asesores de crédito. |
| **Backend** | Python 3.10+ + FastAPI | API asíncrona de alto rendimiento para el procesamiento de solicitudes. |
| **Client SDK** | `boto3` / `botocore` | Librería oficial de AWS para interactuar con los servicios en la nube. |
| **Storage (Cloud)**| Amazon S3 | Repositorio de objetos donde residen los documentos fuente (PDFs normativos). |
| **Vector Database**| Amazon OpenSearch Serverless | Base de datos vectorial totalmente administrada por AWS en la nube. |
| **Embeddings** | Titan Text Embeddings v2 | Modelo de incrustación para transformar el PDF en vectores (1024 dimensiones). |
| **Orquestador RAG**| Amazon Bedrock Knowledge Bases | Motor que gestiona el parseo, chunking, almacenamiento e indexación vectorial. |
| **LLM (Cerebro)** | Anthropic Claude Sonnet | Modelo fundacional invocado mediante Bedrock para razonamiento normativo avanzado. |

---

## 3. Arquitectura Cloud (AWS) paso a paso

### 3.1. Almacenamiento de Origen (Amazon S3)
* **Bucket:** `fira-normativa-ceres-398050109115-us-east-2-an`
* **Región:** EE. UU. Este (Ohio) `us-east-2`
* **Contenido:** Contiene el archivo fuente `DOF - Diario Oficial de la Federación.pdf` con la normativa vigente de FIRA. Este archivo sirve como la única fuente de verdad (*Ground Truth*) para el agente.

### 3.2. Motor de Vectores y Embeddings (Knowledge Base)
Para maximizar los puntos técnicos en el hackatón, se implementó una base de conocimientos nativa que automatiza el procesamiento del documento eliminando bases vectoriales locales.
* **ID de la Base de Conocimientos:** `BWWFT7NT0O`
* **Estrategia de Fragmentación:** Predeterminada (Default chunking de texto).
* **Base de Datos Vectorial:** Amazon OpenSearch sin servidor (Serverless), aprovisionada automáticamente por AWS para evitar costos de infraestructura o aprovisionamientos manuales.

> ⚠️ **Regla de Operación Crítica (Sincronización):** Cada vez que se agregue o modifique un PDF en el bucket de S3, se debe ingresar a la consola de Bedrock, seleccionar el origen de datos y presionar el botón **Sincronizar (Sync)**. De lo contrario, el agente ignorará los nuevos datos.

---

## 4. Control de Seguridad e Identidades (IAM)

### Solución al error estructural de Cuenta Raíz (Root Account)
Durante la fase inicial de despliegue, AWS emitió un bloqueo de seguridad crítico:
`No se admite la creación de una base de conocimientos con un usuario raíz. Inicie sesión con un usuario o rol de IAM e inténtelo de nuevo.`

**Resolución Aplicada:**
1. Se restringió el uso de la cuenta raíz para la manipulación directa de Bedrock.
2. Se creó un usuario técnico dedicado bajo el servicio IAM llamado **`desarrollador-agent`**.
3. Se le asignó la política de control de acceso directo **`AdministratorAccess`**. Esto habilitó los privilegios requeridos para que el backend externo cree y consulte colecciones de OpenSearch Serverless y ejecute llamadas de inferencia en Bedrock sin topar con políticas restrictivas de VPC.

---

## 5. Exclusión de Arquitecturas Alternativas (ChromaDB / Docker)

**Por qué NO se utiliza ChromaDB ni contenedores locales de Docker en este proyecto:**
* **Duplicidad de Código:** ChromaDB local requeriría implementar scripts manuales en Python para la lectura del PDF, el manejo de librerías de partición de texto (*PyPDF*, *LangChain TextSplitters*) y el bucle de inserción vectorial. Bedrock resuelve esto mediante infraestructura nativa con un solo clic (Sync).
* **Persistencia y Despliegue:** Un contenedor local de ChromaDB no es accesible de forma nativa por una arquitectura cloud distribuida a menos que se configure tunelización (ngrok) o despliegues en instancias EC2 con almacenamiento adjunto (EBS), lo cual añade complejidad innecesaria para el tiempo del evento.
* **Criterio de Evaluación del Hackatón:** El uso de servicios Serverless administrados de AWS (S3 + Bedrock + OpenSearch) demuestra un nivel de madurez de arquitectura cloud significativamente superior para el ecosistema corporativo de Grupo Ceres.

---

## 6. Configuración del Entorno de Desarrollo (`.env`)

El archivo `.env` debe crearse en la raíz del proyecto de Backend (asegurándose de que esté listado en el archivo `.gitignore` para no subir credenciales a repositorios públicos). Utiliza la siguiente plantilla:

```env
# AWS IAM Credenciales del Usuario Técnico (desarrollador-agent)
AWS_ACCESS_KEY_ID=TU_ACCESS_KEY_ID_AQUÍ
AWS_SECRET_ACCESS_KEY=TU_SECRET_ACCESS_KEY_AQUÍ

# Configuración Regional de Infraestructura
AWS_REGION=us-east-2

# ID único de la Base de Conocimientos de Bedrock
AWS_KNOWLEDGE_BASE_ID=BWWFT7NT0O