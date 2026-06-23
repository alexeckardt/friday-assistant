.PHONY: up down dev logs build build-clean shell import-workflows

# ── Local dev (docker-compose) ────────────────────────────────────────────────
up:
	docker compose up -d
	@echo "\nFriday is up:"
	@echo "  Voice service → http://localhost:8000"
	@echo "  n8n UI        → http://localhost:5678"

down:
	docker compose down

build:
	docker compose build

build-clean:
	docker compose build --no-cache

logs:
	docker compose logs -f voice

logs-n8n:
	docker compose logs -f n8n

shell:
	docker compose exec voice bash

# ── n8n workflow import ───────────────────────────────────────────────────────
# Run this after 'make up' to load all workflows into n8n.
# You'll still need to add credentials (Anthropic, Twilio) in the n8n UI.
import-workflows:
	@echo "Importing n8n workflows..."
	docker compose exec n8n n8n import:workflow --input=/workflows/notify-complete.json
	docker compose exec n8n n8n import:workflow --input=/workflows/task-research.json
	docker compose exec n8n n8n import:workflow --input=/workflows/task-dispatcher.json
	docker compose exec n8n n8n import:workflow --input=/workflows/sms-agent.json
	@echo "Done. Open http://localhost:5678 to activate them."

# ── Health check ──────────────────────────────────────────────────────────────
health:
	curl -s http://localhost:8000/health | python3 -m json.tool

# ── ngrok tunnel (local → public, for Twilio webhook testing) ─────────────────
# Requires: brew install ngrok && ngrok config add-authtoken <token>
tunnel:
	ngrok http 8000
