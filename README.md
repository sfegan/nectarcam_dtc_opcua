# L2 Trigger System OPC UA Server

OPC UA server for the L2 Trigger System, providing standardized remote access to the L2CB controller board and CTDB trigger modules. This server is designed to integrate into larger telescope control systems through the OPC UA protocol.

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>  
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris

---

## Overview

The L2 Trigger System controls 270 trigger modules across 18 crate slots (15 channels per slot). This OPC UA server provides:

- Real-time monitoring of module status, currents, and errors
- Remote control of power, trigger enables, and timing parameters
- Controlled power ramping to prevent electrical stress
- Automatic polling with configurable update rates
- Safe multi-client access through OPC UA subscriptions

**Primary Components:**
- **OPC UA Server** (`l2trig_asyncua_server.py`) — Production interface for integration with telescope control systems
- **Direct Controller** (`l2trig_direct_client.py`) — Pre-configuration tool for hardware setup before server startup

**Testing Tools:**
- GUI (`l2trig_gui.py`) and test client (`l2trig_test_client.py`) for development and verification

---

## Quick Start

### 1. Install Dependencies

**Requirements:**
- Python 3.9 or newer
- GCC and Make (for building hardware access layer)

Install Python packages:
```bash
pip install -r requirements.txt
```

### 2. Build the Hardware Interface

**If you have the L2 Trigger hardware:**
```bash
make
sudo make install
```

**For testing without hardware (simulation mode):**
```bash
make dummy
```

The dummy mode simulates realistic hardware behavior including current readings (~300mA per enabled channel) and maintains internal state.

### 3. Start the OPC UA Server

```bash
python3 l2trig_asyncua_server.py
```

The server runs on `opc.tcp://0.0.0.0:4840/l2trigger/` by default and is ready for OPC UA clients to connect.

---

## Pre-Configuring Hardware

The direct controller (`l2trig_direct_client.py`) provides low-level access to the hardware **before** the OPC UA server starts. This is essential for:

- Setting initial MCF threshold and timing parameters
- Disabling triggers on specific channels that won't be used
- Configuring channels marked as immutable in the server
- Setting up known-good hardware states for testing

**Critical:** Only use the direct controller when the OPC UA server is **NOT** running. Concurrent access causes SPI transfer corruption and unstable behavior.

### Usage Modes

**Interactive mode:**
```bash
python3 l2trig_direct_client.py
l2trig> mcfthr 20
l2trig> trig 21 12 off
l2trig> exit
```

**Batch mode from file:**
```bash
python3 l2trig_direct_client.py config.txt
```

**Piped commands (for automation in server startup script, for example):**
```bash
python3 l2trig_direct_client.py << 'EOF'
allpower off    # Should presumably be the default on DTC start-up
mcf on          # Enable the muon candidate flag
mcfthr 20       # Set the muon threshold to 20 modules
mcfdel 20       # Set the muon delay to 100 ns (5ns per digital code)
allcurmin 200   # Set the minimum current to 97mA (0.485mA/step)
allcurmax 1000  # Set the maximum current to 485mA
trig 21 11 off  # Disable trigger on Slot 21 Channel 11
trig 21 12 off
trig 21 13 off
trig 21 14 off
trig 21 15 off
EOF
```

### Available Commands

The direct controller operates with **raw digital codes** and **slot/channel** addresses. Key commands:

```
allpower on/off             All power channels on all slots
power <slot> <ch> [on/off]  Single power channel (ch 1-15)
alltrig on/off              All trigger enables on all slots
trig <slot> <ch> [on/off]   Single trigger channel (ch 1-15)
delay <slot> <ch> [val]     Trigger delay (37ps/step, 0-127)
alldelay <val>              Set all trigger delays
curmax <slot> [val]         Max current limit (0.485mA/step)
allcurmax <val>             Set all max current limits
curmin <slot> [val]         Min current limit (0.485mA/step)
allcurmin <val>             Set all min current limits
mcfthr [val]                MCF threshold (L1 counts)
mcfdel [val]                MCF delay (5ns/step, 0-15)
deadtime [val]              L1 deadtime (5ns/step, 0-255)
mcf on/off                  MCF enable
glitch on/off               Busy glitch filter
tibblock on/off             TIB trigger blocking
cur <slot> <ch>             Read channel current (code & mA)
state                       Show L2CB control state
help                        Show all commands
exit                        Quit
```

---

## Server Configuration

The OPC UA server supports extensive configuration through command-line options. Understanding these options is essential for production deployment.

### Command-Line Options Reference

```bash
python3 l2trig_asyncua_server.py [options]
```

#### Network Configuration

**`--opcua-endpoint <url>`**  
Server endpoint URL for client connections.  
**Default:** `opc.tcp://0.0.0.0:4840/l2trigger/`  
**Example:** `--opcua-endpoint opc.tcp://192.168.1.100:4840/l2trigger/`  
Use `0.0.0.0` to listen on all interfaces, or specify an IP to bind to a specific interface.

