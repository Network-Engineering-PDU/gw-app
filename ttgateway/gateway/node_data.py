import csv
import asyncio
import logging
from datetime import datetime as dt

from ttgwlib import EventType as LibEventType

from ttgateway.events import EventType
from ttgateway.config import config


logger = logging.getLogger(__name__)

pwmt_params = {"frequency": "f",
    "phase_total": "ph_t",
    "phase_vi": "ph",
    "active_power": "p",
    "reactive_power": "q",
    "apparent_power": "s",
    "energy": "e",
    "voltage": "v",
    "current": "i",
    "power_factor": "pf",
    "total_active_power": "p_tot",
    "total_reactive_power": "q_tot",
    "total_apparent_power": "s_tot",
    "total_energy": "e_tot"
}

pwmt_total_params = ("total_active_power", "total_reactive_power",
    "total_apparent_power", "total_energy")

pwmt_line_params = ("frequency", "phase_total", "phase_vi",
    "active_power", "reactive_power", "apparent_power", "energy",
    "voltage", "current", "power_factor")


class NodeData:
    RSSI_K = 0.02

    def __init__(self, event_handler):
        self.tel_data = {}
        self.co2_data = {}
        self.iaq_data = {}
        self.bat_data = {}
        self.pwmt_data = {}
        self.ota_status_data = {}
        self.stats = {}
        self.coverage = {}
        self.event_handler = event_handler
        self.event_handler.add_handler(LibEventType.RSSI_NEIGHBR_DATA,
                self.rssi_data_handler)
        self.event_handler.add_handler(LibEventType.TEMP_DATA,
                self.telemetry_handler)
        self.event_handler.add_handler(LibEventType.TEMP_DATA_RELIABLE,
                self.telemetry_handler)
        self.event_handler.add_handler(LibEventType.IAQ_DATA,
                self.iaq_handler)
        self.event_handler.add_handler(LibEventType.CO2_DATA,
                self.co2_handler)
        self.event_handler.add_handler(LibEventType.BAT_DATA,
                self.battery_handler)
        self.event_handler.add_handler(LibEventType.OTA_STATUS_ACK,
                self.ota_status_handler)
        self.event_handler.add_handler(LibEventType.OTA_VERSION_ACK,
                self.ota_version_handler)
        self.event_handler.add_handler(LibEventType.PWMT_DATA,
                self.pwmt_handler)
        self.event_handler.add_handler(LibEventType.WAKE_RESET,
                self.wake_reset_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_MEDIAN,
                self.median_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_MAX,
                self.max_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_MIN,
                self.min_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_MAX_NO_OUTLIERS,
                self.max_no_outl_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_MIN_NO_OUTLIERS,
                self.min_no_outl_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_WEIGHTED_SUM,
                self.weighted_sum_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_SNMP_GET,
                self.snmp_get_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_MODBUS_GET,
                self.modbus_get_handler)
        self.event_handler.add_handler(EventType.VIRTUAL_BACKEND_GET,
                self.backend_get_handler)

    def get_data(self, node_mac, tel, co2, iaq, bat, ota, stats, pwmt, cvg):
        data = {}
        if tel and node_mac in self.tel_data:
            data.update(self.tel_data[node_mac])
        if co2 and node_mac in self.co2_data:
            data.update(self.co2_data[node_mac])
        if iaq and node_mac in self.iaq_data:
            data.update(self.iaq_data[node_mac])
        if bat and node_mac in self.bat_data:
            data.update(self.bat_data[node_mac])
        if ota and node_mac in self.ota_status_data:
            data.update(self.ota_status_data[node_mac])
        if stats and node_mac in self.stats:
            data.update(self.stats[node_mac])
        if pwmt and node_mac in self.pwmt_data:
            data.update(self.pwmt_data[node_mac])
        if cvg and node_mac in self.coverage:
            data.update({"coverage": self.coverage[node_mac]})
        return data

    def get_summary(self):
        data = {}
        ttl = [0, 0, 0, 0]
        for node_mac in self.stats:
            if "ttl" in self.stats[node_mac]:
                for i in range(4):
                    ttl[i] += self.stats[node_mac]["ttl"][i]
        total_msg = ttl[0] + ttl[1] + ttl[2] + ttl[3]
        data["msg_drct"] = ttl[0]
        data["msg_1hop"] = ttl[1]
        data["msg_2hop"] = ttl[2]
        data["msg_3hop"] = ttl[3]
        data["per_drct"] = None
        data["per_1hop"] = None
        data["per_2hop"] = None
        data["per_3hop"] = None
        if total_msg != 0:
            data["per_drct"] = round((ttl[0] * 100) / total_msg, 2)
            data["per_1hop"] = round((ttl[1] * 100) / total_msg, 2)
            data["per_2hop"] = round((ttl[2] * 100) / total_msg, 2)
            data["per_3hop"] = round((ttl[3] * 100) / total_msg, 2)
        batts = [bat["battery"] for bat in self.bat_data.values()]
        data["batt_avg"], data["batt_min"], data["batt_max"] = None, None, None
        if len(batts) != 0:
            data["batt_avg"] = round(sum(batts) / (len(batts) * 1000), 2)
            data["batt_min"] = round(min(batts) / 1000, 2)
            data["batt_max"] = round(max(batts) / 1000, 2)
        rssi_avgs = []
        for stat in self.stats.values():
            if "rssi_avg" in stat:
                rssi_avgs.append(stat["rssi_avg"])
        data["rssi_avg"], data["rssi_min"], data["rssi_max"] = None, None, None
        if len(rssi_avgs) != 0:
            data["rssi_avg"] = round(sum(rssi_avgs) / len(rssi_avgs), 2)
            data["rssi_min"] = round(min(rssi_avgs), 2)
            data["rssi_max"] = round(max(rssi_avgs), 2)
        temps = [(tel["temperature"] / 100) for tel in self.tel_data.values()]
        temp_avg, temp_min, temp_max = None, None, None
        if len(temps) > 0:
            temp_sum, temp_len = 0, 0
            temp_max, temp_min = temps[0], temps[0]
            for temp in temps:
                if temp != 200:
                    temp_sum += temp
                    temp_len += 1
                    if temp_max < temp or temp == 200:
                        temp_max = temp
                    if temp_min > temp or temp == 200:
                        temp_min = temp
            temp_avg = round(temp_sum / temp_len, 2) if temp_len else None
        data["temp_avg"] = temp_avg
        data["temp_min"] = temp_min
        data["temp_max"] = temp_max
        humds = [tel["humidity"] for tel in self.tel_data.values()]
        humd_avg, humd_min, humd_max = None, None, None
        if len(humds) > 0:
            humd_sum, humd_len = 0, 0
            humd_max, humd_min = humds[0], humds[0]
            for humd in humds:
                if humd != 120:
                    humd_sum += humd
                    humd_len += 1
                    if humd_max < humd or humd_max == 120:
                        humd_max = humd
                    if humd_min > humd or humd_min == 120:
                        humd_min = humd
            humd_avg = round(humd_sum / humd_len, 2) if humd_len else None
        data["humd_avg"] = humd_avg
        data["humd_min"] = humd_min
        data["humd_max"] = humd_max
        press = [(tel["pressure"] / 10000) for tel in self.tel_data.values()]
        pres_avg, pres_min, pres_max = None, None, None
        if len(press) > 0:
            pres_sum, pres_len = 0, 0
            pres_max, pres_min = press[0], press[0]
            for pres in press:
                if pres != 0:
                    pres_sum += pres
                    pres_len += 1
                    if pres_max < pres or pres_max == 0:
                        pres_max = pres
                    if pres_min > pres or pres_min == 0:
                        pres_min = pres
            pres_avg = round(pres_sum / pres_len, 4) if pres_len else None
        data["pres_avg"] = pres_avg
        data["pres_min"] = pres_min
        data["pres_max"] = pres_max
        return data

    def update_stats(self, node_mac, rssi, ttl):
        self.update_avg_rssi_stat(node_mac, rssi)
        self.update_ttl_stat(node_mac, ttl)

    def update_avg_rssi_stat(self, node_mac, rssi):
        if node_mac not in self.stats:
            self.stats[node_mac] = {}
        if "rssi_avg" not in self.stats[node_mac]:
            rssi_avg = rssi
        else:
            old_rssi = self.stats[node_mac]["rssi_avg"]
            rssi_avg = old_rssi * (1 - self.RSSI_K) + rssi * self.RSSI_K
        self.stats[node_mac]["rssi_avg"] = round(rssi_avg, 2)

    def update_ttl_stat(self, node_mac, ttl):
        if node_mac not in self.stats:
            self.stats[node_mac] = {}
        if "ttl" not in self.stats[node_mac]:
            self.stats[node_mac]["ttl"] = [0, 0, 0, 0]
        if ttl == 127:
            self.stats[node_mac]["ttl"][0] += 1
        elif ttl == 126:
            self.stats[node_mac]["ttl"][1] += 1
        elif ttl == 125:
            self.stats[node_mac]["ttl"][2] += 1
        elif ttl <= 124:
            self.stats[node_mac]["ttl"][3] += 1

    def update_coverage(self, node_mac, gw_id, rssi, assigned):
        if None in (node_mac, gw_id, rssi):
            return
        if node_mac not in self.coverage:
            self.coverage[node_mac] = {}
        if not gw_id in self.coverage[node_mac]:
            self.coverage[node_mac][gw_id] = {}
        self.coverage[node_mac][gw_id] = {
            "timestamp": dt.utcnow().timestamp(),
            "rssi": rssi,
            "assigned": assigned
        }

    def rssi_data_handler(self, event):
        def _write_csv(self, event):
            addr = event.data["addr"]
            rssi = event.data["rssi"]
            csv_file = f"{config.TT_DIR}/rssi_data.csv"
            with open(csv_file, mode="a") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow([dt.now().timestamp, event.node.mac.hex(),
                    self.gw.get_node_by_addr(addr).mac.hex(), rssi])
        asyncio.create_task(asyncio.to_thread(_write_csv, event))

    def telemetry_handler(self, event):
        mac = event.node.mac.hex()
        self.update_stats(mac, event.data["rssi"], event.data["ttl"])
        if mac not in self.tel_data:
            self.tel_data[mac] = {}
        self.tel_data[mac].update({
            "datetime": dt.utcnow().timestamp(),
            "temperature": event.data["temp"],
            "humidity": event.data["hum"],
            "pressure": event.data["press"],
            "rssi": event.data["rssi"],
        })

    def iaq_handler(self, event):
        mac = event.node.mac.hex()
        self.update_stats(mac, event.data["rssi"], event.data["ttl"])
        if mac not in self.iaq_data:
            self.iaq_data[mac] = {}
        self.iaq_data[mac].update({
            "datetime": dt.utcnow().timestamp(),
            "iaq": event.data["iaq"],
            "tvoc": event.data["tvoc"],
            "etoh": event.data["etoh"],
            "eco2": event.data["eco2"],
        })

    def co2_handler(self, event):
        mac = event.node.mac.hex()
        self.update_stats(mac, event.data["rssi"], event.data["ttl"])
        if mac not in self.co2_data:
            self.co2_data[mac] = {}
        self.co2_data[mac].update({
            "datetime": dt.utcnow().timestamp(),
            "co2": event.data["co2"],
        })

    def battery_handler(self, event):
        mac = event.node.mac.hex()
        self.update_stats(mac, event.data["rssi"], event.data["ttl"])
        if mac not in self.bat_data:
            self.bat_data[mac] = {}
        self.bat_data[mac].update({
            "bat_timestamp": dt.utcnow().timestamp(),
            "battery": event.data["bat"],
        })

    def ota_status_handler(self, event):
        mac = event.node.mac.hex()
        self.update_stats(mac, event.data["rssi"], event.data["ttl"])
        if mac not in self.ota_status_data:
            self.ota_status_data[mac] = {}
        self.ota_status_data[mac].update({
            "status": event.data["status"],
        })

    def ota_version_handler(self, event):
        mac = event.node.mac.hex()
        # If ota version is successful delete the previous
        # ota status (if exist) to avoid confusing the new
        # with the old status
        self.update_stats(mac, event.data["rssi"], event.data["ttl"])
        if mac in self.ota_status_data:
            if event.data["status"] == 0:
                del self.ota_status_data[mac]

    def pwmt_handler(self, event):
        """ PWMT handler that updates pwmt data.

        Creates node entry if node is not found in node data. Then, updates the
        total pwmt data. Finally, updates the line pwmt data. To do so, it gets
        the line if already exists and updates each param (by reference). If it
        does not exist, creates the line and appends it to node data.
        """
        mac = event.node.mac.hex()
        self.update_stats(mac, event.data["rssi"], event.data["ttl"])
        if mac not in self.pwmt_data:
            self.pwmt_data[mac] = {
                "datetime": dt.utcnow().timestamp(),
                "lines": []
            }
        self.pwmt_data[mac]["datetime"] = dt.utcnow().timestamp()
        for pwmt_total_param in pwmt_total_params:
            if pwmt_params[pwmt_total_param] in event.data:
                self.pwmt_data[mac][pwmt_total_param] = \
                    event.data[pwmt_params[pwmt_total_param]]
        line_id = event.data["ctl"] & 0b11
        if line_id == 0:
            return
        pwmt_line = {
            "line_id": line_id
        }
        line_exist = False
        for line in self.pwmt_data[mac]["lines"]:
            if line["line_id"] == line_id:
                line_exist = True
                pwmt_line = line
                break
        for pwmt_line_param in pwmt_line_params:
            if pwmt_params[pwmt_line_param] in event.data:
                pwmt_line[pwmt_line_param] = \
                        event.data[pwmt_params[pwmt_line_param]]
        if not line_exist:
            self.pwmt_data[mac]["lines"].append(pwmt_line)

    def wake_reset_handler(self, event):
        mac = event.node.mac.hex()
        if mac not in self.stats:
            self.stats[mac] = {}
        self.stats[mac]["last_reset"] = dt.utcnow().timestamp()

    def median_handler(self, event):
        if event.node.is_local():
            return
        mac = event.node.mac.hex()
        if mac not in self.tel_data:
            self.tel_data[mac] = {}
        tel_data = {
            "datetime": dt.utcnow().timestamp(),
        }
        if event.data["type"] == "temp":
            tel_data["temperature"] = event.data["median"]
        elif event.data["type"] == "hum":
            tel_data["humidity"] = event.data["median"]
        elif event.data["type"] == "press":
            tel_data["pressure"] = event.data["median"]
        else:
            return
        self.tel_data[mac].update(tel_data)

    def max_handler(self, event):
        if event.node.is_local():
            return
        mac = event.node.mac.hex()
        if mac not in self.tel_data:
            self.tel_data[mac] = {}
        tel_data = {
            "datetime": dt.utcnow().timestamp(),
        }
        if event.data["type"] == "temp":
            tel_data["temperature"] = event.data["max"]
        elif event.data["type"] == "hum":
            tel_data["humidity"] = event.data["max"]
        elif event.data["type"] == "press":
            tel_data["pressure"] = event.data["max"]
        else:
            return
        self.tel_data[mac].update(tel_data)

    def min_handler(self, event):
        if event.node.is_local():
            return
        mac = event.node.mac.hex()
        if mac not in self.tel_data:
            self.tel_data[mac] = {}
        tel_data = {
            "datetime": dt.utcnow().timestamp(),
        }
        if event.data["type"] == "temp":
            tel_data["temperature"] = event.data["min"]
        elif event.data["type"] == "hum":
            tel_data["humidity"] = event.data["min"]
        elif event.data["type"] == "press":
            tel_data["pressure"] = event.data["min"]
        else:
            return
        self.tel_data[mac].update(tel_data)

    def max_no_outl_handler(self, event):
        if event.node.is_local():
            return
        mac = event.node.mac.hex()
        if mac not in self.tel_data:
            self.tel_data[mac] = {}
        tel_data = {
            "datetime": dt.utcnow().timestamp(),
        }
        if event.data["type"] == "temp":
            tel_data["temperature"] = event.data["max_no_outliers"]
        elif event.data["type"] == "hum":
            tel_data["humidity"] = event.data["max_no_outliers"]
        elif event.data["type"] == "press":
            tel_data["pressure"] = event.data["max_no_outliers"]
        else:
            return
        self.tel_data[mac].update(tel_data)

    def min_no_outl_handler(self, event):
        if event.node.is_local():
            return
        mac = event.node.mac.hex()
        if mac not in self.tel_data:
            self.tel_data[mac] = {}
        tel_data = {
            "datetime": dt.utcnow().timestamp(),
        }
        if event.data["type"] == "temp":
            tel_data["temperature"] = event.data["min_no_outliers"]
        elif event.data["type"] == "hum":
            tel_data["humidity"] = event.data["min_no_outliers"]
        elif event.data["type"] == "press":
            tel_data["pressure"] = event.data["min_no_outliers"]
        else:
            return
        self.tel_data[mac].update(tel_data)

    def weighted_sum_handler(self, event):
        if event.node.is_local():
            return
        mac = event.node.mac.hex()
        if mac not in self.tel_data:
            self.tel_data[mac] = {}
        tel_data = {
            "datetime": dt.utcnow().timestamp(),
        }
        if event.data["type"] == "temp":
            tel_data["temperature"] = event.data["weighted_sum"]
        elif event.data["type"] == "hum":
            tel_data["humidity"] = event.data["weighted_sum"]
        elif event.data["type"] == "press":
            tel_data["pressure"] = event.data["weighted_sum"]
        else:
            return
        self.tel_data[mac].update(tel_data)

    def snmp_get_handler(self, event):
        if event.node.is_local():
            return
        mac = event.node.mac.hex()
        if mac not in self.tel_data and not event.data["type"] == "power":
            self.tel_data[mac] = {}
        if mac not in self.pwmt_data and event.data["type"] == "power":
            self.pwmt_data[mac] = {
                "lines": []
            }

        data = {
            "datetime": dt.utcnow().timestamp(),
        }

        snmp_data = round(float(event.data["snmp_data"]), 4)
        if ("extra_params" in event.data and
                "conversion" in event.data["extra_params"]):
            if "multiply" in event.data["extra_params"]["conversion"]:
                k_mult = event.data["extra_params"]["conversion"]["multiply"]
                snmp_data = round(snmp_data * k_mult, 4)
            if "add" in event.data["extra_params"]["conversion"]:
                k_add = event.data["extra_params"]["conversion"]["add"]
                snmp_data = round(snmp_data + k_add, 4)

        if event.data["type"] == "power":
            self.pwmt_data[mac]["datetime"] = dt.utcnow().timestamp()
            if ("extra_params" in event.data and
                    "power_params" in event.data["extra_params"]):
                power_params = event.data["extra_params"]["power_params"]
                if power_params["param"] in pwmt_total_params:
                    self.pwmt_data[mac][power_params["param"]] = snmp_data
                elif power_params["param"] in pwmt_line_params:
                    pwmt_line = {
                        "line_id": power_params["line_id"]
                    }
                    line_exist = False
                    for line in self.pwmt_data[mac]["lines"]:
                        if line["line_id"] == power_params["line_id"]:
                            line_exist = True
                            pwmt_line = line
                            break
                    pwmt_line[power_params["param"]] = snmp_data
                    if not line_exist:
                        self.pwmt_data[mac]["lines"].append(pwmt_line)
                else:
                    logger.warning("Invalid snmp power param")
            else:
                self.pwmt_data[mac]["total_active_power"] = snmp_data
        elif event.data["type"] == "temp":
            data["temperature"] = snmp_data
            self.tel_data[mac].update(data)
        elif event.data["type"] == "hum":
            data["humidity"] = snmp_data
            self.tel_data[mac].update(data)
        elif event.data["type"] == "press":
            data["pressure"] = snmp_data
            self.tel_data[mac].update(data)

    def modbus_get_handler(self, event):
        logger.info(event.data)

    def backend_get_handler(self, event):
        mac = event.node.mac.hex()
        now = dt.utcnow().timestamp()
        data_type = event.data["type"]
        if data_type in ("temp", "hum", "press"):
            if mac not in self.tel_data:
                self.tel_data[mac] = {}
            self.tel_data[mac]["datetime"] = now
        if data_type == "power":
            if mac not in self.pwmt_data:
                self.pwmt_data[mac] = {}
            self.pwmt_data[mac]["datetime"] = now
        if data_type == "temp":
            self.tel_data[mac]["temperature"] = event.data["backend_data"]
        elif data_type == "hum":
            self.tel_data[mac]["humidity"] = event.data["backend_data"]
        elif data_type == "press":
            self.tel_data[mac]["pressure"] = event.data["backend_data"]
        elif data_type == "power":
            self.pwmt_data[mac]["total_active_power"] = \
                event.data["backend_data"]
