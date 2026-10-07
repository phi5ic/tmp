# ==============================================================================
# Stage 1: Builder — install dependencies into a virtual environment
# This stage is discarded after the build, keeping the final image lean.
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed to compile torch native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Use --only-binary=:all: to pull pre-built wheels, avoids slow compilation
# Install into an isolated prefix we will copy across to the runtime stage
RUN pip install --upgrade pip \
 && pip install --only-binary=:all: \
        --no-cache-dir \
        --prefix=/install \
        -r requirements.txt

# ==============================================================================
# Stage 2: Runtime — minimal image suitable for IBM Cloud Code Engine
#
# Key Code Engine optimisations applied here:
#   • Non-root USER (Code Engine requirement for rootless container execution)
#   • PORT env-var respected: Code Engine injects PORT=8080 at runtime
#   • SIGTERM-aware Gunicorn worker: zero-downtime scale-to-zero & scale-up
#   • PYTHONDONTWRITEBYTECODE / PYTHONUNBUFFERED: faster cold-start, clean logs
#   • Minimal layer footprint: runtime has no compiler toolchain
# ==============================================================================
FROM python:3.11-slim AS runtime

# ── Code Engine expects a non-root user ──────────────────────────────────────
RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy only the installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY model.py vdtn_simulation.py webhook_server.py ./

# ── Python runtime tuning ────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # IBM Code Engine injects PORT at runtime; default to 8080 for local runs
    PORT=8080

# Install lightweight WSGI server (no extra layer weight — no build tools needed)
RUN pip install --no-cache-dir gunicorn flask

# Drop to non-root
USER appuser

# ── Health-check so Code Engine knows the container is ready ─────────────────
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

# ── Entrypoint ────────────────────────────────────────────────────────────────
# Gunicorn settings tuned for Code Engine scale-to-zero reactive scaling:
#   --workers 1          Single worker keeps cold-start RAM under the 256 MB
#                        minimum allocation used by Code Engine scale-to-zero.
#   --timeout 120        Allows PI-GNN inference (torch matmul) to complete
#                        before the worker is killed.
#   --graceful-timeout   Matches Code Engine's SIGTERM drain window (30 s).
#   --preload-app        Loads the model once per worker at startup so
#                        inference requests are served with no per-request load.
#   --bind 0.0.0.0:$PORT Binds to the port Code Engine injects.
CMD ["sh", "-c", \
     "gunicorn webhook_server:app \
      --workers 1 \
      --threads 4 \
      --timeout 120 \
      --graceful-timeout 30 \
      --preload \
      --bind 0.0.0.0:${PORT} \
      --access-logfile - \
      --error-logfile -"]
