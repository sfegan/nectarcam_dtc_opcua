#include <stdint.h>
#include <stdio.h>

#include "l2trig_hal.h"

ctdb_spi_readwrite_timing_t g_ctdb_spi_timing = {
    .addressing_wait_iters = 16,  // about 0.2us
    .readwrite_wait_iters = 16,  // about 0.2us
    .timeout_iters = 10  // 20us (more than enough to cover 8.4 us SPI read/write cycle)
};

l1_readwrite_timing_t g_l1_timing = {
    .addressing_wait_iters = 16,  // about 0.2us
    .timeout_iters = 10  // 20us (more than enough to cover 8.4 us SPI read/write cycle)
};

ts_trigger_timing_t g_timestamp_timing = {
    .edge_delay_iters = 16,  // about 0.2us
    .latch_delay_iters = 64, // about 0.8us
    .unchanged_iters = 16
};

int cta_l2cb_l1_wait(void)
{
    uint32_t timeout_count = g_l1_timing.timeout_iters;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), BIT_CTA_L2CB_STAT_DELAY_BUSY))
    {
        if (--timeout_count == 0) return CTA_L2CB_ERROR_TIMEOUT;
    }
    return CTA_L2CB_NO_ERROR;
}

// set trigger delay for a CTDB trigger cluster/channel
// if a set-delay process for the selected channel is ongoing, it waits until complete or timeout
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
int cta_l2cb_setL1TriggerDelay(uint16_t _slot, uint16_t _channel, uint16_t _delay)
{
	if (!cta_l2cb_isValidSLot(_slot)) return CTA_L2CB_INVALID_PARAMETER;
	if(_channel < CTA_L2CB_CHANNEL_MIN || _channel > CTA_L2CB_CHANNEL_MAX) return CTA_L2CB_INVALID_PARAMETER;

	cta_l2cb_l1sel(_slot, _channel);
    cta_l2cb_delay_cycles(g_l1_timing.addressing_wait_iters);

	// wait for completion of previous command and enough delay for next command
    uint32_t timeout_count = g_l1_timing.timeout_iters;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), BIT_CTA_L2CB_STAT_SPIBUSY))
    {
        if (--timeout_count == 0) return CTA_L2CB_ERROR_TIMEOUT;
    }

	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DEL, _delay & 0x007F);
	return CTA_L2CB_NO_ERROR;
}

// get trigger delay for a CTDB trigger cluster/channel
// if a set-delay process for the selected channel is ongoing, it waits until complete or timeout
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
int cta_l2cb_getL1TriggerDelay_err(uint16_t _slot, uint16_t _channel, uint16_t* _delay)
{
	if (!_delay) return CTA_L2CB_INVALID_PARAMETER;
	if (!cta_l2cb_isValidSLot(_slot)) return CTA_L2CB_INVALID_PARAMETER;
	if(_channel < CTA_L2CB_CHANNEL_MIN || _channel > CTA_L2CB_CHANNEL_MAX) return CTA_L2CB_INVALID_PARAMETER;

	cta_l2cb_l1sel(_slot, _channel);

	// wait for completion of previous command and enough delay for next command
    uint32_t timeout_count = g_l1_timing.timeout_iters;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), BIT_CTA_L2CB_STAT_SPIBUSY))
    {
        if (--timeout_count == 0) return CTA_L2CB_ERROR_TIMEOUT;
    }

	// get delay
	*_delay = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DEL);
	return CTA_L2CB_NO_ERROR;
}

int cta_l2cb_spi_read(uint16_t _slot, uint16_t _register, uint16_t* _value)
{
    // Ansatz: no previous SPI read/write is in progress when this function is called.
    // cta_l2cb_spi_read and cta_l2cb_spi_write wait for completion before returning

    if (!_value) return CTA_L2CB_INVALID_PARAMETER;
    if (!cta_l2cb_isValidSLot((int)_slot)) return CTA_L2CB_INVALID_PARAMETER;

    uint16_t config = (_register & 0xff) | ((_slot & 0x1f) << 8);
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, config);

    cta_l2cb_delay_cycles(g_ctdb_spi_timing.addressing_wait_iters);

    uint32_t timeout_count = g_ctdb_spi_timing.timeout_iters;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), BIT_CTA_L2CB_STAT_SPIBUSY))
    {
        if (--timeout_count == 0) return CTA_L2CB_ERROR_TIMEOUT;
    }

    cta_l2cb_delay_cycles(g_ctdb_spi_timing.readwrite_wait_iters);

    *_value = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPRX);
    return CTA_L2CB_NO_ERROR;
}

int cta_l2cb_spi_write(uint16_t _slot, uint16_t _register, uint16_t _value)
{
    // Ansatz: no previous SPI read/write is in progress when this function is called.
    // cta_l2cb_spi_read and cta_l2cb_spi_write wait for completion before returning

    if (!cta_l2cb_isValidSLot((int)_slot)) return CTA_L2CB_INVALID_PARAMETER;

    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPTX, _value);

    cta_l2cb_delay_cycles(g_ctdb_spi_timing.readwrite_wait_iters);

    uint16_t config = (_register & 0xff) | ((_slot & 0x1f) << 8) | 0x8000;
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, config);

    cta_l2cb_delay_cycles(g_ctdb_spi_timing.addressing_wait_iters);

    uint32_t timeout_count = g_ctdb_spi_timing.timeout_iters;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), BIT_CTA_L2CB_STAT_SPIBUSY))
    {
        if (--timeout_count == 0) return CTA_L2CB_ERROR_TIMEOUT;
    }

    return CTA_L2CB_NO_ERROR;
}
