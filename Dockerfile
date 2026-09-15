FROM python:3.11.15-slim-bookworm AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-bridge.txt ./
RUN pip install --no-cache-dir -r requirements-bridge.txt \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin calendar
COPY bridge/ ./bridge/
USER 10001:10001
CMD ["python", "-m", "uvicorn", "bridge.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM python:3.11.15-slim-bookworm AS ui
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin calendar
COPY blind_invite.py calendar_utils.py consultant_config.py bridge_client.py caltest_fixtures.py ./
USER 10001:10001
CMD ["python", "-m", "streamlit", "run", "blind_invite.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.baseUrlPath=calendar-invites", "--server.headless=true", "--browser.gatherUsageStats=false"]