**`--opcua-root <name>`**  
Root object name in the OPC UA address space.  
**Default:** `L2Trigger`  
**Example:** `--opcua-root MST_L2Trigger`  
All monitoring variables and methods appear under this root object.

**`--monitoring-path <name>`**  
Name of the monitoring object under the root.  
**Default:** `Monitoring`  
**Example:** `--monitoring-path Status`  
Monitoring variables appear at `<root>.<monitoring-path>` (e.g., `L2Trigger.Monitoring`).

**`--opcua-user <user:password>`**  
Add user authentication (can be specified multiple times).  
**Default:** Anonymous access only  
**Example:** `--opcua-user admin:secret123 --opcua-user operator:pass456`  
When set, clients must authenticate. Without this option, anonymous connections are allowed.

#### Polling Configuration

**`--poll-interval <seconds>`**  
Base polling interval for high-frequency variables.  
**Default:** `1.0`  
**Range:** `0.1` to `10.0` seconds recommended  
**Example:** `--poll-interval 0.5`  
Critical data (currents, errors, L2CB status) updates at this rate.

**`--poll-ratio <N>`**  
Ratio of high-frequency to full status reads.  
**Default:** `10`  
**Range:** `1` to `100`  
**Example:** `--poll-ratio 20`  
Slow-changing data (firmware, trigger settings) updates every N cycles. With `--poll-interval 1.0 --poll-ratio 10`, slow variables update every 10 seconds.

#### Power Management

**`--power-ramp-delay-ms <milliseconds>`**  
Delay between enabling individual modules during power ramp.  
**Default:** `10` ms  
**Range:** `0` to `1000` ms  
**Example:** `--power-ramp-delay-ms 20`  
Total ramp time = delay × number of modules. At 10ms: 2.7s for 270 modules. At 20ms: 5.4s.  
Set to `0` for instant enable (not recommended for hardware).

#### Hardware Configuration

**`--slots <list>`**  
Comma-separated list of active crate slots.  
**Default:** All valid slots (1-18, 21)  
**Example:** `--slots 1,2,3,4,5`  
Only specified slots are monitored and controlled. Reduces polling overhead if some slots are empty.

**`--immutable-channels <list>`**  
Comma-separated list of slot/channel pairs to exclude from server control.  
**Default:** `S21C11,S21C12,S21C13,S21C14,S21C15`  
**Format:** `S<slot>C<channel>` where slot is 1-21 and channel is 1-15  
**Example:** `--immutable-channels S21C11,S21C12,S1C15,S2C15`  
These channels are not controlled by the server but can be pre-configured using the direct controller.

#### Logging

**`--log-level <level>`**  
Logging verbosity level.  
**Default:** `INFO`  
**Options:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`  
**Example:** `--log-level DEBUG`  
- `DEBUG`: Detailed diagnostic output (polling cycles, SPI transactions)
- `INFO`: Normal operation (connections, configuration changes, watchdog summaries)
- `WARNING`: Unexpected conditions (timeouts, retries)
- `ERROR`: Failures requiring attention
- `CRITICAL`: Severe problems

### Configuration Examples

**Production deployment with authentication:**
```bash
python3 l2trig_asyncua_server.py \
  --opcua-endpoint opc.tcp://10.0.1.50:4840/l2trigger/ \
  --opcua-user admin:secure_password \
  --poll-interval 1.0 \
  --power-ramp-delay-ms 15 \
  --log-level INFO
```

**High-speed monitoring (2 Hz updates):**
```bash
python3 l2trig_asyncua_server.py \
  --poll-interval 0.5 \
  --poll-ratio 20 \
  --log-level WARNING
```

**Testing with limited slots:**
```bash
python3 l2trig_asyncua_server.py \
  --slots 1,2,3 \
  --poll-interval 0.5 \
  --log-level DEBUG
```

**Custom immutable channels:**
```bash
python3 l2trig_asyncua_server.py \
  --immutable-channels S1C15,S2C15,S3C15,S21C11,S21C12,S21C13,S21C14,S21C15 \
  --log-level INFO
```

**Fast power ramping for testing:**
```bash
python3 l2trig_asyncua_server.py \
  --power-ramp-delay-ms 5 \
  --log-level DEBUG
