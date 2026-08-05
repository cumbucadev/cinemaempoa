# Reduce production Docker image size (#197)

## Problem

`Dockerfile.prod` currently produces a ~1.09GB image. Deploys run on a
single SSH server via `deploy-server.yml`: the workflow builds the new
image, runs migrations, starts the container, and only reclaims disk
(`docker system prune -af`) *after* the new container is up. During the
build step itself, the previous running image, its layers, and any build
cache all coexist on disk alongside the image being built — a full build
can transiently need multiples of the final image size in free space.
On the SSH server this pushes past capacity and the deploy fails.

## Root causes

Investigation of the repo found four contributors to image size, in
roughly descending order of impact:

1. **The runtime dependency stack is genuinely large.** The venv is
   ~500MB, dominated by `litellm` (59MB), `pandas` (45MB), `numpy`
   (33MB+27MB libs), and `llama_index` (30MB). These packages back the
   `fetch-movie-metadata` and `inspect-movies` features, both of which
   run via `docker exec` against the live production container (see
   `.github/workflows/fetch-movie-metadata.yml`), so they must remain in
   the runtime image. This sets a floor on how small the image can
   realistically get — the issue's linked article (<100MB) describes a
   project without this kind of ML/LLM dependency footprint, so that
   number is not a realistic target here.

2. **`locales-all` is installed in both `Dockerfile.prod` and
   `Dockerfile.dev`.** This apt package ships every locale on the
   system (typically 200-300MB installed) when the app only ever
   configures `pt_BR.UTF-8`.

3. **No multi-stage build.** The final image carries the `uv` binary,
   apt package lists/cache, and anything `uv sync` downloaded or cached
   during dependency resolution — none of which are needed at runtime.

4. **Dev/test/lint tooling ships in the production image.** `pytest`,
   `ruff`, `djlint`, `pre-commit`, `faker`, and `debugpy` are listed as
   plain `dependencies` in `pyproject.toml` rather than in the `dev`
   dependency group, so `uv sync --frozen` installs them into the prod
   image. Verified none are imported by runtime code:
   - `faker` is only used by `flask_backend/seeds/screening_seeds.py`,
     which backs the dev-only `seed-db` CLI command (not invoked by any
     workflow or production script).
   - `pytest`, `ruff`, `djlint`, `debugpy` have no imports outside
     tests/tooling and are not referenced by any Dockerfile.prod-run
     command.
   This tooling plus its own transitive deps (e.g. `pyfiglet`, pulled in
   by `djlint`) adds roughly 60-70MB of dead weight.

## Design

### 1. `pyproject.toml` — move dev-only tooling into the `dev` group

Move `pytest`, `ruff`, `djlint`, `pre-commit`, `faker`, and `debugpy`
from the top-level `dependencies` list into the existing
`[dependency-groups] dev` list, alongside `coverage`, `vulture`,
`xenon`, and `radon`.

`uv sync --frozen` (used throughout `ci.yml` with no `--no-dev` flag)
installs the `dev` group by default, so CI lint/test/quality jobs are
unaffected by this move.

### 2. `Dockerfile.prod` — convert to a multi-stage build

- **`builder` stage** (`FROM python:3.14-slim AS builder`): install the
  `uv` binary, copy only `pyproject.toml` and `uv.lock` (no dep on app
  source, since the project has no `[build-system]` table — `uv sync`
  only needs the lockfile), and run `uv sync --frozen --no-dev` into
  `/opt/venv`.
- **runtime stage** (`FROM python:3.14-slim`): install `locales` and
  `tzdata` in a single `RUN` layer (replacing `locales locales-all`),
  generate only the `pt_BR.UTF-8` locale via `locale-gen`, and clean up
  apt lists/cache (`rm -rf /var/lib/apt/lists/*`) in that same layer.
  Copy `/opt/venv` from the `builder` stage, copy the app source, and
  keep the existing `EXPOSE`/`CMD`.

This removes the `uv` binary, apt cache, and all dev/test/lint tooling
from the final image, and collapses the current three separate
`apt-get update`/`apt update` invocations (each its own layer) into one
cleaned-up layer.

### 3. `Dockerfile.dev` — apply the same locale fix

Replace `locales locales-all` with `locales` + `locale-gen
pt_BR.UTF-8`, matching the prod fix, for consistency and because the
waste is identical. `Dockerfile.dev` keeps `uv sync --frozen` without
`--no-dev` (no change there) since the dev container needs `pytest`,
`ruff`, etc., plus `debugpy` for editor integration.

### 4. `deploy-server.yml` — prune stale images before building

Add a `docker image prune -af` step immediately before the
`docker compose -f docker-compose.shared.yml build flask` step. This is
scoped to dangling/unused *images* only (not the full `docker system
prune -af` used post-deploy, which also touches containers/networks/build
cache and isn't safe to run before the new container exists). This
prevents images from previous failed or superseded builds from
compounding with the in-progress build's disk needs. The existing
post-deploy `docker system prune -af` step is unchanged.

## Validation plan

- Build `Dockerfile.prod` locally and compare `docker image ls` size
  before/after the change.
- Build `Dockerfile.dev` and run `pytest`, `ruff check`, `ruff format
  --check`, and `djlint --lint` inside it to confirm dev tooling is
  still present and functional there.
- Start the prod image via `docker-compose.production.yml` (or
  `docker-compose.shared.yml`), run `flask --app flask_backend
  db-upgrade`, and confirm the app serves a request successfully.
- Confirm `docker exec cinemaempoa_flask flask --app flask_backend
  fetch-movie-metadata` still works against the trimmed image (exercises
  the `litellm`/`llama-index`/`pandas` stack that must survive the
  `--no-dev` trim).

## Out of scope

- Switching the base image to Alpine — `numpy`, `pandas`, and `pillow`
  ship as glibc-linked manylinux wheels; Alpine's musl libc risks
  slower/broken builds for little additional size win, given the ML
  stack already sets the size floor.
- Splitting the ML/LLM stack into a separate image or service.
  `fetch-movie-metadata` and `inspect-movies` run via `docker exec`
  against the single `cinemaempoa_flask` container, so splitting would
  require compose/workflow changes beyond this issue's scope.
- Chasing a specific target image size (e.g. the <100MB mentioned in the
  issue). The goal is the meaningful reduction available from the
  changes above, not a fixed number.
