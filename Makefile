.PHONY: dev test engine-dev engine-test mcp seed contracts preflight

dev: engine-dev

engine-dev:
	cd services/sag-engine && PYTHONPATH=src uvicorn sag_video.app:app --reload --port 8080

test: engine-test

engine-test:
	cd services/sag-engine && PYTHONPATH=src pytest

mcp:
	cd services/sag-engine && PYTHONPATH=src python -m sag_video.mcp_server

seed:
	cd services/sag-engine && PYTHONPATH=src python -m sag_video.cli project show --json

contracts:
	cd services/sag-engine && PYTHONPATH=src python ../../scripts/export_contracts.py

preflight:
	sh scripts/termux-preflight.sh
