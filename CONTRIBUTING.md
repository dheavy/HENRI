# Contributing to HENRI

HENRI is an internal ICRC tool. Contributions are welcome from anyone within T&I and the wider ICT organisation.

## Before you start

Ask yourself: **"Does this help someone in Field ICT do their job better?"**

HENRI exists to give field network teams advance warning of infrastructure disruptions. Every feature should either:

1. Surface a signal that helps anticipate or respond to a network event
2. Improve the accuracy or coverage of existing intelligence
3. Make the tool easier to operate or understand

If your change doesn't serve one of these goals, it probably doesn't belong here.

## Development workflow

1. **Create a branch** from `main` — never commit directly to `main`
2. **Keep changes focused** — one feature or fix per branch
3. **Write tests** — new features need tests, bug fixes need regression tests
4. **Run the full suite** before opening a PR:
   ```bash
   uv run pytest tests/
   cd frontend && npx tsc --noEmit && npm run build
   ```
5. **Security audit** — if your change touches API endpoints, file handling, or credentials, consider what a Checkmarx scan would flag
6. **Open a PR** with a clear description of what changed and why

## Code style

- **Python**: type hints throughout, `logging.getLogger(__name__)` for all modules, defensive error handling (log and continue, don't crash the pipeline)
- **TypeScript**: strict mode, no `any` types, native `fetch` only (no axios — it was removed for supply chain security reasons)
- **Commits**: conventional commit format (`feat:`, `fix:`, `docs:`, `refactor:`)

## Architecture decisions

- **Single container**: FastAPI serves both the API and the React SPA. Background jobs run via APScheduler in the same process. Keep it simple.
- **Fixture fallback**: Every data source must degrade gracefully. If an API is down, use cached data. If no cache exists, use fixtures. Never crash.
- **On-prem only**: No external CDN dependencies in production. All JS/CSS bundled by Vite. No data leaves the ICRC network.

## Adding a new data source

1. Create a client module in `src/` (e.g. `src/new_source/client.py`)
2. Add a fixture file in `data/fixtures/` for offline testing
3. Wire it into `src/henri/run_all.py` as a pipeline step
4. Add source status tracking (`source_status.json`) for the Source Health card
5. Add tests in `tests/`
6. Update `.env.example` with any required credentials

## Adding a new dashboard card

1. Add the data to an existing or new API endpoint in `src/henri/web/api/`
2. Create the React component in `frontend/src/components/`
3. Wire it into `frontend/src/pages/Dashboard.tsx`
4. Include a `.text-label` title and a one-liner description in `text-text-muted`
5. Use the ICRC colour palette (see `frontend/src/styles/globals.css`)

## Questions?

Reach out to Davy Braun &lt;dbraun@icrc.org&gt; — T&I Architecture.
