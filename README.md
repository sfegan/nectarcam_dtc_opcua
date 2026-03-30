# L2 Trigger System OPC UA Server

This repository contains the OPC UA server and associated tools for the L2 Trigger System. The server provides a high-level interface for monitoring and controlling the L2 trigger hardware, including the L2CB controller board and multiple CTDB boards.

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris

## System Architecture

The project is structured into three main layers:

1.  **Low-Level HAL (`l2trig_low_level.py`)**: A `ctypes` wrapper for the C shared library (`libl2trig_hal.so`) that provides direct hardware access.
2.  **High-Level API (`l2trig_api.py`)**: An asynchronous Python API that provides business logic, error handling, and unit conversions.
3.  **OPC UA Server (`l2trig_asyncua_server.py`)**: An asynchronous OPC UA server built on the `asyncua` library.

## Requirements

### Software Requirements
- Python 3.9+
- GCC and Make (for building the HAL library)
- Python packages (install via `pip install -r requirements.txt`):
    - `asyncua`
    - `python-json-logger`
    - `pytest`, `pytest-asyncio` (for development/testing)

### Hardware Requirements
- L2 Trigger hardware (L2CB and CTDBs) or use the **DUMMY** mode for testing without hardware.

## Building the HAL Library

The server requires the `libl2trig_hal.so` library to be compiled.

### Standard Build (with Hardware)
```bash
make
sudo make install
```

### Dummy Build (for Testing/Development)
If you don't have the hardware, you can build with dummy implementations that simulate hardware behavior:
```bash
make dummy
# The library will be built in hal/libl2trig_hal.so
```
The dummy mode simulates currents (~300mA per enabled channel) and maintains internal state for power and trigger settings.

## Running the OPC UA Server

Start the server using:
```bash
python3 l2trig_asyncua_server.py [options]
```

### Command Line Options

| Option | Description | Default |
| :--- | :--- | :--- |
| `--opcua-endpoint` | Endpoint URL for the server | `opc.tcp://0.0.0.0:4840/l2trigger/` |
| `--opcua-root` | Root object path in the address space | `L2Trigger` |
| `--monitoring-path` | Name of the monitoring object | `Monitoring` |
| `--opcua-user` | Add a user in `USER:PASS` format | (Anonymous only) |
| `--poll-interval` | Polling interval in seconds (PLL controlled) | `1.0` |
| `--poll-ratio` | Ratio of high-frequency to full status reads | `10` |
| `--slots` | Comma-separated list of active slots | (All valid slots) |
| `--log-level` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

### Polling Mechanism
The server implements a **Phase-Locked Loop (PLL)** polling loop to maintain a constant update rate.
- **High-Frequency Data**: Currents and error states are read every cycle (`poll-interval`).
- **Low-Frequency Data**: Firmware versions, current limits, and trigger settings are read every `poll-ratio` cycles.
- **Immediate Update**: Calling any control method (e.g., `SetModulePower`) triggers an immediate full status read outside the normal schedule.

## OPC UA Address Space

### Monitoring Variables
Located under `<Root>.<MonitoringPath>/` (e.g., `L2Trigger.Monitoring/`):

| Node Name | Type | Description |
| :--- | :--- | :--- |
| `l2cb_firmware` | UInt16 | L2CB board firmware version |
| `l2cb_timestamp` | DateTime | L2CB hardware timestamp (converted to UTC) |
| `l2cb_timestamp_raw`| UInt64 | Raw L2CB hardware timestamp counter |
| `active_slots` | Int32[] | List of slots enabled in the server |
| `ctdb_firmware` | UInt16[] | Firmware versions for each active slot |
| `ctdb_current_ma` | Double[] | Current readings for each CTDB board |
| `ctdb_total_channel_current_ma` | Double[] | Sum of currents for all enabled channels per slot |
| `ctdb_limit_min_ma` | Double[] | Minimum current limit per slot |
| `ctdb_limit_max_ma` | Double[] | Maximum current limit per slot |
| `ctdb_has_errors` | Boolean[] | Error status flag per slot |
| `channel_enabled` | Boolean[] | Flattened array (slot_idx * 15 + ch-1) of power status |
| `channel_current_ma` | Double[] | Flattened array of channel currents |
| `channel_state` | String[] | Flattened array of channel states (on, off, error_over_current, etc.) |
| `trigger_masked` | Boolean[] | Flattened array of trigger mask status |
| `trigger_delay_ns` | Double[] | Flattened array of trigger delays (0-5 ns) |

### Control Methods
Located under the `<Root>/` object:

| Method Name | Arguments | Description |
| :--- | :--- | :--- |
| `EmergencyShutdown` | None | Immediately disables all power channels on all slots. |
| `SetAllPower` | `enabled: Boolean` | Enables or disables power for all modules. |
| `SetModulePower` | `module: Int32`, `enabled: Boolean` | Controls power for a specific module (1-270). |
| `SetBoardCurrentLimits`| `board: Int32`, `min_ma: Double`, `max_ma: Double` | Configure safety current limits for an entire CTDB board identified by its sequence index. |
| `SetModuleTriggerMask` | `module: Int32`, `masked: Boolean` | Sets trigger mask for a specific module. |
| `SetModuleTriggerDelay`| `module: Int32`, `delay_ns: Double` | Sets trigger delay (0-5 ns) for a specific module. |
| `SetAllTriggerMask`| `masked: Boolean` | Sets trigger mask for all modules. |
| `SetAllTriggerDelay`| `delay_ns: Double` | Sets trigger delay for all modules. |
| `HealthCheck` | None | Returns a summary string of system health. |

## Test Client

An interactive test client is provided to verify the server functionality.

### Running the Client
```bash
python3 l2trig_test_client.py --endpoint opc.tcp://localhost:4840/l2trigger/
```

### Interactive Commands
Once connected, you can use the following commands at the `l2trig>` prompt:
- `summary`: Displays a formatted table of all slots, channels, currents, and states.
- `list`: Lists all raw monitoring variables and their current values.
- `power <module> <on|off>`: Control power for a module (e.g., `power 5 on`).
- `mask <module> <on|off>`: Control trigger mask for a module.
- `delay <module> <ns>`: Set trigger delay in nanoseconds.
- `limits <board> <min> <max>`: Set current limits for a board (1-based index).
- `health`: Run the system health check.
- `shutdown`: Trigger emergency shutdown.
- `help`: Show all available commands.
- `exit`: Close the client.

## Development and Testing

### Running Tests
To run the automated test suite (requires `pytest` and `pytest-asyncio`):
```bash
python3 -m pytest test_l2trig_system.py
```
Note: Ensure you have built the HAL in **dummy** mode before running tests on a system without hardware.
