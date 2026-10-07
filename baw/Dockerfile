# ==============================================================================
# baw/ Dockerfile — hosts both:
#   • watsonx_orchestrate_connector.py  (MCP bridge, port 9090 → /mcp/*)
#   • baw_flood_response.py             (BAW logic, imported as a library)
#
# Deployed to IBM Cloud Code Engine as a separate App from pi-gnn/.
# Env-var secrets (Twilio, ERP, MCP_API_KEY, etc.) are injected at runtime
# via Code Engine secret references — never baked into this image.
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --only-binary=:all: \
        --no-cache-dir \
        --prefix=/install \
        -r requirements.txt

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY watsonx_orchestrate_connector.py baw_flood_response.py ./

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=9090

USER appuser

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

CMD ["sh", "-c", \
     "gunicorn watsonx_orchestrate_connector:app \
      --workers 1 \
      --threads 4 \
      --timeout 60 \
      --graceful-timeout 30 \
      --preload \
      --bind 0.0.0.0:${PORT} \
      --access-logfile - \
      --error-logfile -"]
