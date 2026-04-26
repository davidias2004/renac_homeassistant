DOMAIN = "renac_power"

CONF_BASE_URL = "base_url"
CONF_STATION_ID = "station_id"
CONF_USER_ID = "user_id"
CONF_EQU_SN = "equ_sn"

DEFAULT_BASE_URL = "https://sec.bg.renacpower.cn:8084"
DEFAULT_SCAN_INTERVAL_FAST = 30   # seconds — station overview (current power)
DEFAULT_SCAN_INTERVAL_SLOW = 300  # seconds — statistics, savings, inverter chart

PLATFORMS = ["sensor", "binary_sensor"]
