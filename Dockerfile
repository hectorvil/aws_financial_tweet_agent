# ─────────────────────────────────────────────────────────────
# Financial-Tweet Agent • Imagen runtime ligera (≈ 600 MB)
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Variables de entorno esenciales
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

#  Instalar librerías del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl && \
    rm -rf /var/lib/apt/lists/*

#  Directorio de trabajo
WORKDIR /app

#  Copiar requirements primero (mejora la cache de Docker)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

#  Copiar el resto del código
COPY . .

#  Puerto donde escucha Streamlit
EXPOSE 8501

#  Comando de arranque
CMD ["streamlit", "run", "app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0"]
