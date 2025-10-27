.PHONY: dev-up dev-down dev-shell migrate seed test

dev-up:
	docker-compose up -d

dev-down:
	docker-compose down

dev-shell:
	docker-compose exec web bash

migrate:
	docker-compose exec web python manage.py migrate

seed:
	docker-compose exec web python manage.py seed_data

test:
	docker-compose exec web pytest
