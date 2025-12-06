.PHONY: dev-up dev-down dev-shell migrate seed test beat-up beat-down
.PHONY: prod-build prod-up prod-down prod-logs prod-shell
.PHONY: health backup create-hq-user generate-secrets

# Development commands
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

# Production commands
prod-build:
	docker-compose -f docker-compose.prod.yml build

prod-up:
	docker-compose -f docker-compose.prod.yml up -d

prod-down:
	docker-compose -f docker-compose.prod.yml down

prod-logs:
	docker-compose -f docker-compose.prod.yml logs -f

prod-shell:
	docker-compose -f docker-compose.prod.yml exec web bash

prod-migrate:
	docker-compose -f docker-compose.prod.yml exec web python manage.py migrate --noinput

# Utility commands
health:
	@bash scripts/check_health.sh

backup:
	@bash scripts/backup_db.sh

create-hq-user:
	@bash scripts/create_hq_user.sh

generate-secrets:
	@bash scripts/generate_secrets.sh
