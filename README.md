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
| `--power-ramp-delay-ms` | Delay between enabling power channels during ramp (milliseconds) | `10` |
| `--slots` | Comma-separated list of active slots | (All valid slots) |
| `--log-level` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

### Polling Mechanism
The server implements a **Phase-Locked Loop (PLL)** polling loop to maintain a constant update rate.
- **High-Frequency Data**: Currents, error states, and L2CB status are read every cycle (`poll-interval`).
- **Low-Frequency Data**: Firmware versions, current limits, and trigger settings are read every `poll-ratio` cycles.
- **Immediate Update**: Calling any control method (e.g., `SetModulePower`) triggers an immediate full status read outside the normal schedule.
- **Watchdog Timer**: The server logs a system status summary (number of active boards, powered modules, and enabled trigger modules) at the `INFO` level every 180 seconds.

### Power Ramping

When `SetAllPower(true)` is called to enable power on all modules, the server performs a **controlled power ramp** rather than instantly enabling all channels. This prevents power supply inrush and helps reduce electrical stress on the hardware.

**Ramping Mechanism:**
- Modules are enabled sequentially, one at a time, across all active slots.
- The delay between enabling consecutive modules is controlled by the `--power-ramp-delay-ms` command line parameter (default: 10 ms).
- A ramping task runs in the background, tracking which modules have been enabled and waiting the specified delay before moving to the next module.
- If power is ramping and `SetAllPower(false)` is called, the ramping is cancelled immediately and all modules are disabled.
- If a new power command is issued while ramping is in progress, the previous ramp is cancelled and the new command starts immediately.

**Example:**
To ramp power with 5ms delay between modules:
```bash
python3 l2trig_asyncua_server.py --power-ramp-delay-ms 5
```

## OPC UA Address Space

### Monitoring Variables
Located under `<Root>.<MonitoringPath>` (e.g., `L2Trigger.Monitoring`). All monitoring variables have their `MinimumSamplingInterval` attribute set to match the server's polling frequency (fast or slow) for efficient client subscriptions.

| Node Name | Type | Polling | Description |
| :--- | :--- | :--- | :--- |
| `CrateFirmwareRevision` | UInt16 | Fast | L2CB board firmware version |
| `CrateUpTime` | UInt64 | Fast | L2CB uptime in nanoseconds |
| `CrateMCFEnabled` | Boolean | Fast | L2CB MCF enabled status |
| `CrateBusyGlitchFilterEnabled` | Boolean | Fast | L2CB busy glitch filter enabled |
| `CrateTIBTriggerBusyBlockEnabled` | Boolean | Fast | L2CB TIB trigger blocking enabled |
| `CrateMCFThreshold` | Int16 | Fast | L2CB MCF threshold (0-512) |
| `CrateMCFDelay` | Double | Fast | L2CB MCF delay in ns (0-75 ns) |
| `CrateL1Deadtime` | Double | Fast | L2CB L1 deadtime in ns (0-1275 ns) |
| `CrateNumPoweredModules` | UInt16 | Fast | Total number of modules currently in 'on' state (enabled and no errors) |
| `CrateNumTriggerEnabledModules` | UInt16 | Slow | Total number of modules with trigger enabled |
| `BoardSlots` | Int32[] | Constant | List of crate slots enabled in the server |
| `BoardFirmwareRevision` | UInt16[] | Slow | Firmware versions for each active slot |
| `BoardCurrent` | Double[] | Fast | Current readings for each CTDB board |
| `BoardCurrentSum` | Double[] | Fast | Sum of currents for all enabled channels per slot |
| `BoardCurrentLimitMin` | Double[] | Slow | Minimum current limit per slot |
| `BoardCurrentLimitMax` | Double[] | Slow | Maximum current limit per slot |
| `BoardHasErrors` | Boolean[] | Fast | Error status flag per slot |
| `ModulePowerEnabled` | Boolean[] | Fast | Flattened array of power status |
| `ModuleCurrent` | Double[] | Fast | Flattened array of channel currents |
| `ModuleState` | String[] | Fast | Flattened array of channel states (on, off, error, etc.) |
| `ModuleTriggerEnabled` | Boolean[] | Slow | Flattened array of trigger enabled status |
| `ModuleTriggerDelay` | Double[] | Slow | Flattened array of trigger delays (0-5 ns) |

