FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home bot
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
# Normalize source permissions even when checkout uses umask 077.
RUN chmod -R a+rX /app/app /app/alembic && chmod a+r /app/alembic.ini
USER bot
CMD ["python", "-m", "app.bot.bot"]
