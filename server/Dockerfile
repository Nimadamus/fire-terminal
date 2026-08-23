# The licence service and the website in one container.
#
# Exists so the deployment is not tied to one host. Render, Fly, Railway, a
# plain VPS with docker, or anything else that runs a container will serve
# this identically. If a hosting account expires, the recovery is to point a
# different host at the same image rather than to rebuild anything.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

# The service imports the token format from the application package, and
# serves the website from disk. Both come along.
COPY server /app/server
COPY site /app/site
COPY src /app/src

ENV FIRE_SITE_DIR=/app/site \
    PYTHONPATH=/app/src

WORKDIR /app/server
EXPOSE 8000

# Render and most hosts set PORT. Default to 8000 for a local run.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
