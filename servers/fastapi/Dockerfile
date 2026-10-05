FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    # PPTX → PDF download (released deck via Impress).
    libreoffice-impress \
    # PPTX visual verify: PDF pages → PNG for SSIM vs HTML previews.
    poppler-utils \
    fonts-liberation \
    fonts-inter \
    # CJK fallback so Impress does not drop glyphs that pack fonts omit.
    fonts-noto-cjk \
    # OpenCV arrives via Docling's PDF pipeline and links against these even when
    # only its array functions are used, so a parse fails on libGL.so.1 without them.
    libgl1 \
    libglib2.0-0 \
    # Formula PNG worker (MathJax TeX → paths → rsvg PNG). Image-baked so cold
    # workers do not need network npm on first formula slide.
    nodejs \
    npm \
    librsvg2-bin \
    # Privilege drop in docker-entrypoint.sh (Celery must not run as root).
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# PyPI wheels (docling/torch deps) are large; default pip timeout dies on a stall.
ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

# Docling pulls torch, whose default PyPI wheel drags in the whole CUDA runtime
# (~2.9GB of nvidia-* plus ~650MB of triton) that a CPU deployment never
# executes. Installing the CPU build first leaves the requirements install below
# seeing the dependency as satisfied. This applies to arm64 too: PyPI now ships
# aarch64 CUDA wheels, so restricting it to amd64 quietly cost 3.5GB per image.
RUN pip install --no-cache-dir torch torchvision \
      --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# Docling resolves weights through the HuggingFace Hub the first time a pipeline
# runs. A fresh cloud host has nothing to seed a cache from, so an unbaked image
# either refetches ~730MB on every cold start or fails outright once
# HF_HUB_OFFLINE is set. Baking them makes the models part of the immutable
# image: no network at runtime, and a deploy cannot half-succeed with weights
# missing. RapidOCR is included because the scanned-PDF retry depends on it.
# The formula model is another 610MB for a feature that ships off, so it is
# opt-in via --build-arg WITH_FORMULA_MODEL=1.
ARG WITH_FORMULA_MODEL=0
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models
# Prefer a local seed (docker/docling-models/, gitignored) so laptop rebuilds skip
# HuggingFace. OCI/CI clones have no seed → download from the hub (needs network).
# Refresh seed: docker create sunairum-celery-generation:latest && \
#   docker cp <id>:/opt/docling-models/. servers/fastapi/docker/docling-models/
ENV HF_HUB_DISABLE_XET=1 \
    HF_HUB_ENABLE_HF_TRANSFER=0 \
    HF_HUB_DOWNLOAD_TIMEOUT=60
COPY docker/ /tmp/docling-seed/
RUN set -e; \
    mkdir -p "${DOCLING_ARTIFACTS_PATH}"; \
    if [ -d /tmp/docling-seed/docling-models/docling-project--docling-models ]; then \
      echo "[docling] seeding from docker/docling-models"; \
      cp -a /tmp/docling-seed/docling-models/. "${DOCLING_ARTIFACTS_PATH}/"; \
    else \
      echo "[docling] no local seed — downloading from HuggingFace"; \
      python -c "\
from pathlib import Path; \
from docling.utils.model_downloader import download_models; \
download_models(output_dir=Path('${DOCLING_ARTIFACTS_PATH}'), progress=False, \
    with_layout=True, with_tableformer=True, with_rapidocr=True, \
    with_code_formula=('${WITH_FORMULA_MODEL}' == '1'), \
    with_picture_classifier=False, with_smolvlm=False, \
    with_granite_vision=False, with_easyocr=False)"; \
    fi; \
    test -d "${DOCLING_ARTIFACTS_PATH}/docling-project--docling-models"; \
    rm -rf /tmp/docling-seed

