# RENAC Power - Home Assistant Custom Integration

Experimental integration for Home Assistant using the RENAC web API observed at `sec.eu.renacpower.com` / `sec.bg.renacpower.cn:8084`.

## Manual Installation

1. Copy the `custom_components/renac_power` folder to:

```text
/config/custom_components/renac_power
```

2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration**.
4. Search for **RENAC Power**.
5. Fill in:
   - `Base URL`: `https://sec.bg.renacpower.cn:8084`
   - `Username`
   - `Password`
   - `User ID`
   - `Station ID`
   - `Equ SN`, optional, for inverter details.

## Created Sensors

- Current Power
- Battery SOC
- Today Energy
- Month Energy
- Year Energy
- Total Savings
- Online Equipment
- Error Count
- Problem

## Used Endpoints

- `/api/user/login`
- `/api/home/station/powerFlow`
- `/api/station/storage/overview`
- `/api/station/all/savings`
- `/api/station/equipStat`
- `/api/home/errorList2`
- `/api/station/chart/station`
- `/bg/equList`
- `/bg/inv/detail`, if `equ_sn` is defined
- `/api/inv/gridChart2`, if `equ_sn` is defined

## Important Note

This integration is still experimental because the exact names of the fields returned by the API may vary depending on the type of RENAC installation. The code already tries to look for several possible names, but it is likely that the fields will need to be adjusted after seeing the real responses in the log/debug.

To help the community, avoid publishing:

- token
- username
- password
- real station_id, if you don't want to expose the installation
- real user_id
- inverter serial number

## Development

Enable logs in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.renac_power: debug
```
