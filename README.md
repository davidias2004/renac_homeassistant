# RENAC Power — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Experimental Home Assistant integration for RENAC solar inverters, using the cloud API observed at `sec.eu.renacpower.com` / `sec.bg.renacpower.cn:8084`.

---

## Installation via HACS (recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations → ⋮ → Custom repositories**.
3. Add `https://github.com/davidias2004/renac_homeassistant` as an **Integration**.
4. Search for **RENAC Power** and install it.
5. Restart Home Assistant.

---

## Manual Installation

1. Copy the `custom_components/renac_power` folder to your HA config:

```text
/config/custom_components/renac_power
```

2. Restart Home Assistant.

---

## Setup

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **RENAC Power**.
3. Enter your **Username** and **Password**.
   - The integration will automatically discover your Station ID and User ID from the API.
   - If discovery fails, you will be prompted to enter them manually (find them in the network requests of the RENAC web app).
4. Optionally enter the **Inverter serial number** (enables extra sensors). You can find it later via the **RENAC Power** device page or by enabling debug logs.

---

## Sensors

| Entity | Unit | Description |
|--------|------|-------------|
| Current Power | kW | Real-time PV production |
| Battery SOC | % | Battery state of charge |
| Today Energy | kWh | Energy produced today |
| Month Energy | kWh | Energy produced this month |
| Year Energy | kWh | Energy produced this year |
| Total Savings | — | Accumulated financial savings |
| Online Equipment | — | Number of devices online |
| Error Count | — | Active errors today |
| Problem | binary | True if any active errors |

---

## Debug Logs

Add to `configuration.yaml` to capture raw API responses:

```yaml
logger:
  default: info
  logs:
    custom_components.renac_power: debug
```

---

## Notes

- This integration is **experimental**. Field names in the RENAC API vary by installation type. If sensors show unavailable, enable debug logs and share the raw response to help improve field mapping.
- The API endpoint `https://sec.bg.renacpower.cn:8084` is used by default. European users may also see traffic through `sec.eu.renacpower.com`.

### Please do not share publicly

- Token / password
- Real `station_id` or `user_id` if you want to keep your installation private
- Inverter serial number

---

## Contributing

Found a field name that works for your installation? Open an issue or PR with the raw JSON response (credentials redacted) so the field list can be expanded for everyone.
