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
- 📈 **Generación de gráficos** automáticos por hora (App y General)
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

## 🛠 Cómo ejecutarlo localmente (para pruebas)

### Ingesta (opcional)

```bash
cd lambda/
python lambda_function.py
