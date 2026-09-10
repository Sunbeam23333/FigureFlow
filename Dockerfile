FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    GRADIO_SHARE=false \
    FIGUREFLOW_OUTPUT_DIR=demo/output \
    FIGUREFLOW_MAX_RUNS=8

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        fonts-noto-cjk \
        fonts-dejavu-core \
        fontconfig \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml README.md LICENSE ./
COPY demo_core ./demo_core
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/demo/output \
    && useradd --create-home --uid 10001 figureflow \
    && chown -R figureflow:figureflow /app

USER figureflow

EXPOSE 7860

CMD ["python", "app.py"]
