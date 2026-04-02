/*
 * l2trig_hal_exports.c
 *
 * Export layer for Python binding
 * Wraps static inline functions from l2trig_hal.h as regular exported functions
 *
 * Define DUMMY to compile with dummy implementations for testing on systems
 * without the correct hardware registers. Getters return dummy values, setters are NOOPs.
* 
* Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
* Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
*/

#include "l2trig_hal.h"
#include <stdio.h>

#ifdef DUMMY

#include <time.h>

// ============================================================================
// DUMMY STATE FOR TESTING
// ============================================================================

typedef struct {
    uint16_t power_enable;       // bits 1-15
    uint16_t trigger_enabled;    // bits 1-15
    uint16_t trigger_delays[16]; // index 1-15 used
    uint16_t current_min;
    uint16_t current_max;
    uint16_t firmware;
} DummySlot;

typedef struct {
    DummySlot slots[32]; // Max slot index used is 21, but we allocate 32 for simplicity
    struct timespec start_time;
    uint16_t mcf_enabled;
    uint16_t busy_glitch_filter_enabled;
    uint16_t tib_trigger_block_enabled;
    uint16_t initialized;
} DummyState;

static DummyState dummy_state = {
    .initialized = 0
};

static void init_dummy_state() {
    if (dummy_state.initialized) return;
    clock_gettime(CLOCK_MONOTONIC, &dummy_state.start_time);
    for (int i = 0; i < 32; i++) {
        dummy_state.slots[i].power_enable = 0x0000;    // All off
        dummy_state.slots[i].trigger_enabled = 0x0000; // All disabled (assuming 1=active, 0=disabled)
        for (int j = 0; j < 15; j++) dummy_state.slots[i].trigger_delays[j] = 27; // ~1ns
        dummy_state.slots[i].current_min = 206;       // ~100mA
        dummy_state.slots[i].current_max = 2000;      // ~1000mA
        dummy_state.slots[i].firmware = 0x0100;
    }
    dummy_state.mcf_enabled = 0;
    dummy_state.busy_glitch_filter_enabled = 0;
    dummy_state.tib_trigger_block_enabled = 0;
    dummy_state.initialized = 1;
}

// ============================================================================
// DUMMY IMPLEMENTATIONS FOR TESTING
// ============================================================================

uint16_t cta_l2cb_getFirmwareRevision_export(void)
{
#ifdef DUMMY_DEBUG
    printf("cta_l2cb_getFirmwareRevision()\n");
    fflush(stdout);
#endif
    return 0x0100;
}

uint64_t cta_l2cb_readTimestamp_export(void)
{
    // Return a monotonic-ish timestamp based on real time
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t timestamp = (uint64_t)(ts.tv_sec - dummy_state.start_time.tv_sec) * 1000000000ULL + (ts.tv_nsec - dummy_state.start_time.tv_nsec)/8; // Convert to 8ns units;
#ifdef DUMMY_DEBUG
    printf("cta_l2cb_readTimestamp() -> %llu\n", (unsigned long long)timestamp);
    fflush(stdout);
#endif
    return timestamp;
}

void cta_l2cb_getControlState_export(uint16_t* mcf_enabled, uint16_t* busy_glitch_filter_enabled, uint16_t* tib_trigger_block_enabled)
{
    init_dummy_state();
    if (mcf_enabled) *mcf_enabled = dummy_state.mcf_enabled;
    if (busy_glitch_filter_enabled) *busy_glitch_filter_enabled = dummy_state.busy_glitch_filter_enabled;
    if (tib_trigger_block_enabled) *tib_trigger_block_enabled = dummy_state.tib_trigger_block_enabled;
}

void cta_l2cb_setL1TriggerEnabled_export(uint8_t slot, uint16_t enabled)
{
    init_dummy_state();
    if (slot < 32) {
        dummy_state.slots[slot].trigger_enabled = enabled;
#ifdef DUMMY_DEBUG
        printf("cta_l2cb_setL1TriggerEnabled(slot=%u, enabled=0x%04x)\n", slot, enabled);
        fflush(stdout);
#endif
    }
}

uint16_t cta_l2cb_getL1TriggerEnabled_export(uint8_t slot)
{
    init_dummy_state();
    uint16_t enabled = (slot < 32) ? dummy_state.slots[slot].trigger_enabled : 0;
#ifdef DUMMY_DEBUG
    printf("cta_l2cb_getL1TriggerEnabled(slot=%u) -> 0x%04x\n", slot, enabled);
    fflush(stdout);
#endif
    return enabled;
}

