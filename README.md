# L2 Trigger System OPC UA Server

OPC UA server for the NectarCAM L2 Trigger System, providing standardized remote access to the L2CB controller board and CTDB trigger modules.

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>  
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris

---

## Overview

The L2 Trigger System manages 270 trigger modules across 18 crate slots (15 channels per slot). To ensure stability and security on the embedded hardware, the system uses a split architecture:

1.  **Backend Server (`l2tcp_server`):** A lightweight C-based server running directly on the ARM-based controller board. It manages the low-level SPI hardware interface, implements safety-critical power ramping, and provides a TCP bridge for remote control.
2.  **OPC UA Bridge (`l2trig_asyncua_bridge.py`):** A Python-based server that runs on a control PC. It connects to the backend server over TCP and exposes the system state and control methods via the OPC UA protocol.
3.  **Direct Client (`l2trig_direct_client`):** A native C command-line tool for the ARM board, used for low-level pre-configuration and diagnostics.

---

## Deployment and Setup

### 1. Obtain ARM Binaries
For the embedded ARM-based controller board, you can download pre-compiled static binaries from the **GitHub Releases** page.
*   `l2tcp_server`: The backend TCP bridge.
*   `l2trig_direct_client`: The configuration CLI.

### 2. Install Python Bridge (Control PC)
On your control workstation, install the required Python dependencies:
```bash
pip install -r requirements.txt
```

### 3. Start the Backend Server (ARM Board)
Transfer the `l2tcp_server` binary to the ARM board and run it:
```bash
./l2tcp_server -p 4242 -v
```

### 4. Start the OPC UA Bridge (Control PC)
```bash
python3 l2trig_asyncua_bridge.py --device-host <ARM_BOARD_IP>
```
The bridge will connect to the ARM board and start an OPC UA server on `opc.tcp://0.0.0.0:4840/l2trig/`.

---

## Pre-Configuring Hardware

The **Direct Client** (`l2trig_direct_client`) provides native access to the hardware on the ARM board. Use it **before** starting the backend server.

| Command | Description |
| :--- | :--- |
| `l2cb_fw` | Get L2CB firmware revision |
| `mcf <on\|off>` | Enable/Disable MCF propagation |
| `mcfthr [val]` | Get/Set MCF threshold (L1 counts) |
| `deadtime [val]` | Get/Set L1 deadtime (5ns steps) |
| `trigmask <slot> [m]` | Get/Set trigger mask (16-bit hex) |
| `trig <slot> <ch> [o]`| Get/Set trigger for specific channel |
| `alltrig <on\|off>` | Enable/Disable all trigger channels |
| `powermask <slot> [m]`| Get/Set power mask (16-bit hex) |
| `allpower <on\|off>` | Set power for all channels |

---

## OPC UA Interface Reference

### Status Variables (`Monitoring/`)

All monitoring data is accessible under `L2Trigger.Monitoring`:

**L2CB Controller Status (Scalars):**
- `CrateFirmwareRevision` (`UInt16`) — Firmware version
- `CrateUpTime` (`UInt64`) — Time since boot (nanoseconds)
- `CrateNumPoweredModules` (`UInt16`) — Modules currently powered
- `CrateNumTriggerEnabledModules` (`UInt16`) — Modules with trigger enabled

**L2CB Trigger Configuration (Scalars):**
- `CrateMCFEnabled` (`Boolean`) — MCF propagation state
- `CrateBusyGlitchFilterEnabled` (`Boolean`) — Glitch filter state
- `CrateTIBTriggerBusyBlockEnabled` (`Boolean`) — TIB blocking state
- `CrateMCFThreshold` (`Int16`) — MCF threshold (0-512)
- `CrateMCFDelay` (`Double`) — MCF delay in ns (0-75)
- `CrateL1Deadtime` (`Double`) — L1 deadtime in ns (0-1275)

**Per-Slot Board Data (Arrays):**
- `BoardSlots` (`Int32[]`) — Active slot numbers
- `BoardFirmwareRevision` (`UInt16[]`) — Firmware per slot
- `BoardCurrent` (`Double[]`) — Total current per slot (mA)
- `BoardCurrentLimitMin/Max` (`Double[]`) — Current safety limits
- `BoardHasErrors` (`Boolean[]`) — Error flag per slot

**Per-Module Data (Arrays):**
- `ModulePowerEnabled` (`Boolean[]`) — Power state
- `ModuleCurrent` (`Double[]`) — Current reading (mA)
- `ModuleState` (`String[]`) — Detailed state (on/off/error/etc.)
- `ModuleTriggerEnabled` (`Boolean[]`) — Trigger state
- `ModuleTriggerDelay` (`Double[]`) — Trigger delay (ns)

### Control Methods

Methods return a string prefixed with **`OK:`** or **`ERROR:`**. Boards are indexed 1-18; modules are indexed 1-270.

| Method | Parameters | Description |
| :--- | :--- | :--- |
| `EmergencyShutdown` | None | Immediately disable all power |
| `SetAllPowerEnabled` | `enabled: Boolean` | Ramp all modules on/off |
| `SetModulePowerEnabled` | `module: Int32, enabled: Boolean` | Control single module power |
| `SetAllTriggerEnabled` | `enabled: Boolean` | Enable/Disable all triggers |
| `SetModuleTriggerEnabled`| `module: Int32, enabled: Boolean`| Control specific trigger |
| `SetModuleTriggerDelay` | `module: Int32, ns: Double` | Set trigger delay (37ps steps) |
| `SetMCFThreshold` | `threshold: Int16` | Set MCF threshold (0-512) |
| `SetMCFEnabled` | `enabled: Boolean` | Set MCF propagation |

---

## System Architecture

### Safe Power Ramping
The backend server implements a **round-robin sequence** to prevent electrical surges. When `SetAllPowerEnabled(true)` is called:
1.  One module per slot is enabled (S1C1, S2C1, ... S18C1).
2.  The sequence moves to the next channel level (S1C2, ... S18C2).
3.  A configurable delay (default 100ms) is maintained between modules.

### Error Recovery
The system monitors for over/under current errors. If a module is in an error state, the backend server automatically attempts a "Reset cycle" (Power OFF then ON) when a power-on request is received.

### Bridge Configuration
The `l2trig_asyncua_bridge.py` supports several advanced options:
- `--poll-interval`: Frequency of fast updates (currents, errors).
- `--poll-ratio`: Frequency of slow updates (firmware, configuration).
- `--immutable-channels`: List of channels the server is forbidden to modify.
- `--opcua-user`: `user:pass` for authentication.
