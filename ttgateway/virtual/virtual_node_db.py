import os
import json


class VirtualNodeDatabase:
    """
    :param database_file: Database file.
    :type  database_file: str
    :param virtual_manager: Virtual manager instance.
    :type  virtual_manager: VirtualManager
    """
    def __init__(self, database_file, virtual_manager):
        self.database_file = database_file
        self.virtual_manager = virtual_manager
        self.nodes = []

        if os.path.isfile(self.database_file):
            self._load_nodes()

    def _load_nodes(self):
        with open(self.database_file, 'r') as f:
            data = json.load(f)
        for json_node in data["nodes"]:
            virtual_node = self.virtual_manager.node_from_json(json_node)
            if virtual_node:
                self.nodes.append(virtual_node)

    def _write_nodes(self):
        data = {"nodes": [node.to_json() for node in self.nodes]}
        with open(self.database_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_nodes(self):
        return self.nodes

    def store_node(self, node):
        for n in self.nodes:
            if node.address == n.address:
                self.nodes[self.nodes.index(n)] = node
                break
        else:
            self.nodes.append(node)
        self._write_nodes()

    def remove_node(self, node):
        try:
            self.nodes.remove(node)
            self._write_nodes()
        except ValueError:
            pass
