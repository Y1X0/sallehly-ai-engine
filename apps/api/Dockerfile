FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* /app/
COPY apps /app/apps
COPY services /app/services
COPY packages /app/packages

# Installs the whole workspace in editable mode - apps/api depends on
# services/ai-director, services/creative-compiler,
# services/render-orchestrator, services/asset-manager,
# services/video-engine-adapter, and several packages/*, all resolved
# via the root pyproject.toml's [tool.uv.workspace].
RUN uv sync --frozen --no-dev --package api

COPY apps/api/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
