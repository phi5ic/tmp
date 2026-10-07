import os

TWILIO_ACCOUNT_SID    = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN     = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER    = os.environ.get("TWILIO_FROM_NUMBER", "+10000000000")

ERP_BASE_URL          = os.environ.get("ERP_BASE_URL", "https://erp.example.internal")
ERP_API_KEY           = os.environ.get("ERP_API_KEY", "")

_raw_warehouse_urls   = os.environ.get("WAREHOUSE_WEBHOOK_URLS", "")
WAREHOUSE_WEBHOOK_URLS = [u.strip() for u in _raw_warehouse_urls.split(",") if u.strip()]

_raw_drivers          = os.environ.get("DRIVER_PHONE_NUMBERS", "")
DRIVER_PHONE_NUMBERS  = [p.strip() for p in _raw_drivers.split(",") if p.strip()]

ELEVATED_REST_AREA    = os.environ.get(
    "ELEVATED_REST_AREA", "Athirappilly Rest Area — 10.284°N 76.569°E"
)
BAW_CALLBACK_URL      = os.environ.get("BAW_CALLBACK_URL", "")

DEMO_MODE = not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and ERP_API_KEY)
