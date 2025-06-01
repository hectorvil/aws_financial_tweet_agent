# 📊 BBVA Twitter Sentiment Monitor

Un sistema automático de análisis de sentimiento en tweets que mencionan a **BBVA**, construido sobre AWS Lambda, Amazon Bedrock y S3. El objetivo es conocer la percepción pública **hora a hora**, diferenciando entre:

- Tweets generales sobre el banco
- Tweets específicamente relacionados con su app

---

## ¿Qué hace?

- 🐦 **Ingesta automática** de tweets desde la API de Twitter cada 2 horas
- 💬 **Clasificación de sentimiento** (`positive`, `neutral`, `negative`) con **Claude 3 Sonnet (Amazon Bedrock)**
- ⚽ **Filtro de tweets de fútbol** para no contaminar la señal financiera
- 📱 **Identificación de tweets sobre la app BBVA**
- 🧾 **Almacenamiento en Parquet** en S3 particionado por `year/month/day/hour`
- 📈 **Generación de gráficos** automáticos cada 2 horas (App y General)
- ☁️ **Despliegue sin servidores** con AWS Lambda y contenedores

---

## 🔄 Flujo de extremo a extremo

| Etapa | Qué ocurre | Tecnología |
|-------|------------|------------|
| **1. EventBridge (cada 2h)** | Llama a la función `bbvaTweetIngestor` | AWS Scheduler |
| **2. Ingesta de tweets** | Busca menciones a "BBVA", filtra spam y clasifica con Claude 3 | Twitter API, Amazon Bedrock |
| **3. Guardado** | Se genera un Parquet y se sube a `s3://.../tweets/...` | S3 (versionado y particionado) |
| **4. Trigger automático** | Al subir un nuevo Parquet, se activa `bbvaTrendPlotContainer` | Trigger S3 (evento PUT) |
| **5. Generación de gráficos** | Se leen los últimos 30 Parquet, se agrupan por hora y sentimiento | pandas, matplotlib |
| **6. Subida de PNG** | Se guardan dos archivos en `s3://.../charts/` | PNG: uno para `app=True`, otro general |

---
## ¿Dónde encontrar cada parte?

| Carpeta / Archivo                 | Componente                          | Descripción                                                                                 |
|----------------------------------|-------------------------------------|---------------------------------------------------------------------------------------------|
| `lambda/`                        | Lambda ZIP (`bbvaTweetIngestor`)    | Función que se ejecuta cada 2 horas (vía AWS Scheduler). Ingiere tweets que mencionan a "BBVA", clasifica el sentimiento usando Claude 3 Sonnet (Amazon Bedrock), etiqueta `is_app` y `is_futbol`, y guarda archivos `.parquet` en S3 particionados por `year/month/day/hour`. |
| `bbva_plot_lambda/`              | Lambda contenedor (`bbvaTrendPlotContainer`) | Función basada en contenedor (Docker) que se activa automáticamente cuando se sube un nuevo `.parquet` a `s3://.../tweets/`. Carga los últimos 30 archivos, excluye `is_futbol=True`, filtra por `is_app`, y genera gráficos de tendencia de sentimiento (.png) por hora. |
| `bbva_plot_lambda/Dockerfile`    | Dockerfile del contenedor           | Imagen base para ejecutar `bbvaTrendPlotContainer` con las dependencias necesarias (`matplotlib`, `pandas`, `pyarrow`, `s3fs`). Se despliega como imagen a ECR y se conecta a Lambda. |
| `lambda/lambda_function.py`      | Código de `bbvaTweetIngestor`       | Lógica completa de ingesta: búsqueda en Twitter, clasificación con Bedrock, creación del `.parquet` y escritura en S3. |
| `bbva_plot_lambda/lambda_function.py` | Código de `bbvaTrendPlotContainer` | Lógica de visualización: lectura de Parquet, agrupación por hora y sentimiento, generación y guardado de gráficos en `s3://.../charts/`. |
| `lambda_build/`                  | Carpeta de construcción local       | Carpeta temporal usada para empaquetar la función `bbvaTweetIngestor` en formato `.zip`. **No se sube al repositorio**. |
| `.gitignore`                     | Exclusión de archivos locales       | Evita subir `.zip`, entornos virtuales, imágenes, cachés de Python y carpetas de build temporales. |

---
## 📊 Qué hace cada Lambda