### Control Methods
Located under the `<Root>` object:

| Method Name | Arguments | Description |
| :--- | :--- | :--- |
| `EmergencyShutdown` | None | Immediately disables all power channels on all slots. |
| `SetAllPower` | `enabled: Boolean` | Enables or disables power for all modules. |
| `SetModulePower` | `module: Int32`, `enabled: Boolean` | Controls power for a specific module (1-270). |
| `SetBoardCurrentLimits`| `board: Int32`, `min_ma: Double`, `max_ma: Double` | Configure safety current limits for an entire CTDB board. |
| `SetModuleTriggerEnabled` | `module: Int32`, `enabled: Boolean` | Enables or disables trigger for a specific module. |
| `SetModuleTriggerDelay`| `module: Int32`, `delay_ns: Double` | Sets trigger delay (0-5 ns) for a specific module. |
| `SetAllTriggerEnabled`| `enabled: Boolean` | Enables or disables all triggers. |
| `SetAllTriggerDelay`| `delay_ns: Double` | Sets trigger delay for all modules. |
| `HealthCheck` | None | Returns a summary string of system health. |
| `SetMCFEnabled` | `enabled: Boolean` | Enable or disable MCF trigger propagation. |
| `SetBusyGlitchFilterEnabled` | `enabled: Boolean` | Enable or disable busy glitch filter. |
| `SetTIBTriggerBusyBlockEnabled` | `enabled: Boolean` | Enable or disable TIB trigger blocking. |
| `SetMCFDelay` | `delay: Double` | Set MCF delay (0-75 ns). |
| `SetMCFThreshold` | `threshold: Int16` | Set MCF threshold (0-512). |
| `SetL1Deadtime` | `deadtime: Double` | Set L1 deadtime (0-1275 ns). |

### Power Ramping

When `SetAllPower(true/false)` is called to enable power on all modules, the server performs a **controlled power ramp** rather than instantly enabling/disabling all channels. This prevents power supply inrush and helps reduce electrical stress on the hardware.

**Ramping Mechanism:**
- Modules are enabled sequentially in a round-robin pattern across all active slots: for each channel level, the server enables one module per slot before moving to the next channel. Concretely, the 270 modules are enabled in this order: S1C1, S2C1, S3C1, ..., S18C1, S1C2, S2C2, ..., S18C2, ..., S18C1, ..., S18C15.
- The delay between enabling each module is controlled by the `--power-ramp-delay-ms` command line parameter (default: 10 ms).
- A ramping task runs in the background, tracking which modules have been enabled and waiting the specified delay before moving to the next module.
- If a new power command is issued while ramping is in progress, the ramp is cancelled and the new command starts immediately; this could be an emergency shutdown (`EmergencyShutdown`), another ramping command (`SetAllPower`), or a command to change the power status of an individual module (`SetModulePower`).

**Example:**
To ramp power with 20ms delay between modules (5.4s to power all 270 modules):
```bash
python3 l2trig_asyncua_server.py --power-ramp-delay-ms 20
```

## GUI (Graphical User Interface)

A Tkinter-based graphical user interface is provided for interactive control and monitoring of the L2 Trigger system.

### Running the GUI
```bash
python3 l2trig_gui.py
```

### GUI Layout
The interface is divided into two main regions:

**Left Column (75%):** Module Matrix Display
- Displays all 18 slots (or enabled slots) as vertical columns, each containing 15 channel indicators.
- Each indicator is a colored square showing the status of a single module (slot + channel).
- The color and text change based on the selected display mode.
- Clicking on a module indicator allows interaction (toggle power or trigger, or set trigger delay depending on the mode).