# HTML measure + preview PNGs need Chromium. Default ON (~500MB).
# Slim/CI images can still opt out: docker compose build --build-arg WITH_RENDERER=0
ARG WITH_RENDERER=1
ENV SUNAIRUM_RENDERER_AVAILABLE=${WITH_RENDERER}
# Browsers must live outside /root so the non-root runtime user can launch them.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# playwright is already in requirements.txt; this step installs browser binaries + OS deps.
RUN if [ "${WITH_RENDERER}" = "1" ]; then \
      python -m playwright install --with-deps chromium && \
      python -c "import playwright.sync_api" && \
      chmod -R a+rX /ms-playwright && \
      rm -rf /var/lib/apt/lists/*; \
    fi

# Release fidelity is fail-closed, so a renderer image without the PDF raster
# bridge must fail during build instead of after a full generation job.
RUN test -x /usr/bin/pdftoppm

COPY . .

# Bake MathJax for formula PNG plates. Runtime npm install is a fallback only.
RUN if [ -f tasks/formula_worker/package.json ]; then \
      npm install --omit=dev --no-fund --no-audit --prefix tasks/formula_worker \
      && test -d tasks/formula_worker/node_modules/mathjax-full; \
    fi

# HTML → PPTX via the vendored DeckHTML CLI. Build directly from its committed
# lockfile; never resolve the obsolete public @deckflow dependency graph.
# TypeScript is build-only, while pptxgenjs remains a production dependency.
WORKDIR /app/vendor/deckhtml
RUN npm ci --no-fund --no-audit \
    && npm run build \
    && npm prune --omit=dev \
    && test -f dist/cli.js \
    && test -d node_modules/pptxgenjs
WORKDIR /app
ENV DECKHTML_BIN=/app/vendor/deckhtml/dist/cli.js
ENV PDF_ENGINE=html_hidpi

# Text is measured from the advance widths in these files, but LibreOffice and
# Chromium resolve fonts through fontconfig, which knew none of the pack families
# and silently substituted Liberation Sans. Every rasterised QA image and every
# exported PDF therefore showed a font the deck does not use, with different
# metrics than the ones we measured. Registering the shipped faces makes what the
# renderers draw match what we measured.
# Closed-loop fidelity: the same faces are also embedded into the PPTX by
# deckhtml `embedDeckFonts` (DECKHTML_FONTS_DIR defaults to this tree), so
# PowerPoint openers and the LibreOffice verify gate share identical metrics.
# The curated library is copied first so its name wins any collision with a pack's own
# copy of the same family: those were harvested per pack and differ in version and
# coverage, while these were vetted and are the files the engine measures and embeds.
# Monospace closes the same loop. `fonts-liberation` already installs Liberation
# Mono, but the embedder only reads the font dirs below, so a code run would be
# measured against it and then exported with no embedded face — resolved on the
# reader's machine by whatever mono they have, at a different advance width.
# Stage it under the slug the embedder resolves ('liberation-mono-<weight>').
RUN set -eu; \
    mkdir -p /usr/local/share/fonts/sunairum /etc/fonts/conf.d; \
    for spec in 'Regular:400' 'Bold:700' 'Italic:400-italic' 'BoldItalic:700-italic'; do \
      face="${spec%%:*}"; slug="${spec##*:}"; \
      src="/usr/share/fonts/truetype/liberation/LiberationMono-${face}.ttf"; \
      [ -f "$src" ] && cp -n "$src" "assets/fonts/liberation-mono-${slug}.ttf" || true; \
    done; \
    find assets/fonts templates -type f \( -name '*.ttf' -o -name '*.otf' \) \
      -exec cp -n {} /usr/local/share/fonts/sunairum/ \; ; \
    if [ -f docker/99-sunairum-font-aliases.conf ]; then \
      cp docker/99-sunairum-font-aliases.conf /etc/fonts/conf.d/99-sunairum-font-aliases.conf; \
    fi; \
    fc-cache -f >/dev/null; \
    fc-list : family | sort -u | head -40
ENV DECKHTML_FONTS_DIR=/app/assets/fonts
ENV SUNAIRUM_FONTS_DIR=/usr/local/share/fonts/sunairum

# Celery refuses (warns today, harder later) to run as root. Named volumes for
# /app/storage also start root-owned; the entrypoint chowns then gosu's to app.
RUN useradd --create-home --uid 1000 --shell /bin/bash app \
    && mkdir -p /app/storage \
    && chown -R app:app /home/app /app/storage \
    && chmod +x /app/docker-entrypoint.sh
ENV HOME=/home/app

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# FastAPI start (compose overrides command for --reload / celery)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
