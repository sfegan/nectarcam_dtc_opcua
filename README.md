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
For the embedded ARM-based controller board, you can download pre-compiled static binaries from the [**GitHub Releases**](https://github.com/sfegan/nectarcam_dtc_opcua/releases) page. Alternatively you can cross-compile from source using the toolchain provideed in the `toolchain` directory (only on Linux). The repository contains two applications that can run on the ARM board:
*   `l2tcp_server`: The backend TCP bridge, should be run from a terminal or from `systemd` after boot.
*   `l2trig_direct_client`: The configuration application, can be used interactively or with scripts to pre-configue the system before starting the backend server.

### 2. Install Python Bridge (Control PC)
On your control workstation, install the required Python dependencies:
```bash
pip install -r requirements.txt
```

### 3. Start the Backend Server (ARM Board)
Transfer the `l2tcp_server` binary to the ARM board (via ssh) and run it:
```bash
./l2tcp_server -p 4242 -v
```

### 4. Start the OPC UA Bridge (Control PC)
```bash
python3 l2trig_asyncua_bridge.py --device-host <ARM_BOARD_IP>
```
The bridge will connect to the ARM board and start an OPC UA server on `opc.tcp://0.0.0.0:4840/l2trig/`.

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
| `deadtime [val]` | Get/Set L1 deadtime (5ns steps) |
| `trigmask <slot> [m]` | Get/Set trigger mask (16-bit hex) |
| `trig <slot> <ch> [o]`| Get/Set trigger for specific channel |
| `alltrig <on\|off>` | Enable/Disable all trigger channels |
| `powermask <slot> [m]`| Get/Set power mask (16-bit hex) |
| `allpower <on\|off>` | Set power for all channels |

The client can be used interafctively, allowing commands to be typed from the terminal, or via a script to allow command to be piped or read from a file. For example, the following  will pre-configure the system parameters for the muon candidate flag and disable the trigger from the unused channels in slot 21:

```bash
l2trig_direct_client << 'EOF'
allpower off    # Should presumably be the default on DTC start-up
mcf on          # Enable the muon candidate flag
mcfthr 20       # Set the muon threshold to 20 modules
mcfdel 15       # Set the muon delay to 75 ns (5ns per digital code)
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
- `CrateMCFThreshold` (`Int16`) — MCF threshold (0-512 channels)
- `CrateMCFDelay` (`Double`) — MCF delay in ns (0-75ns in 5ns steps)
- `CrateL1Deadtime` (`Double`) — L1 deadtime in ns (0-1275ns in 5ns steps)

**Per-Slot Board Data. (Arrays; one element per configured slot):**
- `BoardSlots` (`Int32[]`) — List of active slot numbers
- `BoardFirmwareRevision` (`UInt16[]`) — Firmware per CDTB board
- `BoardCurrent` (`Double[]`) — Total current per CDTB board (mA in 0.485mA steps)
- `BoardCurrentSum` (`Double[]`) — Sum of all enabled channels per CDTB board (mA in 0.485mA steps)
- `BoardCurrentLimitMin/Max` (`Double[]`) — Current safety limits per CDTB board (mA in 0.485mA steps)
- `BoardHasErrors` (`Boolean[]`) — Error flag per CDTB board

**Per-Module Data (Arrays; one element per configured channel):**
- `ModulePowerEnabled` (`Boolean[]`) — Power state (1=on/0=off)
- `ModuleCurrent` (`Double[]`) — Current reading (mA in 0.485mA steps)
- `ModuleState` (`String[]`) — Detailed state (on/off/error/etc.)
- `ModuleTriggerEnabled` (`Boolean[]`) — Trigger state (1=enabled/0=disabled)
- `ModuleTriggerDelay` (`Double[]`) — Trigger delay in ns (0-4.7ns in 37ps steps)
- `ModuleIsMutable` (`Boolean[]`) — Whether server controls this module

### Control Methods

Methods return a string prefixed with **`OK:`** or **`ERROR:`**. Boards are indexed 1-18; modules are indexed 1-270.

| Method | Parameters | Description |
| :--- | :--- | :--- |
| `EmergencyShutdown` | None | Immediately disable all power |
| `SetAllPowerEnabled` | `enabled: Boolean` | Ramp all modules on/off |
| `SetModulePowerEnabled` | `module: Int32, enabled: Boolean` | Control single module power |
| `SetBoardCurrentLimits` | `board: Int32, min_ma: Double, max_ma: Double` | Configure board current limits (0-1986mA in 0.485mA steps) |
| `SetAllTriggerEnabled` | `enabled: Boolean` | Enable/Disable triggers from all modules |
| `SetModuleTriggerEnabled`| `module: Int32, enabled: Boolean`| Enable/Disable trigger from specific module |
| `SetAllTriggerDelay` | `delay_ns: Double` | Set uniform trigger delay for all modules (0-4.7ns in 37ps steps) |
| `SetModuleTriggerDelay` | `module: Int32, ns: Double` | Set trigger delay for specific module (0-4.7ns in 37ps steps) |
| `SetMCFEnabled` | `enabled: Boolean` | Enable muon candidate flag propagation to TIB |
| `SetMCFDelay` | `delay: Double` | Set MCF delay in ns (0-75ns in 5ns steps) |
| `SetMCFThreshold` | `threshold: Int16` | Set MCF threshold in modules (0-512) |
| `SetBusyGlitchFilterEnabled`| `enabled: Boolean` | Enable/Disable busy glitch filter |
| `SetTIBTriggerBusyBlockEnabled`| `enabled: Boolean` | Enable/Disable TIB trigger blocking |
| `SetL1Deadtime` | `deadtime: Double` | Set L1 deadtime in ns (0-1275ns in 5ns steps) |

---

## System Architecture

### Safe Power Ramping
The backend server implements a **round-robin sequence** to prevent electrical surges. When `SetAllPowerEnabled(true)` is called:
1.  One module per slot is enabled (S1C1, S2C1, ... S18C1).
2.  The sequence moves to the next channel level (S1C2, ... S18C2).
3.  A configurable delay (default 100ms) is maintained between powering subsequent modules on the same board.

### Recovery from Under/Overcurrent Errors
The system monitors for over/under current errors. If a module is in an error state, the backend server automatically clear the error when a subsequent power-on request is received. So, for example, if a set of modules does not power on correctly, the user can simply call `SetAllPowerEnabled(true)` again to attempt recovery.

### Bridge Configuration
The `l2trig_asyncua_bridge.py` supports several advanced options:
- `--poll-interval`: Frequency of fast updates (currents, errors).
- `--poll-ratio`: Frequency of slow updates (firmware, configuration).
- `--immutable-channels`: List of channels the server is forbidden to modify.
- `--opcua-user`: `user:pass` for authentication.

## Cross-compilation of backend-server using supplied toolchain
The `toolchain` directory contains a Docker-based cross-compilation environment for building the ARM binaries on Linux. It uses the `arm-none-eabi` toolchain. To build the binaries (as imoplemented in the GitHub actions workflow included here), run the following command from the repository root:

```bash
tar -xzf toolchain/crosstoll-ng-1.2.00-arm-926ejs-linux-gnueabi.tar.gz -C toolchain
PATH=$PWD/toolchain/arm-926ejs-linux-gnueabi/bin:$PATH
cd l2tcp_server
arm-926ejs-linux-gnueabi-gcc -std=gnu99 -march=armv5te -I../hal -static -o l2tcp_server l2tcp_server_main.c ../hal/smc.c ../hal/l2trig_hal.c
```
