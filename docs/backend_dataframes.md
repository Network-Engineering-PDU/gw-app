# Backend dataframes

## /data/push/

### Description

TycheTools gateways aggregate the data received by the network sensors and send it using the client API [https://{client}.tychetools.com/data/push/](https://{client}.tychetools.com/data/push/`).

The body of this API can contain telemetry information, such as temperature, humidity or pressure measurements; or power consumption information, such as power, energy or current data.

### Schema ID

To provide the client with the structure and content of the message, the body includes a `schema_id` field where the expected message is specified:

```python
class DataframeSchemaId:
    TELEMETRY_SCHEMA_ID = "temp"
    POWER_SCHEMA_ID     = "power"
```

### General parameters

The following parameters are always required in a dataframe:

- `device_id` (string, required): MAC address of the gateway.
- `datetime` (string, required): Date and time representing the timestamp of the dataframe. It must follow the format `%d/%m/%Y %H:%M`.
- `schema_id` (string, required): Schema ID of the dataframe.
- `data` (list, required): List of nodes containing the sensor data. If there is no data available, it should be an empty list. Every item on the list contains:
    - `mac_address` (string, required): MAC address of the sensor.
    - `datetime` (string, required): Date and time representing the timestamp of sensor data. It must follow the format `%d/%m/%Y %H:%M`.

### Telemetry parameters (temp)

Telemetry parameters are included in `data` field:

- `temperature` (integer, optional): Temperature, expressed in [ºC * 100], of the sensor. Error value is 20000.
- `humidity` (integer, optional): Relative humidity, expressed in [%HR], of the sensor. Error value is 120.
- `pressure` (integer, optional): Pressure, expressed in [hPa * 10000], of the sensor. Error value is 0.
- `rssi` (integer, optional): RSSI, expressed in [dBm], of the messages received by the sensor.

Example:

```
{
  "device_id": "f8dc7a651a3c",
  "datetime": "29/08/2023 08:50",
  "schema_id": "temp",
  "data": [
    {
      "mac_address": "ec789fce4aa8",
      "datetime": "29/08/2023 08:47",
      "temperature": 2807,
      "humidity": 36,
      "pressure": 9423134,
      "rssi": -62
    },
    {
      "mac_address": "e34812bf9ad6",
      "datetime": "29/08/2023 08:46",
      "temperature": 3019,
      "humidity": 34,
      "pressure": 0,
      "rssi": -71
    }
  ]
}
```

### Power parameters (power)

Power parameters are included in `data` field:

- `total_active_power` (integer, optional): Total active power, expressed in [W].
- `total_reactive_power` (integer, optional): Total reactive power, expressed in [VAr].
- `total_apparent_power` (integer, optional): Total apparent power, expressed in [VA].
- `total_energy` (integer, optional): Total energy, expressed in [Wh].
- `lines` (list, required): List of lines containing the data line. Empty list if no data available. Each line contains:
    - `line_id` (string, required): Line ID of the power line to be measured.
    - `frequency` (integer, optional): Frequency, expressed in [Hz], of the power line.
    - `phase_total` (integer, optional): Phase, expressed in [º], of the power line with respect to a reference point.
    - `phase_vi` (integer, optional): Phase, expressed in [º], between the voltage and the current measurements.
    - `active_power` (integer, optional): Active power, expressed in [W], of the power line.
    - `reactive_power` (integer, optional): Reactive power, expressed in [VAr], of the power line. 
    - `apparent_power` (integer, optional): Apparent power, expressed in [VA], of the power line. 
    - `energy` (integer, optional): Energy, expressed in [Wh], of the power line.
    - `voltage` (integer, optional): Voltage, expressed in [V], of the power line.
    - `current` (integer, optional): Current, expressed in [A], of the power line. 
    - `power_factor` (integer, optional): Power factor, expressed as a dimensionless number, of the power line.

Example:

```
{
  "device_id": "f8dc7a651a3c",
  "datetime": "29/08/2023 08:50",
  "schema_id": "power",
  "data": [
    {
      "mac_address": "fd9afce5a914",
      "datetime": "29/08/2023 08:46",
      "total_active_power": 1164.0,
      "total_reactive_power": 123.5,
      "total_apparent_power": 1170.5,
      "total_energy": 16479350,
      "lines": [
        {
          "current": 4.5,
          "line_id": "1"
        }
      ]
    },
    {
      "mac_address": "e59dece20c62",
      "datetime": "29/08/2023 08:46",
      "lines": [
        {
          "line_id": "1",
          "frequency": 49.99,
          "phase_vi": 25.48,
          "active_power": 5101.0,
          "reactive_power": 2421.0,
          "apparent_power": 5649.0,
          "energy": 420548.0,
          "voltage": 219.0,
          "current": 25.92,
          "power_factor": 0.95
        }
      ]
    }
  ]
}
```