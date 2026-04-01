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

#include "unistd.h"
#include "smc.h"
#include "bits.h"

#undef CEXTERN
#ifdef __cplusplus
    #define CEXTERN extern "C"
#else
    #define CEXTERN
#endif

#define BASE_CTA_L2CB			0x00
#define ADDR_CTA_L2CB_CTRL		0x00
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

#define ADDR_CTA_L2CB_FRREV		0xfe		// Firmware Revision

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
	// latch timestamp
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, 0x0000);
	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, 0x0001);

	tmp=IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP0);
	tmp|=IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP1) << 8;
	tmp|=IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP2) << 16;

	return tmp;
}

// get the firmware revision 16bit value
static inline uint16_t cta_l2cb_getFirmwareRevision(void)
{
	return IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_FRREV);
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
static inline int cta_l2cb_setL1TriggerDelay(uint8_t _slot, uint8_t _channel, uint16_t _delay, uint16_t _timeout_us)
{
	cta_l2cb_l1sel(_slot, _channel);
	// wait for trigger delay process to get ready, if busy
	int timer = 0;
	while(testBitVal16(IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT), BIT_CTA_L2CB_STAT_DELAY_BUSY))
	{
		// spi transfer ongoing, lets wait
		usleep(10);
		timer+=10;
		if(timer >= _timeout_us) return CTA_L2CB_ERROR_TIMEOUT; // error, timeout
	}

	IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DEL, _delay);

	return CTA_L2CB_NO_ERROR;
}

// get trigger delay for a CTDB trigger cluster/channel
// if a set-delay process for the selected channel is ongoing, it waits until complete or timeout
// returns delay value that has been set last time
static inline uint16_t cta_l2cb_getL1TriggerDelay(uint8_t _slot, uint8_t _channel)
{
	cta_l2cb_l1sel(_slot, _channel);
	// get delay
	return IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DEL);
}

// ***** Helper Functions for the SPI Interface to access registers of the CTDB modules

// wait for a spi transfer to complete
// if no spi transfer is ongoing, it returns immediate
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
CEXTERN int cta_l2cb_spi_wait(int _timeout_us);

// reads a register from a CTDB at slot x
// valid register addresses are 0..255
// valid slot are 1..9 and 13..21
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
CEXTERN int cta_l2cb_spi_read(uint8_t _slot, uint8_t _register, uint16_t* _value, int _timeout_us);
// reads a register from a CTDB at slot x
// valid register addresses are 0..255
// valid slot are 1..9 and 13..21
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
CEXTERN int cta_l2cb_spi_write(uint8_t _slot, uint8_t _register, uint16_t _value, int _timeout_us);

// ***** Helper Functions to access registers aof the CTDB modules


// *** Helper Functions to control power of the CTDB channels


// set the CTDB Power On/Off Register
// bit 1..15 -> power channel 1..15
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setPowerEnabled(uint8_t _slot, uint16_t _value, int _timeout_us)
{
	return cta_l2cb_spi_write(_slot, ADDR_CTA_CTDB_PONF, _value, _timeout_us);
}

// set the CTDB Power On/Off Register
// bit 1..15 -> power channel 1..15
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline void cta_ctdb_setPowerEnabledToAll(uint16_t _on, int _timeout_us)
{
	int s;
	int value=(_on)?0xfffe:0x0;
	int slots[] = CTA_L2CB_SLOT_LIST;
	for(s=0;s<CTA_L2CB_SLOT_COUNT;s++) {
		cta_l2cb_spi_write(slots[s], ADDR_CTA_CTDB_PONF, value, _timeout_us);
	}
}

// get the CTDB Power On/Off Register
// bit 1..15 -> power channel 1..15
// returns readback value into *_value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerEnabled(uint8_t _slot, uint16_t* _value, int _timeout_us)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_PONF, _value , _timeout_us);
}

// set the individual CTDB Power Channel On/Off
// _on : 1 = power requested to switch on , 0 = power requested to switch off
// returns CTA_L2CB_NO_ERROR on success
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setPowerChannelEnabled(uint8_t _slot, uint16_t _channel, int _on, int _timeout_us)
{
	uint16_t val=0;
	int err;
	err=cta_ctdb_getPowerEnabled(_slot, &val , _timeout_us);
	if (err!=CTA_L2CB_NO_ERROR) return err;
	val=changeBitVal16(val,_channel, _on);
	return cta_ctdb_setPowerEnabled(_slot, val, _timeout_us);
}

