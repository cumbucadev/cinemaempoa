pr:
	@uv run pytest --disable-warnings
	@uv run ruff check --fix
	@uv run ruff format
	@uv run djlint flask_backend/templates --lint --profile=jinja
	@uv run djlint --reformat flask_backend/templates --format-css --format-js
	@uv run vulture flask_backend scrapers cinemaempoa.py vulture_whitelist.py --exclude "*/tests/*" --min-confidence 80
