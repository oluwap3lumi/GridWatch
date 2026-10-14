ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif

.PHONY: setup up down lint test build smoke seed train types hooks
setup up down lint test build smoke seed train types hooks:
	$(PYTHON) scripts/tasks.py $@
