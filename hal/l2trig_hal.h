/*
 * l2trig_hal.h
 *
 *  Created on: Dec 1, 2017
 *      Author: marekp
 *
 * Register Access Level Hardware Interface for the L2 trigger Controller Board (L2CB)
 * and its CTDB Boards inside the trigger crate.
 *
 * Hardware hierarchy:
 *
 * L2 Trigger Crate
 *  |
 *  |-- L2CB
 *       |
 *       |-- CTDB at slot 1..9 and 13..21
 *            |
 *            |-- Trigger Channel
 *            |
 *            |-- Power Channel
 *
 */

#ifndef SOURCE_DIRECTORY__SRC_CTAPOWER_L2CB_HAL_H_
#define SOURCE_DIRECTORY__SRC_CTAPOWER_L2CB_HAL_H_

#include <time.h>
#include <stdint.h>
#include "unistd.h"
#include "smc.h"
#include "bits.h"

#undef CEXTERN
#ifdef __cplusplus
    #define CEXTERN extern "C"
#else
    #define CEXTERN
#endif

typedef struct {
	int spi_bit;
	struct timespec earliest_command_ts;
	struct timespec earliest_read_ts;
	int64_t min_command_delay_ns;
	int64_t min_read_delay_ns;
	int64_t timeout_ns;
} cta_l2cb_spi_wait_config_t;

CEXTERN cta_l2cb_spi_wait_config_t cta_l2cb_spi_wait_config_ctdb;
CEXTERN cta_l2cb_spi_wait_config_t cta_l2cb_spi_wait_config_delay;

CEXTERN void cta_l2cb_spi_set_delays(cta_l2cb_spi_wait_config_t* _config, int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns);
CEXTERN int cta_l2cb_spi_generalized_wait(cta_l2cb_spi_wait_config_t* _config, int _is_read);
CEXTERN void cta_l2cb_spi_mark_command_sent(cta_l2cb_spi_wait_config_t* _config);

CEXTERN void cta_l2cb_spi_set_ctdb_delays_export(int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns);
CEXTERN void cta_l2cb_spi_set_delay_delays_export(int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns);

#define BASE_CTA_L2CB			0x00

#define ADDR_CTA_L2CB_CTRL		0x00
#define BIT_CTA_L2CB_CTRL_TIB_TRIG_BUSY_BLOCK	 0
#define BIT_CTA_L2CB_CTRL_BUSY_GLITCH_FILTER_EN	 12
#define BIT_CTA_L2CB_CTRL_MCF_EN		         13
#define BIT_CTA_L2CB_CTRL_LATCH_TIMESTAMP		 15

#define ADDR_CTA_L2CB_STAT		0x02
#define BIT_CTA_L2CB_STAT_SPIBUSY		0
#define BIT_CTA_L2CB_STAT_DELAY_BUSY	1

#define ADDR_CTA_L2CB_SPAD		0x04		// SPI Address register
#define ADDR_CTA_L2CB_SPTX		0x06		// SPI TX Data Register
#define ADDR_CTA_L2CB_SPRX		0x08		// SPI RX Data Register
#define ADDR_CTA_L2CB_TSTMP0	0x0a		// latched timestamp, bits 15..0
#define ADDR_CTA_L2CB_TSTMP1	0x0c		// latched timestamp, bits 31..16
#define ADDR_CTA_L2CB_TSTMP2	0x0e		// latched timestamp, bits 47..32
#define ADDR_CTA_L2CB_TEST		0x10		// Test Register, 16 bit r/w
#define ADDR_CTA_L2CB_L1SEL		0x12		// L1 Trigger channel select for masking and up delay adjust
#define ADDR_CTA_L2CB_L1MSK		0x14		// L1 Trigger mask for channels of selected L2-crate slot
#define ADDR_CTA_L2CB_L1DEL		0x16		// L1 Trigger Delay in 37 ps steps, 0..5ns range
#define ADDR_CTA_L2CB_MUTHR		0x18		// Muon threshold, amount of L1s, causing a Muon-trigger,
#define ADDR_CTA_L2CB_MUDEL		0x20		// Muon trigger delay, in steps of 5ns
#define ADDR_CTA_L2CB_L1DT		0x22		// L1 dead time in multiples of 5ns

