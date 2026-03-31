/*
 * l2trig_hal.c
 *
 *  Created on: Dec 1, 2017
 *      Author: marekp
 */

#include <time.h>
#include <stdint.h>

#include "l2trig_hal.h"

// ***** Helper Functions for the SPI Interface to access registers of the CTDB modules

// wait for a spi transfer to complete
// if no spi transfer is ongoing, it returns immediate
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
int cta_l2cb_spi_wait(int _timeout_us)
{
    if (_timeout_us <= 0)
        return CTA_L2CB_ERROR_TIMEOUT;

    const int64_t timeout_ns = (int64_t)_timeout_us * 1000;

    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);

    // Fixed small sleep interval (10 µs)
    const struct timespec sleep_ts = {
        .tv_sec = 0,
        .tv_nsec = 10000
    };

	// Simple relative sleep
	nanosleep(&sleep_ts, NULL);

    while (testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT),
                        BIT_CTA_L2CB_STAT_SPIBUSY))
    {
        clock_gettime(CLOCK_MONOTONIC, &now);

        int64_t elapsed_ns =
            (int64_t)(now.tv_sec - start.tv_sec) * 1000000000LL +
            (int64_t)(now.tv_nsec - start.tv_nsec);

        if (elapsed_ns >= timeout_ns)
            return CTA_L2CB_ERROR_TIMEOUT;

        // Simple relative sleep
        nanosleep(&sleep_ts, NULL);
    }

    return CTA_L2CB_NO_ERROR;
}

// reads a register from a CTDB at slot x
// valid register addresses are 0..255
// valid slot are 1..9 and 13..21
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
int cta_l2cb_spi_read(uint8_t _slot, uint8_t _register, uint16_t* _value, int _timeout_us)
{
	// check parameters
	if (!_value) return CTA_L2CB_INVALID_PARAMETER; // null pointer as parameter, not nice
	if ((_slot==0) || ((_slot>9) && (_slot<13)) || (_slot>21)) return CTA_L2CB_INVALID_PARAMETER;
	// wait for completion
	{
		int err=cta_l2cb_spi_wait(_timeout_us);
		if (err!=CTA_L2CB_NO_ERROR) return err; // return error
	}
	// initiate transfer
	uint16_t config = (_register & 0xff) | ((_slot & 0x1f) << 8);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, config);
	// wait for completion
	{
		int err=cta_l2cb_spi_wait(_timeout_us);
		if (err!=CTA_L2CB_NO_ERROR) return err; // return error
	}
	// store return value
	*_value=IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPRX);
	return CTA_L2CB_NO_ERROR;
}

// reads a register from a CTDB at slot x
// valid register addresses are 0..255
// valid slot are 1..9 and 13..21
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
int cta_l2cb_spi_write(uint8_t _slot, uint8_t _register, uint16_t _value, int _timeout_us)
{
	// check parameters
	if (!cta_l2cb_isValidSLot(_slot)) return CTA_L2CB_INVALID_PARAMETER;
	// wait for completion
	{
		int err=cta_l2cb_spi_wait(_timeout_us);
		if (err!=CTA_L2CB_NO_ERROR) return err; // return error
	}
	// initiate transfer
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPTX, _value);
	uint16_t config = (_register & 0xff) | ((_slot & 0x1f) << 8) | 0x8000;
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, config);
	// wait for completion
	{
		int err=cta_l2cb_spi_wait(_timeout_us);
		if (err!=CTA_L2CB_NO_ERROR) return err; // return error
	}
	return CTA_L2CB_NO_ERROR;
}



