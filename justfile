setup:
    uv venv
    uv pip install -e .

test:
    uv run python -m unittest discover -s tests

lint:
    uv run python -m compileall -q src tests

check: lint test
    uv run freshdocs doctor

build:
    uv build

ci: check build
