FROM python:3.13-slim

WORKDIR /app

# System deps for opencv, native extensions, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and filter out macOS-only packages before installing
COPY requirements.txt .
RUN grep -ivE '^(pyobjc|ocrmac)' requirements.txt > requirements-docker.txt \
    && pip install --no-cache-dir -r requirements-docker.txt \
    && rm requirements-docker.txt

# Copy application code
COPY . .

RUN mkdir -p data/users data/vectorstore

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
