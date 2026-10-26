.PHONY: all test check guard clean

all: test

guard:
	PYTHONPATH=. ./.venv/bin/python3 scripts/licence_and_secret_guard.py

test-cli:
	PYTHONPATH=.:packages/cli ./.venv/bin/pytest -v packages/cli/tests

test-web:
	npm --prefix packages/web test

test-contracts:
	~/.foundry/bin/forge test --root packages/contracts

test: guard test-cli test-contracts test-web

clean:
	rm -rf .pytest_cache packages/cli/__pycache__ packages/cli/tests/__pycache__ packages/web/dist
