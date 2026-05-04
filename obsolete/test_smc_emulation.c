/*
 * test_smc_emulation.c
 * 
 * Test program demonstrating the emulated SMC driver functionality.
 * Tests register reads/writes and SPI transactions without hardware.
 */

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <assert.h>
#include <stdint.h>

#include "smc.h"

/* Forward declarations for HAL functions we'll use */
extern int cta_l2cb_spi_read(uint8_t _slot, uint8_t _register, uint16_t* _value);
extern int cta_l2cb_spi_write(uint8_t _slot, uint8_t _register, uint16_t _value);
extern void cta_l2cb_spi_set_ctdb_delays_export(int64_t _min_command_delay_ns, int64_t _min_read_delay_ns, int64_t _timeout_ns);
extern int cta_l2cb_isValidSLot(int _slot);

/* HAL constants */
#define BASE_CTA_L2CB 0x00
#define ADDR_CTA_L2CB_CTRL   0x00
#define ADDR_CTA_L2CB_STAT   0x02
#define ADDR_CTA_L2CB_SPAD   0x04
#define ADDR_CTA_L2CB_SPTX   0x06
#define ADDR_CTA_L2CB_SPRX   0x08
#define ADDR_CTA_L2CB_TSTMP0 0x0A
#define ADDR_CTA_L2CB_TSTMP1 0x0C
#define ADDR_CTA_L2CB_TSTMP2 0x0E
#define ADDR_CTA_L2CB_MUTHR  0x18
#define ADDR_CTA_L2CB_MUDEL  0x20
#define ADDR_CTA_L2CB_L1DT   0x22

#define CTA_L2CB_NO_ERROR 0

/* External test helper functions */
extern void smc_emu_set_ctdb_register(uint8_t slot, uint8_t reg_addr, uint16_t value);
extern uint16_t smc_emu_get_ctdb_register(uint8_t slot, uint8_t reg_addr);
extern void smc_emu_complete_spi(void);

void test_basic_register_access(void)
{
    printf("\n=== Test 1: Basic Register Access ===\n");
    
    /* Test read/write to TEST register */
    IOWR_16DIRECT(BASE_CTA_L2CB, 0x10, 0x1234);
    unsigned short value = IORD_16DIRECT(BASE_CTA_L2CB, 0x10);
    
    printf("TEST register: wrote 0x1234, read 0x%04X\n", value);
    assert(value == 0x1234);
    
    /* Test firmware revision read */
    unsigned short frev = IORD_16DIRECT(BASE_CTA_L2CB, 0xFE);
    printf("Firmware revision: 0x%04X\n", frev);
    assert(frev == 0x0021);
    
    printf("✓ Basic register access works\n");
}

void test_timestamp_latch(void)
{
    printf("\n=== Test 2: Timestamp Latch ===\n");
    
    /* Read CTRL register */
    unsigned short ctrl = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL);
    printf("Initial CTRL: 0x%04X\n", ctrl);
    
    /* Wait a bit */
    usleep(1000);
    
    /* Latch timestamp by toggling bit 15 */
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, ctrl | 0x8000);
    
    /* Read timestamp */
    unsigned short ts0 = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP0);
    unsigned short ts1 = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP1);
    unsigned short ts2 = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_TSTMP2);
    
    uint64_t timestamp = ((uint64_t)ts2 << 32) | ((uint64_t)ts1 << 16) | ts0;
    
    printf("Latched timestamp: 0x%016llX (counter ticks)\n", 
           (unsigned long long)timestamp);
    printf("  = %.3f µs (at 125 MHz = 8ns period)\n", 
           timestamp * 8.0 / 1000.0);
    
    /* Clear latch */
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_CTRL, ctrl & ~0x8000);
    
    printf("✓ Timestamp latch works\n");
}

void test_spi_transactions(void)
{
    printf("\n=== Test 3: SPI Transactions ===\n");
    
    /* Setup: Pre-populate a CTDB register with test data */
    uint8_t test_slot = 5;
    uint8_t test_reg = 0x20;
    uint16_t test_value = 0xABCD;
    
    smc_emu_set_ctdb_register(test_slot, test_reg, test_value);
    printf("Pre-set CTDB slot %d reg 0x%02X = 0x%04X\n", 
           test_slot, test_reg, test_value);
    
    /* Perform SPI read using HAL function */
    uint16_t read_value = 0;
    int err = cta_l2cb_spi_read(test_slot, test_reg, &read_value);
    
    printf("cta_l2cb_spi_read() returned: %d\n", err);
    printf("Read value: 0x%04X\n", read_value);
    
    assert(err == CTA_L2CB_NO_ERROR);
    assert(read_value == test_value);
    
    /* Perform SPI write */
    uint16_t write_value = 0x5678;
    err = cta_l2cb_spi_write(test_slot, test_reg, write_value);
    
    printf("cta_l2cb_spi_write(0x%04X) returned: %d\n", write_value, err);
    assert(err == CTA_L2CB_NO_ERROR);
    
    /* Verify the write */
    uint16_t verify_value = smc_emu_get_ctdb_register(test_slot, test_reg);
    printf("Verified CTDB slot %d reg 0x%02X = 0x%04X\n", 
           test_slot, test_reg, verify_value);
    assert(verify_value == write_value);
    
    printf("✓ SPI transactions work\n");
}

