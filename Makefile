PY ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: setup test lint validate demo eval run tick doctor

setup:            ## create venv, install, regenerate demo data
	test -d $(VENV) || $(PY) -m venv $(VENV)
	$(BIN)/pip install -q -e '.[dev]'
	-$(BIN)/backoffice demo reset   # refuses (harmlessly) once demo: true is removed
	$(BIN)/backoffice validate

test:             ## offline test suite (no tokens spent)
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check src tests

validate:         ## config, agents, Rule of Two, skills, schedules
	$(BIN)/backoffice validate

demo:             ## reset the demo company relative to today
	$(BIN)/backoffice demo reset

eval:             ## live evals against the demo company (spends tokens)
	$(BIN)/backoffice eval $(if $(CASE),--case $(CASE)) $(if $(TRIALS),--trials $(TRIALS))

run:              ## make run JOB=kpi-weekly
	$(BIN)/backoffice run $(JOB)

tick:
	$(BIN)/backoffice tick

doctor:
	$(BIN)/backoffice doctor
