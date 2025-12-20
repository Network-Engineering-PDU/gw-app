# Virtual functions

## Functions

1. [maximum](#maximum-minimum-median-max_no_outliers-min_no_outliers)
1. [minimum](#maximum-minimum-median-max_no_outliers-min_no_outliers)
1. [median](#maximum-minimum-median-max_no_outliers-min_no_outliers)
1. [max_no_outliers](#maximum-minimum-median-max_no_outliers-min_no_outliers)
1. [min_no_outliers](#maximum-minimum-median-max_no_outliers-min_no_outliers)
1. [weighted_sum](#weighted_sum)
1. [snmp_get](#snmp_get)
1. [backend_get](#backend_get)


## Types
Each virtual sensor produce one type of data. The following list includes the supported types, which must be specified in the virtual sensor arguments:

1. temp
2. hum
3. press
4. power


## Arguments

### maximum, minimum, median, max_no_outliers, min_no_outliers
The [type](#type) and a list of sensor macs (either real or virtual sensors).

```
{
    "type": "temp",
    "sensor_list": [
        "112233445566",
        "778899AABBCC"
    ]
}
```

### weighted_sum
Similar to the previous one, but now the list contains both the mac and its relative weight.

```
{
    "type": "hum",
    "sensor_list": [
        {
            "mac": "112233445566",
            "weight": 0.3
        },
        {
            "mac": "778899AABBCC",
            "weight": 0.8
        }
    ]
}
```

### snmp_get
The [type](#type), the IP address of the device running the SNMP server, the community string, the version (only 1 and 2 are supported) and the OID.

```
{
    "type": "power",
    "host": "192.168.0.110",
    "community": "public",
    "version": 2,
    "oid": ".1.3.124.16"
}
```

### backend_get
The [type](#type) and a backend (ECOaaS) URL from where to get the value. The gateway will use the already configured credentials for authentication.

```
{
    "type": "temp",
    "url": "https://ecoaas-url.com/data/get/api/"
    "path": "results.data.value1"
}
```


## Extra parameters

### Measurement conversion
Performs a conversion `ax + b` for the sensor measurement.

```
{
  ...
  "extra_params": {
    "conversion": {
      "add": 0,
      "multiply": 100
    }
    ...
  }
}
```

### Power parameters
For power measurements, an specific magnitude can be specified.

Valid total power arguments:

- total_active_power
- total_reactive_power
- total_apparent_power
- total_energy

```
{
  ...
  "extra_params": {
    "power_params": {
      "param": "total_active_power"
    }
    ...
  }
}
```

Valid line power arguments (`line_id` required):

- frequency
- phase_total
- phase_vi
- active_power
- reactive_power
- apparent_power
- energy
- voltage
- current
- power_factor

```
{
  ...
  "extra_params": {
    "power_params": {
      "param": "total_energy",
      "line_id": "2"
    }
    ...
  }
}
```