import re
import time
from datetime import datetime as dt
from datetime import timedelta as td

import requests


FILENAME = "log_error"
DEVICE_ID = "f8dc7a8041b6"
URL = "https://ecoaas-api-adif.tychetools.com"
COMPANY = "adif"
USER = "test-adif@example.com"
PASSWORD = "123"
PERIOD = 600


class HttpHelperConnectionError(Exception):
    pass


class HttpHelper:
    def __init__(self, base_url="", user="", password=""):
        self.base_url = base_url
        self.user = user
        self.password = password
        self.access_token = ""
        self.refresh_token = ""

    def _headers(self, include_auth):
        headers = {
            "content-type": "application/json",
            "user-agent": "manual_upload/1.0.0",
        }
        if include_auth:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _request(self, name, method, url, body, auth, timeout=15):
        init_ts = time.monotonic()
        try:
            rsp = requests.request(method, url, json=body,
                headers=self._headers(auth), timeout=timeout)
        except requests.exceptions.ConnectionError:
            if name:
                print(f"HTTP connection error: {name}")
            return None
        except requests.exceptions.ReadTimeout:
            if name:
                print(f"HTTP connection timeout: {name}")
            return None

        if name:
            print("HTTP %s %s rsp status: %d (delay: %d s)", method, name,
                    rsp.status_code, int(time.monotonic() - init_ts))
            if not rsp.ok:
                try:
                    data = rsp.json()
                except json.JSONDecodeError:
                    data = rsp.text
                print(f"HTTP {method} {name} error: {data}")

        return rsp

    def token_verify(self):
        url = f"{self.base_url}/auth/token/verify/"
        body = {"token": self.access_token}
        rsp =  self._request("", "POST", url, body, auth=False)
        if rsp is None:
            raise HttpHelperConnectionError()
        return rsp.ok

    def token_refresh(self):
        url = f"{self.base_url}/auth/token/refresh/"
        body = {"refresh": self.refresh_token}
        rsp = self._request("", "POST", url, body, auth=False)
        if rsp is None:
            raise HttpHelperConnectionError()
        if rsp.ok:
            self.access_token = rsp.json()["access"]
        return rsp.ok

    def token_get(self):
        url = f"{self.base_url}/auth/token/"
        body = {"email": self.user, "password": self.password}
        rsp = self._request("", "POST", url, body, auth=False)
        if rsp is None:
            raise HttpHelperConnectionError()
        if rsp.ok:
            self.access_token = rsp.json()["access"]
            self.refresh_token = rsp.json()["refresh"]
        return rsp.ok

    def request(self, name, method, url, body=None, timeout=15):
        try:
            if not self.token_verify():
                if not self.token_refresh():
                    if not self.token_get():
                        print("Incorrect HTTP credentials")
                        return None
            return self._request(name, method, url, body, True, timeout)
        except HttpHelperConnectionError:
            print("Connection error %s", name)
            return None


class ManualBackendApp:
    PATTERN_TEMP_LOG = re.compile("(.*),.* - ttgwlib.models.nrf_temp - DEBUG - "
        + "Temp received: ([0-9]*), ([0-9a-f]*), ([0-9]*), ([0-9]*), ([0-9]*), "
        + "-([0-9]*)")
    DATE_FMT = "%Y-%m-%d %H:%M:%S"
    SEND_TIME_DELTA = td(seconds=PERIOD)

    def __init__(self, http_helper, filename, url, company, device_id):
        self.http = http_helper
        self.filename = filename
        self.device_id = device_id
        self.url = url
        self.company = company
        self.device_id = device_id

        self.data = {}
        self.next_send_date = None

    def run(self):
        with open(self.filename) as f:
            lines = f.readlines()

        for line in lines:
            re_tel = re.match(self.PATTERN_TEMP_LOG, line)
            if not re_tel:
                continue
            ts, addr, mac, temp, humd, pres, rssi = re_tel.groups()
            date = dt.strptime(ts, self.DATE_FMT)

            if self.next_send_date is None:
                self.next_send_date = date + self.SEND_TIME_DELTA

            if date > self.next_send_date:
                self.next_send_date += self.SEND_TIME_DELTA
                self.send(date)
                self.data.clear()

            if mac not in self.data:
                self.data[mac] = {}
            self.data[mac].update({
                "mac_address": mac,
                "datetime": date.strftime("%d/%m/%Y %H:%M"),
                "temperature": int(temp),
                "humidity": int(humd),
                "pressure": int(pres),
                "rssi": - int(rssi),
            })

        self.send(date) # Send last values

    def send(self, date):
        if not self.data:
            print("No data")
            return

        body = {
            "device_id": self.device_id,
            "datetime": date.strftime("%d/%m/%Y %H:%M"),
            "data": list(self.data.values()),
        }
        url = f"{self.url}/{self.company}/data/push/"
        print("Sending {}, {} nodes".format(body["datetime"], len(self.data)))
        rsp = self.http.request("backend_tel", "POST", url, body)
        if rsp is None:
            print("No response")


def main():
    http_helper = HttpHelper(URL, USER, PASSWORD)
    app = ManualBackendApp(http_helper, FILENAME, URL, COMPANY, DEVICE_ID)
    app.run()
    print("Finished!")


if __name__ == "__main__":
    main()
