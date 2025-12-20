import os
import sqlite3
from datetime import datetime as dt

from ttgwlib import NodeDatabase
from ttgwlib.node import Node

from ttgateway.config import config


class SqliteDatabase(NodeDatabase):
    def __init__(self, database_file):
        self.database_file = database_file
        self.sql_conn = None
        self.address = None
        self.netkey = None
        self.node_list = []

    def start(self):
        self.sql_conn = sqlite3.connect(self.database_file,
            check_same_thread = False)
        assert self.is_threadsafe()
        try:
            self.load()
        except sqlite3.OperationalError:
            self.init_db()
            self.load()

    def stop(self):
        if self.sql_conn:
            self.sql_conn.close()

    def init_db(self):
        # Node table
        self.sql_conn.execute("""CREATE TABLE IF NOT EXISTS node (
            mac INTEGER PRIMARY KEY,
            uuid BLOB,
            address INTEGER UNIQUE,
            name TEXT,
            devkey BLOB,
            sleep_period INTEGER DEFAULT 0
        );""")

        # Netkey table
        try:
            self.sql_conn.execute("CREATE TABLE netkey (netkey BLOB);")
            self.sql_conn.execute("INSERT INTO netkey VALUES (?);",
                (os.urandom(16),))
        except sqlite3.OperationalError:
            pass
        # Unicast address table
        try:
            self.sql_conn.execute("CREATE TABLE address (address INTEGER);")
            self.sql_conn.execute("INSERT INTO address VALUES (?);", (1,))
        except sqlite3.OperationalError:
            pass
        self.sql_conn.commit()

    def is_threadsafe(self):
        query = ("select * from pragma_compile_options"
            + " where compile_options like 'THREADSAFE=%';")
        threadsafe, = self.sql_conn.execute(query).fetchone()
        if threadsafe[-1] == "1":
            return True
        return False

    def load(self):
        query = "SELECT address FROM address;"
        self.address, = self.sql_conn.execute(query).fetchone()
        query = "SELECT netkey FROM netkey;"
        self.netkey, = self.sql_conn.execute(query).fetchone()
        self.node_list = []
        for n in self.sql_conn.execute("SELECT * FROM node;"):
            node = Node(n[0].to_bytes(6, "big"), n[1], n[2], n[3], n[4])
            node.sleep_period = n[5]
            self.node_list.append(node)

    def store_node_db(self, node):
        v = (int.from_bytes(node.mac, "big"), node.uuid, node.unicast_addr,
            node.name, node.devkey, node.sleep_period)
        self.sql_conn.execute("REPLACE INTO node VALUES (?, ?, ?, ?, ?, ?);", v)
        self.sql_conn.commit()

    def remove_node_db(self, node):
        self.sql_conn.execute("DELETE FROM node WHERE mac = ?;",
            (int.from_bytes(node.mac, "big"),))

    def set_address(self, address):
        self.address = address
        rowid, = self.sql_conn.execute("SELECT rowid FROM address;").fetchone()
        self.sql_conn.execute("UPDATE address SET address = ? WHERE rowid = ?;",
            (self.address, rowid))
        self.sql_conn.commit()

    def set_netkey(self, netkey):
        self.netkey = netkey
        rowid, = self.sql_conn.execute("SELECT rowid FROM netkey;").fetchone()
        self.sql_conn.execute("UPDATE netkey SET netkey = ? WHERE rowid = ?;",
            (self.netkey, rowid))
        self.sql_conn.commit()

    def get_address(self):
        return self.address

    def get_netkey(self):
        return self.netkey

    def get_nodes(self):
        return self.node_list

    def get_node_by_address(self, address):
        for node in self.node_list:
            if node.unicast_addr == address:
                return node
        return None

    def get_node_by_mac(self, mac):
        for node in self.node_list:
            if node.mac == mac:
                return node
        return None

    def store_node(self, node):
        if node in self.node_list:
            self.node_list[self.node_list.index(node)] = node
        else:
            self.node_list.append(node)
        self.store_node_db(node)

    def remove_node(self, node):
        if node in self.node_list:
            self.node_list.remove(node)
            self.remove_node_db(node)

    def remove_nodes(self):
        self.node_list.clear()
        self.sql_conn.execute("DELETE FROM node")

    def backup(self):
        backups_dir = f"{config.TT_DIR}/.backups/database"
        os.makedirs(backups_dir, exist_ok=True)
        now = dt.now().strftime("%Y%m%d-%H%M%S")
        os.system(f"cp {config.TT_DIR}/mesh_nodes.db "
            + f"{backups_dir}/{now}_mesh_nodes.db")

    def erase(self):
        self.set_address(1)
        self.set_netkey(os.urandom(16))
        self.remove_nodes()
