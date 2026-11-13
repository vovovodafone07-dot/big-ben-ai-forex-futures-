# Portable Big Ben AI Pro backend. No broker/order execution.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY platform/backend/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY platform/backend/ /app/platform/backend/
COPY platform/index.html /app/platform/index.html
RUN useradd --system --uid 10001 bigben
USER bigben
EXPOSE 8080
CMD ["python", "platform/backend/app.py"]
