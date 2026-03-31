.PHONY = build test test-metadata
.DEFAULT_GOAL = test

build:
	docker compose build

test:
	docker compose run --rm --build app

test-metadata:
	docker compose run --rm --build app uv run pytest -vv --doctest-modules -k "not test_generate_indices"
