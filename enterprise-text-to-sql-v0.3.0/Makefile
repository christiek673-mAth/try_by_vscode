.PHONY: install test lint check run

PROJECT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

install:
	python3 -m pip install -r $(PROJECT_DIR)requirements-dev.txt

test:
	cd $(PROJECT_DIR) && pytest -q

lint:
	cd $(PROJECT_DIR) && ruff check app tests

check: lint test
	cd $(PROJECT_DIR) && python3 -m compileall -q app tests
	git diff --check

run:
	cd $(PROJECT_DIR) && uvicorn app.main:app --reload