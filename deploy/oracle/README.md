# Oracle Cloud deployment

Sunairum runs as Docker Compose on a single OCI Compute VM. This folder adds the
Oracle-specific pieces on top of the shared `deploy/` scripts:

| File | Purpose |
|---|---|
| `setup.sh` | SSH path: firewall + Docker + env + `up.sh` |
| `open-firewall.sh` | Host iptables for TCP 80/443 (OCI Ubuntu gotcha) |
| `cloud-init.yml` | Optional first-boot automation |
| `cloud.env.example` | Free-tier-friendly defaults (`CELERY_CONCURRENCY=1` generation; import concurrency 1) |

## Shape

| Goal | Shape | Arch | Notes |
|---|---|---|---|
| Always Free / short beta | `VM.Standard.A1.Flex` **2 OCPU, 12 GB** | **aarch64** | Build on the VM, or push `linux/arm64` images |
| Trial credits, less friction | AMD flex **≥4 OCPU, ≥8 GB** | **amd64** | Matches default `build-push.sh` |

Boot volume: **≥50 GB** (100 GB safer if you build images on the host).

## Console checklist (required)

1. **Compute → Create instance**
   - Image: **Ubuntu 22.04 or 24.04**
   - Shape as above
   - **Public IPv4** assigned
   - SSH public key (`.pub` only)
2. **VCN → Security List → Ingress**
   - TCP **22**, **80**, **443** (source `0.0.0.0/0` for a short beta)
3. Host firewall is opened by `open-firewall.sh` / cloud-init — without that,
   security-list rules alone still look like “No route to host”.

## Recommended path (private GitHub repo)

Your repo is private, so cloud-init cannot `git clone` without a token. Prefer SSH:

```bash
# from your laptop
ssh -i ~/.ssh/<your_key> ubuntu@<PUBLIC_IP>   # or opc@ on some Oracle images

# on the VM
git clone https://github.com/asimsinan/sunairum.git
cd sunairum
# if private: use a PAT, or gh auth, or deploy key

sudo SETTINGS_SECRET_KEY='your-secret' ./deploy/oracle/setup.sh
```

First run with `--build` can take **20–40+ minutes** on Ampere while it pulls
torch and bakes Docling weights. Then open `http://<PUBLIC_IP>` and configure
text/image/vision engines in Settings (OpenAI-compatible only).

Useful flags:

```bash
sudo SETTINGS_SECRET_KEY='...' CELERY_CONCURRENCY=1 ./deploy/oracle/setup.sh
sudo SKIP_BUILD=1 ./deploy/oracle/setup.sh   # prepare only; start later
```

## Optional: cloud-init

Paste [`cloud-init.yml`](cloud-init.yml) into **Advanced options → Management →
Initialization script**, after replacing:

- `CHANGE_ME_STRONG_DB_PASSWORD`
- `CHANGE_ME_LONG_RANDOM_STRING`

For a **private** repo, either make it public for the beta or set the clone URL to
include a fine-scoped PAT:

```text
https://<TOKEN>@github.com/asimsinan/sunairum.git
```

(Prefer the SSH + `setup.sh` path so the token is not stored in user-data.)

## ARM images from a Mac

Ampere instances need `linux/arm64`. Building on the VM avoids cross-compile.
From a workstation/registry instead:

```bash
PLATFORM=linux/arm64 IMAGE_PREFIX=ghcr.io/asimsinan/sunairum ./deploy/build-push.sh
```

Then on the VM set `IMAGE_PREFIX` / `IMAGE_TAG` in `deploy/cloud.env` and run
`./deploy/up.sh` (no `--build`).

## Smoke test

```bash
./deploy/status.sh
curl -fsS http://127.0.0.1/health
# from your laptop:
curl -fsS http://<PUBLIC_IP>/health
```

UI → Settings → save OpenAI-compatible text/image keys → upload a short PDF.

## HTTPS without owning a domain (sslip.io)

Caddy issues a Let’s Encrypt cert when `DOMAIN` is a real hostname. With only a
public IP (e.g. `170.9.238.9`), set on the **host** (gitignored) `deploy/cloud.env`:

```bash
DOMAIN=170-9-238-9.sslip.io
```

Then recreate Caddy and open the HTTPS URL (not the raw IP):

```bash
sudo docker compose --env-file deploy/cloud.env -f docker-compose.cloud.yml up -d caddy
# https://170-9-238-9.sslip.io
```

OCI security list + host firewall must allow TCP 80/443 (required for the ACME
challenge). Confirm `DOMAIN` survives GitHub redeploys (`git reset --hard` must
not overwrite host `cloud.env`).

## Auth env (on the host)

Add to `deploy/fastapi.env` (gitignored) when enabling login:

```bash
SESSION_COOKIE_SECURE=1
SETTINGS_SECRET_KEY=<long-random>
# optional overrides; otherwise seed is admin / admin
# ADMIN_EMAIL=admin
# ADMIN_PASSWORD=admin
```

On first API boot with zero admins, Sunairum seeds `admin`/`admin` and migrates
legacy `default_user` projects/storage to that admin. Change the password on
`/profile` immediately. Redis restart clears sessions (everyone re-logs in).

## Desktop apps vs OCI

`desktop/` and `desktop-offline/` live in the same GitHub repo, but OCI must
not check them out. GitHub Actions (`deploy-oci.yml`) already:

1. Ignores pushes that only touch those trees (`paths-ignore`)
2. Uses `git fetch --filter=blob:none` + sparse checkout so the VM never
   materialises `desktop/` or `desktop-offline/`

One-time / repair on an existing VM:

```bash
cd ~/sunairum
./deploy/oracle/sparse-checkout-cloud.sh
git fetch --filter=blob:none origin main
git reset --hard origin/main
```

## Ops

```bash
./deploy/status.sh
docker compose --env-file deploy/cloud.env -f docker-compose.cloud.yml logs -f \
  celery_generation celery_source_import
./deploy/up.sh          # after changing IMAGE_TAG / rebuilding
```

Tear down the instance when the beta ends so trial credits / free limits are not
consumed by an idle box.
