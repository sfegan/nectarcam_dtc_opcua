# L2 Trigger System OPC UA Server

OPC UA server for the NectarCAM L2 Trigger System, providing standardized remote access to the L2CB controller board and CTDB trigger modules.

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>  
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris

---

## Overview

The L2 Trigger System manages 270 trigger modules across 18 crate slots (15 channels per slot). The system uses a split architecture:

1.  **Backend Server (`l2tcp_server`):** A lightweight C-based server running directly on the ARM-based controller board. It manages the low-level SPI hardware interface, implements power ramping, and provides a binary TCP messaging interface for remote control.
2.  **OPC UA Bridge (`l2trig_asyncua_bridge.py`):** A Python-based server that runs on a control PC. It connects to the backend server over TCP and exposes the system state and control methods via the OPC UA protocol.
3.  **Direct Client (`l2trig_direct_client`):** A native C command-line tool for the ARM board, used for low-level pre-configuration and diagnostics.
4.  **GUI (`l2tring_gui.py`):** A GUI test application for monitoring and controlling the system via OPC UA.

---

## Deployment and Setup

### 1. Obtain ARM Binaries
For the embedded ARM-based controller board, you can download pre-compiled static binaries from the [**GitHub Releases**](https://github.com/sfegan/nectarcam_dtc_opcua/releases) page. Alternatively you can cross-compile from source using the toolchain provided in the `toolchain` directory (only on Linux). The repository contains two applications that can run on the ARM board:
*   `l2tcp_server`: The backend TCP bridge, should be run from a terminal or from `systemd` after boot.
*   `l2trig_direct_client`: The configuration application, can be used interactively or with scripts to pre-configure the system before starting the backend server.

To download the latest release with `wget`:
```bash
wget https://github.com/sfegan/nectarcam_dtc_opcua/releases/download/latest/l2tcp_server
wget https://github.com/sfegan/nectarcam_dtc_opcua/releases/download/latest/l2trig_direct_client
```

### 2. Install Python Bridge (Control PC)
On your control workstation, install the required Python dependencies:
```bash
pip install -r requirements.txt
```

### 3. Start the Backend Server (ARM Board)
Transfer the `l2tcp_server` binary to the ARM board (via `scp`) and run it:
```bash
./l2tcp_server -p 4242 -v
```

**Available Options:**
- `-p <port>` — TCP listening port (default: 4242)
- `-d <ms>` — Power ramp delay in milliseconds between channels (default: 100ms)
- `-s <device>` — SMC device path (if not using default)
- `-v` — Verbose logging (repeat for more verbosity)
- `-c <ms>` — Client inactivity timeout in milliseconds (default: 60000ms)
- `-r <ms>` — Socket receive timeout in milliseconds (default: 1000ms)

### 4. Start the OPC UA Bridge (Control PC)
```bash
python3 l2trig_asyncua_bridge.py --device-host <ARM_BOARD_IP>
```
The bridge will connect to the ARM board and start an OPC UA server on `opc.tcp://0.0.0.0:4840/l2trig/`.

**Note:** By default, channels S21C11-S21C15 are marked as immutable (the server will not modify their state). This can be changed with the `--immutable-channels` option.

### 5. Use the GUI or OPC UA Client if desired
```bash
python3 l2tring_gui.py --server opc.tcp://<CONTROL_PC_IP>:4840/l2trig/
```

---

## Pre-Configuring Hardware

The **Direct Client** (`l2trig_direct_client`) provides native access to the hardware on the ARM board. Use it **before** starting the backend server.

| Command | Description |
| :--- | :--- |
| `l2cb_fw` | Get L2CB firmware revision |
| `mcf <on\|off>` | Enable/Disable MCF propagation |
| `mcfthr [val]` | Get/Set MCF threshold (L1 counts) |
| `mcfdel [val]` | Get/Set MCF delay (5ns steps, 0-15) |
| `deadtime [val]` | Get/Set L1 deadtime (5ns steps, 0-255) |
| `trigmask <slot> [m]` | Get/Set trigger mask (16-bit hex) |
| `trig <slot> <ch> [o]`| Get/Set trigger for specific channel |
| `alltrig <on\|off>` | Enable/Disable all trigger channels |
| `powermask <slot> [m]`| Get/Set power mask (16-bit hex) |
| `allpower <on\|off>` | Set power for all channels |

The client can be used interactively, allowing commands to be typed from the terminal, or via a script to allow commands to be piped or read from a file. For example, the following will pre-configure the system parameters for the muon candidate flag and disable the trigger from the unused channels in slot 21:

```bash
l2trig_direct_client << 'EOF'
allpower off    # Should presumably be the default on DTC start-up
mcf on          # Enable the muon candidate flag
mcfthr 20       # Set the muon threshold to 20 modules
mcfdel 15       # Set the muon delay to 75 ns (15 × 5ns = 75ns)
trig 21 11 off  # Disable trigger on Slot 21 Channel 11
trig 21 12 off  # Alternatively, disable all five channels with: 
trig 21 13 off  # trigmask 21 0x07FE
trig 21 14 off
trig 21 15 off
EOF
```
---

## OPC UA Interface Reference

### Status Variables (`Monitoring/`)

All monitoring data is accessible under `L2Trigger.Monitoring`:

**Bridge and Connection Status (Scalars):**
- `device_host` (`String`) — Host or IP of the TCP bridge server
- `device_port` (`UInt16`) — Port of the TCP bridge server
- `device_state` (`Int32`) — Device state: 0 if TCP connection down, 1 if TCP connected but no modules powered, 2 if TCP connected and at least one module is powered
- `device_connected` (`Boolean`) — TCP connection state (True if connected)
- `device_connection_uptime` (`Double`) — Time in ms the TCP connection has been up
- `device_connection_downtime` (`Double`) — Time in ms the TCP connection has been down
- `device_polling_interval` (`Double`) — Polling interval in milliseconds

**L2CB Controller Status (Scalars):**
- `CrateFirmwareRevision` (`UInt16`) — Firmware version
- `CrateUpTime` (`UInt64`) — Time since boot (nanoseconds)
- `CrateNumMutableModules` (`UInt16`) — Total actively controlled modules
- `CrateNumPoweredModules` (`UInt16`) — Modules currently powered
- `CrateNumTriggerEnabledModules` (`UInt16`) — Modules with trigger enabled

**L2CB Trigger Configuration (Scalars):**
- `CrateMCFEnabled` (`Boolean`) — MCF propagation state
- `CrateBusyGlitchFilterEnabled` (`Boolean`) — Glitch filter state
- `CrateTIBTriggerBusyBlockEnabled` (`Boolean`) — TIB blocking state
- `CrateMCFThreshold` (`UInt16`) — MCF threshold (0-512 channels)
- `CrateMCFDelay` (`Double`) — MCF delay in ns (0-75ns in 5ns steps)
- `CrateL1Deadtime` (`Double`) — L1 deadtime in ns (0-1275ns in 5ns steps)

**Per-Slot Board Data (Arrays; one element per configured slot):**
- `BoardSlotId` (`UInt16[]`) — List of active slot numbers
- `BoardFirmwareRevision` (`UInt16[]`) — Firmware per CTDB board
- `BoardCurrent` (`Double[]`) — Total current per CTDB board (mA in 0.485mA steps)
- `BoardCurrentSum` (`Double[]`) — Sum of all enabled channels per CTDB board (mA in 0.485mA steps)
- `BoardCurrentLimitMin/Max` (`Double[]`) — Current safety limits per CTDB board (mA in 0.485mA steps)
- `BoardHasErrors` (`Boolean[]`) — Error flag per CTDB board

**Per-Module Data (Arrays; one element per configured channel):**
- `ModulePowerEnabled` (`Boolean[]`) — Power state (1=on/0=off)
- `ModuleCurrent` (`Double[]`) — Current reading (mA in 0.485mA steps)
- `ModuleState` (`String[]`) — Detailed state (on/off/error_over_current/error_under_current/error_both/offline)
- `ModuleTriggerEnabled` (`Boolean[]`) — Trigger state (1=enabled/0=disabled)
- `ModuleTriggerDelay` (`Double[]`) — Trigger delay in ns (0-4.7ns in 37ps steps)
- `ModuleIsMutable` (`Boolean[]`) — Whether server controls this module
- `ModuleSlotId` (`UInt16[]`) — Crate slot ID for this module
- `ModuleChannelId` (`UInt16[]`) — Crate channel ID for this module

**Module Numbering:**
Modules are numbered consecutively starting from 1, ordered by slot and channel. For example, with all slots enabled:
- Modules 1-15: Slot 1, Channels 1-15
- Modules 16-30: Slot 2, Channels 1-15
- ...
- Modules 256-270: Slot 21, Channels 1-15

If only specific slots are enabled (via `--slots`), module numbers are renumbered consecutively across only those slots. The variables `ModuleSlotId` and `ModuleChannelId` can be used to map module indices to their physical slot and channel.

### Control Methods

Methods return a string prefixed with **`OK:`** or **`ERROR:`**. Boards are indexed by slot number (1-9, 13-21); modules are indexed 1-270 (or 1-N if fewer slots are enabled).

| Method | Parameters | Description |
| :--- | :--- | :--- |
| `EmergencyShutdown` | None | Immediately disable all power |
| `SetAllPowerEnabled` | `enabled: Boolean` | Ramp all modules on/off |
| `SetModulePowerEnabled` | `module: Int32, enabled: Boolean` | Control single module power |
| `SetSlotChannelPowerEnabled` | `slot: Int16, channel: Int16, enabled: Boolean` | Control single module power by slot and channel |
| `SetBoardCurrentLimits` | `board: Int32, min_ma: Double, max_ma: Double` | Configure board current limits (0-1986mA in 0.485mA steps) |
| `SetSlotCurrentLimits` | `slot: Int16, min_ma: Double, max_ma: Double` | Configure board current limits by slot ID (0-1986mA in 0.485mA steps) |
| `SetAllTriggerEnabled` | `enabled: Boolean` | Enable/Disable triggers from all modules |
| `SetModuleTriggerEnabled`| `module: Int32, enabled: Boolean`| Enable/Disable trigger from specific module |
| `SetSlotChannelTriggerEnabled`| `slot: Int16, channel: Int16, enabled: Boolean`| Enable/Disable trigger from specific module by slot and channel |
| `SetAllTriggerDelay` | `delay_ns: Double` | Set uniform trigger delay for all modules (0-4.7ns in 37ps steps) |
| `SetModuleTriggerDelay` | `module: Int32, ns: Double` | Set trigger delay for specific module (0-4.7ns in 37ps steps) |
| `SetSlotChannelTriggerDelay` | `slot: Int16, channel: Int16, ns: Double` | Set trigger delay for specific module by slot and channel (0-4.7ns in 37ps steps) |
| `SetMCFEnabled` | `enabled: Boolean` | Enable muon candidate flag propagation to TIB |
| `SetMCFDelay` | `delay: Double` | Set MCF delay in ns (0-75ns in 5ns steps) |
| `SetMCFThreshold` | `threshold: Int16` | Set MCF threshold in modules (0-512) |
| `SetBusyGlitchFilterEnabled`| `enabled: Boolean` | Enable/Disable busy glitch filter |
| `SetTIBTriggerBusyBlockEnabled`| `enabled: Boolean` | Enable/Disable TIB trigger blocking |
| `SetL1Deadtime` | `deadtime: Double` | Set L1 deadtime in ns (0-1275ns in 5ns steps) |
| `SetModuleIsImmutable` | `module: Int32, immutable: Boolean` | Set whether a module is immutable (protected from changes) |
| `SetSlotChannelIsImmutable` | `slot: Int16, channel: Int16, immutable: Boolean` | Set whether a module is immutable by slot and channel |

---

## Testing Applications

Four test applications are included in the repository for different use cases. Three of them are implemented in Python and run on the control PC, while the `l2trig_direct_client` is a native C application that runs on the ARM board for direct hardware access. Of the three Python applications, two are OPC UA clients that connect to the `l2trig_asyncua_bridge.py` server, while the third is a TCP client that connects directly to the `l2tcp_server` backend for low-level testing.

- `l2tring_gui.py`: A GUI application for monitoring and controlling the system via OPC UA. It provides real-time status updates and interactive controls for power and trigger settings.
- `l2trig_test_opcua_cli.py`: An interactive command-line client for testing and debugging the OPC UA interface. It allows users to read monitoring variables and call control methods directly from the terminal, making it useful for quick tests and automation scripts.
- `l2trig_test_tcp_client.py`: A simple TCP client for testing the backend server's binary protocol. It can be used to send raw commands and receive responses, bypassing the OPC UA layer for low-level diagnostics.
- `l2trig_direct_client`: A command-line tool that runs on the ARM board, allowing direct access to the hardware for pre-configuration and diagnostics. It supports commands for reading firmware versions, configuring power and trigger settings, and more.

---

## System Architecture

### Active slots vs immutable channels
The backend server can be configured to manage a subset of the total 18 available slots using the `--slots` option of `l2trig_asyncua_bridge` (see below). Only channels in these active slots will be monitored and controlled by the server. This allows for scenarios where not all slots are populated or where CTDB slots are malfunctioning and should be ignored. In this case the backend server will never attempt communication with inactive slots. Active slots can only be changed by restarting the OPCUA server with a different `--slots` configuration. Thie list of active slots is communicated to the backend server at startup of the OPCUA server - the backend server itself does not need to be restarted when the active slots are changed. The variables `BoardSlotId` and `ModuleSlotId` can be used to map the module indices to their physical slot numbers.

Immutable channels are a separate concept that applies to individual channels within the active slots. An immutable channel is one that the backend server will never attempt to change the power or trigger state of. This allows users to protect specific channels from being powered on or off by the server, which can be useful for known faulty modules or for safety reasons. By default, channels S21C11-S21C15 are marked as immutable, since they are not connected to FEB modules by default, but this can be customized with the `--immutable-channels` option. The list of immutable channels can be modified on the fly by calling the `SetModuleIsImmutable` or `SetSlotChannelIsImmutable` methods via OPCUA, which can be used to add or remove immutability from specific channels without restarting the server OPCUA or backend server. The OPCUA server maintains the list of immutable channels in memory and communicates it to the backend server, enforcing it when processing power and trigger control requests (and in particular, when processing the `SetAllPowerEnabled` request).

### Safe Power Ramping
The backend server implements a **round-robin sequence** to prevent excessive inrush currents. When `SetAllPowerEnabled(true)` is called:
1.  The server automatically recovers any channels in an under/over current error state by un-powering them before proceeding.
2.  The first module in each CTDB board is powered up (S1C1, S2C1, S9C1, S13C1... S21C1).
3.  A configurable delay (default 100ms) is introduced to allow inrush currents to stabilize.
4.  The sequence moves to the next module attached to each CTDB board (S1C2, ... S21C2) and these two steps repeat until all modules are powered.
5.  The power state of any immutable channels is never changed by the server.

### Recovery from Under/Overcurrent Errors
If a module is in an under/over current error state, the backend server **automatically clears this error** when the channel is commanded to power on, either using `SetModulePowerEnabled(True)` or during the `SetAllPowerEnabled(True)` ramp sequence. Any such channel is turned off before attempting to power it on again. 

The user does not need to manually clear errors by calling `SetModulePowerEnabled(False)` explicitly before calling `SetModulePowerEnabled(True)`.

If a module is consistently tripped due to a hardware fault, the server will log this and continue to attempt to power it on during each ramp sequence. The user can choose to disable the channel permanently by marking it as immutable (e.g., `--immutable-channels S1C5,S2C3`), which will prevent the server from attempting to change its state.

### Bridge Configuration
The `l2trig_asyncua_bridge.py` supports several advanced options:
- `--device-host`: Host or IP address of the backend TCP server (default: 127.0.0.1)
- `--device-port`: TCP port of the backend server (default: 4242)
- `--device-timeout`: TCP connection and receive timeout in seconds (default: 5.0)
- `--poll-interval`: Frequency of fast updates in seconds for currents and errors (default: 1.0)
- `--poll-ratio`: Ratio of fast to slow polling cycles for firmware and configuration (default: 10, meaning slow poll every 10 fast polls)
- `--slots`: Comma-separated list of slots to enable (e.g., `--slots 1,2,3,13,14`); if omitted, all valid slots (1-9, 13-21) are enabled
- `--immutable-channels`: Comma-separated list of channels the server should not modify (default: `S21C11,S21C12,S21C13,S21C14,S21C15`). Format: `S<slot>C<channel>` (e.g., `S1C1,S18C15`)
- `--opcua-endpoint`: OPC UA server endpoint URL (default: `opc.tcp://0.0.0.0:4840/l2trig/`)
- `--opcua-user`: Username:password for authentication (format: `user:pass`); disables anonymous access
- `--reconnection-backoff-interval`: Maximum delay between reconnection attempts in seconds (default: 30.0)
- `--log-level`: Logging verbosity (DEBUG, INFO, WARNING, ERROR; default: INFO)
- `--log-file`: Optional path to write logs to file

---

## Cross-compilation of Backend Server Using Supplied Toolchain
The `toolchain` directory contains a Docker-based cross-compilation environment for building the ARM binaries on Linux. It uses the `arm-none-eabi` toolchain. To build the binaries (as implemented in the GitHub actions workflow included here), run the following command from the repository root:

```bash
tar -xzf toolchain/crosstoll-ng-1.2.00-arm-926ejs-linux-gnueabi.tar.gz -C toolchain
PATH=$PWD/toolchain/arm-926ejs-linux-gnueabi/bin:$PATH
cd l2tcp_server
arm-926ejs-linux-gnueabi-gcc -std=gnu99 -march=armv5te -I../hal -static -o l2tcp_server l2tcp_server_main.c ../hal/smc.c ../hal/l2trig_hal.c
```

## Note to self

- Push changes to CTA GitLab: `git push cta_gitlab main`
- Generate new release on GitHub: `git tag v1.0.6` and `git push origin v1.0.6`
