FROM python:3.12-slim

LABEL maintainer="Threadpower Labs"
LABEL description="The Architect — Sovereign Development & Autonomy Platform"

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Application code
COPY . .

# Non-root user for security
RUN useradd -m architect && chown -R architect:architect /app
USER architect

EXPOSE 8000

CMD ["uvicorn", "architect.main:app", "--host", "0.0.0.0", "--port", "8000"]
