.PHONY: all format lint spell_check spell_fix help

all: help

######################
# LINTING AND FORMATTING
######################

PYTHON_FILES=src/
MYPY_CACHE=.mypy_cache

lint:
	python -m ruff check .
	python -m ruff format $(PYTHON_FILES) --diff
	python -m ruff check --select I $(PYTHON_FILES)
	mkdir -p $(MYPY_CACHE) && python -m mypy --strict $(PYTHON_FILES) --cache-dir $(MYPY_CACHE)

format:
	ruff format $(PYTHON_FILES)
	ruff check --select I --fix $(PYTHON_FILES)

spell_check:
	codespell --toml pyproject.toml

spell_fix:
	codespell --toml pyproject.toml -w

######################
# HELP
######################

help:
	@echo '----'
	@echo 'format       - run code formatters'
	@echo 'lint         - run linters'
	@echo 'spell_check  - run spell checker'
	@echo 'spell_fix    - run spell checker with auto-fix'
