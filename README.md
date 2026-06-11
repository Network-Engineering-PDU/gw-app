# ttgateway

Application to manage a Bluetooth Mesh network using python 3.

## Installation

The application is intended to be included as a package in a Linux distribution generated using Yocto. However, it can also be installed using pip. In the root directory of the project,
type the following command:

    pip install .

This will install the application and also the required dependencies.

## ttdaemon - TycheTools daemon
Gateway application daemon. This is the main gateway process. It receives and
processes any events sent by the gateway microcontroller. It is also in charge
of forwarding the telemetry and battery data from the sensors (through http,
snmp, etc...).

To interact with it, the daemon creates a server on an unix socket. This server
can receive a number of actions or commands, defined in *ttgateway/commands.py*.

It creates a directory, *~/.tychetools*, to store some files. The file
*gw.config* has some general configuration parameters. On startup, the daemon
executes the commands found in *gwrc* (see ttcli commands). On this directory
can also be found the *log* and *mesh_nodes.db* files.

```
$ ttdaemon start|stop|restart
```

## ttcli - TycheTools command line interface

Main interface to configure and control the gateway daemon. It starts a
command line interface implemented using the python library cmd2, which allows
the user to input commands. This commands are forwarded to the daemon through
a socket, and the cli prints on screen the response, if any.

```
$ ttcli
#gateway> example_command
example response
  ...
#gateway> quit
```

The commands can also be executed directly from the terminal.

```
$ ttcli example_command
example response
```

## ttcli_remote - TycheTools remote command line interface

Remote interface to configure and control gateways. It displays a list of connected gateways and allows to send commands in the same way *ttcli* does.

```
$ ttcli_remote
#gateway> example_command
example response
  ...
#gateway> quit
```


## ttlog - TycheTools log

Opens a real time log. To exit, press CTRL+C.

```
$ ttlog
```

## ttdiagnosis - TycheTools diagnosis

If run from a gateway, it runs a set of tests and returns a JSON with diagnostic information. If run from a non-gateway machine, it displays a list of connected gateways and allows to be perform a diagnostic on any of them.

```
$ ttdiagnosis
```

## ttwatchdog - TycheTools watchdog

Periodically checks gateway status and reboots the machine if the nRF52 connection is not alive:

```
$ ttwatchdog
```

## ttjson_to_sqlite - JSON to SQLite conversor

Converts a JSON file to SQLite. It can be useful to modify mesh databases:

```
$ ttjson_to_sqlite <JSON_FILE>
```

## ttsqlite_to_json - SQLite to JSON conversor

Converts a SQLite file to JSON. It can be useful to modify mesh databases:

```
$ ttsqlite_to_json <SQLITE_FILE>
```