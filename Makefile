.PHONY: demo-seed demo-reset demo-status headless-up headless-down headless-reset headless-golden-path agent-demo agent-demo-report

PYTHON ?= python3
DEMO_SEED := examples/platform_ops_demo/seed_platform_demo.py
DEMO_ARGS ?=
HEADLESS_COMPOSE := docker compose --env-file deploy/docker/headless.env.example -f docker-compose.headless.yml

demo-seed:
	$(PYTHON) $(DEMO_SEED) $(DEMO_ARGS)

demo-reset:
	$(PYTHON) $(DEMO_SEED) --reset $(DEMO_ARGS)

demo-status:
	$(PYTHON) $(DEMO_SEED) --status $(DEMO_ARGS)

headless-up:
	$(HEADLESS_COMPOSE) up --build -d

headless-down:
	$(HEADLESS_COMPOSE) down

headless-reset:
	$(HEADLESS_COMPOSE) down -v

headless-golden-path:
	deploy/docker/scripts/headless-golden-path.sh

agent-demo:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report

agent-demo-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-demo-report examples/agents/openrouter_alias_scout/reports/demo-report.json
