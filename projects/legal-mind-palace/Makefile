.PHONY: install test lint check index query

install:
	python3 -m pip install -r requirements-dev.txt

test:
	pytest -q

lint:
	ruff check app tests

check: lint test
	python3 -m compileall -q app tests
	git diff --check

index:
	python3 -m app.cli index --source-dir "$${LAW_SOURCE_DIR:?Set LAW_SOURCE_DIR to the cloned law Markdown directory}" --reset

query:
	python3 -m app.cli query --question "$${QUESTION:?Set QUESTION to a legal question}"
