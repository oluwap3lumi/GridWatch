ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif

.PHONY: setup up down lint test build smoke seed train verify-train types hooks migrate verify-clean
setup up down lint test build smoke seed train verify-train types hooks migrate verify-clean:
	$(PYTHON) scripts/tasks.py $@
