# Single container: FastAPI serves the API, the WebSocket feed and the built React app.
# Build:  docker build -t insidethegame .
# Run:    docker run -p 8000:8000 --env-file backend/.env insidethegame

FROM node:20-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STATIC_DIR=/app/static
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .
COPY --from=frontend /src/dist ./static
EXPOSE 8000
# First start generates the default synthetic match (~10 s) into /app/data.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
