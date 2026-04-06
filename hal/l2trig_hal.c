#include <time.h>
#include <stdint.h>

#include "l2trig_hal.h"

cta_l2cb_spi_wait_config_t cta_l2cb_spi_wait_config_ctdb = {
    .spi_bit = BIT_CTA_L2CB_STAT_SPIBUSY,
    .earliest_command_ts = {0, 0},
    .earliest_read_ts = {0, 0},
    .min_command_delay_ns = 10000, // 10us default
    .min_read_delay_ns = 0,
    .timeout_ns = 100000 // 100us default
};

cta_l2cb_spi_wait_config_t cta_l2cb_spi_wait_config_delay = {
    .spi_bit = BIT_CTA_L2CB_STAT_DELAY_BUSY,
    .earliest_command_ts = {0, 0},
    .earliest_read_ts = {0, 0},
    .min_command_delay_ns = 10000, // 10us default
    .min_read_delay_ns = 0,
    .timeout_ns = 100000 // 100us default
};

void cta_l2cb_spi_set_delays(cta_l2cb_spi_wait_config_t* _config, int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns)
{
    if (!_config) return;
    _config->min_command_delay_ns = _min_command_delay_ns;
    _config->min_read_delay_ns = _min_read_delay_ns;
    _config->timeout_ns = _timeout_ns;
}

void cta_l2cb_spi_mark_command_sent(cta_l2cb_spi_wait_config_t* _config)
{
    if (!_config) return;
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);

    _config->earliest_command_ts = now;
    _config->earliest_command_ts.tv_nsec += _config->min_command_delay_ns;
    while (_config->earliest_command_ts.tv_nsec >= 1000000000LL) {
        _config->earliest_command_ts.tv_nsec -= 1000000000LL;
        _config->earliest_command_ts.tv_sec += 1;
    }

    _config->earliest_read_ts = now;
    _config->earliest_read_ts.tv_nsec += _config->min_read_delay_ns;
    while (_config->earliest_read_ts.tv_nsec >= 1000000000LL) {
        _config->earliest_read_ts.tv_nsec -= 1000000000LL;
        _config->earliest_read_ts.tv_sec += 1;
    }
}

int cta_l2cb_spi_generalized_wait(cta_l2cb_spi_wait_config_t* _config, int _is_read)
{
    if (!_config) return CTA_L2CB_INVALID_PARAMETER;

    struct timespec now, target;
    clock_gettime(CLOCK_MONOTONIC, &now);

    target = _is_read ? _config->earliest_read_ts : _config->earliest_command_ts;

    while (now.tv_sec < target.tv_sec || (now.tv_sec == target.tv_sec && now.tv_nsec < target.tv_nsec))
    {
        struct timespec sleep_ts = {0, 10000}; // 10us
        nanosleep(&sleep_ts, NULL);
        clock_gettime(CLOCK_MONOTONIC, &now);
    }

    struct timespec start = now;
    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), _config->spi_bit))
    {
        clock_gettime(CLOCK_MONOTONIC, &now);
        int64_t elapsed_ns = (int64_t)(now.tv_sec - start.tv_sec) * 1000000000LL + (int64_t)(now.tv_nsec - start.tv_nsec);
        if (elapsed_ns >= _config->timeout_ns) return CTA_L2CB_ERROR_TIMEOUT;

        struct timespec sleep_ts = {0, 10000};
        nanosleep(&sleep_ts, NULL);
    }

    if (!_is_read) {
        cta_l2cb_spi_mark_command_sent(_config);
    }

    return CTA_L2CB_NO_ERROR;
}

// wait for a spi transfer to complete
int cta_l2cb_spi_wait(void)
{
    return cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 1);
}

// reads a register from a CTDB at slot x
int cta_l2cb_spi_read(uint8_t _slot, uint8_t _register, uint16_t* _value)
{
	if (!_value) return CTA_L2CB_INVALID_PARAMETER;
	if (!cta_l2cb_isValidSLot(_slot)) return CTA_L2CB_INVALID_PARAMETER;

	// wait for completion of previous command and enough delay for next command
	int err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 0);
	if (err != CTA_L2CB_NO_ERROR) return err;

	// initiate transfer
	uint16_t config = (_register & 0xff) | ((_slot & 0x1f) << 8);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, config);

	// wait for completion and enough delay for read
	err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 1);
	if (err != CTA_L2CB_NO_ERROR) return err;

	// store return value
	*_value = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPRX);
	return CTA_L2CB_NO_ERROR;
}

// writes a register to a CTDB at slot x
int cta_l2cb_spi_write(uint8_t _slot, uint8_t _register, uint16_t _value)
{
	if (!cta_l2cb_isValidSLot(_slot)) return CTA_L2CB_INVALID_PARAMETER;

	// wait for completion of previous command and enough delay for next command
	int err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 0);
	if (err != CTA_L2CB_NO_ERROR) return err;

	// initiate transfer
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPTX, _value);
	uint16_t config = (_register & 0xff) | ((_slot & 0x1f) << 8) | 0x8000;
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, config);

	// wait for completion
	err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_ctdb, 1);
	if (err != CTA_L2CB_NO_ERROR) return err;

	return CTA_L2CB_NO_ERROR;
}



