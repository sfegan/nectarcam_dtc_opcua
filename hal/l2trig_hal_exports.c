/*
 * l2trig_hal_exports.c
 *
 * Export layer for Python binding
 * Wraps static inline functions from l2trig_hal.h as regular exported functions
 *
 * Define DUMMY to compile with dummy implementations for testing on systems
 * without the correct hardware registers. Getters return dummy values, setters are NOOPs.
 */

#include "l2trig_hal.h"
#include <stdio.h>

#ifdef DUMMY

#include <time.h>

// ============================================================================
// DUMMY STATE FOR TESTING
// ============================================================================

typedef struct {
    uint16_t power_enable;      // bits 1-15
    uint16_t trigger_mask;      // bits 0-14
    uint16_t trigger_delays[15];
    uint16_t current_min;
    uint16_t current_max;
    uint16_t firmware;
} DummySlot;

static DummySlot dummy_slots[32]; // Max slot index used is 21
static int dummy_initialized = 0;

static void init_dummy_state() {
    if (dummy_initialized) return;
    for (int i = 0; i < 32; i++) {
        dummy_slots[i].power_enable = 0x0000;    // All off
        dummy_slots[i].trigger_mask = 0x0000;    // All masked (assuming 1=active, 0=masked per API use)
        for (int j = 0; j < 15; j++) dummy_slots[i].trigger_delays[j] = 27; // ~1ns
        dummy_slots[i].current_min = 206;       // ~100mA
        dummy_slots[i].current_max = 4123;      // ~2000mA
        dummy_slots[i].firmware = 0x0100;
    }
    dummy_initialized = 1;
}

// ============================================================================
// DUMMY IMPLEMENTATIONS FOR TESTING
// ============================================================================

uint16_t cta_l2cb_getFirmwareRevision_export(void)
{
    printf("cta_l2cb_getFirmwareRevision()\n");
    fflush(stdout);
    return 0x0100;
}

