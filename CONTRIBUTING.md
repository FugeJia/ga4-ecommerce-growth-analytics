# Contributing

Use Python 3.12. Install requirements.lock and the editable package. Generate the default demo before pytest. Run `ruff check .`, `ruff format --check .`, and `pytest -q`.

Changes to metric definitions require updated docs and a meaningful regression fixture. Never commit credentials, raw public exports, user-level real data, or unsupported business claims. Keep synthetic examples labeled and generated deterministically. Record cloud execution separately from static SQL validation.
