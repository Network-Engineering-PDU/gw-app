import socket
import json
import struct

from ttgateway.config import Config


def send_json(cmd):
    s = socket.socket(socket.AF_UNIX)
    s.connect(Config.SERVER_SOCKET)
    cmd_bytes = json.dumps(cmd).encode()
    s.sendall(struct.pack("<I", len(cmd_bytes)) + cmd_bytes)

    raw_data = s.recv(1024)
    data_length = int.from_bytes(raw_data[0:4], "little")
    data = bytearray()
    data += raw_data[4:]
    while len(data) < data_length:
        raw_data = s.recv(1024)
        data += raw_data

    rsp = json.loads(data.decode())
    print(json.dumps(rsp, indent=2))
