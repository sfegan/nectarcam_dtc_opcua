/***************************************************************************** 
 * File		  i4_bus_driver.c
 * created on 10.02.2012
 *****************************************************************************
 * Author:	M.Eng. Dipl.-Ing(FH) Marek Penno, EL/1L23, Tel:033762/77275 marekp
 * Email:	marek.penno@desy.de
 * Mail:	DESY, Platanenallee 6, 15738 Zeuthen
 *****************************************************************************
 * Description
 * 
 * Changes:
 *  - Added Support for choosing different bus devices
 *  - Added save close/opening
 *
 * 2013-06-14 MP Bug fix FPGA Error Readback
 *
 ****************************************************************************/

#include "smc.h"

#include <string.h>
#include <sys/types.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <stdlib.h>
#include <stdio.h>

#include "smc_ioctl_defines.h"

typedef struct {
	int bus_handle;
} smc_instance_t;

static smc_instance_t bus_instance = { .bus_handle = -1 };

// returns true, if bus is open
int smc_isOpen()
{
	return (bus_instance.bus_handle >= 0);
}

// returns default device name
const char* smc_default_device(void)
{
	return SMCBUS_DEVICE;
}

// opening the device
smc_driver_error_t smc_open(const char* devname)
{
	if (smc_isOpen()) smc_close();

	if (!devname) devname = smc_default_device();

	// open io memory device
	int handle = open(devname, O_RDWR);
	if (handle < 0) {
		fprintf(stderr, "Error opening device '%s'. Please check, if smc device driver is loaded.\n", devname);
		return ERROR_OPENING_DEVICE;
	}

	bus_instance.bus_handle = handle;
	return ERROR_NONE;
}

// close the device
void smc_close()
{
	if (!smc_isOpen()) return;
	close(bus_instance.bus_handle);
	bus_instance.bus_handle = -1;
}

// function checks, if bus is open and does halt the program if bus is not open
// --> early fail strategy
void smc_assertIsOpen()
{
	if (smc_isOpen()) return;

	fprintf(stderr, "### ERROR ### smc bus device not open! Internal program error!\n");
	exit(1);
}

// reads from smc memory location
unsigned short smc_rd16(unsigned int _addr)
{
	ioctl_smc_rdwr_t cmd;
	cmd.address = _addr;
	int ret = ioctl(bus_instance.bus_handle, IOCTL_SMC_RD16, &cmd);
	if (ret == 0) {
		return cmd.value;
	} else {
		fprintf(stderr, "### ERROR ### smc_rd16 error! Internal program error!\n");
		exit(1);
		return 0xDEAF;
	}
}

// reads from smc memory location
unsigned int smc_rd32(unsigned int _addr)
{
	ioctl_smc_rdwr_t cmd;
	cmd.address = _addr;
	int ret = ioctl(bus_instance.bus_handle, IOCTL_SMC_RD32, &cmd);
	if (ret == 0) {
		return cmd.value;
	} else {
		fprintf(stderr, "### ERROR ### smc_rd32 error! Internal program error!\n");
		exit(1);
		return 0xDEADBEAF;
	}
}

// writes to smc memory location
void smc_wr16(unsigned int _addr, unsigned short _value)
{
	ioctl_smc_rdwr_t cmd;
	cmd.address = _addr;
	cmd.value = _value;
	int ret = ioctl(bus_instance.bus_handle, IOCTL_SMC_WR16, &cmd);
	if (ret != 0) {
		fprintf(stderr, "### ERROR ### smc_wr16 error! Internal program error!\n");
		exit(1);
	}
}

// writes to smc memory location
void smc_wr32(unsigned int _addr, unsigned int _value)
{
	ioctl_smc_rdwr_t cmd;
	cmd.address = _addr;
	cmd.value = _value;
	int ret = ioctl(bus_instance.bus_handle, IOCTL_SMC_WR32, &cmd);
	if (ret != 0) {
		fprintf(stderr, "### ERROR ### smc_wr32 error! Internal program error!\n");
		exit(1);
	}
}
