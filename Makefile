.PHONY: setup demo test lint dashboard
setup:
	python -m pip install -r requirements.lock
	python -m pip install --no-deps -e .
demo:
	ga4 demo
	ga4 build --input data/demo/events.parquet --output artifacts/demo
test:
	pytest -q
lint:
	ruff check .
	ruff format --check .
dashboard:
	streamlit run app.py
