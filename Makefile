.PHONY = build test
.DEFAULT_GOAL = test

build:
	docker compose build

test:
	docker compose run --rm --build tox