#define ADDR_CTA_L2CB_FREV		0xfe		// Firmware Revision

// *** CTDB spi bus register ***
#define ADDR_CTA_CTDB_PONF		0x00		// power on/off registers
#define BASE_CTA_CTDB_CUR  		0x01		// base address of the 15 adc values readback registers (0x1 - 0xf)
#define ADDR_CTA_CTDB_CUR_00	0x10		// Current of the CTDB itself
#define ADDR_CTA_CTDB_CUR_MIN	0x11		// global FEB current lower limit
#define ADDR_CTA_CTDB_CUR_MAX	0x12		// global FEB current upper limit
#define ADDR_CTA_CTDB_OVER_CUR	0x13		// over current detected status register
#define ADDR_CTA_CTDB_UNDER_CUR	0x14		// under current detected status register
#define ADDR_CTA_CTDB_CTRL		0x20		// control register
#define BIT_CTA_CTDB_STAT_ERROR    0		// over or under current error bit
#define BIT_CTA_CTDB_STAT_ADC_OK   1		// adc values available

#define ADDR_CTA_CTDB_STAT		0x21		// status register
#define ADDR_CTA_CTDB_ADC_SRATE	0xFD		// adc rate register
#define ADDR_CTA_CTDB_DEBUG		0xFE		// programmable usage of the test pins sel0..3
#define ADDR_CTA_CTDB_FREV		0xff		// firmware revision

// *** HAL error codes definitions
#define CTA_L2CB_NO_ERROR 			0
#define CTA_L2CB_ERROR_TIMEOUT		1
#define CTA_L2CB_INVALID_PARAMETER 	2

inline static const char* cta_l2cb_getErrorString(int _error)
{
	switch (_error) {
	case CTA_L2CB_NO_ERROR: return "NO ERROR";
	case CTA_L2CB_ERROR_TIMEOUT: return "TIMEOUT ERROR";
	case CTA_L2CB_INVALID_PARAMETER: return "INVALID PARAMETER";
	default:
		return "UKNOWN ERROR";
	}
}

#define CTA_L2CB_CHANNEL_MIN		1
#define CTA_L2CB_CHANNEL_MAX		15
#define CTA_L2CB_CHANNEL_COUNT		15

#define CTA_L2CB_SLOT_LIST			{ 1, 2, 3, 4, 5, 6, 7, 8, 9, 13,14,15,16,17,18,19,20,21}
#define CTA_L2CB_SLOT_COUNT			18

// checks, if a slot is a valid slot
// return 1 if the slot is a valid existing slot
// return 0 if te slot does not exists
inline static int cta_l2cb_isValidSLot(int _slot)
{
	if (_slot>=1 && _slot<=9) return 1;
	if (_slot>=13 && _slot<=21) return 1;
	return 0;
}

// reads timestamp value
// for internal use only
static inline uint64_t cta_l2cb_readTimestamp(void)
{
	uint64_t tmp=0;
	
	// latch timestamp with a 0->1 transition of the latch bit
	uint16_t ctrl = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL);
	ctrl = changeBitVal16(ctrl, BIT_CTA_L2CB_CTRL_LATCH_TIMESTAMP, 0);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, ctrl);
	ctrl = changeBitVal16(ctrl, BIT_CTA_L2CB_CTRL_LATCH_TIMESTAMP, 1);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, ctrl);

	// wait a short time to ensure timestamp is latched and ready to read
	struct timespec sleep_ts = {0, 200}; // 200ns delay to ensure timestamp is latched and ready to read
	nanosleep(&sleep_ts, NULL);

	tmp=IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP0);
	tmp|=(uint64_t)IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP1) << 16;
	tmp|=(uint64_t)IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP2) << 32;

	return tmp;
}

