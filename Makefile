PY := PYTHONPATH=backend python3

.PHONY: dev api serve ui check test clean

dev:
	@echo "API :8000   UI :5173"
	@$(PY) -m uvicorn abletonhelper.main:app --reload --port 8000 & \
	 cd frontend && npm run dev

api:
	$(PY) -m uvicorn abletonhelper.main:app --reload --port 8000

# Bind to every interface so phones and tablets on the same network can
# open it. Localhost-only is the default on purpose; this is opt-in.
serve:
	@echo "Others on this network: http://$$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $$1}'):8000"
	$(PY) -m uvicorn abletonhelper.main:app --host 0.0.0.0 --port 8000

ui:
	cd frontend && npm run dev

check:
	$(PY) -c "import abletonhelper.main, abletonhelper.cli; print('backend imports ok')"
	$(PY) -m abletonhelper.cli backends
	cd frontend && npm run build
	$(PY) -m pytest tests -q

test:
	$(PY) -m pytest tests -q

clean:
	rm -rf data out/* frontend/dist
	find . -name __pycache__ -prune -exec rm -rf {} +
