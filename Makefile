.PHONY: setup dev start test test-agent test-web lint typecheck build demo-ready demo-reset smoke smoke-offline

PYTHON ?= .venv/bin/python
WEB = npm --prefix apps/web
export NEXT_TELEMETRY_DISABLED = 1

setup:
	./scripts/setup.sh

dev:
	./scripts/dev.sh

start:
	./scripts/dev.sh start

test: test-agent test-web

test-agent:
	$(PYTHON) -m pytest services/agent/tests

test-web:
	$(WEB) test

lint:
	$(WEB) run lint

typecheck:
	$(WEB) run typecheck

build:
	$(WEB) run build

demo-ready:
	$(PYTHON) scripts/smoke-test.py check

demo-reset:
	$(PYTHON) scripts/smoke-test.py reset

smoke:
	$(PYTHON) scripts/smoke-test.py flow

smoke-offline:
	$(PYTHON) scripts/smoke-test.py flow --expect-offline