// get the firmware revision 16bit value
static inline uint16_t cta_l2cb_getFirmwareRevision(void)
{
	return IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_FREV);
}

// get the configuration from the control register
static inline void cta_l2cb_getControlState(uint16_t* mcf_enabled, uint16_t* busy_glitch_filter_enabled, uint16_t* tib_trigger_busy_block_enabled)
{
	uint16_t value = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL);
	if(mcf_enabled) *mcf_enabled = testBitVal16(value, BIT_CTA_L2CB_CTRL_MCF_EN);
	if(busy_glitch_filter_enabled) *busy_glitch_filter_enabled = testBitVal16(value, BIT_CTA_L2CB_CTRL_BUSY_GLITCH_FILTER_EN);
	if(tib_trigger_busy_block_enabled) *tib_trigger_busy_block_enabled = testBitVal16(value, BIT_CTA_L2CB_CTRL_TIB_TRIG_BUSY_BLOCK);
}

static inline void cta_l2cb_setMCFEnabled(uint16_t _enabled)
{
	uint16_t val = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL);
	val = changeBitVal16(val, BIT_CTA_L2CB_CTRL_MCF_EN, _enabled);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, val);
}

static inline void cta_l2cb_setBusyGlitchFilterEnabled(uint16_t _enabled)
{
	uint16_t val = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL);
	val = changeBitVal16(val, BIT_CTA_L2CB_CTRL_BUSY_GLITCH_FILTER_EN, _enabled);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, val);
}

static inline void cta_l2cb_setTIBTriggerBusyBlockEnabled(uint16_t _enabled)
{
	uint16_t val = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL);
	val = changeBitVal16(val, BIT_CTA_L2CB_CTRL_TIB_TRIG_BUSY_BLOCK, _enabled);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, val);
}

// ***** Helper Functions to set and get muon candidate flag (MCF) parameters

static inline uint16_t cta_l2cb_getMCFThreshold()
{
	return IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_MUTHR) & 0x01FF;
}

static inline void cta_l2cb_setMCFThreshold(uint16_t _threshold)
{
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_MUTHR, _threshold & 0x01FF);
}

static inline uint16_t cta_l2cb_getMCFDelay()
{
	return IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_MUDEL) & 0x000F;
}

static inline void cta_l2cb_setMCFDelay(uint16_t _delay)
{
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_MUDEL, _delay & 0x000F);
}

// ***** Helper Functions to set and get L1 deadtime (L1DT) parameter

static inline uint16_t cta_l2cb_getL1Deadtime()
{
	return IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DT) & 0x00FF;
}

static inline void cta_l2cb_setL1Deadtime(uint16_t _delay)
{
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DT, _delay & 0x00FF);
}

// ***** Helper Functions to set trigger enabled status and delays

// select CTDB trigger cluster/channels by selecting a CTDB slot and CTDB cluster/channel
// for internal use only
static inline void cta_l2cb_l1sel(uint8_t _slot, uint8_t _channel)
{
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1SEL, ((_slot & 0x1f) << 4) | (_channel & 0xf));
}

// set trigger enabled status for CTDB trigger cluster/channels
static inline void cta_l2cb_setL1TriggerEnabled(uint8_t _slot, uint16_t _enabled)
{
	cta_l2cb_l1sel(_slot, 0); // channel parameter does matter at this point
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1MSK, _enabled);
}

// get trigger enabled status for CTDB trigger cluster/channels
static inline uint16_t cta_l2cb_getL1TriggerEnabled(uint8_t _slot)
{
	cta_l2cb_l1sel(_slot, 0); // channel parameter does matter at this point
	return IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1MSK);
}

// set trigger enabled status for given CTDB trigger cluster/channel
static inline void cta_l2cb_setL1TriggerChannelEnabled(uint8_t _slot, uint8_t _channel, uint16_t _on)
{
	cta_l2cb_l1sel(_slot, 0); // channel parameter does matter at this point
	uint16_t val=IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1MSK);
	val=changeBitVal16(val,_channel, _on);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1MSK, val);
}

