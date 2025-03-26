.PHONY: setup sync dev-sync test clean ensure-uv

VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python3
UV := $(shell which uv 2>/dev/null || echo "$(VENV_DIR)/bin/uv")

ensure-uv:
	@if ! which uv > /dev/null; then \
		echo "uv not found, creating virtual environment..."; \
		python3 -m venv $(VENV_DIR); \
		$(VENV_DIR)/bin/pip install uv; \
	else \
		echo "uv found in PATH, using it."; \
	fi

$(VENV_DIR): ensure-uv
	@if [ ! -d $(VENV_DIR) ]; then \
		$(UV) venv; \
	fi

setup: $(VENV_DIR)
	$(UV) pip install -e .

sync: $(VENV_DIR)
	$(UV) sync

dev-sync: $(VENV_DIR)
	$(UV) pip install -e ".[dev]"

test: dev-sync
	$(UV) run pytest

clean:
	rm -rf $(VENV_DIR)
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf __pycache__
	rm -rf */__pycache__
