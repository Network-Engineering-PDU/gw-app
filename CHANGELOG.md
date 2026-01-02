# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.14.3] - 2024-11-20
### Fixed
 - Backup error when corrupt backup file
 - Backup error when wrong file extension
 - Exception in command process propagates to server
 - Server tries to use disabled fault manager

### Changed
 - Update package versions for Kirkstone

## [1.14.2] - 2024-10-26
### Added
 - Hardware self-test in initialization process
 - Leader prompted in fault status command
 - Thread list CLI command

### Fixed
 - Datetime update in pwmt handler
 - Fault status cmd when not initialized
 - App manager race condition when pausing multiple times
 - Unknown node downloads node multiple times
 - Cli error when fault is disabled

### Changed
 - Improve config file creation

## [1.14.1]
### Fixed
 - Wait until process terminates before restarting

## [1.14.0]
### Added
 - Automation application
 - Automation commands
 - Consensus commands
 - Consensus log with node db, backups and node data
 - Network helper to update gateway network in backend
 - Decide fault manager strategy based on backend info
 - Node-Gateway coverage information
 - Node task queue that handles gateway assignation
 - Ntp chrony restart when not in sync
 - Virtual sensor backend_get path

### Changed
 - Move gateway cmds to gateway manager
 - Deprecate gateway init and restart cmds
 - Replace gw manager by fault initialization in gwrc
 - Remove fault strategy and cluster from config
 - Consensus module log to INFO
 - Use default config if params are not set

### Fixed
 - Handle unknown websocket command ID handle
 - Virtual sensor backend get handle
 - Pwmt backend task cancel when app stops
 - Influx pwmt data mask
 - Copy snmp config file to home
 - Stop asyncio tasks, threads and modules when exit
 - Random byte generation in simulator module

## [1.13.0] - 2023-12-20
### Added
 - Modular log level config command
 - Multi-gateway feature

### Fixed
 - Handle errors when downloading invalid nodes
 - Handle snmp errors
 - Handle close remote connection error
 - Multi-word remote_shell commands

### Changed
 - Gateway managed by gateway manager

## [1.12.1] - 2023-11-10
### Added
 - Schema ID backend dataframes for telemetry and power data
 - Dataframe documentation

### Fixed
 - Multiple tasks accesing backup files at same time
 - Node list not returning all nodes by default 

### Changed
 - Remove duplicate info in diagnosis
 - Use GPIO module instead of direct GPIO control
 - Check internet connection URL

## [1.12.0] - 2023-06-09
### Added
 - CLI command to change tasks without deleting them
 - Bi-directional ping
 - Ping cli command
 - Remote shell cli command
 - Node data module
 - Ntp sync before backup
 - Node summary command
 - Tasks, stats and pwmt data to node list
 - Linux shell over ttcli
 - Config node tasks using change opcode
 - Fw, lib & app version in gateway status
 - Mqtt & ne application
 - Modbus client
 - Modbus, backend and snmp virtual functions
 - Get backend nodes command
 - Diagnosis report script

### Changed
 - Use monotonic clk in stead of real clk for periodic actions
 - Backup manager checks if data is corrupt
 - TycheTools api url forwarded to single-database backend

## [1.11.0] - 2023-02-03
### Added
 - Listener mode enable/disable command
 - Virtual sensors
 - Output (relay & dac) cli commands
 - Sensor calibration cli commands
 - Sensor config (heater & repeatability) cli commands
 - Snmp client get and walk commands
 - Show log cli command
 - Http logging feature
 - Default gwrc
 - Automatically detect platform
 - Ota status
 - Node sqlite database
 - Node memory database
 - Simulator: Simulates iris sensors sending data

### Changed
 - Adapt power meter dataframes to new structure
 - SNMP: Now data is serve through a Unix socket

### Removed
 - Power meter alerts

## [1.10.0] - 2022-12-08
### Added
 - Backup module, stores http post backups in persistent storage
 - Save state command, for backend app
 - Add location CLI
 - Add delete & modify node task CLI commands
 - Clear Heimdall leds on start & exit
 - Influx app
 - Power meter nodes
 - SQLite node database
 - Configuration commands - for BLE configuration
 - Debug get\_element\_info command
 - Catch and recover from exceptions

### Fixed
 - Fix Exit callback not being executed on error
 - Send backend and air quality times as UTC
 - Fix sleep time error
 - Check node field on UNKNOWN\_NODE event

### Changed
 - Log cleaning and refactoring

## [1.9.1]
### Fixed
 - Led error on RPI reboot

## [1.9.0]
### Added
 - CSV file app
 - Remove failover module
 - Add set\_config\_level command
 - Add Heimdall led support
 - Add remote ws client and remote cli

## [1.8.2]
### Fixed
 - Fix dependencies

## [1.8.1]
### Added
 - Add C02_START opcode if sensor has co2

## [1.8.0]
### Added
 - This changelog

[Unreleased]: https://bitbucket.org/tychetools/gw-app/branches/compare/devel..master
[1.8.1]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.8.1..1.8.0
[1.8.2]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.8.2..1.8.1
[1.9.0]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.9.0..1.8.2
[1.9.1]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.9.1..1.9.0
[1.10.0]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.10.0..1.9.1
[1.11.0]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.11.0..1.10.0
[1.12.0]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.12.0..1.11.0
[1.12.1]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.12.1..1.12.0
[1.13.0]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.13.0..1.12.1
[1.14.0]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.14.0..1.13.0
[1.14.1]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.14.1..1.14.0
[1.14.2]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.14.2..1.14.1
[1.14.3]: https://bitbucket.org/tychetools/gw-app/branches/compare/1.14.3..1.14.2
