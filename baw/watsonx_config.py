import os

INFER_ENDPOINT       = os.environ.get("INFER_ENDPOINT", "http://localhost:8080/infer")
ES_URL               = os.environ.get("EVENT_STREAMS_URL", "")
ES_APIKEY            = os.environ.get("EVENT_STREAMS_APIKEY", "")
ES_TOPIC             = os.environ.get("EVENT_STREAMS_TOPIC", "chalakudy-basin-telemetry")
MCP_API_KEY          = os.environ.get("MCP_API_KEY", "dev-insecure-key")
BAW_TRIGGER_TOKEN    = os.environ.get("BAW_TRIGGER_TOKEN", "")
