# Cloud Deployment

The cloud deployment is Docker Compose based and does not depend on a host
Python environment. PDF parsing runs in-process in the Celery worker via
Docling, whose models are baked into the worker image rather than fetched at
runtime.

This baseline targets a single Linux cloud VM running Docker Compose. A single
Docling parse peaks around 2.3 GB of resident memory and takes roughly 40
seconds for a short PDF on CPU. Generation and source-import run as **two**
Celery services (`celery_generation` / `celery_source_import`) so they do not
share concurrency slots. `CELERY_CONCURRENCY` still controls generation
(default 2); import defaults to `CELERY_SOURCE_IMPORT_CONCURRENCY=1`. Plan for
at least 8 GB RAM and 4 CPU cores (on DigitalOcean, `s-4vcpu-8gb`).
LibreOffice Impress (PPTX→PDF export), Playwright Chromium (HTML measure /
preview), and the Next.js, Postgres and Redis services share the same box. A GPU
can be enabled later by giving the worker a CUDA runtime and setting
`DOCLING_DEVICE=cuda`; the default is CPU-only.

Managed container platforms that provide no persistent volumes, such as
DigitalOcean App Platform, are not supported: they cannot host the Postgres and
storage volumes this compose file relies on.

## Compose files

| File | Project name | Use |
|---|---|---|
| `docker-compose.yml` | `sunairum` | **Local / dev only:** published ports, bind-mounted source, uvicorn `--reload`, Next.js `Dockerfile.dev` + `npm run dev`. |
| `docker-compose.cloud.yml` | `sunairum-cloud` | **Production / OCI:** Caddy TLS, named volumes, prebuilt images, Next.js `Dockerfile.prod` + `node server.js`, API without `--reload`. |
| `docker-compose.ui-prod.yml` | (overlay) | Optional local overlay to run Next in prod mode for RAM checks. Not used on OCI. |
| `docker-compose.verify.yml` | (overlay) | Turns on in-generation rendered + aesthetic QA for checkpoint runs. Not the default (costs a vision call per page). |

Local verification overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.verify.yml up -d \
  db redis fastapi celery_generation celery_source_import
