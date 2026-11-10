# API + worker image (single image, two commands).
# Build context is the repository root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependency layer first for caching.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Application code.
COPY services ./services
COPY agents ./agents
COPY database ./database
COPY tools ./tools
COPY sandbox ./sandbox
COPY alembic.ini ./

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
