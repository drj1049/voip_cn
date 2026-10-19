# This Dockerfile builds the whole app in two stages. Stage 1 compiles the React dashboard
# into plain HTML/JS/CSS files. Stage 2 is the small Python image that actually runs, and it
# only copies the finished dashboard files across, so Node is not needed when running.

# Stage 1: build the React dashboard
FROM node:20-slim AS frontend
WORKDIR /app/frontend
# Copy only the package lists first. Docker can then reuse the installed packages
# next time if only the code changed, which makes rebuilds much faster.
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend that also serves the built dashboard
FROM python:3.12-slim
WORKDIR /app
# Print logs straight away instead of holding them back, so they show up live on Render
ENV PYTHONUNBUFFERED=1
# Same trick as above: install Python packages first so they are cached between builds
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
# Bring in the dashboard files that stage 1 built (the backend serves them from frontend/dist)
COPY --from=frontend /app/frontend/dist ./frontend/dist
EXPOSE 8000
# Render gives us the port to use in $PORT; when running it yourself it falls back to 8000.
# 0.0.0.0 means "accept connections from outside the container", which Render needs.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
