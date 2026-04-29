/*
 * main.c
 *
 * L2 Trigger Embedded TCP Server (L2TCP)
 * Light-weight bridge between TCP and L2 Trigger HAL.
 *
 * Features:
 * - Non-blocking select() loop for network and ramp state machine.
 * - Hardware-specific power reset logic (OFF then ON) for channels in error.
 * - Batch monitoring and efficient power ramping.
 *
 * Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <time.h>

#include "l2tcp_protocol.h"
#include "../hal/l2trig_hal.h"

/* --- Server State --- */

static struct {
    uint32_t active_slots_mask;
    uint16_t immutable_masks[L2TCP_MAX_SLOTS];
    int ramp_delay_ms;
    
    struct {
        int active;
        int enable;
        int current_ch; /* 1-15 */
        struct timespec next_step_ts;
    } ramp;

    int listen_fd;
    int client_fd;
} g_server;

/* --- Helpers --- */

static void get_now(struct timespec *ts) {
    clock_gettime(CLOCK_MONOTONIC, ts);
}

static int is_slot_active(int slot) {
    if (slot < 0 || slot >= 32) return 0;
    return (g_server.active_slots_mask & (1 << slot)) != 0;
}

static int is_ch_immutable(int slot, int ch) {
    if (slot < 0 || slot >= L2TCP_MAX_SLOTS) return 1;
    if (ch < 1 || ch > 15) return 1;
    return (g_server.immutable_masks[slot] & (1 << ch)) != 0;
}

static void send_error(uint8_t seq, uint8_t code, const char *msg) {
    l2tcp_header_t resp_hdr;
    l2tcp_payload_error_t resp_err;

    resp_hdr.type = L2TCP_MSG_ERROR;
    resp_hdr.seq = seq;
    resp_hdr.len = sizeof(resp_err);
    
    resp_err.code = code;
    strncpy(resp_err.message, msg, sizeof(resp_err.message) - 1);
    resp_err.message[sizeof(resp_err.message) - 1] = '\0';

    send(g_server.client_fd, &resp_hdr, sizeof(resp_hdr), 0);
    send(g_server.client_fd, &resp_err, sizeof(resp_err), 0);
}

static void send_ack(uint8_t seq) {
    l2tcp_header_t resp_hdr = { L2TCP_MSG_ACK, seq, 0 };
    send(g_server.client_fd, &resp_hdr, sizeof(resp_hdr), 0);
}

/* --- Power Logic --- */

static void handle_ch_power(int slot, int ch, int enable) {
    if (!is_slot_active(slot) || is_ch_immutable(slot, ch)) return;

    if (enable) {
        uint16_t over, under;
        cta_ctdb_getOverCurrentErrors(slot, &over);
        cta_ctdb_getUnderCurrentErrors(slot, &under);
        
        if ((over | under) & (1 << ch)) {
            /* Error detected: explicit OFF to reset latch */
            cta_ctdb_setPowerChannelEnabled(slot, ch, 0);
        }
        cta_ctdb_setPowerChannelEnabled(slot, ch, 1);
    } else {
        cta_ctdb_setPowerChannelEnabled(slot, ch, 0);
    }
}

/* --- Ramp State Machine --- */

static void start_ramp(int enable) {
    g_server.ramp.active = 1;
    g_server.ramp.enable = enable;
    g_server.ramp.current_ch = 1;
    get_now(&g_server.ramp.next_step_ts);

    if (enable) {
        /* Pre-sweep: Reset channels in error before starting timed ramp */
        for (int s = 0; s < L2TCP_MAX_SLOTS; s++) {
            if (!is_slot_active(s)) continue;
            uint16_t over, under;
            cta_ctdb_getOverCurrentErrors(s, &over);
            cta_ctdb_getUnderCurrentErrors(s, &under);
            uint16_t err_mask = (over | under);
            if (err_mask) {
                uint16_t pwr;
                cta_ctdb_getPowerEnabled(s, &pwr);
                cta_ctdb_setPowerEnabled(s, pwr & ~err_mask);
            }
        }
    }
}

static void process_ramp() {
    if (!g_server.ramp.active) return;

    struct timespec now;
    get_now(&now);

    if (now.tv_sec < g_server.ramp.next_step_ts.tv_sec ||
       (now.tv_sec == g_server.ramp.next_step_ts.tv_sec && now.tv_nsec < g_server.ramp.next_step_ts.tv_nsec)) {
        return;
    }

    /* Process one channel index across ALL slots */
    for (int s = 0; s < L2TCP_MAX_SLOTS; s++) {
        if (!is_slot_active(s)) continue;
        if (is_ch_immutable(s, g_server.ramp.current_ch)) continue;
        cta_ctdb_setPowerChannelEnabled(s, g_server.ramp.current_ch, g_server.ramp.enable);
    }

    g_server.ramp.current_ch++;
    if (g_server.ramp.current_ch > 15) {
        g_server.ramp.active = 0;
        printf("Ramp complete\n");
    } else {
        /* Schedule next step */
        g_server.ramp.next_step_ts.tv_nsec += (long)g_server.ramp_delay_ms * 1000000L;
        while (g_server.ramp.next_step_ts.tv_nsec >= 1000000000L) {
            g_server.ramp.next_step_ts.tv_nsec -= 1000000000L;
            g_server.ramp.next_step_ts.tv_sec += 1;
        }
    }
}