### 1. `bbvaTweetIngestor` (ZIP)
- Se ejecuta cada 2 horas
- Busca tweets con `"BBVA"`, en español
- Clasifica con **Claude 3 Sonnet**
- Agrega `is_app` y `is_futbol`
- Guarda `.parquet` con columnas:  
  `tweet_id`, `text`, `sentiment`, `is_app`, `is_futbol`, `created_at`, etc.

### 2. `bbvaTrendPlotContainer` (Contenedor)
- Se activa por evento PUT en `s3://.../tweets/`
- Lee los últimos 30 `.parquet`
- Filtra `is_futbol=True` del gráfico general
- Genera:
  - `charts/app_<timestamp>.png`
  - `charts/general_<timestamp>.png`

---

## 🧰 Tecnologías utilizadas

- **AWS Lambda (ZIP y contenedor)**
- **Amazon Bedrock** (Claude 3 Sonnet)
- **Twitter API (v2)**
- **pandas, matplotlib, pyarrow**
- **EventBridge / AWS Scheduler**
- **S3 (almacenamiento y triggers)**

---

## 🛠 Cómo probarlo localmente

Aunque el sistema ya se encuentra **en producción**, ejecutándose automáticamente cada 2 horas mediante AWS Scheduler, también puedes probar las funciones de forma local para depuración o desarrollo.

### 🐍 A. Probar la función de ingesta (`bbvaTweetIngestor`)

1. Asegúrate de tener Python 3.9+ y las siguientes librerías instaladas:
   ```bash
   pip install tweepy boto3 pandas pyarrow```
2. Exporta tus variables de entorno necesarias:
```bash
  export TWITTER_BEARER="tu_token"
  export BUCKET_NAME="tu-bucket-s3"
```
3. Corre la función localmente:
```bash
  cd lambda/
  python lambda_function.py
```
Resultado:
- Buscará tweets de BBVA

- Clasificará con Claude 3 Sonnet (vía Bedrock)

- Guardará un .parquet nuevo localmente o en S3 según configuración. Si se guarda en S3, automaticamente se activará el trigger de bbvaTrendPlotContainer y producirá un png con la gráfica correspondiente.

---

## 🧪 Módulo interactivo: Research portafolio de inversión (en fase de pruebas)

Este repositorio también incluye una **fase experimental** que permite explorar los tweets clasificados a través de un **agente interactivo en Streamlit**, útil para:

- 🧠 Hacer preguntas sobre el historial de tweets usando RAG (Claude 3 Sonnet via Bedrock)
- ⚡ Buscar tweets en tiempo real desde cuentas financieras, mayormente especializado en finanzas mediante FinBert
- 📊 Visualizar sentimiento por *ticker* en dashboards

> 🧪 **Esta funcionalidad está en fase de pruebas. No está integrada aún a producción.**

---

### 🧩 Archivos de esta segunda parte

| Carpeta / Archivo       | Rol                                                                 |
|-------------------------|----------------------------------------------------------------------|
| `app.py`                | Interfaz principal de Streamlit                                      |
| `agent.py`              | Clase `FinancialTweetAgent` que orquesta ingestión, RAG y dashboard |
| `vector_db.py`          | Base vectorial ChromaDB con embeddings vía Titan o MiniLM            |
| `twitter_live.py`       | Búsqueda en tiempo real en Twitter                                   |
| `data_pipeline.py`      | Limpieza de texto, etiquetado con FinBERT y clasificación temática   |
| `bedrock_client.py`     | Cliente de Amazon Bedrock para Claude-3 y Titan                      |
| `plotting.py`           | Visualización de sentimiento con Plotly                              |
| `requirements.txt`      | Lista de dependencias para entorno local                             |

---

### 🚀 ¿Cómo probar esta parte?

## ☁️ Despliegue opcional en AWS: App interactiva (Streamlit)

Además del análisis automático con Lambda, puedes desplegar la app `app.py` como una interfaz web persistente en **AWS App Runner**.

> 🔒 Recomendado para entornos de prueba o producción donde se requiere acceso web constante al dashboard.

---

### 🚀 Opción recomendada: **AWS App Runner**

Permite desplegar aplicaciones Streamlit directamente desde un repositorio GitHub o contenedor, sin preocuparte por servidores.

#### 📦 Paso 1. Añadir un `Dockerfile` al repo

Crea un archivo llamado `Dockerfile` con este contenido:

```dockerfile
# Dockerfile para lanzar Streamlit + Bedrock
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