uint64_t cta_l2cb_readTimestamp_export(void)
{
    // Return a monotonic-ish timestamp based on real time
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t timestamp = (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
    printf("cta_l2cb_readTimestamp() -> %llu\n", (unsigned long long)timestamp);
    fflush(stdout);
    return timestamp;
}

void cta_l2cb_setL1TriggerMask_export(uint8_t slot, uint16_t mask)
{
    init_dummy_state();
    if (slot < 32) {
        dummy_slots[slot].trigger_mask = mask;
        printf("cta_l2cb_setL1TriggerMask(slot=%u, mask=0x%04x)\n", slot, mask);
    }
    fflush(stdout);
}

uint16_t cta_l2cb_getL1TriggerMask_export(uint8_t slot)
{
    init_dummy_state();
    uint16_t mask = (slot < 32) ? dummy_slots[slot].trigger_mask : 0;
    printf("cta_l2cb_getL1TriggerMask(slot=%u) -> 0x%04x\n", slot, mask);
    fflush(stdout);
    return mask;
}

void cta_l2cb_setL1TriggerChannelMask_export(uint8_t slot, uint8_t channel, uint16_t on)
{
    init_dummy_state();
    if (slot < 32 && channel < 15) {
        if (on) dummy_slots[slot].trigger_mask |= (1 << channel);
        else dummy_slots[slot].trigger_mask &= ~(1 << channel);
        printf("cta_l2cb_setL1TriggerChannelMask(slot=%u, channel=%u, on=%u)\n", slot, channel, on);
    }
    fflush(stdout);
}

uint16_t cta_l2cb_getL1TriggerChannelMask_export(uint8_t slot, uint8_t channel)
{
    init_dummy_state();
    uint16_t active = 0;
    if (slot < 32 && channel < 15) {
        active = (dummy_slots[slot].trigger_mask & (1 << channel)) ? 1 : 0;
    }
    printf("cta_l2cb_getL1TriggerChannelMask(slot=%u, channel=%u) -> %u\n", slot, channel, active);
    fflush(stdout);
    return active;
}

int cta_l2cb_setL1TriggerDelay_export(uint8_t slot, uint8_t channel, uint16_t delay, uint16_t timeout_us)
{
    init_dummy_state();
    if (slot < 32 && channel < 15) {
        dummy_slots[slot].trigger_delays[channel] = delay;
        printf("cta_l2cb_setL1TriggerDelay(slot=%u, channel=%u, delay=%u)\n", slot, channel, delay);
    }
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

uint16_t cta_l2cb_getL1TriggerDelay_export(uint8_t slot, uint8_t channel)
{
    init_dummy_state();
    uint16_t delay = 0;
    if (slot < 32 && channel < 15) {
        delay = dummy_slots[slot].trigger_delays[channel];
    }
    printf("cta_l2cb_getL1TriggerDelay(slot=%u, channel=%u) -> %u\n", slot, channel, delay);
    fflush(stdout);
    return delay;
}

int cta_ctdb_setPowerEnable_export(uint8_t slot, uint16_t value, int timeout_us)
{
    init_dummy_state();
    if (slot < 32) {
        dummy_slots[slot].power_enable = value;
        printf("cta_ctdb_setPowerEnable(slot=%u, value=0x%04x)\n", slot, value);
    }
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerEnable_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    init_dummy_state();
    if (value && slot < 32) {
        *value = dummy_slots[slot].power_enable;
        printf("cta_ctdb_getPowerEnable(slot=%u) -> 0x%04x\n", slot, *value);
    }
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setPowerChannelEnable_export(uint8_t slot, uint16_t channel, int on, int timeout_us)
{
    init_dummy_state();
    if (slot < 32 && channel >= 1 && channel <= 15) {
        if (on) dummy_slots[slot].power_enable |= (1 << channel);
        else dummy_slots[slot].power_enable &= ~(1 << channel);
        printf("cta_ctdb_setPowerChannelEnable(slot=%u, channel=%u, on=%d)\n", slot, channel, on);
    }
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerChannelEnable_export(uint8_t slot, uint16_t channel, int* isOn, int timeout_us)
{
    init_dummy_state();
    if (isOn && slot < 32 && channel >= 1 && channel <= 15) {
        *isOn = (dummy_slots[slot].power_enable & (1 << channel)) ? 1 : 0;
        printf("cta_ctdb_getPowerChannelEnable(slot=%u, channel=%u) -> %d\n", slot, channel, *isOn);
    }
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

void cta_ctdb_setPowerEnableToAll_export(uint16_t on, int timeout_us)
{
    init_dummy_state();
    uint16_t val = on ? 0xFFFE : 0x0000;
    for (int i = 0; i < 32; i++) {
        dummy_slots[i].power_enable = val;
    }
    printf("cta_ctdb_setPowerEnableToAll(on=%u)\n", on);
    fflush(stdout);
}

int cta_ctdb_setPowerCurrentMax_export(uint8_t slot, uint16_t value, int timeout_us)
{
    init_dummy_state();
    if (slot < 32) dummy_slots[slot].current_max = value;
    printf("cta_ctdb_setPowerCurrentMax(slot=%u, value=%u)\n", slot, value);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerCurrentMax_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    init_dummy_state();
    if (value && slot < 32) *value = dummy_slots[slot].current_max;
    printf("cta_ctdb_getPowerCurrentMax(slot=%u) -> %u\n", slot, *value);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setPowerCurrentMin_export(uint8_t slot, uint16_t value, int timeout_us)
{
    init_dummy_state();
    if (slot < 32) dummy_slots[slot].current_min = value;
    printf("cta_ctdb_setPowerCurrentMin(slot=%u, value=%u)\n", slot, value);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerCurrentMin_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    init_dummy_state();
    if (value && slot < 32) *value = dummy_slots[slot].current_min;
    printf("cta_ctdb_getPowerCurrentMin(slot=%u) -> %u\n", slot, *value);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerCurrent_export(uint8_t slot, uint16_t channel, uint16_t* value, int timeout_us)
{
    init_dummy_state();
    if (!value || slot >= 32) return CTA_L2CB_NO_ERROR;

    if (channel == 0) {
        // Slot current = sum of enabled channels + base load
        uint32_t total_raw = 1023; // ~500mA base load
        for (int ch = 1; ch <= 15; ch++) {
            if (dummy_slots[slot].power_enable & (1 << ch)) {
                total_raw += 619; // ~300mA per channel
            }
        }
        *value = (uint16_t)(total_raw & 0x0FFF);
    } else if (channel <= 15) {
        if (dummy_slots[slot].power_enable & (1 << channel)) {
            *value = 619; // ~300mA
        } else {
            *value = 0;
        }
    } else {
        *value = 0;
    }

    printf("cta_ctdb_getPowerCurrent(slot=%u, channel=%u) -> %u\n", slot, channel, *value);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getUnderCurrentErrors_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    init_dummy_state();
    if (value && slot < 32) {
        // Simulate error if power is on but current is too low (not possible in this dummy logic yet)
        *value = 0x0000;
    }
    printf("cta_ctdb_getUnderCurrentErrors(slot=%u)\n", slot);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getOverCurrentErrors_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    init_dummy_state();
    if (value && slot < 32) {
        *value = 0x0000;
    }
    printf("cta_ctdb_getOverCurrentErrors(slot=%u)\n", slot);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getFirmwareRevision_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    init_dummy_state();
    if (value && slot < 32) *value = dummy_slots[slot].firmware;
    printf("cta_ctdb_getFirmwareRevision(slot=%u)\n", slot);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setDebugPins_export(uint8_t slot, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setDebugPins(slot=%u, value=0x%04x, timeout_us=%d)\n", slot, value, timeout_us);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;  // NOOP - return success
}

int cta_ctdb_getDebugPins_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getDebugPins(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    if (value) *value = 0x0000;  // Dummy debug pins
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getSlaveRegister_export(uint8_t slot, uint8_t address, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getSlaveRegister(slot=%u, address=0x%02x, timeout_us=%d)\n", slot, address, timeout_us);
    fflush(stdout);
    if (value) *value = 0xABCD;  // Dummy register value
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setSlaveRegister_export(uint8_t slot, uint8_t address, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setSlaveRegister(slot=%u, address=0x%02x, value=0x%04x, timeout_us=%d)\n", slot, address, value, timeout_us);
    fflush(stdout);
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

// ============================================================================
// L1 Trigger Control Functions
// ============================================================================

void cta_l2cb_setL1TriggerMask_export(uint8_t slot, uint16_t mask)
{
    printf("cta_l2cb_setL1TriggerMask(slot=%u, mask=0x%04x)\n", slot, mask);
    fflush(stdout);
    cta_l2cb_setL1TriggerMask(slot, mask);
}

uint16_t cta_l2cb_getL1TriggerMask_export(uint8_t slot)
{
    printf("cta_l2cb_getL1TriggerMask(slot=%u)\n", slot);
    fflush(stdout);
    return cta_l2cb_getL1TriggerMask(slot);
}

void cta_l2cb_setL1TriggerChannelMask_export(uint8_t slot, uint8_t channel, uint16_t on)
{
    printf("cta_l2cb_setL1TriggerChannelMask(slot=%u, channel=%u, on=%u)\n", slot, channel, on);
    fflush(stdout);
    cta_l2cb_setL1TriggerChannelMask(slot, channel, on);
}

uint16_t cta_l2cb_getL1TriggerChannelMask_export(uint8_t slot, uint8_t channel)
{
    printf("cta_l2cb_getL1TriggerChannelMask(slot=%u, channel=%u)\n", slot, channel);
    fflush(stdout);
    return cta_l2cb_getL1TriggerChannelMask(slot, channel);
}

int cta_l2cb_setL1TriggerDelay_export(uint8_t slot, uint8_t channel, uint16_t delay, uint16_t timeout_us)
{
    printf("cta_l2cb_setL1TriggerDelay(slot=%u, channel=%u, delay=%u, timeout_us=%u)\n", slot, channel, delay, timeout_us);
    fflush(stdout);
    return cta_l2cb_setL1TriggerDelay(slot, channel, delay, timeout_us);
}

uint16_t cta_l2cb_getL1TriggerDelay_export(uint8_t slot, uint8_t channel)
{
    printf("cta_l2cb_getL1TriggerDelay(slot=%u, channel=%u)\n", slot, channel);
    fflush(stdout);
    return cta_l2cb_getL1TriggerDelay(slot, channel);
}

// ============================================================================
// CTDB Power Control Functions
// ============================================================================

int cta_ctdb_setPowerEnable_export(uint8_t slot, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setPowerEnable(slot=%u, value=0x%04x, timeout_us=%d)\n", slot, value, timeout_us);
    fflush(stdout);
    return cta_ctdb_setPowerEnable(slot, value, timeout_us);
}

int cta_ctdb_getPowerEnable_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getPowerEnable(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    return cta_ctdb_getPowerEnable(slot, value, timeout_us);
}

int cta_ctdb_setPowerChannelEnable_export(uint8_t slot, uint16_t channel, int on, int timeout_us)
{
    printf("cta_ctdb_setPowerChannelEnable(slot=%u, channel=%u, on=%d, timeout_us=%d)\n", slot, channel, on, timeout_us);
    fflush(stdout);
    return cta_ctdb_setPowerChannelEnable(slot, channel, on, timeout_us);
}

int cta_ctdb_getPowerChannelEnable_export(uint8_t slot, uint16_t channel, int* isOn, int timeout_us)
{
    printf("cta_ctdb_getPowerChannelEnable(slot=%u, channel=%u, timeout_us=%d)\n", slot, channel, timeout_us);
    fflush(stdout);
    return cta_ctdb_getPowerChannelEnable(slot, channel, isOn, timeout_us);
}

void cta_ctdb_setPowerEnableToAll_export(uint16_t on, int timeout_us)
{
    printf("cta_ctdb_setPowerEnableToAll(on=%u, timeout_us=%d)\n", on, timeout_us);
    fflush(stdout);
    cta_ctdb_setPowerEnableToAll(on, timeout_us);
}

// ============================================================================
// CTDB Current Monitoring Functions
// ============================================================================

int cta_ctdb_setPowerCurrentMax_export(uint8_t slot, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setPowerCurrentMax(slot=%u, value=%u, timeout_us=%d)\n", slot, value, timeout_us);
    fflush(stdout);
    return cta_ctdb_setPowerCurrentMax(slot, value, timeout_us);
}

int cta_ctdb_getPowerCurrentMax_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getPowerCurrentMax(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    return cta_ctdb_getPowerCurrentMax(slot, value, timeout_us);
}

int cta_ctdb_setPowerCurrentMin_export(uint8_t slot, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setPowerCurrentMin(slot=%u, value=%u, timeout_us=%d)\n", slot, value, timeout_us);
    fflush(stdout);
    return cta_ctdb_setPowerCurrentMin(slot, value, timeout_us);
}

int cta_ctdb_getPowerCurrentMin_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getPowerCurrentMin(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    return cta_ctdb_getPowerCurrentMin(slot, value, timeout_us);
}

int cta_ctdb_getPowerCurrent_export(uint8_t slot, uint16_t channel, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getPowerCurrent(slot=%u, channel=%u, timeout_us=%d)\n", slot, channel, timeout_us);
    fflush(stdout);
    return cta_ctdb_getPowerCurrent(slot, channel, value, timeout_us);
}

int cta_ctdb_getUnderCurrentErrors_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getUnderCurrentErrors(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    return cta_ctdb_getUnderCurrentErrors(slot, value, timeout_us);
}

int cta_ctdb_getOverCurrentErrors_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getOverCurrentErrors(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    return cta_ctdb_getOverCurrentErrors(slot, value, timeout_us);
}

// ============================================================================
// CTDB Utility Functions
// ============================================================================

int cta_ctdb_getFirmwareRevision_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getFirmwareRevision(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    return cta_ctdb_getFirmwareRevision(slot, value, timeout_us);
}

int cta_ctdb_setDebugPins_export(uint8_t slot, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setDebugPins(slot=%u, value=0x%04x, timeout_us=%d)\n", slot, value, timeout_us);
    fflush(stdout);
    return cta_ctdb_setDebugPins(slot, value, timeout_us);
}

int cta_ctdb_getDebugPins_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getDebugPins(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    return cta_ctdb_getDebugPins(slot, value, timeout_us);
}

int cta_ctdb_getSlaveRegister_export(uint8_t slot, uint8_t address, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getSlaveRegister(slot=%u, address=0x%02x, timeout_us=%d)\n", slot, address, timeout_us);
    fflush(stdout);
    return cta_ctdb_getSlaveRegister(slot, address, value, timeout_us);
}

int cta_ctdb_setSlaveRegister_export(uint8_t slot, uint8_t address, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setSlaveRegister(slot=%u, address=0x%02x, value=0x%04x, timeout_us=%d)\n", slot, address, value, timeout_us);
    fflush(stdout);
    return cta_ctdb_setSlaveRegister(slot, address, value, timeout_us);
}

// ============================================================================
// Validation Helper
// ============================================================================

int cta_l2cb_isValidSlot_export(int slot)
{
    return cta_l2cb_isValidSLot(slot);
}

#endif  // DUMMY
