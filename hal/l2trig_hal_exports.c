/*
 * l2trig_hal_exports.c
 *
 * Export layer for Python binding
 * Wraps static inline functions from l2trig_hal.h as regular exported functions
 *
 * 
 * Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
 * Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
 */

#include "l2trig_hal.h"
#include <stdio.h>

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

void cta_l2cb_getControlState_export(uint16_t* mcf_enabled, uint16_t* busy_glitch_filter_enabled, uint16_t* tib_trigger_busy_block_enabled)
{
    cta_l2cb_getControlState(mcf_enabled, busy_glitch_filter_enabled, tib_trigger_busy_block_enabled);
}

void cta_l2cb_setMCFEnabled_export(uint16_t enabled)
{
    cta_l2cb_setMCFEnabled(enabled);
}

void cta_l2cb_setBusyGlitchFilterEnabled_export(uint16_t enabled)
{
    cta_l2cb_setBusyGlitchFilterEnabled(enabled);
}

void cta_l2cb_setTIBTriggerBusyBlockEnabled_export(uint16_t enabled)
{
    cta_l2cb_setTIBTriggerBusyBlockEnabled(enabled);
}

uint16_t cta_l2cb_getMCFThreshold_export()
{
    return cta_l2cb_getMCFThreshold();
}

void cta_l2cb_setMCFThreshold_export(uint16_t _threshold)
{
    cta_l2cb_setMCFThreshold(_threshold);
}

uint16_t cta_l2cb_getMCFDelay_export()
{
	return cta_l2cb_getMCFDelay();
}

void cta_l2cb_setMCFDelay_export(uint16_t _delay)
{
    cta_l2cb_setMCFDelay(_delay);
}

uint16_t cta_l2cb_getL1Deadtime_export()
{
    return cta_l2cb_getL1Deadtime();
}

void cta_l2cb_setL1Deadtime_export(uint16_t _delay)
{
    cta_l2cb_setL1Deadtime(_delay);
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
    cta_l2cb_spi_set_delays(&cta_l2cb_spi_wait_config_ctdb, _min_command_delay_ns, _min_read_delay_ns, _timeout_ns);
}

void cta_l2cb_spi_set_delay_delays_export(int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns)
{
    cta_l2cb_spi_set_delays(&cta_l2cb_spi_wait_config_delay, _min_command_delay_ns, _min_read_delay_ns, _timeout_ns);
}

// ============================================================================
// Validation Helper
// ============================================================================

int cta_l2cb_isValidSlot_export(int slot)
{
    return cta_l2cb_isValidSLot(slot);
}

// ============================================================================
// SMC open / close
// ============================================================================

int smc_open_export(const char* devname)
{
    return smc_open(devname);
}

void smc_close_export()
{
    smc_close();
}
