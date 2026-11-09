# Setup

> Skeleton document — commands will work once the services are implemented.

## Requirements

- Python 3.12+
- Node.js 22+
- Docker
- Redis + PostgreSQL (hosted mode)

## Local development

```bash
# Python environment
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e ".[dev]"

# Environment
copy .env.example .env      # Windows
cp .env.example .env        # macOS/Linux

# Stack
docker compose up -d

# Dashboard
cd apps/dashboard
npm install
npm run dev
```

## Tests

```bash
pytest -q
ruff check .
mypy .
```