void test_status_register(void)
{
    printf("\n=== Test 4: Status Register ===\n");
    
    /* Check initial status */
    unsigned short stat = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT);
    printf("Initial STAT: 0x%04X\n", stat);
    printf("  SPI_BUSY: %d\n", (stat >> 0) & 1);
    printf("  DELAY_BUSY: %d\n", (stat >> 1) & 1);
    printf("  TIB_BUSY: %d\n", (stat >> 2) & 1);
    
    /* Initiate an SPI write (async) */
    printf("\nInitiating SPI write...\n");
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPTX, 0x9999);
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_SPAD, (1 << 15) | (3 << 8) | 0x10);
    
    /* Check status immediately */
    stat = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT);
    printf("STAT during transaction: 0x%04X\n", stat);
    printf("  SPI_BUSY: %d (should be 1)\n", (stat >> 0) & 1);
    
    /* Wait for completion */
    printf("Waiting for SPI to complete...\n");
    usleep(10000);  /* 10ms, well beyond 5.4µs */
    
    stat = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_STAT);
    printf("STAT after wait: 0x%04X\n", stat);
    printf("  SPI_BUSY: %d (should be 0)\n", (stat >> 0) & 1);
    
    assert(((stat >> 0) & 1) == 0);
    
    printf("✓ Status register dynamics work\n");
}

void test_hal_functions(void)
{
    printf("\n=== Test 5: HAL Functions ===\n");
    
    /* Test delay configuration */
    printf("Testing SPI delay configuration...\n");
    cta_l2cb_spi_set_ctdb_delays_export(20000, 5000, 200000);
    printf("✓ Delay configuration works\n");
    
    /* Test multiple SPI operations */
    printf("\nTesting sequential SPI operations...\n");
    for (int slot = 1; slot <= 3; slot++) {
        uint16_t value = 0x1000 + slot;
        int err = cta_l2cb_spi_write(slot, 0x00, value);
        assert(err == CTA_L2CB_NO_ERROR);
        printf("  Wrote 0x%04X to slot %d\n", value, slot);
    }
    printf("✓ Sequential operations work\n");
}

void test_configuration_registers(void)
{
    printf("\n=== Test 6: Configuration Registers ===\n");
    
    /* Test MUTHR */
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_MUTHR, 0x0030);
    unsigned short muthr = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_MUTHR);
    printf("MUTHR: wrote 0x0030, read 0x%04X\n", muthr);
    assert(muthr == 0x0030);
    
    /* Test MUDEL */
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_MUDEL, 0x000F);
    unsigned short mudel = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_MUDEL);
    printf("MUDEL: wrote 0x000F, read 0x%04X\n", mudel);
    assert(mudel == 0x000F);
    
    /* Test L1DT */
    IOWR_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DT, 0x0042);
    unsigned short l1dt = IORD_16DIRECT(BASE_CTA_L2CB, ADDR_CTA_L2CB_L1DT);
    printf("L1DT: wrote 0x0042, read 0x%04X\n", l1dt);
    assert(l1dt == 0x0042);
    
    printf("✓ Configuration registers work\n");
}

int main(int argc, char *argv[])
{
    printf("========================================\n");
    printf("  L2CB HAL Emulation Test Suite\n");
    printf("========================================\n");
    
    /* Open emulated driver */
    printf("\nOpening emulated SMC driver...\n");
    smc_driver_error_t err = smc_open(NULL);
    if (err != ERROR_NONE) {
        fprintf(stderr, "Failed to open emulated SMC driver\n");
        return 1;
    }
    
    /* Run tests */
    test_basic_register_access();
    test_timestamp_latch();
    test_spi_transactions();
    test_status_register();
    test_hal_functions();
    test_configuration_registers();
    
    /* Close driver */
    printf("\n========================================\n");
    printf("Closing emulated SMC driver...\n");
    smc_close();
    
    printf("\n✓✓✓ All tests passed! ✓✓✓\n");
    printf("========================================\n");
    
    return 0;
}
