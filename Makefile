.PHONY: demo-seed demo-reset demo-status

PYTHON ?= python3
DEMO_SEED := examples/platform_ops_demo/seed_platform_demo.py
DEMO_ARGS ?=

demo-seed:
	$(PYTHON) $(DEMO_SEED) $(DEMO_ARGS)

demo-reset:
	$(PYTHON) $(DEMO_SEED) --reset $(DEMO_ARGS)

demo-status:
	$(PYTHON) $(DEMO_SEED) --status $(DEMO_ARGS)
