/*
 * l2tcp_protocol.h
 *
 * Binary protocol definitions for the L2 Trigger Embedded Server (L2TCP).
 * Designed for light-weight communication between the ARM-based hardware 
 * controller and the remote OPC UA bridge.
 *
 * Protocol characteristics:
 * - Binary, fixed-size or predictable length payloads.
 * - Little Endian byte order.
 * - Single-client connection model.
 *
 * Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
 */

#ifndef L2TCP_PROTOCOL_H
#define L2TCP_PROTOCOL_H

#include <stdint.h>

#define L2TCP_PORT 4242
#define L2TCP_MAX_CHANNELS 15
#define L2TCP_MIN_SLOT 1
#define L2TCP_MAX_SLOT 22 // Slots used are labelled 1-9 13-21

/* --- Message Types --- */

typedef enum {
    L2TCP_MSG_ACK                     = 0x00,
    L2TCP_MSG_ERROR                   = 0xFF,

    /* System Configuration & Global Control */
    L2TCP_MSG_SYS_SET_CONFIG          = 0x01,
    L2TCP_MSG_SYS_RAMP_POWER          = 0x02,
    L2TCP_MSG_SYS_EMERGENCY_OFF       = 0x03,
    L2TCP_MSG_SYS_SET_ALL_TRIG_EN     = 0x04,
    L2TCP_MSG_SYS_SET_ALL_TRIG_DELAY  = 0x05,
    L2TCP_MSG_KEEPALIVE               = 0x06,

    /* L2CB Global Control & Monitoring */
    L2TCP_MSG_L2CB_GET_STATE          = 0x10,
    L2TCP_MSG_L2CB_SET_MCF_EN         = 0x11,
    L2TCP_MSG_L2CB_SET_GLITCH_EN      = 0x12,
    L2TCP_MSG_L2CB_SET_TIB_BLOCK_EN   = 0x13,
    L2TCP_MSG_L2CB_SET_MCF_THRESH     = 0x14,
    L2TCP_MSG_L2CB_SET_MCF_DELAY      = 0x15,
    L2TCP_MSG_L2CB_SET_L1_DEADTIME    = 0x16,

    /* CTDB Single Channel Control */
    L2TCP_MSG_CTDB_SET_CH_POWER       = 0x20,
    L2TCP_MSG_CTDB_SET_CH_TRIG        = 0x21,
    L2TCP_MSG_CTDB_SET_CH_DELAY       = 0x22,
    L2TCP_MSG_CTDB_SET_LIMITS         = 0x23,

    /* Monitoring & Batch */
    L2TCP_MSG_CTDB_GET_MONITORING     = 0x30,
    L2TCP_MSG_CTDB_GET_CONFIG         = 0x31,
    L2TCP_MSG_BATCH_MONITOR_ALL       = 0x32
} l2tcp_msg_type_t;

/* --- Error Codes --- */

typedef enum {
    L2TCP_ERR_PAYLOAD_TOO_LARGE       = 1,
    L2TCP_ERR_UNKNOWN_COMMAND         = 2,
    L2TCP_ERR_MALFORMED_PAYLOAD       = 3,
    L2TCP_ERR_INVALID_PARAMETER       = 4,
    L2TCP_ERR_HARDWARE_ERROR          = 5
} l2tcp_error_code_t;

/* --- Protocol Header --- */

#pragma pack(push, 1)

typedef struct {
    uint8_t type;     /* l2tcp_msg_type_t */
    uint8_t seq;      /* Sequence number for matching requests/responses */
    uint16_t len;     /* Length of payload following header (Little Endian) */
} l2tcp_header_t;

/* --- Payloads --- */

/* L2TCP_MSG_ERROR payload */
typedef struct {
    uint8_t code;
    char message[64];
} l2tcp_payload_error_t;

/* L2TCP_MSG_SYS_SET_CONFIG */
typedef struct {
    uint32_t active_slots_mask;       /* Bitmask of slots 0-31 */
    uint16_t immutable_masks[22];     /* One mask per slot (1-based index) */
} l2tcp_payload_sys_config_t;

/* L2TCP_MSG_SYS_RAMP_POWER */
typedef struct {
    uint8_t enable;    /* 1 = ON, 0 = OFF */
} l2tcp_payload_ramp_t;

/* L2CB Setters (Common for uint16 types) */
typedef struct {
    uint16_t value;
} l2tcp_payload_u16_t;

/* L2TCP_MSG_L2CB_GET_STATE (Response) */
typedef struct {
    uint16_t fw_rev;
    uint64_t timestamp;
    uint16_t ctrl_state;
    uint16_t mcf_threshold;
    uint16_t mcf_delay;
    uint16_t l1_deadtime;
} l2tcp_payload_l2cb_state_t;

/* L2TCP_MSG_CTDB_SET_CH_POWER, L2TCP_MSG_CTDB_SET_CH_TRIG */
typedef struct {
    uint8_t slot;
    uint8_t channel;
    uint8_t enable;
} l2tcp_payload_ch_ctrl_t;

/* L2TCP_MSG_CTDB_SET_CH_DELAY */
typedef struct {
    uint8_t slot;
    uint8_t channel;
    uint16_t delay;
} l2tcp_payload_ch_delay_t;

/* L2TCP_MSG_CTDB_SET_LIMITS */
typedef struct {
    uint8_t slot;
    uint16_t curr_limit_min;
    uint16_t curr_limit_max;
} l2tcp_payload_ctdb_limits_t;

/* L2TCP_MSG_CTDB_GET_MONITORING (Request: slot u8) (Response: below) */
typedef struct {
    uint8_t slot;
    uint16_t ctdb_curr;
    uint16_t ch_curr[15];
    uint16_t over_curr_mask;
    uint16_t under_curr_mask;
    uint16_t pwr_enabled_mask;
} l2tcp_payload_monitoring_t;

/* L2TCP_MSG_CTDB_GET_CONFIG (Request: slot u8) (Response: below) */
typedef struct {
    uint8_t slot;
    uint16_t fw_rev;
    uint16_t curr_limit_min;
    uint16_t curr_limit_max;
    uint16_t trig_enabled_mask;
    uint16_t trig_delays[15];
} l2tcp_payload_config_t;

/* L2TCP_MSG_BATCH_MONITOR_ALL (Response) */
typedef struct {
    uint8_t count;
    /* Followed by 'count' instances of l2tcp_payload_monitoring_t */
} l2tcp_payload_batch_mon_t;

#pragma pack(pop)

#endif /* L2TCP_PROTOCOL_H */
