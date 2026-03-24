FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-dev libproj-dev proj-data proj-bin \
    libgdal-dev gcc g++ git && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user app/ ./app/

EXPOSE 7860

CMD ["panel", "serve", "app/app.py", \
     "--address", "0.0.0.0", \
     "--port", "7860", \
     "--allow-websocket-origin", "*"]
