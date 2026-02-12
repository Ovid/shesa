.PHONY: install test test-frontend lint typecheck format all loc

install:
	pip install -e ".[dev]"

test:
	pytest -v

test-frontend:
	cd src/shesha/experimental/web/frontend && npx vitest run

lint:
	ruff check src tests

typecheck:
	mypy src/shesha

format:
	ruff format src tests
	ruff check --fix src tests

all: format lint typecheck test test-frontend

loc:
	@cloc src tests examples pyproject.toml Makefile run-web.sh \
		--exclude-dir=node_modules,dist \
		--not-match-f='package-lock\.json'
