.PHONY: install test lint typecheck format all loc

install:
	pip install -e ".[dev]"

test:
	pytest -v

lint:
	ruff check src tests

typecheck:
	mypy src/shesha

format:
	ruff format src tests
	ruff check --fix src tests

all: format lint typecheck test

loc:
	@cloc src tests examples pyproject.toml Makefile run-web.sh \
		--exclude-dir=node_modules,dist \
		--not-match-f='package-lock\.json'
