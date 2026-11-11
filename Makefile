VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: start test

$(PY):
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev]"

start: $(PY)
	$(PY) -m uvicorn mission_control.main:app --host 127.0.0.1 --port 47821

test: $(PY)
	$(PY) -m pytest
