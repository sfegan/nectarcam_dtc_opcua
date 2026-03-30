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

// ============================================================================
// DUMMY IMPLEMENTATIONS FOR TESTING
// ============================================================================

uint16_t cta_l2cb_getFirmwareRevision_export(void)
{
    printf("cta_l2cb_getFirmwareRevision()\n");
    fflush(stdout);
    return 0x0100;  // Dummy firmware version
}

uint64_t cta_l2cb_readTimestamp_export(void)
{
    printf("cta_l2cb_readTimestamp()\n");
    fflush(stdout);
    return 0x123456789ABCDEF0ULL;  // Dummy timestamp
}

void cta_l2cb_setL1TriggerMask_export(uint8_t slot, uint16_t mask)
{
    printf("cta_l2cb_setL1TriggerMask(slot=%u, mask=0x%04x)\n", slot, mask);
    fflush(stdout);
    // NOOP - for testing only
}

uint16_t cta_l2cb_getL1TriggerMask_export(uint8_t slot)
{
    printf("cta_l2cb_getL1TriggerMask(slot=%u)\n", slot);
    fflush(stdout);
    return 0xFFFF;  // Dummy mask - all channels enabled
}

void cta_l2cb_setL1TriggerChannelMask_export(uint8_t slot, uint8_t channel, uint16_t on)
{
    printf("cta_l2cb_setL1TriggerChannelMask(slot=%u, channel=%u, on=%u)\n", slot, channel, on);
    fflush(stdout);
    // NOOP - for testing only
}

uint16_t cta_l2cb_getL1TriggerChannelMask_export(uint8_t slot, uint8_t channel)
{
    printf("cta_l2cb_getL1TriggerChannelMask(slot=%u, channel=%u)\n", slot, channel);
    fflush(stdout);
    return 1;  // Dummy channel mask - enabled
}

int cta_l2cb_setL1TriggerDelay_export(uint8_t slot, uint8_t channel, uint16_t delay, uint16_t timeout_us)
{
    printf("cta_l2cb_setL1TriggerDelay(slot=%u, channel=%u, delay=%u, timeout_us=%u)\n", slot, channel, delay, timeout_us);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;  // NOOP - return success
}

uint16_t cta_l2cb_getL1TriggerDelay_export(uint8_t slot, uint8_t channel)
{
    printf("cta_l2cb_getL1TriggerDelay(slot=%u, channel=%u)\n", slot, channel);
    fflush(stdout);
    return 100;  // Dummy delay value
}

int cta_ctdb_setPowerEnable_export(uint8_t slot, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setPowerEnable(slot=%u, value=0x%04x, timeout_us=%d)\n", slot, value, timeout_us);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;  // NOOP - return success
}

int cta_ctdb_getPowerEnable_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getPowerEnable(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    if (value) *value = 0xFFFE;  // Dummy power status - all on except bit 0
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setPowerChannelEnable_export(uint8_t slot, uint16_t channel, int on, int timeout_us)
{
    printf("cta_ctdb_setPowerChannelEnable(slot=%u, channel=%u, on=%d, timeout_us=%d)\n", slot, channel, on, timeout_us);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;  // NOOP - return success
}

int cta_ctdb_getPowerChannelEnable_export(uint8_t slot, uint16_t channel, int* isOn, int timeout_us)
{
    printf("cta_ctdb_getPowerChannelEnable(slot=%u, channel=%u, timeout_us=%d)\n", slot, channel, timeout_us);
    fflush(stdout);
    if (isOn) *isOn = 1;  // Dummy power channel status - on
    return CTA_L2CB_NO_ERROR;
}

void cta_ctdb_setPowerEnableToAll_export(uint16_t on, int timeout_us)
{
    printf("cta_ctdb_setPowerEnableToAll(on=%u, timeout_us=%d)\n", on, timeout_us);
    fflush(stdout);
    // NOOP - for testing only
}

int cta_ctdb_setPowerCurrentMax_export(uint8_t slot, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setPowerCurrentMax(slot=%u, value=%u, timeout_us=%d)\n", slot, value, timeout_us);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;  // NOOP - return success
}

int cta_ctdb_getPowerCurrentMax_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getPowerCurrentMax(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    if (value) *value = 2048;  // Dummy max current limit
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_setPowerCurrentMin_export(uint8_t slot, uint16_t value, int timeout_us)
{
    printf("cta_ctdb_setPowerCurrentMin(slot=%u, value=%u, timeout_us=%d)\n", slot, value, timeout_us);
    fflush(stdout);
    return CTA_L2CB_NO_ERROR;  // NOOP - return success
}

int cta_ctdb_getPowerCurrentMin_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getPowerCurrentMin(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    if (value) *value = 512;  // Dummy min current limit
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getPowerCurrent_export(uint8_t slot, uint16_t channel, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getPowerCurrent(slot=%u, channel=%u, timeout_us=%d)\n", slot, channel, timeout_us);
    fflush(stdout);
    if (value) *value = 1024;  // Dummy current value
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getUnderCurrentErrors_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getUnderCurrentErrors(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    if (value) *value = 0x0000;  // No errors
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getOverCurrentErrors_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getOverCurrentErrors(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    if (value) *value = 0x0000;  // No errors
    return CTA_L2CB_NO_ERROR;
}

int cta_ctdb_getFirmwareRevision_export(uint8_t slot, uint16_t* value, int timeout_us)
{
    printf("cta_ctdb_getFirmwareRevision(slot=%u, timeout_us=%d)\n", slot, timeout_us);
    fflush(stdout);
    if (value) *value = 0x0100;  // Dummy firmware version
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
