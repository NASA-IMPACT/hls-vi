.PHONY = build test
.DEFAULT_GOAL = test

build:
	docker compose build

test:
	docker compose run --rm --build tox -- -v

test-metadata:
	docker compose run --rm --build tox -- -v -k "not test_generate_indices"
