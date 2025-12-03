.PHONY: dev-up dev-down dev-shell migrate seed test beat-up beat-down
.PHONY: prod-build prod-up prod-down prod-logs prod-shell
.PHONY: local-build local-up local-down local-logs local-shell local-migrate local-create-user
.PHONY: health backup create-hq-user generate-secrets check-setup

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

# Local testing commands (full stack test before deployment)
local-build:
	docker-compose -f docker-compose.local.yml build

local-up:
	docker-compose -f docker-compose.local.yml up -d

local-down:
	docker-compose -f docker-compose.local.yml down

local-logs:
	docker-compose -f docker-compose.local.yml logs -f

local-shell:
	docker-compose -f docker-compose.local.yml exec web bash

local-migrate:
	docker-compose -f docker-compose.local.yml exec web python manage.py migrate --noinput

local-create-user:
	@bash scripts/create_hq_user_local.sh

# Utility commands
health:
	@bash scripts/check_health.sh

backup:
	@bash scripts/backup_db.sh

create-hq-user:
	@bash scripts/create_hq_user.sh

generate-secrets:
	@bash scripts/generate_secrets.sh

check-setup:
	docker-compose exec web python manage.py check_setup
