# Scripts

Helper scripts for deployment and maintenance.

## Available Scripts

- **setup.sh** - Initial project setup (creates .env, venv, installs deps)
- **deploy.sh** - Production deployment preparation (builds images, runs migrations)
- **health_check.sh** - System health verification (endpoints, DB, Redis)
- **backup_db.sh** - PostgreSQL backup with compression and cleanup

## Usage

```bash
chmod +x scripts/*.sh
./scripts/setup.sh
./scripts/deploy.sh
./scripts/health_check.sh
./scripts/backup_db.sh
```

## Cron Jobs (Linux/Mac)

```bash
# Health check every 5 minutes
*/5 * * * * /path/to/scripts/health_check.sh >> /var/log/health_check.log 2>&1

# Daily backup at 2 AM
0 2 * * * /path/to/scripts/backup_db.sh >> /var/log/backup.log 2>&1
```

