FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FORWARDER_DB=/data/routes.sqlite3
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home bot && mkdir /data && chown bot:bot /data
COPY forwarder/ forwarder/
COPY main.py ./
COPY tests/ tests/
COPY scripts/check_bot.py scripts/check_bot.py
COPY scripts/diagnose_routes.py scripts/diagnose_routes.py
COPY scripts/verify_delivery.py scripts/verify_delivery.py
USER bot
CMD ["python", "main.py"]