void cta_l2cb_setL1TriggerChannelEnabled_export(uint8_t slot, uint8_t channel, uint16_t on)
{
    init_dummy_state();
    if (slot < 32 && channel < 15) {
        if (on) dummy_state.slots[slot].trigger_enabled |= (1 << channel);
        else dummy_state.slots[slot].trigger_enabled &= ~(1 << channel);
#ifdef DUMMY_DEBUG
        printf("cta_l2cb_setL1TriggerChannelEnabled(slot=%u, channel=%u, on=%u)\n", slot, channel, on);
        fflush(stdout);
#endif
    }
}

uint16_t cta_l2cb_getL1TriggerChannelEnabled_export(uint8_t slot, uint8_t channel)
{
    init_dummy_state();
    uint16_t active = 0;
    if (slot < 32 && channel < 15) {
        active = (dummy_state.slots[slot].trigger_enabled & (1 << channel)) ? 1 : 0;
    }
#ifdef DUMMY_DEBUG
    printf("cta_l2cb_getL1TriggerChannelEnabled(slot=%u, channel=%u) -> %u\n", slot, channel, active);
    fflush(stdout);
#endif
    return active;
}

int cta_l2cb_setL1TriggerDelay_export(uint8_t slot, uint8_t channel, uint16_t delay)
{
    init_dummy_state();
    if (slot < 32 && channel < 15) {
        dummy_state.slots[slot].trigger_delays[channel] = delay;
#ifdef DUMMY_DEBUG
        printf("cta_l2cb_setL1TriggerDelay(slot=%u, channel=%u, delay=%u)\n", slot, channel, delay);
        fflush(stdout);
#endif
    }
    return CTA_L2CB_NO_ERROR;
}

uint16_t cta_l2cb_getL1TriggerDelay_export(uint8_t slot, uint8_t channel)
{
    init_dummy_state();
    uint16_t delay = 0;
    if (slot < 32 && channel < 15) {
        delay = dummy_state.slots[slot].trigger_delays[channel];
    }
#ifdef DUMMY_DEBUG
    printf("cta_l2cb_getL1TriggerDelay(slot=%u, channel=%u) -> %u\n", slot, channel, delay);
    fflush(stdout);
#endif
    return delay;
}

