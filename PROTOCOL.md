# L2 Trigger Binary Protocol (L2TCP)

This document describes the binary protocol used for communication between the NectarCam L2 Trigger Embedded Server (running on the ARM-based hardware controller) and the OPC UA Bridge (or other clients).

## General Characteristics

- **Transport:** TCP/IP
- **Port:** `4242`
- **Byte Order:** Little Endian
- **Connection Model:** Single-client: the server accepts one connection at a time; new connections are rejected while the original remains open (a watchdog timer protects against clients that become unresponsive).

## Protocol Header

Every message starts with a fixed-size 8-byte header.

| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `type` | `uint16` | Message type (see [Message Types](#message-types)). |
| 2 | `seq` | `uint16` | Sequence number for matching requests and responses. |
| 4 | `len` | `uint16` | Length of the payload following the header. |
| 6 | `reserved` | `uint16` | Padding for 8-byte (64 bit) alignment (currently unused). |

## HELLO Exchange (Handshake)

Before any functional commands are accepted, a version negotiation handshake must occur.

1. **Client sends `HELLO` (0x07):** The payload is a `uint16` representing the client's protocol version.
2. **Server responds `HELLO` (0x07):** The payload is a `uint16` representing the server's protocol version.
3. **Negotiation Logic:**
    - If the client version matches the server version, the connection is considered **negotiated**.
    - If there is a mismatch, the server sets `is_negotiated = 0` but still responds with its version.
    - The client is expected to "adapt" by sending another `HELLO` message containing the server's version if it wishes to proceed.
    - Once the server receives a `HELLO` matching its own version, the connection is negotiated.

**Important:** If any message other than `HELLO` is sent before negotiation is complete, the server will respond with an `L2TCP_ERR_NOT_INITIALIZED` error and close the connection.

For a full example of the handshake and subsequent configuration, see the [Example Exchange](#example-exchange-hex) at the bottom of this document.

## Post-Connection Configuration

Immediately after a successful `HELLO` exchange, the client **must** configure the server using `L2TCP_MSG_SYS_SET_CONFIG` (0x01). The server resets its configuration state for every new connection.

Functional commands (like Power Ramp or Monitoring) may return errors or produce incomplete results until the active slots and channel masks are defined.

- **Active Slots Mask**: A bitmask where bit `N` is 1 if slot `N` is present and should be managed.
- **Immutable Masks**: An array of bitmasks (one per slot) defining channels that are "immutable" (cannot be changed by standard power and trigger enable/disable commands). This is typically used to protect channels not connected to a module.

## Message Types

| Value | Name | Description | Request Payload | Response Payload |
| :--- | :--- | :--- | :--- | :--- |
| `0x00` | `L2TCP_MSG_ACK` | Generic acknowledgment. | None | None |
| `0xFF` | `L2TCP_MSG_ERROR` | Error notification. | N/A | `Error` |
| `0x01` | `L2TCP_MSG_SYS_SET_CONFIG` | Set active slots and masks. | `System Config` | `ACK` |
| `0x02` | `L2TCP_MSG_SYS_RAMP_POWER` | Global power ramp (ON/OFF). | `Ramp (uint16)` | `ACK` |
| `0x03` | `L2TCP_MSG_SYS_EMERGENCY_OFF` | Immediate power off. | None | `ACK` |
| `0x04` | `L2TCP_MSG_SYS_SET_ALL_TRIG_EN`| Enable/disable all triggers. | `uint16` (1/0) | `ACK` |
| `0x05` | `L2TCP_MSG_SYS_SET_ALL_TRIG_DELAY`| Set delay for all channels. | `uint16` | `ACK` |
| `0x06` | `L2TCP_MSG_KEEPALIVE` | Keepalive message. | None | `ACK` |
| `0x07` | `L2TCP_MSG_HELLO` | Version negotiation. | `uint16` (version) | `uint16` (version) |
| `0x10` | `L2TCP_MSG_L2CB_GET_STATE` | Request L2CB state. | None | `L2CB State` |
| `0x11` | `L2TCP_MSG_L2CB_SET_MCF_EN` | Set MCF Enable. | `uint16` (1/0) | `ACK` |
| `0x12` | `L2TCP_MSG_L2CB_SET_GLITCH_EN` | Set Glitch Filter Enable. | `uint16` (1/0) | `ACK` |
| `0x13` | `L2TCP_MSG_L2CB_SET_TIB_BLOCK_EN`| Set TIB Block Enable. | `uint16` (1/0) | `ACK` |
| `0x14` | `L2TCP_MSG_L2CB_SET_MCF_THRESH` | Set MCF Threshold. | `uint16` | `ACK` |
| `0x15` | `L2TCP_MSG_L2CB_SET_MCF_DELAY` | Set MCF Delay. | `uint16` | `ACK` |
| `0x16` | `L2TCP_MSG_L2CB_SET_L1_DEADTIME`| Set L1 Deadtime. | `uint16` | `ACK` |
| `0x17` | `L2TCP_MSG_L2CB_SET_BUSY_ENABLE_MASK`| Set Busy Enable Mask. | `uint32` | `ACK` |
| `0x18` | `L2TCP_MSG_L2CB_SET_BUSY_ENABLE_SLOT`| Set Busy Enable for Slot. | `Slot Ctrl` | `ACK` |
| `0x19` | `L2TCP_MSG_L2CB_RESET_TIB_COUNT`| Reset TIB Event Count. | None | `ACK` |
| `0x20` | `L2TCP_MSG_CTDB_SET_CH_POWER` | Set Channel Power. | `Channel Ctrl` | `ACK` |
| `0x21` | `L2TCP_MSG_CTDB_SET_CH_TRIG` | Set Channel Trigger. | `Channel Ctrl` | `ACK` |
| `0x22` | `L2TCP_MSG_CTDB_SET_CH_DELAY` | Set Channel Delay. | `Channel Delay` | `ACK` |
| `0x23` | `L2TCP_MSG_CTDB_SET_LIMITS` | Set CTDB Current Limits. | `CTDB Limits` | `ACK` |
| `0x30` | `L2TCP_MSG_CTDB_GET_MONITORING` | Request CTDB monitoring. | `uint16` (slot) | `Monitoring` |
| `0x31` | `L2TCP_MSG_CTDB_GET_CONFIG` | Request CTDB config. | `uint16` (slot) | `Config` |
| `0x32` | `L2TCP_MSG_BATCH_MONITOR_ALL` | Request all monitoring data. | None | `Batch Monitoring`|
| `0x33` | `L2TCP_MSG_FAST_POLL` | Combined L2CB + Monitoring. | None | `Fast Poll` |
| `0x34` | `L2TCP_MSG_SLOW_POLL` | All CTDB configurations. | None | `Batch Config` |

## Payload Structures

All payloads follow the 8-byte (64-bit) header. **Note:** if you modify the message structure, ensure that the alignment of the payload fields is correct for the ARM system. Typically it is preferable to order the fields by their size, starting with the 64-bit types, then 32-bit, then 16-bit, to avoid adding padding fields. The header is 64-bits to ensure proper alignment of the payload on the ARM architecture.

### 1. Error Payload (`L2TCP_MSG_ERROR`)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `code` | `uint16` | Error code (see [Error Codes](#error-codes)). |
| 2 | `message` | `char[64]` | Human-readable error message. |

### 2. System Configuration (`L2TCP_MSG_SYS_SET_CONFIG`)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `active_slots_mask` | `uint32` | Bitmask of active slots (bits 0-31). |
| 4 | `immutable_masks` | `uint16[22]`| Per-slot masks (index 1-21). |

### 3. Simple Value Payloads (`uint16` / `uint32`)
Used for various setters (MCF Enable, Thresholds, etc.).
- **uint16**: 2 bytes.
- **uint32**: 4 bytes.

### 4. L2CB State (`L2TCP_MSG_L2CB_GET_STATE` Response)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `timestamp` | `uint64` | Server timestamp (latched from 125MHz hardware clock). |
| 8 | `busy_mask` | `uint32` | Current Busy bitmask for slots 1-21. |
| 12 | `busy_stuck` | `uint32` | Stuck Busy bitmask for slots 1-21. |
| 16 | `tib_input_count` | `uint32` | 32-bit TIB camera input counter. |
| 20 | `tib_output_count`| `uint32` | 32-bit TIB event output (L1A) counter. |
| 24 | `fw_rev` | `uint16` | Firmware revision (bits 15..0). |
| 26 | `ctrl_state` | `uint16` | Summarized control state bits. |
| 28 | `mcf_threshold` | `uint16` | MCF Threshold setting (amount of L1s). |
| 30 | `mcf_delay` | `uint16` | MCF Delay window (multiples of 20ns, v14+). |
| 32 | `l1_deadtime` | `uint16` | L1 Deadtime setting (multiples of 5ns). |
| 34 | `reserved` | `uint16` | Padding for 32-bit alignment. |

### 5. Channel Control (`L2TCP_MSG_CTDB_SET_CH_POWER` / `SET_CH_TRIG`)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `slot` | `uint16` | Slot number (1-21). |
| 2 | `channel` | `uint16` | Channel number (0-14). |
| 4 | `enable` | `uint16` | 1 = Enable, 0 = Disable. |

### 6. Channel Delay (`L2TCP_MSG_CTDB_SET_CH_DELAY`)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `slot` | `uint16` | Slot number (1-21). |
| 2 | `channel` | `uint16` | Channel number (0-14). |
| 4 | `delay` | `uint16` | Delay value. |

### 7. CTDB Limits (`L2TCP_MSG_CTDB_SET_LIMITS`)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `slot` | `uint16` | Slot number (1-21). |
| 2 | `curr_limit_min` | `uint16` | Minimum current limit. |
| 4 | `curr_limit_max` | `uint16` | Maximum current limit. |

### 8. Monitoring Data (`L2TCP_MSG_CTDB_GET_MONITORING` Response)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `slot` | `uint16` | Slot number. |
| 2 | `ctdb_curr` | `uint16` | Total CTDB board current. |
| 4 | `ch_curr` | `uint16[15]` | Current for each of the 15 channels. |
| 34 | `over_curr_mask` | `uint16` | Bitmask of channels in over-current. |
| 36 | `under_curr_mask`| `uint16` | Bitmask of channels in under-current. |
| 38 | `pwr_enabled_mask`| `uint16` | Bitmask of channels with power enabled. |

### 9. CTDB Config (`L2TCP_MSG_CTDB_GET_CONFIG` Response)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `slot` | `uint16` | Slot number. |
| 2 | `fw_rev` | `uint16` | CTDB Firmware revision. |
| 4 | `curr_limit_min` | `uint16` | Current limit min. |
| 6 | `curr_limit_max` | `uint16` | Current limit max. |
| 8 | `trig_enabled_mask`| `uint16` | Bitmask of enabled triggers. |
| 10 | `trig_delays` | `uint16[15]`| Delay settings for 15 channels. |

### 10. Batch Monitoring (`L2TCP_MSG_BATCH_MONITOR_ALL` Response)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `count` | `uint16` | Number of monitoring entries. |
| 2 | `entries` | `Monitoring[]` | Array of `Monitoring Data` payloads. |

### 11. Fast Poll (`L2TCP_MSG_FAST_POLL` Response)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `l2cb` | `L2CB State` | Full `L2CB State` payload (36 bytes). |
| 36 | `monitor` | `Batch Mon` | Full `Batch Monitoring` payload. |

### 12. Batch Config (`L2TCP_MSG_SLOW_POLL` Response)
| Offset | Field | Type | Description |
| :--- | :--- | :--- | :--- |
| 0 | `count` | `uint16` | Number of config entries. |
| 2 | `entries` | `Config[]` | Array of `CTDB Config` payloads. |

## Error Codes

| Value | Name | Description |
| :--- | :--- | :--- |
| 1 | `L2TCP_ERR_PAYLOAD_TOO_LARGE` | Payload size exceeds buffer limits. |
| 2 | `L2TCP_ERR_UNKNOWN_COMMAND` | Command ID not recognized. |
| 3 | `L2TCP_ERR_MALFORMED_PAYLOAD` | Payload does not match command requirements. |
| 4 | `L2TCP_ERR_INVALID_PARAMETER` | Parameter value out of range (e.g., invalid slot). |
| 5 | `L2TCP_ERR_HARDWARE_ERROR` | Error communicating with the FPGA/SMC. |
| 6 | `L2TCP_ERR_NOT_INITIALIZED` | Command sent before `HELLO` negotiation. |

---

## Example Exchange (Hex)

This example shows a client connecting (Version 5), configuring the standard slots (1-9 and 13-21), setting no immutable channels, and starting a power ramp.

### 1. HELLO Handshake
**Client -> Server** (Type: 0x07, Seq: 1, Len: 2, Ver: 5)
`07 00 01 00 02 00 00 00 05 00`
- `07 00`: Type (HELLO)
- `01 00`: Seq (1)
- `02 00`: Len (2)
- `00 00`: Reserved
- `05 00`: Payload (Version 5)

**Server -> Client** (Type: 0x07, Seq: 1, Len: 2, Ver: 5)
`07 00 01 00 02 00 00 00 05 00`

### 2. Configure System Slots
Standard slots are 1-9 (0x000003FE) and 13-21 (0x003FE000). Total mask: `0x003FE3FE`.
No immutable channels (all 22 masks = 0).

**Client -> Server** (Type: 0x01, Seq: 2, Len: 48, Mask: 0x003FE3FE...)
`01 00 02 00 30 00 00 00 FE E3 3F 00 00 00 00 00 ... (44 more 0x00 bytes)`
- `01 00`: Type (SYS_SET_CONFIG)
- `02 00`: Seq (2)
- `30 00`: Len (48 bytes: 4 for mask + 2*22 for array)
- `00 00`: Reserved
- `FE E3 3F 00`: `active_slots_mask` (0x003FE3FE)
- `00 00 ...`: `immutable_masks[22]` (all zeros)

**Server -> Client** (Type: 0x00, Seq: 2, Len: 0)
`00 00 02 00 00 00 00 00` (ACK)

### 3. Start Power Ramp Up
**Client -> Server** (Type: 0x02, Seq: 3, Len: 2, Enable: 1)
`02 00 03 00 02 00 00 00 01 00`
- `02 00`: Type (SYS_RAMP_POWER)
- `03 00`: Seq (3)
- `02 00`: Len (2)
- `00 00`: Reserved
- `01 00`: Payload (1 = ON)

**Server -> Client** (Type: 0x00, Seq: 3, Len: 0)
`00 00 03 00 00 00 00 00` (ACK)
