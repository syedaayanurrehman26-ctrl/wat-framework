FROM python:3.11-slim

WORKDIR /app

# Install system deps for lxml/bs4
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Health check: confirm Python can import the pipeline
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s \
  CMD python -c "import threadintel.worker" || exit 1

CMD ["python", "threadintel/run.py"]
