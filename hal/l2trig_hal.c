#include <stdint.h>
#include <stdio.h>

#include "l2trig_hal.h"

// Calibrated for 400MHz ARM9 (~120 iters = 1us)
// Initial wait: 2us to allow SPI transfer to start
// Inter-command: 10us delay between commands
// Timeout: 1000 iters (~100us with ioctl overhead)

cta_l2cb_spi_wait_config_t cta_l2cb_spi_wait_config_ctdb = {
    .spi_bit = BIT_CTA_L2CB_STAT_SPIBUSY,
    .initial_wait_iters = 240, 
    .inter_command_iters = 1200,
    .timeout_iters = 10000 
};

cta_l2cb_spi_wait_config_t cta_l2cb_spi_wait_config_delay = {
    .spi_bit = BIT_CTA_L2CB_STAT_DELAY_BUSY,
    .initial_wait_iters = 240,
    .inter_command_iters = 1200,
    .timeout_iters = 10000
};

uint32_t g_l2trig_ts_edge_delay_iters = 120;  // 1us
uint32_t g_l2trig_ts_latch_delay_iters = 1200; // 10us

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

    // 1. Initial wait to allow hardware to register start
    cta_l2cb_delay_cycles(_config->initial_wait_iters);

    // 2. Poll bit with timeout
    uint32_t timeout_count = _config->timeout_iters;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), _config->spi_bit))
    {
        if (--timeout_count == 0) return CTA_L2CB_ERROR_TIMEOUT;
    }

    // 3. Mandatory inter-command delay to ensure bus stability
    cta_l2cb_delay_cycles(_config->inter_command_iters);

    return CTA_L2CB_NO_ERROR;
}

// wait for a spi transfer to complete
int cta_l2cb_spi_wait(void)
{
    return cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 0);
}

// reads a register from a CTDB at slot x
int cta_l2cb_spi_read(uint16_t _slot, uint16_t _register, uint16_t* _value)
{
	if (!_value) return CTA_L2CB_INVALID_PARAMETER;
	if (!cta_l2cb_isValidSLot((int)_slot)) return CTA_L2CB_INVALID_PARAMETER;

	// wait for completion of previous command
	int err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 0);
	if (err != CTA_L2CB_NO_ERROR) return err;

	// initiate transfer
	uint16_t config = (_register & 0xff) | ((_slot & 0x1f) << 8);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, config);

	// wait for completion
	err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 0);
	if (err != CTA_L2CB_NO_ERROR) return err;

	// store return value
	*_value = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPRX);
	return CTA_L2CB_NO_ERROR;
}

// writes a register to a CTDB at slot x
int cta_l2cb_spi_write(uint16_t _slot, uint16_t _register, uint16_t _value)
{
	if (!cta_l2cb_isValidSLot((int)_slot)) return CTA_L2CB_INVALID_PARAMETER;

	// wait for completion of previous command
	int err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 0);
	if (err != CTA_L2CB_NO_ERROR) return err;

	// initiate transfer
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPTX, _value);
	uint16_t config = (_register & 0xff) | ((_slot & 0x1f) << 8) | 0x8000;
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, config);

	// wait for completion
	err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 0);
	if (err != CTA_L2CB_NO_ERROR) return err;

	return CTA_L2CB_NO_ERROR;
}

// Compatibility exports
void cta_l2cb_spi_set_ctdb_delays_export(int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns) {
    // No longer using nanoseconds, but keep for ABI compatibility if needed
    (void)_min_command_delay_ns; (void)_min_read_delay_ns; (void)_timeout_ns;
}

void cta_l2cb_spi_set_delay_delays_export(int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns) {
    (void)_min_command_delay_ns; (void)_min_read_delay_ns; (void)_timeout_ns;
}

void cta_l2cb_spi_set_delays(cta_l2cb_spi_wait_config_t* _config, int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns) {
    (void)_config; (void)_min_command_delay_ns; (void)_min_read_delay_ns; (void)_timeout_ns;
}
