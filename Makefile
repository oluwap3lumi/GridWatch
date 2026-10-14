ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif

.PHONY: setup up down lint test build smoke seed train verify-train types hooks migrate
setup up down lint test build smoke seed train verify-train types hooks migrate:
	$(PYTHON) scripts/tasks.py $@
