# F97 — Demo-environment deployment hardening (Dokploy)

**Phase:** Infrastructure / Deployment (cross-cutting, not tied to a product phase)
**Area:** Both (Frontend build/serve + repo-level CI/branch settings)
**Status:** in-progress

## Goal

Rosetta's only deployed environment is Dokploy (`rosetta.dokploy-1.adc-it.com`, app
"SAS-converter"), used exclusively for ADC-consultant-led demos — not production, but the user
wants it held to solid engineering standards anyway, partly to set an example. This session's
investigation (closing out stale draft PR #135, "fix Dokploy access") found three concrete gaps
beyond that PR's own fix:

1. `main` has zero GitHub branch protection (`gh api .../branches/main/protection` → 404) —
   nothing requires CI to pass before merge or blocks a direct push.
2. `src/frontend/Dockerfile` runs the Vite **dev server** (`npm run dev`) even when deployed —
   this is what caused PR #135's bug in the first place (dev-server Host-header blocking +
   hardcoded `localhost:8000` API base). No production-style static build is used anywhere.
3. In the Dokploy dashboard, the app's Provider → Branch is set to the now-merged feature branch
   `fix/vite-allowed-hosts` instead of `main`, and Watch Paths is empty, so every push — including
   docs-only commits — triggers a full rebuild/redeploy of all five services.

Done looks like: the demo environment is served by a real static build (not a dev server), `main`
cannot receive code that fails CI, and Dokploy is watching the right branch with sensible path
filtering.

## Acceptance Criteria

- [ ] Frontend is served via nginx from a `vite build` static output, not `npm run dev`
- [ ] nginx reverse-proxies `/jobs`, `/migrate`, `/explain`, `/health` to `http://backend:8000`
      (same behavior as the current `vite.config.ts` dev-server proxy) and falls back to
      `/index.html` for client-side routes
- [ ] `docker-compose.yml`'s `frontend` service no longer bind-mounts source/`node_modules`
      (those stay dev-only, in `docker-compose.override.yml`)
- [ ] `main` requires the CI `all-green` status check to pass before merge
- [ ] `make test` exits 0
- [ ] `make docker-build` exits 0 (required by `CLAUDE.md` for any Dockerfile/compose change)
- [ ] ruff and mypy pass
- [ ] Dokploy dashboard repointed to `main` with Watch Paths set (manual step, tracked here but
      performed by the user — no Dokploy API/CLI access in this session)
- [ ] Demo environment verified live: page loads at `rosetta.dokploy-1.adc-it.com`, API calls
      succeed, SSE endpoints (trace stream, explain streaming) still work through the proxy

## Subtasks

### A: Multi-stage frontend Dockerfile + nginx config
**File:** `src/frontend/Dockerfile`, `src/frontend/nginx.conf` (new)
**Depends on:** none
**Done when:** `src/frontend/Dockerfile` has a build stage (`npm ci && npm run build`, reusing the
existing `build` script — already `tsc --noEmit && vite build`) and a final stage that serves
`dist/` via nginx, using a checked-in `nginx.conf` that proxies `/jobs`, `/migrate`, `/explain`,
`/health` to `http://backend:8000` (mirroring `vite.config.ts`'s `server.proxy` table from PR
#135) and serves `index.html` for all other paths (SPA fallback). SSE endpoints
(`/jobs/:id/trace/stream`) must not be buffered by nginx (`proxy_buffering off` on that location).
- [x] done

### B: `docker-compose.yml` frontend service update
**File:** `docker-compose.yml`
**Depends on:** A
**Done when:** the `frontend` service builds the new Dockerfile, no longer mounts
`./src/frontend:/app` or `frontend_node_modules` (dev-only concerns, already isolated in
`docker-compose.override.yml`), and no longer needs `VITE_API_URL` at runtime (API calls are
relative, proxied by nginx). Note: `import.meta.env.VITE_*` is inlined by Vite at **build** time,
not read at container runtime — if a build-time override is ever needed again it must be a Docker
build arg, not a runtime env var like today's setup.
- [x] done

### C: GitHub branch protection on `main`
**File:** none (repo setting, via `gh api` or GitHub UI — not a code change)
**Depends on:** none (independent of A/B)
**Done when:** `main` requires the CI workflow's `all-green` job ("All checks passed") to pass
before a PR can merge. Confirm via `gh api repos/ADC-Consulting/rosetta-decode/branches/main/protection`
returning a configured `required_status_checks` including that job, instead of 404. This is a
shared/account-level setting change — confirm with the user immediately before applying, even
though this plan is already approved.

Done via a GitHub **ruleset** ("Main protection", id 15240362), not the legacy branch-protection
API — that's why the classic `.../branches/main/protection` endpoint still 404s; confirmed instead
via `gh api repos/ADC-Consulting/rosetta-decode/rulesets/15240362`, which shows a
`required_status_checks` rule requiring exactly `"All checks passed"`, plus pre-existing
deletion/non-fast-forward/pull-request rules.
- [x] done

### D: Dokploy dashboard reconfiguration (manual)
**File:** none (Dokploy dashboard only)
**Depends on:** A, B, C (repointing to `main` is only safe once `main` is protected)
**Done when:** the user has, in the Dokploy dashboard: (1) changed Provider → Branch from
`fix/vite-allowed-hosts` to `main`, (2) set Watch Paths to `src/**`, `docker-compose.yml`,
`config/**`, `alembic/**`, (3) triggered a Deploy and confirmed it's green, (4) confirmed
`rosetta.dokploy-1.adc-it.com` loads correctly with working API calls and SSE streams.
- [ ] done

### E: Journal + docs update
**File:** `journal/BACKLOG.md`, `journal/DECISIONS.md`
**Depends on:** A, B, C, D
**Done when:** F97 subtasks marked done in `BACKLOG.md`, a `DECISIONS.md` entry records the
branch-protection addition and the dev-server-to-static-build switch as locked decisions, and the
stale PR #135 follow-up is closed out as fully resolved (not just the immediate fix, but the
underlying dev-server gap it exposed).
- [ ] done

### Final: Full verification
- [ ] `make test` exits 0
- [ ] `make docker-build` exits 0
- [ ] Mark F97 done in `journal/BACKLOG.md`

## Dependencies on other features

- Builds directly on PR #135 (merged this session), which added the `vite.config.ts` proxy table
  this plan's nginx config mirrors.

## Out of scope for this feature

- Pushing built images to a container registry — Dokploy builds from source via its own
  git-based Compose build, no registry needed for a single demo environment.
- Any CI job that calls Dokploy's deploy API (e.g. `benbristow/dokploy-deploy-action`) — Dokploy's
  native autodeploy-on-push already covers this once branch protection (subtask C) makes `main`
  trustworthy. Revisit only if a second, actually-production environment is introduced.
- Traefik path-based routing at the Dokploy/edge level for multi-service-one-domain — Dokploy's
  own docs don't document this for Compose apps (confirmed via `docs.dokploy.com`); the nginx-level
  proxy (subtask A) achieves the same result and is portable to any host, not just Dokploy.
- Changes to `src/backend/Dockerfile` or `src/worker/Dockerfile` — both are already
  production-appropriate (no dev-mode flags, migrations run before app start).
- Fixing `docs/architecture.md`'s stale service list (missing `tensorzero`/`executor`) — pre-existing
  staleness, unrelated to this plan.