```

Cloud defaults keep `QA_DURING_GENERATION=0` so generation stays cheap; the
generation worker still sets `QA_RENDER_REVIEW=1` for post-export / deep QA
paths that need LibreOffice. Chromium for headless render review is opt-in at
image build time (`WITH_RENDERER=1`), because it adds ~500 MB to the worker
image. `./deploy/build-push.sh` publishes `api` and retags it as
`celery-generation` / `celery-source-import` without Chromium unless you
rebuild those services with that build arg.

## One-click Droplet (DigitalOcean)

`deploy/cloud-init.yml` provisions a fresh Droplet unattended. Create a
`s-4vcpu-8gb` Droplet, paste the file into **Advanced Options → Add Initialization
scripts (user data)** with the `CHANGE_ME` values replaced, and the first boot
installs Docker, clones the repository, adds swap, writes both environment files
and starts the stack. Browse to the Droplet's IP a few minutes later.

There is no App Platform button, because the stack needs persistent volumes for
Postgres and generated decks, and a worker larger than the smallest instance.

## Oracle Cloud

Use [`deploy/oracle/`](oracle/README.md) for OCI Compute (Always Free Ampere A1 or
trial AMD). That folder opens the Ubuntu host firewall (required on OCI), tunes
`CELERY_CONCURRENCY=1` (generation) for 12 GB Ampere, and provides `setup.sh` /
`cloud-init.yml`. Import stays at `CELERY_SOURCE_IMPORT_CONCURRENCY=1` by default.

```bash
# on the VM after SSH
sudo SETTINGS_SECRET_KEY='...' ./deploy/oracle/setup.sh
```

## Existing host

```bash
git clone <your-fork> sunairum && cd sunairum
sudo ./deploy/install.sh   # Docker, swap, environment files
# Set SETTINGS_SECRET_KEY in deploy/fastapi.env, DOMAIN in deploy/cloud.env
# Configure text/image/vision keys in the Settings UI after login
./deploy/up.sh
```

The services are:

- `caddy`: the only published ports, `80` and `443`. Terminates TLS and routes
  `/api`, `/ws`, `/storage` and `/health` to `fastapi`, everything else to
  `nextjs`.
- `nextjs`: production Next.js server, internal.
- `fastapi`: API, internal.
- `celery_generation`: slide authoring / compile / fix (`generation` queue;
  concurrency from `CELERY_CONCURRENCY`).
- `celery_source_import`: PDF/Docling parse (`source_import` queue; concurrency
  from `CELERY_SOURCE_IMPORT_CONCURRENCY`, default 1).
- `db`: persistent PostgreSQL.
- `redis`: persistent Redis.

Gallery packs are still bind-mounted from `servers/fastapi/examples` into the
API, worker, and Next.js containers so the host can refresh design references
without rebuilding images. Application code and Docling weights come from the
images themselves; Postgres, Redis, storage, and Caddy certs use named volumes.

Set `DOMAIN` to a hostname whose DNS already points at the Droplet and Caddy
obtains a Let's Encrypt certificate on the first request, with no further
configuration. Leaving it empty serves plain HTTP, which is what you want before
DNS propagates. Because the browser talks to one origin, `NEXT_PUBLIC_API_URL`
is only needed when the API lives on a different host than the frontend.

Deck editor export uses the same release path as history downloads: rebuild
then `GET /api/download/{id}.pptx` or `GET /api/download/{id}.pdf` (PDF is
exported from the released PPTX via LibreOffice Impress). HTML player export
is `GET /api/download/{id}.html.zip` (packs `html_output/` into a self-contained
`index.html` player; no PPTX rebuild required).

## Images

`./deploy/up.sh` pulls prebuilt images rather than building on the host, since a
build there fetches ~900 MB of torch and bakes 731 MB of Docling weights while
competing for the RAM the running stack needs. Publish them from a workstation
or CI:

```bash
IMAGE_PREFIX=ghcr.io/your-org/sunairum ./deploy/build-push.sh          # :latest
IMAGE_PREFIX=ghcr.io/your-org/sunairum ./deploy/build-push.sh v1.2.0
```

It builds `linux/amd64` by default, which matters when publishing from an Apple
Silicon machine: a mismatched image fails at start with an exec format error.
`api`, `celery-generation`, and `celery-source-import` are the same image under
three tags, so it is pushed once and retagged.

With no registry available, `./deploy/up.sh --build` builds on the host instead.

## Operations

```bash
./deploy/status.sh
docker compose --env-file deploy/cloud.env -f docker-compose.cloud.yml logs -f \
  celery_generation celery_source_import
./deploy/up.sh          # pull the current tag and restart changed services
```

PDF parsing runs fully offline. Docling's weights are baked into the worker
image at `/opt/docling-models` during the build, so a fresh host needs no
seeding step and a cold container start does no network I/O. `HF_HUB_OFFLINE=1`
is the default, which turns a missing model into an immediate error instead of a
parse that appears to hang while a download stalls.

The formula model is another 610MB for a feature that ships off, so it is not
baked by default. To enable `DOCLING_FORMULA_ENRICHMENT=1`, rebuild with the
model included:

```bash
docker compose --env-file deploy/cloud.env -f docker-compose.cloud.yml build \
  --build-arg WITH_FORMULA_MODEL=1 celery_generation celery_source_import
```

## Security

- Do not commit `deploy/cloud.env` or `deploy/fastapi.env`.
- Put API keys in the cloud secret manager or protected environment files.
- Only `caddy` publishes ports. The API, database and Redis are reachable only on
  the internal compose network, so the firewall needs `80` and `443` open and
  nothing else.
- HTTPS is handled by Caddy once `DOMAIN` is set. Authentication is still
  missing — every endpoint uses a hardcoded `default_user` — so put an
  authenticating proxy in front before exposing this to real traffic.
- Add backups and centralized logs before production traffic.