```

### How Polling Works

The server uses a Phase-Locked Loop (PLL) to maintain consistent update rates:

1. **High-Frequency Variables** (every `poll-interval`):
   - Module currents (`ModuleCurrent`, `BoardCurrent`)
   - Error states (`BoardHasErrors`, `ModuleState`)
   - L2CB status (`CrateUpTime`, MCF settings, deadtime)
   - Power states (`ModulePowerEnabled`)
   - System counters (`CrateNumPoweredModules`)

2. **Low-Frequency Variables** (every `poll-ratio` × `poll-interval`):
   - Firmware versions (`CrateFirmwareRevision`, `BoardFirmwareRevision`)
   - Current limits (`BoardCurrentLimitMin/Max`)
   - Trigger settings (`ModuleTriggerEnabled`, `ModuleTriggerDelay`)
   - Immutable flags (`ModuleIsMutable`)

3. **Immediate Updates**:
   - Any control method call triggers a full status read outside the normal schedule
   - Ensures clients see changes immediately after commands

4. **Watchdog Timer**:
   - System summary logged at `INFO` level every 180 seconds
   - Shows active boards, powered modules, and trigger-enabled modules
   - Useful for long-term monitoring without verbose debug output

### Power Ramping Details

When `SetAllPowerEnabled(true)` is called, modules enable sequentially to prevent electrical stress:

**Round-Robin Pattern:**
- Modules enable one per slot before moving to the next channel level
- Order: S1C1, S2C1, S3C1, ..., S18C1, S1C2, S2C2, ..., S18C2, ..., S18C15
- Distributes load evenly across the power supply

**Timing:**
- Delay between modules: `--power-ramp-delay-ms`
- Total ramp time: delay × number of active modules
- Example: 270 modules × 10ms = 2.7 seconds

**Cancellation:**
- New power command cancels ongoing ramp
- This includes: `SetAllPowerEnabled`, `SetModulePowerEnabled`, `EmergencyShutdown`
- Cancelled ramps don't leave modules in undefined states

**Monitoring During Ramp:**
- `CrateNumPoweredModules` updates in real-time as modules turn on
- Clients can subscribe to this variable to track progress

---

## Testing and Development Tools

### Graphical Interface (GUI)

A Tkinter-based GUI is provided for visual testing and development:

```bash
python3 l2trig_gui.py
```

**Features:**
- Visual matrix of all 270 modules (18 slots × 15 channels)
- Multiple display modes: power status, currents, trigger state, trigger delays
- Click modules to toggle power/triggers or set delays
- Real-time updates via OPC UA subscriptions
- Control panel for crate-level settings
- System log showing all commands and responses

**Usage:**
1. Enter server endpoint (default: `opc.tcp://localhost:4840/l2trigger/`)
2. Click **Connect**
3. Select display mode from dropdown
4. Click modules to interact, use control panel buttons for bulk operations

The GUI is useful for hardware verification and debugging but not intended for production control system integration.

### Interactive Test Client

Command-line tool for testing server functionality:

```bash
python3 l2trig_test_client.py --endpoint opc.tcp://localhost:4840/l2trigger/
```

**Common Commands:**
```
summary                  Show formatted system status
list                     List all monitoring variables
read <var>               Read specific variable
power 42 on              Control module power (1-270)
allpower on/off          Ramp all modules
trig 42 on               Enable module trigger
delay 42 2.5             Set trigger delay (ns)
limits 1 50.0 500.0      Set board current limits
mcfthreshold 256         Configure MCF threshold
subscribe all            Monitor variable changes
health                   Run health check
shutdown                 Emergency shutdown
help                     Show all commands
```

The test client supports both interactive use and scripting via pipes or command files.

---

## OPC UA Interface Reference

### Monitoring Data Reference

### Available Status Variables

All monitoring data is accessible through the OPC UA address space under `L2Trigger.Monitoring`:

**L2CB Controller Status:**
- `CrateFirmwareRevision` — Firmware version
- `CrateUpTime` — Time since boot (nanoseconds)
- `CrateNumMutabeModules` — Total actively controlled modules
- `CrateNumPoweredModules` — Modules currently powered
- `CrateNumTriggerEnabledModules` — Modules with trigger enabled

**L2CB Trigger Configuration:**
- `CrateMCFEnabled` — MCF propagation state
- `CrateBusyGlitchFilterEnabled` — Glitch filter state
- `CrateTIBTriggerBusyBlockEnabled` — TIB blocking state
- `CrateMCFThreshold` — MCF threshold (0-512)
- `CrateMCFDelay` — MCF delay in ns (0-75)
- `CrateL1Deadtime` — L1 deadtime in ns (0-1275)

**Per-Slot Board Data (Arrays):**
- `BoardSlots` — List of active slot numbers
- `BoardFirmwareRevision` — Firmware per slot
- `BoardCurrent` — Total current per slot
- `BoardCurrentSum` — Sum of all enabled channels per slot
- `BoardCurrentLimitMin/Max` — Current safety limits
- `BoardHasErrors` — Error flag per slot

**Per-Module Data (Flattened Arrays, 1-270):**
- `ModulePowerEnabled` — Power state
- `ModuleCurrent` — Current reading (mA)
- `ModuleState` — Detailed state (on/off/error/etc.)
- `ModuleTriggerEnabled` — Trigger state
- `ModuleTriggerDelay` — Trigger delay (ns)
- `ModuleIsMutable` — Whether server controls this module

