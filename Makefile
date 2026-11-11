PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python
READY := $(VENV)/.dependencies-installed

.PHONY: setup start test

setup: $(READY)

$(PY):
	$(PYTHON) -c 'import sys; sys.exit("Python 3.11 or newer is required. Run make with PYTHON=/path/to/python3.11 (or newer).") if sys.version_info < (3, 11) else None'
	$(PYTHON) -m venv $(VENV)

$(READY): pyproject.toml $(PY)
	$(PY) -c 'import sys; sys.exit("This virtual environment requires Python 3.11 or newer. Choose a fresh VENV path and a supported PYTHON.") if sys.version_info < (3, 11) else None'
	$(PY) -m pip install -e ".[dev]"
	touch $(READY)

start: setup
	$(PY) -m uvicorn mission_control.main:app --host 127.0.0.1 --port 47821

test: setup
	$(PY) -m pytest
