/***************************************************************************** 
 * File		  Intlk4BusDriver.h
 * created on 08.02.2012
 *****************************************************************************
 * Author:	M.Eng. Dipl.-Ing(FH) Marek Penno, EL/1L23, Tel:033762/77275 marekp
 * Email:	marek.penno@desy.de
 * Mail:	DESY, Platanenallee 6, 15738 Zeuthen
 *****************************************************************************
 * Description
 * 
 ****************************************************************************/

#ifndef USER_SMC_BUS_DRIVER_H_
#define USER_SMC_BUS_DRIVER_H_

#define SMCBUS_SIZE (32*1024*1024)
#define SMCBUS_DEVICE "/dev/smcbus0"

#ifdef __cplusplus
	extern "C" {
#endif

typedef enum {
	ERROR_NONE = 0,
	ERROR_OPENING_DEVICE=1,

} smc_driver_error_t;

// opening the device
smc_driver_error_t smc_open(const char* devname);

// returns default device name
const char* smc_default_device(void);

// close the device
void smc_close();

// returns true, if bus is open
int smc_isOpen();

// function checks, if bus is open and does halt the program if bus is not open
// --> early fail strategy
void smc_assertIsOpen();

// ********** ioctl based smc bus interface

// reads 16bit word from smc memory location
unsigned short 	smc_rd16(unsigned int _addr);

// reads 32bit word from smc memory location
unsigned int 	smc_rd32(unsigned int _addr);

// writes 16bit word to smc memory location
void 	smc_wr16(unsigned int _addr, unsigned short _value);

// writes 32bit word to smc memory location
void 	smc_wr32(unsigned int _addr, unsigned int _value);

// ********** IODIRECT_* functions

static inline void IOWR_16DIRECT(unsigned int base, unsigned int offset, unsigned short value)
{
	smc_wr16(base + offset, value);
}

static inline unsigned short IORD_16DIRECT(unsigned int base, unsigned int offset)
{
	return smc_rd16(base + offset);
}

static inline void IOWR_32DIRECT(unsigned int base, unsigned int offset, unsigned int data)
{
	smc_wr32(base + offset, data);
}

static inline unsigned int IORD_32DIRECT(unsigned int base, unsigned int offset)
{
	return smc_rd32(base + offset);
}

#ifdef __cplusplus
}	// extern "C"
#endif

#endif /* USER_SMC_BUS_DRIVER_H_ */