**Right Column (300px wide):** Control Panels and Status
- **Top Area (60%):** Subdivided into two sections:
  - **Status Panel**: Displays L2CB firmware version, uptime, powered module count, and trigger-enabled module count. Also shows per-slot board status (current readings and error flags).
  - **Control Panel**: Three main sections:
    - **Crate Controls**: Checkboxes and input fields for MCF settings, busy glitch filter, TIB trigger blocking, MCF threshold, MCF delay, and L1 deadtime.
    - **Power Control**: Buttons for ramping up/down all power and emergency stop (red button).
    - **Trigger Control**: Buttons to enable or disable all triggers at once.
- **Bottom Area (40%):** System Log displaying all commands sent and responses received from the server.

### Display Modes
The display mode dropdown at the top allows switching between different visualization modes for the module matrix:

| Mode | Display | Color Code | Interaction |
| :--- | :--- | :--- | :--- |
| **Power Status** | Shows module on/off/error state | Green=ON, Red=ERROR, Gray=OFF | Click to toggle power |
| **Current (mA)** | Shows channel current readings | Blue→Green→Yellow→Red (0→200mA) | Click to toggle power |
| **Trigger Enabled** | Shows trigger enabled/disabled state | Blue=ENABLED, Gray=DISABLED | Click to toggle trigger |
| **Trigger Delay (ns)** | Shows trigger delay value (0-5ns) | Blue→Red gradient | Click to set custom delay (dialog) |
| **Module State** | Shows detailed state string | Color coded by state | Click indicator (no state change) |

### Connection
1. At the top of the window, enter the OPC UA server endpoint (default: `opc.tcp://localhost:4840/l2trigger/`).
2. Click **Connect** to establish connection to the server.
3. The status indicator shows "Connected" in green when successful, or an error message if connection fails.
4. Click **Disconnect** to cleanly close the connection when done.

### Key Features
- **Real-time Updates**: All display values are updated in real-time as data arrives from the server.
- **Subscriptions**: The GUI subscribes to all monitoring variables for efficient real-time notifications.
- **Module Interactions**: Clicking on individual module indicators allows quick control (power toggle, trigger toggle, or delay adjustment).
- **Log Display**: All actions and server responses are logged in the system log for debugging and audit purposes.
- **Responsive Layout**: The interface automatically resizes and fills available space.



An interactive test client is provided to verify the server functionality.

### Running the Client
```bash
python3 l2trig_test_client.py --endpoint opc.tcp://localhost:4840/l2trigger/
```

### Interactive Commands
Once connected, you can use the following commands at the `l2trig>` prompt:

**Inquiry:**
- `summary`: Displays a formatted status summary (including L2CB and all slots).
- `list`: Lists all raw monitoring variables and their current values.
- `read <var>`: Read a specific variable by name.
- `methods`: List all available methods on the server.
- `subscribe <var|all>`: Subscribe to real-time change notifications for variables.
- `unsubscribe <var|all>`: Stop receiving notifications.

**Control:**
- `power <module> <on|off>`: Control power for a module (1-270).
- `allpower <on|off>`: Control power for all modules.
- `trig <module> <on|off>`: Enable or disable trigger for a module.
- `delay <module> <ns>`: Set trigger delay (0-5 ns) for a module.
- `alltrig <on|off>`: Enable or disable all triggers.
- `alldelay <ns>`: Set trigger delay for all modules.
- `limits <board> <min> <max>`: Set current limits for a board (1-based index).
- `mcf <on|off>`, `glitch <on|off>`, `tibblock <on|off>`: Control L2CB features.
- `mcfdelay <ns>`, `mcfthreshold <val>`, `deadtime <ns>`: Configure L2CB timing/trigger.
- `health`: Run the system health check.
- `shutdown`: Trigger emergency shutdown.
- `call <name> [args]`: Manually call any server method.

**General:**
- `reconnect`: Force a reconnection to the server (preserves subscriptions).
- `cls`: Clear the terminal screen.
- `help` / `?`: Show help information.
- `exit` / `quit` (or `Ctrl-D`): Close the client.

## Development and Testing

### Running Tests
To run the automated test suite (requires `pytest` and `pytest-asyncio`):
```bash
python3 -m pytest test_l2trig_system.py
```
Note: Ensure you have built the HAL in **dummy** mode before running tests on a system without hardware.
