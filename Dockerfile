FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    PATH="$PATH:/usr/games" \
    MIGRATIONS_DIR=/app/migrations
CMD ["python", "-m", "marione"]
