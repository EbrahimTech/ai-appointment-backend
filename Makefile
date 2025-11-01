.PHONY: dev-up dev-down dev-shell migrate seed test beat-up beat-down

dev-up:
	docker-compose up -d

dev-down:
	docker-compose down

beat-up:
	docker-compose up -d beat

beat-down:
	docker-compose stop beat

dev-shell:
	docker-compose exec web bash

migrate:
	docker-compose exec web python manage.py migrate

seed:
	docker-compose exec web python manage.py seed_data

test:
	docker-compose exec web pytest
