# KuzuWiki-OSINT backend

FastAPI backend for the KuzuWiki-OSINT graph-compiled expert intelligence
system: the six agents (Gatekeeper, Lande HVG, JEV swarm, Graph-Wiki compiler,
adversarial linter, OSINT complicator) plus the embedded KùzuDB graph layer.

See the [project README](../README.md) for the full architecture and the
[AGENTS.md](../AGENTS.md) for the JEV type contracts every agent binds to.

## Local development

```bash
pip install -e backend
cd backend
uvicorn kuzuwiki.main:app --reload
```

The KùzuDB path, wiki vault and raw archive are configurable through the
environment (see `backend/.env.example`).

## Tests

```bash
cd backend
python -m pytest
```
