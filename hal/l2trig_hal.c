#include <stdint.h>
#include <stdio.h>

#include "l2trig_hal.h"

ctdb_spi_readwrite_timing_t g_ctdb_spi_timing = {
    .addressing_wait_iters = 8,
    .readwrite_wait_iters = 32,
    .timeout_iters = 1000
};

cta_l2cb_spi_wait_config_t cta_l2cb_spi_wait_config_delay = {
    .spi_bit = BIT_CTA_L2CB_STAT_DELAY_BUSY,
    .initial_wait_iters = 8,
    .inter_command_iters = 32,
    .timeout_iters = 1000
};

uint32_t g_l2trig_ts_edge_delay_iters = 16;
uint32_t g_l2trig_ts_latch_delay_iters = 16;
uint32_t g_l2trig_ts_unchanged_iters = 16;

void cta_l2cb_spi_set_timing_iters(cta_l2cb_spi_wait_config_t* _config, uint32_t _initial, uint32_t _inter, uint32_t _timeout)
{
    if (!_config) return;
    _config->initial_wait_iters = _initial;
    _config->inter_command_iters = _inter;
    _config->timeout_iters = _timeout;
}

void cta_l2cb_set_ts_timing_iters(uint32_t _edge, uint32_t _latch)
{
    g_l2trig_ts_edge_delay_iters = _edge;
    g_l2trig_ts_latch_delay_iters = _latch;
}

int cta_l2cb_spi_generalized_wait(cta_l2cb_spi_wait_config_t* _config, int _is_read)
{
    (void)_is_read;
    if (!_config) return CTA_L2CB_INVALID_PARAMETER;

    cta_l2cb_delay_cycles(_config->initial_wait_iters);

    uint32_t timeout_count = _config->timeout_iters;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), _config->spi_bit))
    {
        if (--timeout_count == 0) return CTA_L2CB_ERROR_TIMEOUT;
    }

    cta_l2cb_delay_cycles(_config->inter_command_iters);

    return CTA_L2CB_NO_ERROR;
}

int cta_l2cb_spi_wait(void)
{
    uint32_t timeout_count = g_ctdb_spi_timing.timeout_iters;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), BIT_CTA_L2CB_STAT_SPIBUSY))
    {
        if (--timeout_count == 0) return CTA_L2CB_ERROR_TIMEOUT;
    }
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