/* --- Command Processing --- */

static void handle_request() {
    l2tcp_header_t hdr;
    ssize_t n = recv(g_server.client_fd, &hdr, sizeof(hdr), 0);
    if (n <= 0) {
        close(g_server.client_fd);
        g_server.client_fd = -1;
        printf("Client disconnected\n");
        return;
    }

    uint8_t buffer[4096];
    if (hdr.len > sizeof(buffer)) {
        send_error(hdr.seq, 1, "Payload too large");
        return;
    }

    if (hdr.len > 0) {
        n = recv(g_server.client_fd, buffer, hdr.len, MSG_WAITALL);
        if (n != hdr.len) return;
    }

    switch (hdr.type) {
        case L2TCP_MSG_SYS_SET_CONFIG: {
            l2tcp_payload_sys_config_t *p = (l2tcp_payload_sys_config_t *)buffer;
            uint32_t validated_mask = 0;
            for (int s = 0; s < 32; s++) {
                if ((p->active_slots_mask & (1 << s)) && cta_l2cb_isValidSLot(s)) {
                    validated_mask |= (1 << s);
                }
            }
            g_server.active_slots_mask = validated_mask;
            memcpy(g_server.immutable_masks, p->immutable_masks, sizeof(g_server.immutable_masks));
            
            printf("Configured active slots: ");
            int first_slot = 1;
            for (int s = 0; s < 32; s++) {
                if (g_server.active_slots_mask & (1 << s)) {
                    printf("%s%d", first_slot ? "" : ", ", s);
                    first_slot = 0;
                }
            }
            if (first_slot) printf("none");
            printf(" (mask: 0x%08x)\n", g_server.active_slots_mask);

            printf("Immutable channels: ");
            int first_imm = 1;
            for (int s = 0; s < L2TCP_MAX_SLOTS; s++) {
                if (g_server.active_slots_mask & (1 << s)) {
                    for (int ch = 1; ch <= 15; ch++) {
                        if (g_server.immutable_masks[s] & (1 << ch)) {
                            printf("%sS%dC%d", first_imm ? "" : ", ", s, ch);
                            first_imm = 0;
                        }
                    }
                }
            }
            if (first_imm) printf("none");
            printf("\n");

            send_ack(hdr.seq);
            break;
        }
        case L2TCP_MSG_SYS_RAMP_POWER: {
            l2tcp_payload_ramp_t *p = (l2tcp_payload_ramp_t *)buffer;
            if (g_server.active_slots_mask == 0) {
                send_error(hdr.seq, 3, "No active slots configured");
            } else {
                start_ramp(p->enable);
                send_ack(hdr.seq);
            }
            break;
        }
        case L2TCP_MSG_SYS_EMERGENCY_OFF: {
            cta_ctdb_setPowerEnabledToAll(0);
            g_server.ramp.active = 0;
            send_ack(hdr.seq);
            break;
        }
        case L2TCP_MSG_L2CB_GET_STATE: {
            l2tcp_header_t resp_hdr = { L2TCP_MSG_L2CB_GET_STATE, hdr.seq, sizeof(l2tcp_payload_l2cb_state_t) };
            l2tcp_payload_l2cb_state_t resp;
            resp.fw_rev = cta_l2cb_getFirmwareRevision();
            resp.timestamp = cta_l2cb_readTimestamp();
            uint16_t mcf, busy, tib;
            cta_l2cb_getControlState(&mcf, &busy, &tib);
            resp.ctrl_state = (mcf ? 0x1 : 0) | (busy ? 0x2 : 0) | (tib ? 0x4 : 0);
            resp.mcf_threshold = cta_l2cb_getMCFThreshold();
            resp.mcf_delay = cta_l2cb_getMCFDelay();
            resp.l1_deadtime = cta_l2cb_getL1Deadtime();
            send(g_server.client_fd, &resp_hdr, sizeof(resp_hdr), 0);
            send(g_server.client_fd, &resp, sizeof(resp), 0);
            break;
        }
        case L2TCP_MSG_L2CB_SET_MCF_EN:
            cta_l2cb_setMCFEnabled(((l2tcp_payload_u16_t*)buffer)->value);
            send_ack(hdr.seq);
            break;
        case L2TCP_MSG_L2CB_SET_GLITCH_EN:
            cta_l2cb_setBusyGlitchFilterEnabled(((l2tcp_payload_u16_t*)buffer)->value);
            send_ack(hdr.seq);
            break;
        case L2TCP_MSG_L2CB_SET_TIB_BLOCK_EN:
            cta_l2cb_setTIBTriggerBusyBlockEnabled(((l2tcp_payload_u16_t*)buffer)->value);
            send_ack(hdr.seq);
            break;
        case L2TCP_MSG_L2CB_SET_MCF_THRESH:
            cta_l2cb_setMCFThreshold(((l2tcp_payload_u16_t*)buffer)->value);
            send_ack(hdr.seq);
            break;
        case L2TCP_MSG_L2CB_SET_MCF_DELAY:
            cta_l2cb_setMCFDelay(((l2tcp_payload_u16_t*)buffer)->value);
            send_ack(hdr.seq);
            break;
        case L2TCP_MSG_L2CB_SET_L1_DEADTIME:
            cta_l2cb_setL1Deadtime(((l2tcp_payload_u16_t*)buffer)->value);
            send_ack(hdr.seq);
            break;
        case L2TCP_MSG_CTDB_SET_CH_POWER: {
            l2tcp_payload_ch_ctrl_t *p = (l2tcp_payload_ch_ctrl_t *)buffer;
            if (!is_slot_active(p->slot)) {
                send_error(hdr.seq, 4, "Slot not active");
            } else {
                handle_ch_power(p->slot, p->channel, p->enable);
                send_ack(hdr.seq);
            }
            break;
        }
        case L2TCP_MSG_CTDB_SET_CH_TRIG: {
            l2tcp_payload_ch_ctrl_t *p = (l2tcp_payload_ch_ctrl_t *)buffer;
            if (!is_slot_active(p->slot)) {
                send_error(hdr.seq, 4, "Slot not active");
            } else if (is_ch_immutable(p->slot, p->channel)) {
                send_error(hdr.seq, 5, "Channel is immutable");
            } else {
                cta_l2cb_setL1TriggerChannelEnabled(p->slot, p->channel, p->enable);
                send_ack(hdr.seq);
            }
            break;
        }
        case L2TCP_MSG_CTDB_SET_CH_DELAY: {
            l2tcp_payload_ch_delay_t *p = (l2tcp_payload_ch_delay_t *)buffer;
            if (!is_slot_active(p->slot)) {
                send_error(hdr.seq, 4, "Slot not active");
            } else if (is_ch_immutable(p->slot, p->channel)) {
                send_error(hdr.seq, 5, "Channel is immutable");
            } else {
                cta_l2cb_setL1TriggerDelay(p->slot, p->channel, p->delay);
                send_ack(hdr.seq);
            }
            break;
        }
        case L2TCP_MSG_CTDB_SET_LIMITS: {
            l2tcp_payload_ctdb_limits_t *p = (l2tcp_payload_ctdb_limits_t *)buffer;
            if (!is_slot_active(p->slot)) {
                send_error(hdr.seq, 4, "Slot not active");
            } else {
                cta_ctdb_setPowerCurrentMin(p->slot, p->curr_limit_min);
                cta_ctdb_setPowerCurrentMax(p->slot, p->curr_limit_max);
                send_ack(hdr.seq);
            }
            break;
        }
        case L2TCP_MSG_CTDB_GET_MONITORING: {
            uint8_t slot = buffer[0];
            if (!is_slot_active(slot)) {
                send_error(hdr.seq, 4, "Slot not active");
            } else {
                l2tcp_header_t resp_hdr = { L2TCP_MSG_CTDB_GET_MONITORING, hdr.seq, sizeof(l2tcp_payload_monitoring_t) };
                l2tcp_payload_monitoring_t resp;
                memset(&resp, 0, sizeof(resp));
                resp.slot = slot;
                cta_ctdb_getPowerCurrent(slot, 0, &resp.ctdb_curr);
                for (int i = 0; i < 15; i++) cta_ctdb_getPowerCurrent(slot, i + 1, &resp.ch_curr[i]);
                cta_ctdb_getOverCurrentErrors(slot, &resp.over_curr_mask);
                cta_ctdb_getUnderCurrentErrors(slot, &resp.under_curr_mask);
                cta_ctdb_getPowerEnabled(slot, &resp.pwr_enabled_mask);
                send(g_server.client_fd, &resp_hdr, sizeof(resp_hdr), 0);
                send(g_server.client_fd, &resp, sizeof(resp), 0);
            }
            break;
        }
        case L2TCP_MSG_BATCH_MONITOR_ALL: {
            int count = 0;
            for (int s = 0; s < L2TCP_MAX_SLOTS; s++) if (is_slot_active(s)) count++;
            
            l2tcp_header_t resp_hdr = { L2TCP_MSG_BATCH_MONITOR_ALL, hdr.seq, 1 + count * sizeof(l2tcp_payload_monitoring_t) };
            send(g_server.client_fd, &resp_hdr, sizeof(resp_hdr), 0);
            uint8_t u8_count = (uint8_t)count;
            send(g_server.client_fd, &u8_count, 1, 0);

            for (int s = 0; s < L2TCP_MAX_SLOTS; s++) {
                if (!is_slot_active(s)) continue;
                l2tcp_payload_monitoring_t resp;
                resp.slot = (uint8_t)s;
                cta_ctdb_getPowerCurrent(s, 0, &resp.ctdb_curr);
                for (int i = 0; i < 15; i++) cta_ctdb_getPowerCurrent(s, i + 1, &resp.ch_curr[i]);
                cta_ctdb_getOverCurrentErrors(s, &resp.over_curr_mask);
                cta_ctdb_getUnderCurrentErrors(s, &resp.under_curr_mask);
                cta_ctdb_getPowerEnabled(s, &resp.pwr_enabled_mask);
                send(g_server.client_fd, &resp, sizeof(resp), 0);
            }
            break;
        }
        case L2TCP_MSG_CTDB_GET_CONFIG: {
            uint8_t slot = buffer[0];
            if (!is_slot_active(slot)) {
                send_error(hdr.seq, 4, "Slot not active");
            } else {
                l2tcp_header_t resp_hdr = { L2TCP_MSG_CTDB_GET_CONFIG, hdr.seq, sizeof(l2tcp_payload_config_t) };
                l2tcp_payload_config_t resp;
                memset(&resp, 0, sizeof(resp));
                resp.slot = slot;
                cta_ctdb_getFirmwareRevision(slot, &resp.fw_rev);
                cta_ctdb_getPowerCurrentMin(slot, &resp.curr_limit_min);
                cta_ctdb_getPowerCurrentMax(slot, &resp.curr_limit_max);
                resp.trig_enabled_mask = cta_l2cb_getL1TriggerEnabled(slot);
                for (int i = 0; i < 15; i++) resp.trig_delays[i] = cta_l2cb_getL1TriggerDelay(slot, i + 1);
                send(g_server.client_fd, &resp_hdr, sizeof(resp_hdr), 0);
                send(g_server.client_fd, &resp, sizeof(resp), 0);
            }
            break;
        }
        default:
            send_error(hdr.seq, 2, "Unknown command");
            break;
    }
}