// get the individual CTDB Power Channel On/Off status
// returns power on/off status into *_isOn pointer, 1 = power requested to be on , 0 = power requested to be off
// Note: it is possible, that a enabled power channel is not "on" because of an error condition (over/under current)
// returns CTA_L2CB_NO_ERROR on success
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerChannelEnabled(uint8_t _slot, uint16_t _channel, int* _isOn, int _timeout_us)
{
	if (!_isOn) return CTA_L2CB_INVALID_PARAMETER;
	uint16_t val;
	int err;
	err=cta_ctdb_getPowerEnabled(_slot, &val , _timeout_us);
	if (err!=CTA_L2CB_NO_ERROR) return err;
	*_isOn=testBitVal16(val,_channel);
	return CTA_L2CB_NO_ERROR;
}

// set the CTDB global max current limit
// bit 0..11 -> max value , 0.485mA / count
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setPowerCurrentMax(uint8_t _slot, uint16_t _value, int _timeout_us)
{
	return cta_l2cb_spi_write(_slot, ADDR_CTA_CTDB_CUR_MAX, _value, _timeout_us);
}

// get the CTDB global max current limit
// bit 0..11 -> max value , 0.485mA / count
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerCurrentMax(uint8_t _slot, uint16_t* _value, int _timeout_us)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_CUR_MAX, _value , _timeout_us);
}

// set the CTDB global min current limit
// bit 0..11 -> min value , 0.485mA / count
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setPowerCurrentMin(uint8_t _slot, uint16_t _value, int _timeout_us)
{
	return cta_l2cb_spi_write(_slot, ADDR_CTA_CTDB_CUR_MIN, _value, _timeout_us);
}

// get the CTDB global min current limit
// bit 0..11 -> min value , 0.485mA / count
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerCurrentMin(uint8_t _slot, uint16_t* _value, int _timeout_us)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_CUR_MIN, _value , _timeout_us);
}

// get the individual CTDB Power Channel current
// channel 0 returns CTDB own current
// channel 1..15 returns CTDB channel current...
// bit 0..11 -> adc value , 0.485mA / count
// returns adc value is read back into *_value pointer
// returns CTA_L2CB_NO_ERROR on success
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getPowerCurrent(uint8_t _slot, uint16_t _channel, uint16_t* _value, int _timeout_us)
{
	uint8_t addr=0;
	if (_channel>15) return CTA_L2CB_INVALID_PARAMETER;
	if (_channel>0) addr=BASE_CTA_CTDB_CUR+_channel-1; else addr=ADDR_CTA_CTDB_CUR_00;
	if (!_value) return CTA_L2CB_INVALID_PARAMETER;
	return cta_l2cb_spi_read(_slot, addr, _value , _timeout_us);
}

// get the CTDB power channels under current error vector
// bits 1..15 bit -> channel status 1..15, bit set -> under current error occurred
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getUnderCurrentErrors(uint8_t _slot, uint16_t* _value, int _timeout_us)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_UNDER_CUR, _value , _timeout_us);
}

// get the CTDB power channels over current error vector
// bits 1..15 bit -> channel status 1..15, bit set -> over current error occurred
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getOverCurrentErrors(uint8_t _slot, uint16_t* _value, int _timeout_us)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_OVER_CUR, _value , _timeout_us);
}

// get the CTDB firmware revision
// bit 0..15 -> revision code
// returns readback value via _value pointer
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getFirmwareRevision(uint8_t _slot, uint16_t* _value, int _timeout_us)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_FREV, _value , _timeout_us);
}

// set the CTDB Debug Pins
// value bits 0..3 -> SEL0..3
// for internal use only
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_setDebugPins(uint8_t _slot, uint16_t _value, int _timeout_us)
{
	return cta_l2cb_spi_write(_slot, ADDR_CTA_CTDB_DEBUG, _value, _timeout_us);
}

// get the CTDB Debug Pins
// value bits 0..3 -> SEL0..3
// for internal use only
// returns CTA_L2CB_NO_ERROR on success,
// returns CTA_L2CB_ERROR_TIMEOUT on timeout error
static inline int cta_ctdb_getDebugPins(uint8_t _slot, uint16_t* _value, int _timeout_us)
{
	return cta_l2cb_spi_read(_slot, ADDR_CTA_CTDB_DEBUG, _value, _timeout_us);
}

static inline int cta_ctdb_getSlaveRegister(uint8_t _slot, uint8_t _address, uint16_t* _value, int _timeout_us)
{
	return cta_l2cb_spi_read(_slot, _address, _value, _timeout_us);
}

static inline int cta_ctdb_setSlaveRegister(uint8_t _slot, uint8_t _address, uint16_t _value, int _timeout_us)
{
	return cta_l2cb_spi_write(_slot, _address, _value, _timeout_us);
}


#endif /* SOURCE_DIRECTORY__SRC_CTAPOWER_L2CB_HAL_H_ */
