# ---- frontend build ----
FROM node:22-alpine AS fe
WORKDIR /fe
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY --from=fe /fe/dist ./static
ENV STATIC_DIR=/app/static DB_PATH=/data/reader.db
EXPOSE 8320
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8320"]
