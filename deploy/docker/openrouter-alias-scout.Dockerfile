FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY examples/agents/openrouter_alias_scout ./examples/agents/openrouter_alias_scout

CMD ["python", "examples/agents/openrouter_alias_scout/run_alias_scout.py", "--run-evaluation-report"]
