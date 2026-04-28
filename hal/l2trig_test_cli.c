/*
 * l2trig_test_cli.c
 *
 * Command line interface to exercise the L2 Trigger HAL
 *
 * Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
 * Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>

#include "l2trig_hal.h"
#include "smc.h"

void print_help() {
    printf("Available commands:\n");
    printf("  rev                        - Read L2CB firmware revision\n");
    printf("  ts                         - Read L2CB latched timestamp\n");
    printf("  status                     - Read L2CB control status\n");
    printf("  mcf [0|1]                  - Get/Set MCF trigger propagation\n");
    printf("  mcf_thresh [val]           - Get/Set MCF threshold (0-511)\n");
    printf("  mcf_delay [val]            - Get/Set MCF delay (0-15, in 5ns steps)\n");
    printf("  deadtime [val]             - Get/Set L1 deadtime (0-255, in 5ns steps)\n");
    printf("  slot_rev <slot>            - Read CTDB firmware revision for a slot\n");
    printf("  pwr_all <0|1>              - Set power to all CTDBs\n");
    printf("  pwr_slot <slot> [hex_mask] - Get/Set power mask for a slot (16-bit hex)\n");
    printf("  pwr_ch <slot> <ch> [0|1]   - Get/Set power for a channel (1-15)\n");
    printf("  curr <slot> <ch>           - Read current for a channel (0=CTDB, 1-15=channel)\n");
    printf("  curr_limits <slot> [m M]   - Get/Set current limits (min max, in hex counts)\n");
    printf("  trig_slot <slot> [hex_mask]- Get/Set trigger mask for a slot (16-bit hex)\n");
    printf("  trig_ch <slot> <ch> [0|1]  - Get/Set trigger for a channel (1-15)\n");
    printf("  trig_delay <slot> <ch> [v] - Get/Set trigger delay (0-255, in 37ps steps)\n");
    printf("  errors <slot>              - Read over/under current errors for a slot\n");
    printf("  reg_read <slot> <reg>      - Direct SPI read from CTDB register\n");
    printf("  reg_write <slot> <reg> <v> - Direct SPI write to CTDB register\n");
    printf("  help                       - Print this help\n");
    printf("  quit                       - Exit\n");
}

int main(int argc, char** argv) {
    const char* dev = smc_default_device();
    if (argc > 1) {
        dev = argv[1];
    }

    printf("Opening SMC device: %s\n", dev);
    if (smc_open(dev) != ERROR_NONE) {
        fprintf(stderr, "Failed to open SMC device\n");
        return 1;
    }

    char line[256];
    char cmd[64];
    
    print_help();

    while (1) {
        printf("> ");
        fflush(stdout);
        if (!fgets(line, sizeof(line), stdin)) break;

        if (sscanf(line, "%63s", cmd) != 1) continue;

        if (strcmp(cmd, "quit") == 0 || strcmp(cmd, "exit") == 0) {
            break;
        } else if (strcmp(cmd, "help") == 0) {
            print_help();
        } else if (strcmp(cmd, "rev") == 0) {
            uint16_t rev = cta_l2cb_getFirmwareRevision();
            printf("L2CB Firmware Revision: 0x%04x (%u)\n", rev, rev);
        } else if (strcmp(cmd, "ts") == 0) {
            uint64_t ts = cta_l2cb_readTimestamp();
            printf("L2CB Timestamp: %" PRIu64 " (0x%012" PRIx64 ")\n", ts, ts);
        } else if (strcmp(cmd, "status") == 0) {
            uint16_t mcf, busy, tib;
            cta_l2cb_getControlState(&mcf, &busy, &tib);
            printf("L2CB Status:\n");
            printf("  MCF Enabled: %u\n", mcf);
            printf("  Busy Glitch Filter: %u\n", busy);
            printf("  TIB Trigger Busy Block: %u\n", tib);
        } else if (strcmp(cmd, "mcf") == 0) {
            uint16_t mcf, busy, tib;
            int val;
            if (sscanf(line, "%*s %d", &val) == 1) {
                cta_l2cb_setMCFEnabled(val);
                printf("MCF Enabled set to %d\n", val);
            } else {
                cta_l2cb_getControlState(&mcf, &busy, &tib);
                printf("MCF Enabled: %u\n", mcf);
            }
        } else if (strcmp(cmd, "mcf_thresh") == 0) {
            int val;
            if (sscanf(line, "%*s %d", &val) == 1) {
                cta_l2cb_setMCFThreshold(val);
                printf("MCF Threshold set to %d\n", val);
            } else {
                printf("MCF Threshold: %u\n", cta_l2cb_getMCFThreshold());
            }
        } else if (strcmp(cmd, "mcf_delay") == 0) {
            int val;
            if (sscanf(line, "%*s %d", &val) == 1) {
                cta_l2cb_setMCFDelay(val);
                printf("MCF Delay set to %d\n", val);
            } else {
                printf("MCF Delay: %u (%u ns)\n", cta_l2cb_getMCFDelay(), cta_l2cb_getMCFDelay() * 5);
            }
        } else if (strcmp(cmd, "deadtime") == 0) {
            int val;
            if (sscanf(line, "%*s %d", &val) == 1) {
                cta_l2cb_setL1Deadtime(val);
                printf("L1 Deadtime set to %d\n", val);
            } else {
                printf("L1 Deadtime: %u (%u ns)\n", cta_l2cb_getL1Deadtime(), cta_l2cb_getL1Deadtime() * 5);
            }
        } else if (strcmp(cmd, "slot_rev") == 0) {
            int slot;
            uint16_t rev;
            if (sscanf(line, "%*s %d", &slot) == 1) {
                int err = cta_ctdb_getFirmwareRevision(slot, &rev);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d Revision: 0x%04x\n", slot, rev);
                else printf("Error reading slot %d: %s\n", slot, cta_l2cb_getErrorString(err));
            } else printf("Usage: slot_rev <slot>\n");
        } else if (strcmp(cmd, "pwr_all") == 0) {
            int val;
            if (sscanf(line, "%*s %d", &val) == 1) {
                cta_ctdb_setPowerEnabledToAll(val);
                printf("All slots power set to %d\n", val);
            } else printf("Usage: pwr_all <0|1>\n");
        } else if (strcmp(cmd, "pwr_slot") == 0) {
            int slot;
            unsigned int mask;
            int n = sscanf(line, "%*s %d %x", &slot, &mask);
            if (n == 2) {
                int err = cta_ctdb_setPowerEnabled(slot, (uint16_t)mask);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d power mask set to 0x%04x\n", slot, mask);
                else printf("Error writing slot %d: %s\n", slot, cta_l2cb_getErrorString(err));
            } else if (n == 1) {
                uint16_t val;
                int err = cta_ctdb_getPowerEnabled(slot, &val);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d power mask: 0x%04x\n", slot, val);
                else printf("Error reading slot %d: %s\n", slot, cta_l2cb_getErrorString(err));
            } else printf("Usage: pwr_slot <slot> [hex_mask]\n");
        } else if (strcmp(cmd, "pwr_ch") == 0) {
            int slot, ch, val;
            int n = sscanf(line, "%*s %d %d %d", &slot, &ch, &val);
            if (n == 3) {
                int err = cta_ctdb_setPowerChannelEnabled(slot, ch, val);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d Channel %d power set to %d\n", slot, ch, val);
                else printf("Error: %s\n", cta_l2cb_getErrorString(err));
            } else if (n == 2) {
                int isOn;
                int err = cta_ctdb_getPowerChannelEnabled(slot, ch, &isOn);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d Channel %d power: %d\n", slot, ch, isOn);
                else printf("Error: %s\n", cta_l2cb_getErrorString(err));
            } else printf("Usage: pwr_ch <slot> <ch> [0|1]\n");
        } else if (strcmp(cmd, "curr") == 0) {
            int slot, ch;
            uint16_t val;
            if (sscanf(line, "%*s %d %d", &slot, &ch) == 2) {
                int err = cta_ctdb_getPowerCurrent(slot, ch, &val);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d %s Current: %u (%.2f mA)\n", 
                                                    slot, ch == 0 ? "CTDB" : "Channel", val, val * 0.485);
                else printf("Error: %s\n", cta_l2cb_getErrorString(err));
            } else printf("Usage: curr <slot> <ch>\n");
        } else if (strcmp(cmd, "curr_limits") == 0) {
            int slot;
            unsigned int min, max;
            int n = sscanf(line, "%*s %d %x %x", &slot, &min, &max);
            if (n == 3) {
                int err1 = cta_ctdb_setPowerCurrentMin(slot, (uint16_t)min);
                int err2 = cta_ctdb_setPowerCurrentMax(slot, (uint16_t)max);
                if (err1 == CTA_L2CB_NO_ERROR && err2 == CTA_L2CB_NO_ERROR)
                    printf("Slot %d current limits set to Min=0x%04x, Max=0x%04x\n", slot, min, max);
                else printf("Error setting current limits for slot %d\n", slot);
            } else if (n == 1) {
                uint16_t vmin, vmax;
                int err1 = cta_ctdb_getPowerCurrentMin(slot, &vmin);
                int err2 = cta_ctdb_getPowerCurrentMax(slot, &vmax);
                if (err1 == CTA_L2CB_NO_ERROR && err2 == CTA_L2CB_NO_ERROR)
                    printf("Slot %d current limits: Min=0x%04x (%.2f mA), Max=0x%04x (%.2f mA)\n", 
                           slot, vmin, vmin * 0.485, vmax, vmax * 0.485);
                else printf("Error reading current limits for slot %d\n", slot);
            } else printf("Usage: curr_limits <slot> [min max]\n");
        } else if (strcmp(cmd, "trig_slot") == 0) {
            int slot;
            unsigned int mask;
            int n = sscanf(line, "%*s %d %x", &slot, &mask);
            if (n == 2) {
                cta_l2cb_setL1TriggerEnabled(slot, (uint16_t)mask);
                printf("Slot %d trigger mask set to 0x%04x\n", slot, mask);
            } else if (n == 1) {
                uint16_t val = cta_l2cb_getL1TriggerEnabled(slot);
                printf("Slot %d trigger mask: 0x%04x\n", slot, val);
            } else printf("Usage: trig_slot <slot> [hex_mask]\n");
        } else if (strcmp(cmd, "trig_ch") == 0) {
            int slot, ch, val;
            int n = sscanf(line, "%*s %d %d %d", &slot, &ch, &val);
            if (n == 3) {
                cta_l2cb_setL1TriggerChannelEnabled(slot, ch, val);
                printf("Slot %d Channel %d trigger set to %d\n", slot, ch, val);
            } else if (n == 2) {
                uint16_t isOn = cta_l2cb_getL1TriggerChannelEnabled(slot, ch);
                printf("Slot %d Channel %d trigger: %u\n", slot, ch, isOn);
            } else printf("Usage: trig_ch <slot> <ch> [0|1]\n");
        } else if (strcmp(cmd, "trig_delay") == 0) {
            int slot, ch, val;
            int n = sscanf(line, "%*s %d %d %d", &slot, &ch, &val);
            if (n == 3) {
                int err = cta_l2cb_setL1TriggerDelay(slot, ch, val);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d Channel %d delay set to %d\n", slot, ch, val);
                else printf("Error: %s\n", cta_l2cb_getErrorString(err));
            } else if (n == 2) {
                uint16_t delay = cta_l2cb_getL1TriggerDelay(slot, ch);
                printf("Slot %d Channel %d delay: %u\n", slot, ch, delay);
            } else printf("Usage: trig_delay <slot> <ch> [val]\n");
        } else if (strcmp(cmd, "errors") == 0) {
            int slot;
            uint16_t over, under;
            if (sscanf(line, "%*s %d", &slot) == 1) {
                int err1 = cta_ctdb_getOverCurrentErrors(slot, &over);
                int err2 = cta_ctdb_getUnderCurrentErrors(slot, &under);
                if (err1 == CTA_L2CB_NO_ERROR && err2 == CTA_L2CB_NO_ERROR) {
                    printf("Slot %d Errors:\n", slot);
                    printf("  Over-current Mask:  0x%04x\n", over);
                    printf("  Under-current Mask: 0x%04x\n", under);
                } else printf("Error reading errors for slot %d\n", slot);
            } else printf("Usage: errors <slot>\n");
        } else if (strcmp(cmd, "reg_read") == 0) {
            int slot, reg;
            uint16_t val;
            if (sscanf(line, "%*s %d %i", &slot, &reg) == 2) {
                int err = cta_l2cb_spi_read(slot, reg, &val);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d Reg 0x%02x: 0x%04x (%u)\n", slot, reg, val, val);
                else printf("Error: %s\n", cta_l2cb_getErrorString(err));
            } else printf("Usage: reg_read <slot> <reg>\n");
        } else if (strcmp(cmd, "reg_write") == 0) {
            int slot, reg;
            unsigned int val;
            if (sscanf(line, "%*s %d %i %i", &slot, &reg, &val) == 3) {
                int err = cta_l2cb_spi_write(slot, reg, (uint16_t)val);
                if (err == CTA_L2CB_NO_ERROR) printf("Slot %d Reg 0x%02x set to 0x%04x\n", slot, reg, val);
                else printf("Error: %s\n", cta_l2cb_getErrorString(err));
            } else printf("Usage: reg_write <slot> <reg> <val>\n");
        } else {
            printf("Unknown command: %s. Type 'help' for available commands.\n", cmd);
        }
    }

    smc_close();
    return 0;
}
