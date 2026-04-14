# --- web build stage ---
FROM node:22-alpine AS web-build
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter web
COPY apps/web apps/web
RUN pnpm --filter web build

# --- api runtime stage ---
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/src apps/api/src
RUN uv sync --frozen --no-dev
COPY --from=web-build /repo/apps/web/dist /app/apps/api/src/api/static
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
