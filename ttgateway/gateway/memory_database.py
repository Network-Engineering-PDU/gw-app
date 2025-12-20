from ttgwlib import NodeDatabase


class MemoryDatabase(NodeDatabase):
    def __init__(self):
        self.address = None
        self.netkey = None
        self.node_list = []

    def start(self):
        pass

    def stop(self):
        pass

    def set_address(self, address):
        self.address = address

    def set_netkey(self, netkey):
        self.netkey = netkey

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

    def remove_node(self, node):
        if node in self.node_list:
            self.node_list.remove(node)
