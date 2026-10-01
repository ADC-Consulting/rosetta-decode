# F97 — Demo-environment deployment hardening (Dokploy)

**Phase:** Infrastructure / Deployment (cross-cutting, not tied to a product phase)
**Area:** Both (Frontend build/serve + repo-level CI/branch settings)
**Status:** complete

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

**Added mid-plan (2026-09-29):** checked ADC's Confluence handbook (issue #127 pointed at it) for
the actual ADC-recommended Dokploy process. Found a genuine compliance gap: ADC's demo guide and
its MS2.5 Secure Software Development Policy require internet-facing demos hosted on ADC
infrastructure to have some form of access gating — ADC's own demo templates ship with auth built
in. This deployment currently has none, and the tool already flags `sensitive_data_findings` on
uploaded content, meaning real prospect/client data could reach a fully open instance. Folded in
as subtask F below (shared HTTP Basic Auth via nginx, user's explicit choice over full SSO — see
`journal/DECISIONS.md` 2026-09-29 entries for the full rationale, including the separately-decided
solo-developer exception to MS2.5 §6.2's reviewer requirement, which is NOT being changed here).

## Acceptance Criteria

- [x] Frontend is served via nginx from a `vite build` static output, not `npm run dev`
- [x] nginx reverse-proxies `/jobs`, `/migrate`, `/explain`, `/health` to `http://backend:8000`
      (same behavior as the current `vite.config.ts` dev-server proxy) and falls back to
      `/index.html` for client-side routes
- [x] `docker-compose.yml`'s `frontend` service no longer bind-mounts source/`node_modules`
      (those stay dev-only, in `docker-compose.override.yml`)
- [x] `main` requires the CI `all-green` status check to pass before merge
- [x] `make test` exits 0
- [x] `make docker-build` exits 0 (required by `CLAUDE.md` for any Dockerfile/compose change)
- [x] ruff and mypy pass
- [x] Dokploy dashboard repointed to `main` with Watch Paths set (manual step, tracked here but
      performed by the user — no Dokploy API/CLI access in this session)
- [x] Demo environment verified live: page loads at `rosetta.dokploy-1.adc-it.com`, API calls
      succeed (full migration submission tested), SSE endpoints (trace stream) confirmed working
      through the proxy
- [x] The whole app (static assets + all proxied API routes) is gated behind HTTP Basic Auth when
      `DEMO_AUTH_USER`/`DEMO_AUTH_PASSWORD` are set, and behaves exactly as before (no auth
      prompt) when they're unset — local `make dev` confirmed frictionless; live deployment
      confirmed prompting for credentials
- [x] No credential material (plaintext or hashed) is committed to the repo — it's a **public**
      GitHub repo — the actual password lives in ADC's Bitwarden per MS2.5 §11.1

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

### F: HTTP Basic Auth for the demo environment
**File:** `src/frontend/nginx.conf`, `src/frontend/Dockerfile`, `docker-compose.yml`
**Depends on:** A (extends the same nginx.conf/Dockerfile A created)
**Done when:** the whole nginx server block (static assets + all proxied `/jobs`, `/migrate`,
`/explain`, `/health` routes — not just the SPA shell, or an unauthenticated visitor could hit the
API directly) is gated behind `auth_basic` when credentials are configured. Design:
- A small entrypoint script in the final Docker stage checks for `DEMO_AUTH_USER` and
  `DEMO_AUTH_PASSWORD` env vars at container start. If both are set, it generates
  `/etc/nginx/.htpasswd` (via `htpasswd` from `apache2-utils`, installed in the final stage) and
  enables an `auth_basic` include; if either is unset, auth is skipped entirely (nginx starts
  exactly as it does today) — this keeps `make dev`/local Docker Compose frictionless, since those
  env vars won't be set there.
- `docker-compose.yml`'s `frontend` service gets
  `environment: [DEMO_AUTH_USER=${DEMO_AUTH_USER:-}, DEMO_AUTH_PASSWORD=${DEMO_AUTH_PASSWORD:-}]`
  (empty defaults, same pattern already used for `tensorzero`'s Azure vars) so the values pass
  through when Dokploy's dashboard sets them, without requiring anything locally.
- Nothing about the actual credential value is committed anywhere — no htpasswd file, no hash, no
  plaintext. It's set once in Dokploy's Environment tab (manual, subtask D) and the value itself
  lives in ADC's Bitwarden. Note in a comment (not `.env.example`, which Claude cannot edit in this
  sandbox — flag the addition to the user instead) that these two vars exist and what they do.

Implemented via `src/frontend/docker-entrypoint.sh` (new) + a wildcard `include` in
`nginx.conf` at the `server {}` level (`auth_basic` inherits into every location automatically, no
per-location duplication needed) + `apache2-utils` installed in the Dockerfile's final stage for
`htpasswd`. Independently verified (not just the implementing agent's own report) via a standalone
container run: auth-on + no creds → 401, auth-on + right creds → 200, auth-on + wrong creds → 401,
auth-off (env vars unset) → 200 with no prompt. `.env.example` lines still need adding manually by
the user (sandbox blocks Claude editing `.env*`):
```
# Optional: gates the whole demo deployment behind HTTP Basic Auth when both are set (unset = no auth, local dev unaffected)
DEMO_AUTH_USER=
DEMO_AUTH_PASSWORD=
```
- [x] done

### D: Dokploy dashboard reconfiguration (manual)
**File:** none (Dokploy dashboard only)
**Depends on:** A, B, C, F (repointing to `main` is only safe once `main` is protected and, now,
once the auth gap is closed — don't put an unauthenticated build live even briefly)
**Done when:** the user has, in the Dokploy dashboard: (1) changed Provider → Branch from
`fix/vite-allowed-hosts` to `main`, (2) set Watch Paths to `src/**`, `docker-compose.yml`,
`config/**`, `alembic/**`, (3) set `DEMO_AUTH_USER`/`DEMO_AUTH_PASSWORD` in the Environment tab
with a value generated fresh and stored in Bitwarden (not reused from anywhere else), (4) triggered
a Deploy and confirmed it's green, (5) confirmed `rosetta.dokploy-1.adc-it.com` prompts for
credentials, accepts the right ones, and works correctly afterward (API calls, SSE streams).

Progress (2026-09-29): (1), (2), and the Domains tab's Container Port (`5173` → `80`, needed since
nginx replaced the dev server) are done. A test deploy was run to validate: `frontend`/nginx serves
correctly (no more 404 on the domain), confirming subtasks A/B/F actually work live, not just
locally. But it surfaced a separate, pre-existing Dokploy platform bug blocking (3)-(5): the app's
Environment Settings box shows undecryptable `enc:v1:...` ciphertext, a known, maintainer-
acknowledged Dokploy issue ([Dokploy/dokploy#4833](https://github.com/Dokploy/dokploy/issues/4833))
where rotating `BETTER_AUTH_SECRET` orphans all previously-encrypted env vars and deploys silently
write an empty `.env`. Confirmed with direct evidence, not inference: `tensorzero` crash-loops on
its own `AZURE_AI_FOUNDRY_ENDPOINT:?...` check, and `backend`'s crash log names the exact missing
var (`pydantic_ai.exceptions.UserError: Set the ANTHROPIC_API_KEY environment variable...`). This
predates F97 entirely and is likely instance-wide, not specific to this app. IT ticket filed and
assigned to the Dokploy instance's admin (2026-09-29) with full root cause, evidence, and a
no-patch-needed fix. (3)-(5) are blocked until that's resolved.

Resolved (2026-10-01): admin (Nico Meier) proposed a lower-risk, app-local fix instead of the
instance-wide key-restore workaround — re-create the env vars under this project from scratch.
This works because the encryption bug only breaks *decrypting old* ciphertext; new writes always
encrypt correctly under the current secret. Real values (`ANTHROPIC_API_KEY`, `LLM_MODEL`, the
TensorZero/Azure vars) were copied from the local `.env` (already known-working) into Dokploy's
Environment Settings box fresh, alongside new `DEMO_AUTH_USER=demo` /
`DEMO_AUTH_PASSWORD=<generated, stored in Bitwarden>`. Note: this fixes `rosetta-decode`
specifically, not the instance-wide root cause — any other app hit by the same secret rotation
would need the identical per-app treatment. After saving + deploying: `backend`/`worker`/
`tensorzero` all start clean, `rosetta.dokploy-1.adc-it.com` prompts for credentials, a migration
submission works end-to-end, and the live trace view (SSE) works through the proxy. All five
`Done when` criteria confirmed live.
- [x] done

### E: Journal + docs update
**File:** `journal/BACKLOG.md`, `journal/DECISIONS.md`
**Depends on:** A, B, C, D, F
**Done when:** F97 subtasks marked done in `BACKLOG.md`, a `DECISIONS.md` entry records the
branch-protection addition, the dev-server-to-static-build switch, and the Basic Auth addition as
locked decisions, and the stale PR #135 follow-up is closed out as fully resolved (not just the
immediate fix, but the underlying dev-server gap and the compliance gap it led to discovering).
- [x] done

### Final: Full verification
- [x] `make test` exits 0
- [x] `make docker-build` exits 0
- [x] Mark F97 done in `journal/BACKLOG.md`

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
