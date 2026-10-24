FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/ ./
RUN npm install && npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app
COPY --from=web /web/dist /frontend_dist
ENV FRONTEND_DIST=/frontend_dist
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