// get trigger enabled status for CTDB trigger cluster/channel
static inline uint16_t cta_l2cb_getL1TriggerChannelEnabled(uint8_t _slot, uint8_t _channel)
{
	cta_l2cb_l1sel(_slot, 0); // channel parameter does matter at this point
	return testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1MSK), _channel);
}

// set trigger delay for a CTDB trigger cluster/channel
// if a set-delay process for the selected channel is ongoing, it waits until complete or timeout
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_l2cb_setL1TriggerDelay(uint8_t _slot, uint8_t _channel, uint16_t _delay)
{
	cta_l2cb_l1sel(_slot, _channel);

	// wait for completion of previous command and enough delay for next command
	int err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_delay, 0);
	if (err != CTA_L2CB_NO_ERROR) return err;

	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DEL, _delay);

	return CTA_L2CB_NO_ERROR;
}

// get trigger delay for a CTDB trigger cluster/channel
// if a set-delay process for the selected channel is ongoing, it waits until complete or timeout
// returns delay value that has been set last time
static inline uint16_t cta_l2cb_getL1TriggerDelay(uint8_t _slot, uint8_t _channel)
{
	cta_l2cb_l1sel(_slot, _channel);

	// wait for completion of previous command and enough delay for next command
	int err = cta_l2cb_spi_generalized_wait(&cta_l2cb_spi_wait_config_delay, 0);
	if (err != CTA_L2CB_NO_ERROR) return err;

	// get delay
	return IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DEL);
}

// ***** Helper Functions for the SPI Interface to access registers of the CTDB modules

// wait for a spi transfer to complete
// if no spi transfer is ongoing, it returns immediate
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
CEXTERN int cta_l2cb_spi_wait(void);

// reads a register from a CTDB at slot x
// valid register addresses are 0..255
// valid slot are 1..9 and 13..21
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
CEXTERN int cta_l2cb_spi_read(uint8_t _slot, uint8_t _register, uint16_t* _value);
// reads a register from a CTDB at slot x
// valid register addresses are 0..255
// valid slot are 1..9 and 13..21
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
CEXTERN int cta_l2cb_spi_write(uint8_t _slot, uint8_t _register, uint16_t _value);

// ***** Helper Functions to access registers aof the CTDB modules


// *** Helper Functions to control power of the CTDB channels


// set the CTDB Power On/Off Register
// bit 1..15 -> power channel 1..15
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setPowerEnabled(uint8_t _slot, uint16_t _value)
{
	return cta_l2cb_spi_write(_slot, ADDR_CTA_CTDB_PONF, _value);
}

// set the CTDB Power On/Off Register
// bit 1..15 -> power channel 1..15
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline void cta_ctdb_setPowerEnabledToAll(uint16_t _on)
{
	int s;
	int value=(_on)?0xfffe:0x0;
	int slots[] = CTA_L2CB_SLOT_LIST;
	for(s=0;s<CTA_L2CB_SLOT_COUNT;s++) {
		cta_l2cb_spi_write(slots[s], ADDR_CTA_CTDB_PONF, value);
	}
}

// get the CTDB Power On/Off Register
// bit 1..15 -> power channel 1..15
// returns readback value into *_value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerEnabled(uint8_t _slot, uint16_t* _value)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_PONF, _value);
}

// set the individual CTDB Power Channel On/Off
// _on : 1 = power requested to switch on , 0 = power requested to switch off
// returns CTA_L2CB_NO_ERROR on success
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setPowerChannelEnabled(uint8_t _slot, uint16_t _channel, int _on)
{
	uint16_t val=0;
	int err;
	err=cta_ctdb_getPowerEnabled(_slot, &val);
	if (err!=CTA_L2CB_NO_ERROR) return err;
	val=changeBitVal16(val,_channel, _on);
	return cta_ctdb_setPowerEnabled(_slot, val);
}