/* --- Main Loop --- */

int main(int argc, char **argv) {
    g_server.ramp_delay_ms = 100; /* Default */
    int port = L2TCP_PORT;

    int opt;
    while ((opt = getopt(argc, argv, "p:d:s:")) != -1) {
        switch (opt) {
            case 'p': port = atoi(optarg); break;
            case 'd': g_server.ramp_delay_ms = atoi(optarg); break;
            case 's': smc_open(optarg); break;
        }
    }
    
    if (!smc_isOpen()) smc_open(smc_default_device());

    g_server.listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    int val = 1;
    setsockopt(g_server.listen_fd, SOL_SOCKET, SO_REUSEADDR, &val, sizeof(val));

    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);
    
    if (bind(g_server.listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        return 1;
    }
    listen(g_server.listen_fd, 1);
    g_server.client_fd = -1;

    printf("L2TCP Server listening on port %d, ramp delay %d ms\n", port, g_server.ramp_delay_ms);

    while (1) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(g_server.listen_fd, &fds);
        int max_fd = g_server.listen_fd;
        
        if (g_server.client_fd != -1) {
            FD_SET(g_server.client_fd, &fds);
            if (g_server.client_fd > max_fd) max_fd = g_server.client_fd;
        }

        struct timeval tv = { 0, 10000 }; /* 10ms tick */
        int ret = select(max_fd + 1, &fds, NULL, NULL, &tv);

        if (ret < 0) {
            if (errno == EINTR) continue;
            break;
        }

        if (FD_ISSET(g_server.listen_fd, &fds)) {
            int new_fd = accept(g_server.listen_fd, NULL, NULL);
            if (g_server.client_fd != -1) {
                printf("Rejecting second client\n");
                close(new_fd);
            } else {
                g_server.client_fd = new_fd;
                /* Reset configuration on new client connection */
                g_server.active_slots_mask = 0;
                memset(g_server.immutable_masks, 0, sizeof(g_server.immutable_masks));
                g_server.ramp.active = 0;
                printf("Client connected - configuration reset\n");
            }
        }

        if (g_server.client_fd != -1 && FD_ISSET(g_server.client_fd, &fds)) {
            handle_request();
        }

        process_ramp();
    }

    smc_close();
    return 0;
}
