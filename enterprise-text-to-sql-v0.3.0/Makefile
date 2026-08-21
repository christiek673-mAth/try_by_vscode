.PHONY: install test lint check run

install:
	python3 -m pip install -r requirements-dev.txt

test:
	pytest -q

lint:
	ruff check app tests

check: lint test
	python3 -m compileall -q app tests
	git diff --check

run:
	uvicorn app.main:app --reload