// get the individual CTDB Power Channel On/Off status
// returns power on/off status into *_isOn pointer, 1 = power requested to be on , 0 = power requested to be off
// Note: it is possible, that a enabled power channel is not "on" because of an error condition (over/under current)
// returns CTA_L2CB_NO_ERROR on success
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerChannelEnabled(uint8_t _slot, uint16_t _channel, int* _isOn)
{
	if (!_isOn) return CTA_L2CB_INVALID_PARAMETER;
	uint16_t val;
	int err;
	err=cta_ctdb_getPowerEnabled(_slot, &val);
	if (err!=CTA_L2CB_NO_ERROR) return err;
	*_isOn=testBitVal16(val,_channel);
	return CTA_L2CB_NO_ERROR;
}

// set the CTDB global max current limit
// bit 0..11 -> max value , 0.485mA / count
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setPowerCurrentMax(uint8_t _slot, uint16_t _value)
{
	return cta_l2cb_spi_write(_slot, ADDR_CTA_CTDB_CUR_MAX, _value);
}

// get the CTDB global max current limit
// bit 0..11 -> max value , 0.485mA / count
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerCurrentMax(uint8_t _slot, uint16_t* _value)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_CUR_MAX, _value);
}

// set the CTDB global min current limit
// bit 0..11 -> min value , 0.485mA / count
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setPowerCurrentMin(uint8_t _slot, uint16_t _value)
{
	return cta_l2cb_spi_write(_slot, ADDR_CTA_CTDB_CUR_MIN, _value);
}

// get the CTDB global min current limit
// bit 0..11 -> min value , 0.485mA / count
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerCurrentMin(uint8_t _slot, uint16_t* _value)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_CUR_MIN, _value);
}

// get the individual CTDB Power Channel current
// channel 0 returns CTDB own current
// channel 1..15 returns CTDB channel current...
// bit 0..11 -> adc value , 0.485mA / count
// returns adc value is read back into *_value pointer
// returns CTA_L2CB_NO_ERROR on success
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerCurrent(uint8_t _slot, uint16_t _channel, uint16_t* _value)
{
	uint8_t addr=0;
	if (_channel>15) return CTA_L2CB_INVALID_PARAMETER;
	if (_channel>0) addr=BASE_CTA_CTDB_CUR+_channel-1; else addr=ADDR_CTA_CTDB_CUR_00;
	if (!_value) return CTA_L2CB_INVALID_PARAMETER;
	return cta_l2cb_spi_read(_slot, addr, _value);
}

// get the CTDB power channels under current error vector
// bits 1..15 bit -> channel status 1..15, bit set -> under current error occurred
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getUnderCurrentErrors(uint8_t _slot, uint16_t* _value)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_UNDER_CUR, _value);
}

// get the CTDB power channels over current error vector
// bits 1..15 bit -> channel status 1..15, bit set -> over current error occurred
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getOverCurrentErrors(uint8_t _slot, uint16_t* _value)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_OVER_CUR, _value);
}

// get the CTDB firmware revision
// bit 0..15 -> revision code
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getFirmwareRevision(uint8_t _slot, uint16_t* _value)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_FREV, _value);
}

// set the CTDB Debug Pins
// value bits 0..3 -> SEL0..3
// for internal use only
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setDebugPins(uint8_t _slot, uint16_t _value)
{
	return cta_l2cb_spi_write(_slot, ADDR_CTA_CTDB_DEBUG, _value);
}

// get the CTDB Debug Pins
// value bits 0..3 -> SEL0..3
// for internal use only
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getDebugPins(uint8_t _slot, uint16_t* _value)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_DEBUG, _value);
}

static inline int cta_ctdb_getSlaveRegister(uint8_t _slot, uint8_t _address, uint16_t* _value)
{
	return cta_l2cb_spi_read(_slot, _address, _value);
}

static inline int cta_ctdb_setSlaveRegister(uint8_t _slot, uint8_t _address, uint16_t _value)
{
	return cta_l2cb_spi_write(_slot, _address, _value);
}


#endif /* SOURCE_DIRECTORY__SRC_CTAPOWER_L2CB_HAL_H_ */
