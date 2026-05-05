/*
 * l2trig_direct_client.c
 *
 * Command line interface to exercise the L2 Trigger HAL
 * Mirrors the Python l2trig_direct_client.py interface.
 *
 * Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
 * Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <unistd.h>
#include <strings.h>
#include <ctype.h>

#include "l2trig_hal.h"
#include "smc.h"

// ============================================================================
// Parsing Utilities
// ============================================================================

long parse_int(const char* s) {
    if (!s) return 0;
    return strtol(s, NULL, 0);
}

int parse_bool(const char* s) {
    if (!s) return -1;
    if (strcasecmp(s, "on") == 0 || strcasecmp(s, "true") == 0 || 
        strcasecmp(s, "yes") == 0 || strcmp(s, "1") == 0) return 1;
    if (strcasecmp(s, "off") == 0 || strcasecmp(s, "false") == 0 || 
        strcasecmp(s, "no") == 0 || strcmp(s, "0") == 0) return 0;
    return -1;
}

const char* bool_to_str(int val) {
    return val ? "ON" : "OFF";
}

// ============================================================================
// Command Handlers
// ============================================================================

void print_help() {
    printf("\nAvailable Commands:\n");
    printf("  l2cb_fw               : Get L2CB firmware revision\n");
    printf("  ts                    : Get L2CB timestamp\n");
    printf("  state                 : Get L2CB control state\n");
    printf("  mcf <on|off>          : Set MCF enabled\n");
    printf("  glitch <on|off>       : Set busy glitch filter enabled\n");
    printf("  tibblock <on|off>     : Set TIB trigger busy block enabled\n");
    printf("  tib_count             : Get TIB event count\n");
    printf("  tib_reset             : Reset TIB event count\n");
    printf("  busy_mask [mask]      : Get or set unified 32-bit busy mask\n");
    printf("  busy_slot <s.> <o/f>: Set busy mask for specific slot\n");
    printf("  busy_stuck            : Get unified 32-bit busy stuck status\n");
    printf("  mcfthr [val]          : Get or set MCF threshold (L1 counts)\n");
    printf("  mcfdel [val]          : Get or set MCF delay (5ns/step)\n");
    printf("  deadtime [val]        : Get or set L1 deadtime (5ns/step)\n");
    printf("  trigmask <slot> [mask]: Get or set trigger mask (bit 0 masked)\n");
    printf("  trig <slot> <ch> [on/off]: Get or set trigger for channel\n");
    printf("  alltrig [on|off]      : Set all or show matrix of trigger masks\n");
    printf("  delay <slot> <ch> [v] : Get or set trigger delay (37ps/step)\n");
    printf("  alldelay [val]        : Set all or show matrix of trigger delays\n");
    printf("  powermask <slot> [msk]: Get or set power mask (bit 0 masked)\n");
    printf("  power <slot> <ch> [o/f]: Get or set power for channel\n");
    printf("  allpower [on|off]     : Set all or show matrix of power channels\n");
    printf("  curmax <slot> [val]   : Get or set max current limit (0.485mA/step)\n");
    printf("  allcurmax [val]       : Set all or show matrix of max current limits\n");
    printf("  curmin <slot> [val]   : Get or set min current limit (0.485mA/step)\n");
    printf("  allcurmin [val]       : Set all or show matrix of min current limits\n");
    printf("  cur <slot> <ch>       : Get channel current (code & mA)\n");
    printf("  under <slot>          : Get under-current error mask\n");
    printf("  over <slot>           : Get over-current error mask\n");
    printf("  ctdb_fw <slot>        : Get CTDB firmware revision\n");
    printf("  debug <slot> [val]    : Get or set debug pins\n");
    printf("  sreg <slot> <addr> [v]: Read or write slave register\n");
    printf("  reg <addr> [val]      : Read or write L2CB register\n");
    printf("  help                  : Show this help message\n");
    printf("  exit/quit             : Exit client\n");
    printf("\nNote: Values can be decimal or hex (0x...). Booleans: on/off, true/false, 1/0, yes/no.\n");
}

void process_line(char* line) {
    // Strip comments
    char* comment = strchr(line, '#');
    if (comment) *comment = '\0';

    // Tokenize
    char* tokens[10];
    int n = 0;
    char* token = strtok(line, " \t\n\r");
    while (token && n < 10) {
        tokens[n++] = token;
        token = strtok(NULL, " \t\n\r");
    }

    if (n == 0) return;

    char* cmd = tokens[0];

    if (strcmp(cmd, "l2cb_fw") == 0) {
        printf("L2CB Firmware Revision: 0x%04X\n", cta_l2cb_getFirmwareRevision());
    } else if (strcmp(cmd, "ts") == 0) {
        printf("L2CB Timestamp: %" PRIu64 "\n", cta_l2cb_readTimestamp());
    } else if (strcmp(cmd, "state") == 0) {
        uint16_t mcf, glitch, tib;
        cta_l2cb_getControlState(&mcf, &glitch, &tib);
        printf("MCF Enabled: %s\n", bool_to_str(mcf));
        printf("Busy Glitch Filter Enabled: %s\n", bool_to_str(glitch));
        printf("TIB Trigger Busy Block Enabled: %s\n", bool_to_str(tib));
    } else if (strcmp(cmd, "mcf") == 0) {
        if (n < 2) printf("Usage: mcf <on|off>\n");
        else cta_l2cb_setMCFEnabled(parse_bool(tokens[1]));
    } else if (strcmp(cmd, "glitch") == 0) {
        if (n < 2) printf("Usage: glitch <on|off>\n");
        else cta_l2cb_setBusyGlitchFilterEnabled(parse_bool(tokens[1]));
    } else if (strcmp(cmd, "tibblock") == 0) {
        if (n < 2) printf("Usage: tibblock <on|off>\n");
        else cta_l2cb_setTIBTriggerBusyBlockEnabled(parse_bool(tokens[1]));
    } else if (strcmp(cmd, "tib_count") == 0) {
        printf("TIB Event Count: %u\n", cta_l2cb_getTIBEventCount());
    } else if (strcmp(cmd, "tib_reset") == 0) {
        cta_l2cb_resetTIBEventCount();
        printf("TIB Event Count reset.\n");
    } else if (strcmp(cmd, "busy_mask") == 0) {
        if (n > 1) {
            cta_l2cb_setBusyEnableMask(parse_int(tokens[1]));
        } else {
            uint32_t mask = cta_l2cb_getBusyEnableMask();
            printf("Busy Mask: 0x%08X (Slots: ", mask);
            int first = 1;
            for (int s = 1; s <= 21; s++) {
                if (mask & (1U << s)) {
                    printf("%s%d", first ? "" : ",", s);
                    first = 0;
                }
            }
            if (first) printf("none");
            printf(")\n");
        }
    } else if (strcmp(cmd, "busy_slot") == 0) {
        if (n < 3) printf("Usage: busy_slot <slot> <on|off>\n");
        else {
            int slot = parse_int(tokens[1]);
            int on = parse_bool(tokens[2]);
            cta_l2cb_setBusyEnableSlot(slot, on);
        }
    } else if (strcmp(cmd, "busy_stuck") == 0) {
        uint32_t stuck = cta_l2cb_getBusyStuck();
        printf("Busy Stuck Status: 0x%08X (Slots: ", stuck);
        int first = 1;
        for (int s = 1; s <= 21; s++) {
            if (stuck & (1U << s)) {
                printf("%s%d", first ? "" : ",", s);
                first = 0;
            }
        }
        if (first) printf("none");
        printf(")\n");
    } else if (strcmp(cmd, "mcfthr") == 0) {
        if (n > 1) cta_l2cb_setMCFThreshold(parse_int(tokens[1]));
        else printf("MCF Threshold: %u (L1 counts)\n", cta_l2cb_getMCFThreshold());
    } else if (strcmp(cmd, "mcfdel") == 0) {
        if (n > 1) cta_l2cb_setMCFDelay(parse_int(tokens[1]));
        else {
            uint16_t val = cta_l2cb_getMCFDelay();
            printf("MCF Delay: %u (%.1f ns)\n", val, val * 5.0);
        }
    } else if (strcmp(cmd, "deadtime") == 0) {
        if (n > 1) cta_l2cb_setL1Deadtime(parse_int(tokens[1]));
        else {
            uint16_t val = cta_l2cb_getL1Deadtime();
            printf("L1 Deadtime: %u (%.1f ns)\n", val, val * 5.0);
        }
    } else if (strcmp(cmd, "trigmask") == 0) {
        if (n < 2) printf("Usage: trigmask <slot> [mask]\n");
        else {
            int slot = parse_int(tokens[1]);
            if (n > 2) cta_l2cb_setL1TriggerEnabled(slot, parse_int(tokens[2]) & 0xFFFE);
            else printf("Slot %d Trigger Mask: 0x%04X\n", slot, cta_l2cb_getL1TriggerEnabled(slot));
        }
    } else if (strcmp(cmd, "trig") == 0) {
        if (n < 3) printf("Usage: trig <slot> <ch> [on|off]\n");
        else {
            int slot = parse_int(tokens[1]);
            int ch = parse_int(tokens[2]);
            if (n > 3) cta_l2cb_setL1TriggerChannelEnabled(slot, ch, parse_bool(tokens[3]));
            else printf("Slot %d Ch %d Trigger: %s\n", slot, ch, bool_to_str(cta_l2cb_getL1TriggerChannelEnabled(slot, ch)));
        }
    } else if (strcmp(cmd, "alltrig") == 0) {
        if (n < 2) {
            int slots[] = CTA_L2CB_SLOT_LIST;
            printf("      ");
            for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) printf("%3d", slots[s]);
            printf("\n");
            for (int ch = 1; ch <= 15; ch++) {
                printf("Ch%02d:", ch);
                for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) {
                    int on = cta_l2cb_getL1TriggerChannelEnabled(slots[s], ch);
                    printf("%3s", on ? "ON" : ".");
                }
                printf("\n");
            }
        } else {
            int on = parse_bool(tokens[1]);
            uint16_t mask = on ? 0xFFFE : 0x0000;
            int slots[] = CTA_L2CB_SLOT_LIST;
            for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) cta_l2cb_setL1TriggerEnabled(slots[s], mask);
        }
    } else if (strcmp(cmd, "delay") == 0) {
        if (n < 3) printf("Usage: delay <slot> <ch> [val]\n");
        else {
            int slot = parse_int(tokens[1]);
            int ch = parse_int(tokens[2]);
            if (n > 3) cta_l2cb_setL1TriggerDelay(slot, ch, parse_int(tokens[3]));
            else {
                uint16_t val = cta_l2cb_getL1TriggerDelay(slot, ch);
                printf("Slot %d Ch %d Delay: %u (%.0f ps)\n", slot, ch, val, val * 37.0);
            }
        }
    } else if (strcmp(cmd, "alldelay") == 0) {
        if (n < 2) {
            int slots[] = CTA_L2CB_SLOT_LIST;
            printf("      ");
            for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) printf("%5d", slots[s]);
            printf("\n");
            for (int ch = 1; ch <= 15; ch++) {
                printf("Ch%02d:", ch);
                for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) {
                    printf("%5u", cta_l2cb_getL1TriggerDelay(slots[s], ch));
                }
                printf("\n");
            }
        } else {
            int val = parse_int(tokens[1]);
            int slots[] = CTA_L2CB_SLOT_LIST;
            for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) {
                for (int ch = 1; ch <= 15; ch++) cta_l2cb_setL1TriggerDelay(slots[s], ch, val);
            }
        }
    } else if (strcmp(cmd, "powermask") == 0) {
        if (n < 2) printf("Usage: powermask <slot> [mask]\n");
        else {
            int slot = parse_int(tokens[1]);
            if (n > 2) cta_ctdb_setPowerEnabled(slot, parse_int(tokens[2]) & 0xFFFE);
            else {
                uint16_t val;
                cta_ctdb_getPowerEnabled(slot, &val);
                printf("Slot %d Power Mask: 0x%04X\n", slot, val);
            }
        }
    } else if (strcmp(cmd, "power") == 0) {
        if (n < 3) printf("Usage: power <slot> <ch> [on|off]\n");
        else {
            int slot = parse_int(tokens[1]);
            int ch = parse_int(tokens[2]);
            if (n > 3) cta_ctdb_setPowerChannelEnabled(slot, ch, parse_bool(tokens[3]));
            else {
                int on;
                cta_ctdb_getPowerChannelEnabled(slot, ch, &on);
                printf("Slot %d Ch %d Power: %s\n", slot, ch, bool_to_str(on));
            }
        }
    } else if (strcmp(cmd, "allpower") == 0) {
        if (n < 2) {
            int slots[] = CTA_L2CB_SLOT_LIST;
            printf("      ");
            for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) printf("%3d", slots[s]);
            printf("\n");
            for (int ch = 1; ch <= 15; ch++) {
                printf("Ch%02d:", ch);
                for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) {
                    int on;
                    cta_ctdb_getPowerChannelEnabled(slots[s], ch, &on);
                    printf("%3s", on ? "ON" : ".");
                }
                printf("\n");
            }
        } else {
            cta_ctdb_setPowerEnabledToAll(parse_bool(tokens[1]));
        }
    } else if (strcmp(cmd, "curmax") == 0) {
        if (n < 2) printf("Usage: curmax <slot> [val]\n");
        else {
            int slot = parse_int(tokens[1]);
            if (n > 2) cta_ctdb_setPowerCurrentMax(slot, parse_int(tokens[2]));
            else {
                uint16_t val;
                cta_ctdb_getPowerCurrentMax(slot, &val);
                printf("Slot %d Max Current Limit: %u (%.2f mA)\n", slot, val, val * 0.485);
            }
        }
    } else if (strcmp(cmd, "allcurmax") == 0) {
        if (n < 2) {
            int slots[] = CTA_L2CB_SLOT_LIST;
            printf("Slot: ");
            for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) printf("%5d", slots[s]);
            printf("\nVal:  ");
            for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) {
                uint16_t val;
                cta_ctdb_getPowerCurrentMax(slots[s], &val);
                printf("%5u", val);
            }
            printf("\n");
        } else {
            int val = parse_int(tokens[1]);
            int slots[] = CTA_L2CB_SLOT_LIST;
            for (int s = 0; s < CTA_L2CB_SLOT_COUNT; s++) cta_ctdb_setPowerCurrentMax(slots[s], val);
        }
    } else if (strcmp(cmd, "curmin") == 0) {
        if (n < 2) printf("Usage: curmin <slot> [val]\n");
        else {
            int slot = parse_int(tokens[1]);
            if (n > 2) cta_ctdb_setPowerCurrentMin(slot, parse_int(tokens[2]));
            else {
                uint16_t val;
                cta_ctdb_getPowerCurrentMin(slot, &val);
                printf("Slot %d Min Current Limit: %u (%.2f mA)\n", slot, val, val * 0.485);
            }
        }
    } else if (strcmp(cmd, "allcurmin") == 0) {
        if (n < 2) printf("Usage: allcurmin <val>\n");
        else {
            int val = parse_int(tokens[1]);
            for (int s = 1; s <= 21; s++) if (cta_l2cb_isValidSLot(s)) cta_ctdb_setPowerCurrentMin(s, val);
        }
    } else if (strcmp(cmd, "cur") == 0) {
        if (n < 3) printf("Usage: cur <slot> <ch>\n");
        else {
            int slot = parse_int(tokens[1]);
            int ch = parse_int(tokens[2]);
            uint16_t val;
            cta_ctdb_getPowerCurrent(slot, ch, &val);
            printf("Slot %d Ch %d Current: %u (%.2f mA)\n", slot, ch, val, val * 0.485);
        }
    } else if (strcmp(cmd, "under") == 0) {
        if (n < 2) printf("Usage: under <slot>\n");
        else {
            uint16_t val;
            int slot = parse_int(tokens[1]);
            cta_ctdb_getUnderCurrentErrors(slot, &val);
            printf("Slot %d Under-current Errors: 0x%04X\n", slot, val);
        }
    } else if (strcmp(cmd, "over") == 0) {
        if (n < 2) printf("Usage: over <slot>\n");
        else {
            uint16_t val;
            int slot = parse_int(tokens[1]);
            cta_ctdb_getOverCurrentErrors(slot, &val);
            printf("Slot %d Over-current Errors: 0x%04X\n", slot, val);
        }
    } else if (strcmp(cmd, "ctdb_fw") == 0) {
        if (n < 2) printf("Usage: ctdb_fw <slot>\n");
        else {
            uint16_t val;
            int slot = parse_int(tokens[1]);
            cta_ctdb_getFirmwareRevision(slot, &val);
            printf("Slot %d CTDB Firmware Revision: 0x%04X\n", slot, val);
        }
    } else if (strcmp(cmd, "debug") == 0) {
        if (n < 2) printf("Usage: debug <slot> [val]\n");
        else {
            int slot = parse_int(tokens[1]);
            if (n > 2) cta_ctdb_setDebugPins(slot, parse_int(tokens[2]));
            else {
                uint16_t val;
                cta_ctdb_getDebugPins(slot, &val);
                printf("Slot %d Debug Pins: 0x%04X\n", slot, val);
            }
        }
    } else if (strcmp(cmd, "sreg") == 0) {
        if (n < 3) printf("Usage: sreg <slot> <addr> [val]\n");
        else {
            int slot = parse_int(tokens[1]);
            int addr = parse_int(tokens[2]);
            if (n > 3) cta_ctdb_setSlaveRegister(slot, addr, parse_int(tokens[3]));
            else {
                uint16_t val;
                cta_ctdb_getSlaveRegister(slot, addr, &val);
                printf("Slot %d Reg 0x%02X: 0x%04X\n", slot, addr, val);
            }
        }
    } else if (strcmp(cmd, "reg") == 0) {
        if (n < 2) printf("Usage: reg <addr> [val]\n");
        else {
            int addr = parse_int(tokens[1]);
            if (n > 2) IOWR_16DIRECT(BASE_CTA_L2CB, addr, parse_int(tokens[2]));
            else {
                uint16_t val = IORD_16DIRECT(BASE_CTA_L2CB, addr);
                printf("L2CB Reg 0x%02X: 0x%04X\n", addr, val);
            }
        }
    } else if (strcmp(cmd, "help") == 0 || strcmp(cmd, "?") == 0) {
        print_help();
    } else if (strcmp(cmd, "exit") == 0 || strcmp(cmd, "quit") == 0) {
        exit(0);
    } else {
        printf("Unknown command: %s. Type 'help' for available commands.\n", cmd);
    }
}

// ============================================================================
// Main
// ============================================================================

int main(int argc, char** argv) {
    const char* dev = smc_default_device();
    FILE* input = stdin;
    int interactive = isatty(fileno(stdin));

    if (argc > 1) {
        // If argument is a file, open it. Otherwise assume it's a device.
        if (access(argv[1], R_OK) == 0) {
            input = fopen(argv[1], "r");
            if (!input) {
                perror("Error opening file");
                return 1;
            }
            interactive = 0;
        } else {
            dev = argv[1];
            if (argc > 2) {
                input = fopen(argv[2], "r");
                if (!input) {
                    perror("Error opening file");
                    return 1;
                }
                interactive = 0;
            }
        }
    }

    if (interactive) {
        printf("L2 Trigger Direct CLI Client (C version)\n");
        printf("Opening SMC device: %s\n", dev);
    }

    if (smc_open(dev) != ERROR_NONE) {
        fprintf(stderr, "Failed to open SMC device: %s\n", dev);
        return 1;
    }

    char line[256];
    if (interactive) {
        printf("Type 'help' for available commands or 'exit' to quit.\n");
    }

    while (1) {
        if (interactive) {
            printf("l2trig_direct> ");
            fflush(stdout);
        }

        if (!fgets(line, sizeof(line), input)) break;
        process_line(line);
    }

    if (input != stdin) fclose(input);
    smc_close();
    return 0;
}
