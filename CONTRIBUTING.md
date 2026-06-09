Contributing
============

Developer workflow
- Fork or create a feature branch from `main`.
- Use descriptive commit messages and open PRs for review.

Environment
- Python 3.12 recommended. Use a virtualenv:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r transit-backend/requirements.txt
```

Run the app locally
```bash
cd transit-backend
uvicorn api.main:app --reload --port 8000
```

Testing
- Run unit tests with `pytest` from repository root.
- Add tests for new features and make sure CI passes before merging.

Code style
- Follow PEP8. Use `black` for formatting where helpful.
- Keep functions small and focused. Update `mvp1-plan.md` if you change architecture.

Feature flags
- When adding an integration or feature, add a corresponding feature flag in `api/config.py` and ensure the code checks the flag before performing external calls.

PR checklist
- Tests added/updated
- Docs updated (`README.md`, `docs/*.md`) when behavior or env vars change
- Feature flags respected for new external integrations

Contact
- Leave comments on the PR for review and tag the maintainer.

