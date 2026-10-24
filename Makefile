UV := uv run --locked --extra dev

.PHONY: check format format-check typecheck test

check: format-check typecheck test

format:
	$(UV) isort .
	$(UV) black .

format-check:
	$(UV) isort --check-only .
	$(UV) black --check .

typecheck:
	$(UV) mypy
	PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring $(UV) pytest tools/tests -q

test:
	PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring $(UV) pytest tests -q