int cta_ctdb_setPowerEnabled_export(uint8_t slot, uint16_t value)
{
    init_dummy_state();
    if (slot < 32) {
        dummy_state.slots[slot].power_enable = value;
#ifdef DUMMY_DEBUG
        printf("cta_ctdb_setPowerEnabled(slot=%u, value=0x%04x)\n", slot, value);
        fflush(stdout);
#endif
    }
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerEnabled_export(uint8_t slot, uint16_t* value)
{
    init_dummy_state();
    if (value && slot < 32) {
        *value = dummy_state.slots[slot].power_enable;
#ifdef DUMMY_DEBUG
        printf("cta_ctdb_getPowerEnabled(slot=%u) -> 0x%04x\n", slot, *value);
        fflush(stdout);
#endif
    }
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setPowerChannelEnabled_export(uint8_t slot, uint16_t channel, int on)
{
    init_dummy_state();
    if (slot < 32 && channel >= 1 && channel <= 15) {
        if (on) dummy_state.slots[slot].power_enable |= (1 << channel);
        else dummy_state.slots[slot].power_enable &= ~(1 << channel);
#ifdef DUMMY_DEBUG
        printf("cta_ctdb_setPowerChannelEnabled(slot=%u, channel=%u, on=%d)\n", slot, channel, on);
        fflush(stdout);
#endif
    }
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerChannelEnabled_export(uint8_t slot, uint16_t channel, int* isOn)
{
    init_dummy_state();
    if (isOn && slot < 32 && channel >= 1 && channel <= 15) {
        *isOn = (dummy_state.slots[slot].power_enable & (1 << channel)) ? 1 : 0;
#ifdef DUMMY_DEBUG
        printf("cta_ctdb_getPowerChannelEnabled(slot=%u, channel=%u) -> %d\n", slot, channel, *isOn);
        fflush(stdout);
#endif
    }
    return CTA_L2CB_NO_ERROR;
}

void cta_ctdb_setPowerEnabledToAll_export(uint16_t on)
{
    init_dummy_state();
    uint16_t val = on ? 0xFFFE : 0x0000;
    for (int i = 0; i < 32; i++) {
        dummy_state.slots[i].power_enable = val;
    }
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_setPowerEnabledToAll(on=%u)\n", on);
    fflush(stdout);
#endif
}

int cta_ctdb_setPowerCurrentMax_export(uint8_t slot, uint16_t value)
{
    init_dummy_state();
    if (slot < 32) dummy_state.slots[slot].current_max = value;
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_setPowerCurrentMax(slot=%u, value=%u)\n", slot, value);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerCurrentMax_export(uint8_t slot, uint16_t* value)
{
    init_dummy_state();
    if (value && slot < 32) *value = dummy_state.slots[slot].current_max;
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_getPowerCurrentMax(slot=%u) -> %u\n", slot, *value);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setPowerCurrentMin_export(uint8_t slot, uint16_t value)
{
    init_dummy_state();
    if (slot < 32) dummy_state.slots[slot].current_min = value;
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_setPowerCurrentMin(slot=%u, value=%u)\n", slot, value);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerCurrentMin_export(uint8_t slot, uint16_t* value)
{
    init_dummy_state();
    if (value && slot < 32) *value = dummy_state.slots[slot].current_min;
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_getPowerCurrentMin(slot=%u) -> %u\n", slot, *value);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerCurrent_export(uint8_t slot, uint16_t channel, uint16_t* value)
{
    init_dummy_state();
    if (!value || slot >= 32) return CTA_L2CB_NO_ERROR;

    if (channel == 0) {
        // Slot current = sum of enabled channels + base load
        uint32_t total_raw = 1023; // ~500mA base load
        for (int ch = 1; ch <= 15; ch++) {
            if (dummy_state.slots[slot].power_enable & (1 << ch)) {
                total_raw += 619; // ~300mA per channel
            }
        }
        *value = (uint16_t)(total_raw & 0x0FFF);
    } else if (channel <= 15) {
        if (dummy_state.slots[slot].power_enable & (1 << channel)) {
            *value = 619; // ~300mA
        } else {
            *value = 0;
        }
    } else {
        *value = 0;
    }

#ifdef DUMMY_DEBUG
    printf("cta_ctdb_getPowerCurrent(slot=%u, channel=%u) -> %u\n", slot, channel, *value);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getUnderCurrentErrors_export(uint8_t slot, uint16_t* value)
{
    init_dummy_state();
    if (value && slot < 32) {
        // Simulate error if power is on but current is too low (not possible in this dummy logic yet)
        *value = 0x0000;
    }
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_getUnderCurrentErrors(slot=%u)\n", slot);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getOverCurrentErrors_export(uint8_t slot, uint16_t* value)
{
    init_dummy_state();
    if (value && slot < 32) {
        *value = 0x0000;
    }
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_getOverCurrentErrors(slot=%u)\n", slot);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getFirmwareRevision_export(uint8_t slot, uint16_t* value)
{
    init_dummy_state();
    if (value && slot < 32) *value = dummy_state.slots[slot].firmware;
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_getFirmwareRevision(slot=%u)\n", slot);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setDebugPins_export(uint8_t slot, uint16_t value)
{
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_setDebugPins(slot=%u, value=0x%04x)\n", slot, value);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;  // NOOP - return success
}

int cta_ctdb_getDebugPins_export(uint8_t slot, uint16_t* value)
{
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_getDebugPins(slot=%u)\n", slot);
    fflush(stdout);
#endif
    if (value) *value = 0x0000;  // Dummy debug pins
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getSlaveRegister_export(uint8_t slot, uint8_t address, uint16_t* value)
{
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_getSlaveRegister(slot=%u, address=0x%02x)\n", slot, address);
    fflush(stdout);
#endif
    if (value) *value = 0xABCD;  // Dummy register value
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setSlaveRegister_export(uint8_t slot, uint8_t address, uint16_t value)
{
#ifdef DUMMY_DEBUG
    printf("cta_ctdb_setSlaveRegister(slot=%u, address=0x%02x, value=0x%04x)\n", slot, address, value);
    fflush(stdout);
#endif
    return CTA_L2CB_NO_ERROR;  // NOOP - return success
}

int cta_l2cb_isValidSlot_export(int slot)
{
    return cta_l2cb_isValidSLot(slot);  // Use the actual validation function
}

#else  // !DUMMY - REAL IMPLEMENTATIONS

// ============================================================================
// L2CB Functions
// ============================================================================

uint16_t cta_l2cb_getFirmwareRevision_export(void)
{
    return cta_l2cb_getFirmwareRevision();
}

uint64_t cta_l2cb_readTimestamp_export(void)
{
    return cta_l2cb_readTimestamp();
}

void cta_l2cb_getControlState_export(uint16_t* mcf_enabled, uint16_t* busy_glitch_filter_enabled, uint16_t* tib_trigger_block_enabled)
{
    cta_l2cb_getControlState(mcf_enabled, busy_glitch_filter_enabled, tib_trigger_block_enabled);
}

// ============================================================================
// L1 Trigger Control Functions
// ============================================================================

void cta_l2cb_setL1TriggerEnabled_export(uint8_t slot, uint16_t enabled)
{
    cta_l2cb_setL1TriggerEnabled(slot, enabled);
}

uint16_t cta_l2cb_getL1TriggerEnabled_export(uint8_t slot)
{
    return cta_l2cb_getL1TriggerEnabled(slot);
}

void cta_l2cb_setL1TriggerChannelEnabled_export(uint8_t slot, uint8_t channel, uint16_t on)
{
    cta_l2cb_setL1TriggerChannelEnabled(slot, channel, on);
}

uint16_t cta_l2cb_getL1TriggerChannelEnabled_export(uint8_t slot, uint8_t channel)
{
    return cta_l2cb_getL1TriggerChannelEnabled(slot, channel);
}

int cta_l2cb_setL1TriggerDelay_export(uint8_t slot, uint8_t channel, uint16_t delay)
{
    return cta_l2cb_setL1TriggerDelay(slot, channel, delay);
}

uint16_t cta_l2cb_getL1TriggerDelay_export(uint8_t slot, uint8_t channel)
{
    return cta_l2cb_getL1TriggerDelay(slot, channel);
}

// ============================================================================
// CTDB Power Control Functions
// ============================================================================

int cta_ctdb_setPowerEnabled_export(uint8_t slot, uint16_t value)
{
    return cta_ctdb_setPowerEnabled(slot, value);
}

int cta_ctdb_getPowerEnabled_export(uint8_t slot, uint16_t* value)
{
    return cta_ctdb_getPowerEnabled(slot, value);
}

int cta_ctdb_setPowerChannelEnabled_export(uint8_t slot, uint16_t channel, int on)
{
    return cta_ctdb_setPowerChannelEnabled(slot, channel, on);
}

int cta_ctdb_getPowerChannelEnabled_export(uint8_t slot, uint16_t channel, int* isOn)
{
    return cta_ctdb_getPowerChannelEnabled(slot, channel, isOn);
}

void cta_ctdb_setPowerEnabledToAll_export(uint16_t on)
{
    cta_ctdb_setPowerEnabledToAll(on);
}

// ============================================================================
// CTDB Current Monitoring Functions
// ============================================================================

int cta_ctdb_setPowerCurrentMax_export(uint8_t slot, uint16_t value)
{
    return cta_ctdb_setPowerCurrentMax(slot, value);
}

int cta_ctdb_getPowerCurrentMax_export(uint8_t slot, uint16_t* value)
{
    return cta_ctdb_getPowerCurrentMax(slot, value);
}

int cta_ctdb_setPowerCurrentMin_export(uint8_t slot, uint16_t value)
{
    return cta_ctdb_setPowerCurrentMin(slot, value);
}

int cta_ctdb_getPowerCurrentMin_export(uint8_t slot, uint16_t* value)
{
    return cta_ctdb_getPowerCurrentMin(slot, value);
}

int cta_ctdb_getPowerCurrent_export(uint8_t slot, uint16_t channel, uint16_t* value)
{
    return cta_ctdb_getPowerCurrent(slot, channel, value);
}

int cta_ctdb_getUnderCurrentErrors_export(uint8_t slot, uint16_t* value)
{
    return cta_ctdb_getUnderCurrentErrors(slot, value);
}

int cta_ctdb_getOverCurrentErrors_export(uint8_t slot, uint16_t* value)
{
    return cta_ctdb_getOverCurrentErrors(slot, value);
}

// ============================================================================
// CTDB Utility Functions
// ============================================================================

int cta_ctdb_getFirmwareRevision_export(uint8_t slot, uint16_t* value)
{
    return cta_ctdb_getFirmwareRevision(slot, value);
}

int cta_ctdb_setDebugPins_export(uint8_t slot, uint16_t value)
{
    return cta_ctdb_setDebugPins(slot, value);
}

int cta_ctdb_getDebugPins_export(uint8_t slot, uint16_t* value)
{
    return cta_ctdb_getDebugPins(slot, value);
}

int cta_ctdb_getSlaveRegister_export(uint8_t slot, uint8_t address, uint16_t* value)
{
    return cta_ctdb_getSlaveRegister(slot, address, value);
}

int cta_ctdb_setSlaveRegister_export(uint8_t slot, uint8_t address, uint16_t value)
{
    return cta_ctdb_setSlaveRegister(slot, address, value);
}

// ============================================================================
// SPI Configuration Functions
// ============================================================================

void cta_l2cb_spi_set_ctdb_delays_export(int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns)
{
#ifndef DUMMY
    cta_l2cb_spi_set_delays(&cta_l2cb_spi_wait_config_ctdb, _min_command_delay_ns, _min_read_delay_ns, _timeout_ns);
#endif
}

void cta_l2cb_spi_set_delay_delays_export(int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns)
{
#ifndef DUMMY
    cta_l2cb_spi_set_delays(&cta_l2cb_spi_wait_config_delay, _min_command_delay_ns, _min_read_delay_ns, _timeout_ns);
#endif
}

// ============================================================================
// Validation Helper
// ============================================================================

int cta_l2cb_isValidSlot_export(int slot)
{
    return cta_l2cb_isValidSLot(slot);
}

#endif  // DUMMY
