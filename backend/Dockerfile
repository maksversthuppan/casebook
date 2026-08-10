FROM python:3.12-slim

# uv manages the venv and lockfile; installed here rather than pulled in via pip
# at request time, so the image is self-contained.
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Off $HOME so it isn't tied to whichever user's cache dir - the app later
# runs as an unprivileged user, not the root user doing this install.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Installs Chromium plus the OS libraries headless Chromium needs (fonts,
# libnss3, etc.) - the "--with-deps" is what a slim base image is missing.
# Depends only on the playwright version pinned in uv.lock, not on app code -
# kept above the COPY of app source so an ordinary code change doesn't force
# a multi-minute Chromium re-download on every deploy.
RUN uv run playwright install --with-deps chromium

COPY . .
RUN uv sync --frozen --no-dev

# Playwright's own install step needs root for apt; the running process doesn't.
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app /ms-playwright
USER app

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
