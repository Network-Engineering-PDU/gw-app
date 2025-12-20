# Multi-gateway feature

## Introduction

The multi-gateway functionality is an architecture that allows the coexistence of several gateways in the same TycheTools network, allowing that each node communicates with the most appropriate gateway.

This architecture arises from the need to extend the network in large rooms with a reliable communication, and to increase the network failure resistance.

The general communication diagram is shown below:

![General diagram](multi-gw-img/general_diagram.svg)

The general idea is that gateways belonging to a network are connected to each other in a client-server model, where the clients forward all traffic on the Bluetooth Mesh network to the server, and the server is responsible for managing the entire network.

## Roles

A gateway can have any of the following roles:

- **Server**: A gateway responsible of managing the network. Creates a TCP server and receives network packets from all client gateways.
- **Passthrough** (client): A gateway connected in passthrough mode that serves as a communication interface between the Bluetooth Mesh network and the server gateway. It connects to the TCP server and forwards all packets on the network.
- **Standalone**: Gateway independent of the multi-gateway architecture. Operates as a standard gateway.
- **Fault**: A gateway that uses consensous algorithms to choose between server, passthrough or standalone roles.

## Configuration

### Roles

Gateways belonging to a multi-gateway architecture must be configured according to their role within the network. The configuration is written in the `~/.tychetools/gw.config` file:

- `multi_gw_role`: Role within the network. Can be `server`, `passthrough`, `standalone` or `fault`.
- `host` (`multi_gw_server`): IP address of the socket server.
- `port` (`multi_gw_server`): TCP port of the socket server.

The following parameters need to be configured depending on the role:
- Server: `multi_gw_role` and `port`.
- Client (passthrough): `multi_gw_role`, `host` and `port`.
- Standalone: `multi_gw_role`.
- Fault: `multi_gw_role`.

Configuration can be edited manually or via Bluetooth using the [ble_config_server](https://bitbucket.org/tychetools/ble_config_server/src/master/) program.

### Security

Both the server and the client have a CA certificate, a certificate, and a key, which are used to establish secure communication using SSL/TLS. The path to the certificates and keys is specified in the `~/.tychetools/gw.config` file.

For the server:

- `ca_cert`: Path to the CA certificate.

- `server_cert`: Path to the server certificate.

- `server_ke`: Path to the server key.

For the client:

- `ca_cert`: Path to the CA certificate.

- `client_cert`: Path to the client certificate.

- `client_key`: Path to the client key.

## Usage

This feature includes the following `ttcli` commands:

- `gateway_manager init`: Starts the gateway manager. Depending on the role, creates a socket server or connects to a socket server. In `fault` mode, the initialization is managed by the fault manager, use `fault enable` instead.

- `gateway_manager list`: List gateways managed by the gateway manager.

- `gateway_manager status [--gateway]`: Returns the current gateway status, including version, address, number of nodes, and network status.

## Node and gateway communication

Each of the gateways belonging to the architecture maintains a list of the nodes in the network with which it can communicate. This list is called **whitelist** and is managed by the server gateway. If a gateway does not have a node in its whitelist, it will ignore all messages received by that node.

The assignment of nodes to the whitelist of each gateway is done dynamically based on events arriving from each gateway and its TTL and RSSI values.

The following diagram summarises the dynamic allocation of nodes for each gateway:

![Whitelists](multi-gw-img/node_gw_communication.svg)

### Node assignment

When an event is received from a node that is not assigned to any gateway, an assignment process is initiated for that node. During the allocation time, the events received by the different gateways of that node are stored:

![Node assignment](multi-gw-img/update_node.svg)

After the assignation time has elapsed, the gateway with the best coverage is selected and the node is added to its whitelist:

![Node assignment callback](multi-gw-img/update_node_cb.svg)

### Node reassignment

If messages from a node are not received by the gateway assigned to it, but are received by a gateway that is not assigned to it, a re-assignment process is started:

![Node re-assignment](multi-gw-img/reassign_node.svg)

If, after the re-assignment time, the gateway assigned to the sensor has not received the event from the node, the node is removed from the whitelist and the assignment process is repeated:

![Node re-assignment callback](multi-gw-img/reassign_node_cb.svg)
