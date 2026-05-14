FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install "poetry>=1.8,<2.0"

COPY packages/skeinrank-governance ./packages/skeinrank-governance
COPY packages/skeinrank-governance-api ./packages/skeinrank-governance-api

WORKDIR /app/packages/skeinrank-governance-api
RUN poetry install --only main \
    && python -m pip install "psycopg[binary]>=3,<4"

EXPOSE 8010

CMD ["skeinrank-governance-api", "--host", "0.0.0.0", "--port", "8010"]
