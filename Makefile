.PHONY: demo-seed demo-reset demo-status headless-up headless-down headless-reset headless-golden-path agent-demo agent-demo-report agent-eval agent-eval-report agent-deploy-plan agent-deploy-recipe agent-compose-config agent-new-alias-smoke-plan agent-new-alias-smoke-report agent-es-evidence-plan agent-es-evidence-report agent-tracking-plan agent-tracking-report agent-integration-smoke-plan agent-integration-smoke-report agent-real-es-validation-plan agent-real-es-validation-fixtures agent-real-es-validation-index agent-real-es-validation-report

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

agent-eval:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-evaluation-report

agent-eval-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-evaluation-report examples/agents/openrouter_alias_scout/reports/evaluation-report.json


agent-deploy-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-deployment-recipe

agent-deploy-recipe:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-deployment-recipe examples/agents/openrouter_alias_scout/reports/deployment-recipe.json

agent-compose-config:
	docker compose --env-file deploy/docker/openrouter-alias-scout.env.example -f deploy/docker/openrouter-alias-scout.compose.yml config

agent-new-alias-smoke-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-new-alias-smoke-plan

agent-new-alias-smoke-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-new-alias-smoke-llm-report examples/agents/openrouter_alias_scout/reports/new-alias-smoke-llm-report.json
agent-es-evidence-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-elasticsearch-evidence-plan

agent-es-evidence-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --sample-evidence-from-elasticsearch > examples/agents/openrouter_alias_scout/reports/elasticsearch-evidence-report.json
agent-tracking-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-agent-tracking-plan

agent-tracking-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-agent-tracking-report examples/agents/openrouter_alias_scout/reports/agent-tracking-report.json


agent-proposal-inbox-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-proposal-inbox-plan

agent-proposal-inbox:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-proposal-inbox examples/agents/openrouter_alias_scout/reports/proposal-inbox.json --llm-review-report examples/agents/openrouter_alias_scout/reports/llm-review-report.json


agent-approved-apply-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-approved-apply-plan

agent-approved-apply:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-approved-apply-plan examples/agents/openrouter_alias_scout/reports/approved-apply-plan.json --proposal-inbox-report examples/agents/openrouter_alias_scout/reports/proposal-inbox.json

agent-snapshot-eval:
	mkdir -p examples/agents/openrouter_alias_scout/reports
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-snapshot-evaluation-report examples/agents/openrouter_alias_scout/reports/snapshot-evaluation-report.json --approved-apply-plan examples/agents/openrouter_alias_scout/reports/approved-apply-plan.json

agent-scheduled-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-scheduled-runner-plan

agent-cycle:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-agent-cycle

agent-cycle-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/scheduled
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-agent-cycle-report examples/agents/openrouter_alias_scout/reports/scheduled/agent-cycle-report.json

agent-integration-smoke-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-integration-smoke-plan

agent-integration-smoke-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/integration
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-integration-smoke-report examples/agents/openrouter_alias_scout/reports/integration/full-integration-smoke-report.json


agent-real-es-validation-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-real-elasticsearch-validation-plan

agent-real-es-validation-fixtures:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-real-elasticsearch-validation-fixtures

agent-real-es-validation-index:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --index-real-elasticsearch-validation-docs

agent-real-es-validation-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/real_es_validation
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-real-elasticsearch-validation-report examples/agents/openrouter_alias_scout/reports/real_es_validation/real-es-validation-report.json

agent-artifacts-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-artifacts-standard-plan

agent-artifacts-manifest:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-artifacts-manifest examples/agents/openrouter_alias_scout/reports/scheduled/manifest.json --artifacts-run-id openrouter-alias-scout-cycle


agent-docker-demo-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-docker-demo-plan

agent-docker-demo-config:
	deploy/docker/scripts/openrouter-agent-full-demo.sh config

agent-docker-demo-run:
	deploy/docker/scripts/openrouter-agent-full-demo.sh run

agent-dictionary-quickstart-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-dictionary-quickstart-plan

agent-dictionary-quickstart-payloads:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-dictionary-quickstart-payloads

agent-dictionary-quickstart-validate agent-runtime-smoke-plan agent-runtime-smoke-report:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --run-dictionary-quickstart

agent-runtime-smoke-plan:
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --print-runtime-api-smoke-plan

agent-runtime-smoke-report:
	mkdir -p examples/agents/openrouter_alias_scout/reports/runtime-smoke
	$(PYTHON) examples/agents/openrouter_alias_scout/run_alias_scout.py --write-runtime-api-smoke-report examples/agents/openrouter_alias_scout/reports/runtime-smoke/runtime-api-smoke-report.json
