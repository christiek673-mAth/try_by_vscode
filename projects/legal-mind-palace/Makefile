.PHONY: install test lint check prepare-p0 index validate query web

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
	python3 -m app.cli --db-dir "$${LEGAL_DB_DIR:-data/chroma}" index --source-dir "$${LAW_SOURCE_DIR:?Set LAW_SOURCE_DIR to the cloned law directory}" --reset

validate:
	python3 -m app.cli validate --source-dir "$${LAW_SOURCE_DIR:?Set LAW_SOURCE_DIR to the law directory}"

prepare-p0:
	python3 -m app.cli prepare-p0 --source-dir "$${LAW_SOURCE_DIR:-data/authorized-laws}" --metadata-file "$${LEGAL_CATALOG_FILE:-data/catalogs/central-laws-p0.json}"

query:
	python3 -m app.cli --db-dir "$${LEGAL_DB_DIR:-data/chroma}" query --question "$${QUESTION:?Set QUESTION to a legal question}"

web:
	python3 -m app.cli --db-dir "$${LEGAL_DB_DIR:-data/chroma}" serve --host "$${LEGAL_HOST:-127.0.0.1}" --port "$${LEGAL_PORT:-8000}"