### Available Control Methods

All control methods are located under the `L2Trigger` root object:

**Power Control:**
- `EmergencyShutdown()` — Immediately disable all power
- `SetAllPowerEnabled(enabled)` — Ramp all modules on/off
- `SetModulePowerEnabled(module, enabled)` — Control single module (1-270)
- `SetBoardCurrentLimits(board, min_ma, max_ma)` — Set safety limits

**Trigger Control:**
- `SetAllTriggerEnabled(enabled)` — Enable/disable all triggers
- `SetModuleTriggerEnabled(module, enabled)` — Control single module trigger
- `SetAllTriggerDelay(delay_ns)` — Set delay for all modules
- `SetModuleTriggerDelay(module, delay_ns)` — Set delay for single module (0-5 ns)

**L2CB Configuration:**
- `SetMCFEnabled(enabled)` — Enable MCF trigger propagation
- `SetBusyGlitchFilterEnabled(enabled)` — Enable busy glitch filter
- `SetTIBTriggerBusyBlockEnabled(enabled)` — Enable TIB trigger blocking
- `SetMCFThreshold(threshold)` — Set MCF threshold (0-512)
- `SetMCFDelay(delay_ns)` — Set MCF delay (0-75 ns)
- `SetL1Deadtime(deadtime_ns)` — Set L1 deadtime (0-1275 ns)

**System:**
- `HealthCheck()` — Return system health summary string

---

## System Architecture (For Developers)

The system has three layers:

1. **Low-Level HAL** (`l2trig_low_level.py`) — ctypes wrapper for `libl2trig_hal.so` C library
2. **High-Level API** (`l2trig_api.py`) — Async Python API with business logic and error handling
3. **OPC UA Server** (`l2trig_asyncua_server.py`) — Server built on `asyncua` library

This layered design separates hardware access, business logic, and network protocol concerns.

---

## Testing and Development Tools

### Graphical Interface (GUI)

A Tkinter-based GUI is provided for visual testing and development:

```bash
python3 l2trig_gui.py
```

**Features:**
- Visual matrix of all 270 modules (18 slots × 15 channels)
- Multiple display modes: power status, currents, trigger state, trigger delays
- Click modules to toggle power/triggers or set delays
- Real-time updates via OPC UA subscriptions
- Control panel for crate-level settings
- System log showing all commands and responses

**Usage:**
1. Enter server endpoint (default: `opc.tcp://localhost:4840/l2trigger/`)
2. Click **Connect**
3. Select display mode from dropdown
4. Click modules to interact, use control panel buttons for bulk operations

The GUI is useful for hardware verification and debugging but not intended for production control system integration.

### Interactive Test Client

Command-line tool for testing server functionality:

```bash
python3 l2trig_test_client.py --endpoint opc.tcp://localhost:4840/l2trigger/
```

**Common Commands:**
```
summary                  Show formatted system status
list                     List all monitoring variables
read <var>               Read specific variable
power 42 on              Control module power (1-270)
allpower on/off          Ramp all modules
trig 42 on               Enable module trigger
delay 42 2.5             Set trigger delay (ns)
limits 1 50.0 500.0      Set board current limits
mcfthreshold 256         Configure MCF threshold
subscribe all            Monitor variable changes
health                   Run health check
shutdown                 Emergency shutdown
help                     Show all commands
```

The test client supports both interactive use and scripting via pipes or command files.

### Running Tests

Automated tests verify system functionality:

```bash
python3 -m pytest test_l2trig_system.py
```

Build the HAL in dummy mode before running tests without hardware.

---

## Troubleshooting

**GUI won't connect:**
- Verify server is running: `ps aux | grep l2trig_asyncua_server`
- Check endpoint URL matches server configuration
- Ensure firewall allows port 4840

**Modules showing as "ERROR":**
- Check physical hardware connections
- Verify current limits are appropriate
- Use `health` command in test client for details

**Power ramp is too slow/fast:**
- Adjust `--power-ramp-delay-ms` when starting server
- Default 10ms = 2.7s for all 270 modules
- Increase for gentler power-up, decrease for faster startup

**"Immutable" modules won't respond:**
- These channels are intentionally disabled (see `--immutable-channels`)
- Use direct client to configure them when server is stopped
- Or remove from immutable list when starting server

**Getting "SPI transfer corruption" warnings:**
- Only run ONE client at a time (GUI or test client, not both)
- Never use direct client while server is running
- Stop all clients and restart server if corruption occurs

---

## Support

For issues or questions, contact:  
Stephen Fegan <sfegan@llr.in2p3.fr>  
Laboratoire Leprince-Ringuet, CNRS/IN2P3
