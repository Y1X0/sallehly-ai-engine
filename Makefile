.PHONY: up down logs fmt lint test

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

fmt:
	uv run ruff format .

lint:
	uv run ruff check .

test:
	uv run pytest
