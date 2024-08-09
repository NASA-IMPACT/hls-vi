.PHONY = build test

build:
	docker compose build

test:
	docker compose run --rm --build tox
