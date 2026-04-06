/*
 * smc_emulated.c
 * 
 * Emulated SMC driver for testing the L2CB HAL without hardware.
 * Implements register-level simulation of the L2CB FPGA.
 * 
 * This implementation maintains an internal register map and simulates
 * the behavior of key registers like STAT, SPAD, SPTX, SPRX based on
 * the L2CB User Manual (MST-CAM-UM-0227-DESY v9).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <pthread.h>
#include <unistd.h>
#include <time.h>

#include "smc.h"

/* Enable emulation mode */
#define SMC_EMULATED 1

/* Simulated register memory size */
#define REGISTER_MEMORY_SIZE (32 * 1024 * 1024)

/* L2CB Register addresses (from user manual) */
#define ADDR_CTA_L2CB_CTRL    0x00
#define ADDR_CTA_L2CB_STAT    0x02
#define ADDR_CTA_L2CB_SPAD    0x04
#define ADDR_CTA_L2CB_SPTX    0x06
#define ADDR_CTA_L2CB_SPRX    0x08
#define ADDR_CTA_L2CB_TSTMP0  0x0A
#define ADDR_CTA_L2CB_TSTMP1  0x0C
#define ADDR_CTA_L2CB_TSTMP2  0x0E
#define ADDR_CTA_L2CB_TEST    0x10
#define ADDR_CTA_L2CB_L1SEL   0x12
#define ADDR_CTA_L2CB_L1MSK   0x14
#define ADDR_CTA_L2CB_L1DEL   0x16
#define ADDR_CTA_L2CB_MUTHR   0x18
#define ADDR_CTA_L2CB_MUDEL   0x20
#define ADDR_CTA_L2CB_L1DT    0x22
#define ADDR_CTA_L2CB_FREV    0xFE

/* Status register bits */
#define BIT_STAT_SPIBUSY      0
#define BIT_STAT_DELAY_BUSY   1
#define BIT_STAT_TIB_BUSY     2

/* Default firmware revision */
#define DEFAULT_FIRMWARE_REV  0x0021

/* CTDB slot configuration */
#define MAX_CTDB_SLOTS        32
#define CTDB_REGISTER_SIZE    256

/* CTDB Register addresses (from hal/l2trig_hal.h) */
#define ADDR_CTA_CTDB_PONF      0x00
#define BASE_CTA_CTDB_CUR       0x01
#define ADDR_CTA_CTDB_CUR_00    0x10
#define ADDR_CTA_CTDB_CUR_MIN   0x11
#define ADDR_CTA_CTDB_CUR_MAX   0x12
#define ADDR_CTA_CTDB_OVER_CUR  0x13
#define ADDR_CTA_CTDB_UNDER_CUR 0x14
#define ADDR_CTA_CTDB_FREV      0xFF

typedef struct {
    int is_open;
    pthread_mutex_t lock;
    
    /* Simulated register memory */
    unsigned char *memory;
    
    /* SPI transaction state */
    struct {
        int busy;
        struct timespec start_time;
        int duration_us;  /* Transaction duration in microseconds */
        int is_read;
        uint8_t slot;
        uint8_t reg_addr;
        uint16_t data;
    } spi_state;
    
    /* Delay adjustment state */
    struct {
        int busy;
        struct timespec start_time;
        int duration_us;
    } delay_state;
    
    /* Timestamp counter (48-bit, 125 MHz clock = 8ns period) */
    struct {
        uint64_t counter;
        int latched;
        struct timespec start_time;
    } timestamp;
    
    /* Simulated CTDB registers (simplified model) */
    uint16_t ctdb_registers[MAX_CTDB_SLOTS][CTDB_REGISTER_SIZE];
    
    /* Simulated L2CB per-slot/channel trigger state */
    uint16_t l1_masks[MAX_CTDB_SLOTS];
    uint16_t l1_delays[MAX_CTDB_SLOTS][16];
    
} smc_emulated_t;

static smc_emulated_t emulated_driver = {0};

/* Update CTDB dynamic registers (current and errors) based on power state and limits */
static void update_ctdb_dynamic_registers(uint8_t slot)
{
    if (slot >= MAX_CTDB_SLOTS || slot == 0) return;
    
    uint16_t ponf = emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_PONF];
    uint16_t cur_min = emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MIN];
    uint16_t cur_max = emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MAX];
    
    /* Board current (base load) - around 500mA (raw 1023) */
    emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_CUR_00] = 1023;
    
    uint16_t over_errors = 0;
    uint16_t under_errors = 0;
    
    for (int ch = 1; ch <= 15; ch++) {
        uint16_t current = 0;
        if (ponf & (1 << ch)) {
            /* If powered on, simulate ~300mA current (619 raw) */
            current = 619;
            
            /* Check limits */
            if (current < cur_min) under_errors |= (1 << ch);
            if (current > cur_max) over_errors |= (1 << ch);
        }
        
        /* Update channel current register (BASE_CTA_CTDB_CUR is 0x01) */
        emulated_driver.ctdb_registers[slot][BASE_CTA_CTDB_CUR + ch - 1] = current;
    }
    
    emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_OVER_CUR] = over_errors;
    emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_UNDER_CUR] = under_errors;
}

#if 0
/* Helper function to get current time in nanoseconds */
static uint64_t get_time_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}
#endif

/* Helper function to check if operation has completed */
static int check_operation_complete(struct timespec *start, int duration_us)
{
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    
    int64_t elapsed_us = (now.tv_sec - start->tv_sec) * 1000000LL +
                         (now.tv_nsec - start->tv_nsec) / 1000LL;
    
    return elapsed_us >= duration_us;
}

/* Update dynamic register state */
static void update_dynamic_state(void)
{
    /* Update SPI busy flag */
    if (emulated_driver.spi_state.busy) {
        if (check_operation_complete(&emulated_driver.spi_state.start_time, 
                                     emulated_driver.spi_state.duration_us)) {
            emulated_driver.spi_state.busy = 0;
            
            /* If it was a read operation, populate SPRX with simulated data */
            if (emulated_driver.spi_state.is_read) {
                uint8_t slot = emulated_driver.spi_state.slot;
                uint8_t reg = emulated_driver.spi_state.reg_addr;
                
                if (slot < MAX_CTDB_SLOTS && slot > 0) {
                    /* Update dynamic registers before reading */
                    update_ctdb_dynamic_registers(slot);
                    uint16_t value = emulated_driver.ctdb_registers[slot][reg];
                    unsigned short *sprx = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_SPRX];
                    *sprx = value;
                }
            }
        }
    }
    
    /* Update delay adjustment busy flag */
    if (emulated_driver.delay_state.busy) {
        if (check_operation_complete(&emulated_driver.delay_state.start_time,
                                     emulated_driver.delay_state.duration_us)) {
            emulated_driver.delay_state.busy = 0;
        }
    }
    
    /* Update timestamp counter if not latched */
    if (!emulated_driver.timestamp.latched) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        
        int64_t elapsed_ns = (now.tv_sec - emulated_driver.timestamp.start_time.tv_sec) * 1000000000LL +
                            (now.tv_nsec - emulated_driver.timestamp.start_time.tv_nsec);
        
        /* 125 MHz clock = 8ns period */
        emulated_driver.timestamp.counter = elapsed_ns / 8;
    }
}

/* Get current STAT register value */
static unsigned short get_stat_register(void)
{
    update_dynamic_state();
    
    unsigned short stat = 0;
    
    if (emulated_driver.spi_state.busy) {
        stat |= (1 << BIT_STAT_SPIBUSY);
    }
    
    if (emulated_driver.delay_state.busy) {
        stat |= (1 << BIT_STAT_DELAY_BUSY);
    }
    
    /* TIB_BUSY is typically 0 in simulation */
    
    return stat;
}

/* Handle write to CTRL register */
static void handle_ctrl_write(unsigned short value, unsigned short old_value)
{
    /* Check for 0->1 transition on bit 15 (timestamp latch) */
    if ((value & 0x8000) && !(old_value & 0x8000)) {
        /* Latch the current timestamp */
        update_dynamic_state();
        
        uint64_t ts = emulated_driver.timestamp.counter;
        
        unsigned short *tstmp0 = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_TSTMP0];
        unsigned short *tstmp1 = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_TSTMP1];
        unsigned short *tstmp2 = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_TSTMP2];
        
        *tstmp0 = (unsigned short)(ts & 0xFFFF);
        *tstmp1 = (unsigned short)((ts >> 16) & 0xFFFF);
        *tstmp2 = (unsigned short)((ts >> 32) & 0xFFFF);
        
        emulated_driver.timestamp.latched = 1;
    }
    
    /* Clear latch if bit 15 goes back to 0 */
    if (!(value & 0x8000) && (old_value & 0x8000)) {
        emulated_driver.timestamp.latched = 0;
    }
}

/* Handle write to SPAD register (initiates SPI transaction) */
static void handle_spad_write(unsigned short value)
{
    uint8_t reg_addr = value & 0xFF;
    uint8_t slot = (value >> 8) & 0x1F;
    int is_write = (value >> 15) & 0x01;
    
    /* Start SPI transaction */
    emulated_driver.spi_state.busy = 1;
    clock_gettime(CLOCK_MONOTONIC, &emulated_driver.spi_state.start_time);
    emulated_driver.spi_state.duration_us = 5;  /* ~5.4 us from manual */
    emulated_driver.spi_state.is_read = !is_write;
    emulated_driver.spi_state.slot = slot;
    emulated_driver.spi_state.reg_addr = reg_addr;
    
    if (is_write) {
        /* Store the write data from SPTX to CTDB registers */
        unsigned short *sptx = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_SPTX];
        
        if (slot < MAX_CTDB_SLOTS && slot > 0) {
            emulated_driver.ctdb_registers[slot][reg_addr] = *sptx;
        }
    }
}

/* Handle write to L1SEL and L1DEL registers */
static void handle_l1_delay_write(void)
{
    /* Simulate delay adjustment operation */
    emulated_driver.delay_state.busy = 1;
    clock_gettime(CLOCK_MONOTONIC, &emulated_driver.delay_state.start_time);
    emulated_driver.delay_state.duration_us = 100;  /* Arbitrary delay */
}

/* Initialize emulated driver */
smc_driver_error_t smc_open(const char* devname)
{
    if (emulated_driver.is_open) {
        smc_close();
    }
    
    /* Allocate register memory */
    emulated_driver.memory = (unsigned char *)calloc(REGISTER_MEMORY_SIZE, 1);
    if (!emulated_driver.memory) {
        fprintf(stderr, "[SMC_EMU] Failed to allocate register memory\n");
        return ERROR_OPENING_DEVICE;
    }
    
    /* Initialize mutex */
    pthread_mutex_init(&emulated_driver.lock, NULL);
    
    /* Initialize default register values */
    unsigned short *ctrl = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_CTRL];
    *ctrl = 0x3001;  /* Default from manual */
    
    unsigned short *muthr = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_MUTHR];
    *muthr = 0x0014;  /* Default 20 */
    
    unsigned short *mudel = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_MUDEL];
    *mudel = 0x000A;  /* Default 50ns */
    
    unsigned short *frev = (unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_FREV];
    *frev = DEFAULT_FIRMWARE_REV;
    
    /* Initialize timestamp counter */
    clock_gettime(CLOCK_MONOTONIC, &emulated_driver.timestamp.start_time);
    emulated_driver.timestamp.counter = 0;
    emulated_driver.timestamp.latched = 0;
    
    /* Initialize CTDB and Trigger state with realistic data */
    for (int slot = 0; slot < MAX_CTDB_SLOTS; slot++) {
        memset(emulated_driver.ctdb_registers[slot], 0, sizeof(uint16_t) * CTDB_REGISTER_SIZE);
        emulated_driver.l1_masks[slot] = 0xFFFE; /* All channels 1-15 enabled */
        for (int ch = 0; ch < 16; ch++) {
            emulated_driver.l1_delays[slot][ch] = 27; /* ~1ns */
        }

        if (slot > 0) {
            emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MIN] = 206;  /* ~100mA */
            emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MAX] = 2000; /* ~1000mA */
            emulated_driver.ctdb_registers[slot][ADDR_CTA_CTDB_FREV] = 0x0100;  /* Standard rev */
            
            /* Initial update to populate current/errors */
            update_ctdb_dynamic_registers(slot);
        }
    }
    
    emulated_driver.is_open = 1;
    
    printf("[SMC_EMU] Emulated SMC driver opened successfully\n");
    printf("[SMC_EMU] Firmware revision: 0x%04X\n", DEFAULT_FIRMWARE_REV);
    
    return ERROR_NONE;
}

/* Close emulated driver */
void smc_close(void)
{
    if (!emulated_driver.is_open) {
        return;
    }
    
    pthread_mutex_lock(&emulated_driver.lock);
    
    if (emulated_driver.memory) {
        free(emulated_driver.memory);
        emulated_driver.memory = NULL;
    }
    
    emulated_driver.is_open = 0;
    
    pthread_mutex_unlock(&emulated_driver.lock);
    pthread_mutex_destroy(&emulated_driver.lock);
    
    printf("[SMC_EMU] Emulated SMC driver closed\n");
}

/* Check if driver is open */
int smc_isOpen(void)
{
    return emulated_driver.is_open;
}

/* Assert driver is open */
void smc_assertIsOpen(void)
{
    if (!smc_isOpen()) {
        fprintf(stderr, "[SMC_EMU] ERROR: SMC driver not open!\n");
        exit(1);
    }
}

/* Read 16-bit register */
unsigned short smc_rd16(unsigned int _addr)
{
    smc_assertIsOpen();
    
    pthread_mutex_lock(&emulated_driver.lock);
    
    /* Bounds check */
    if (_addr >= REGISTER_MEMORY_SIZE - 1) {
        pthread_mutex_unlock(&emulated_driver.lock);
        fprintf(stderr, "[SMC_EMU] ERROR: Address 0x%08X out of bounds\n", _addr);
        return 0xDEAF;
    }
    
    unsigned short value;
    
    /* Handle special registers with dynamic behavior */
    if (_addr == ADDR_CTA_L2CB_STAT) {
        value = get_stat_register();
    } else if (_addr == ADDR_CTA_L2CB_L1MSK) {
        unsigned short l1sel = *(unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_L1SEL];
        uint8_t slot = (l1sel >> 4) & 0x1F;
        if (slot < MAX_CTDB_SLOTS) {
            value = emulated_driver.l1_masks[slot];
        } else {
            value = 0;
        }
    } else if (_addr == ADDR_CTA_L2CB_L1DEL) {
        unsigned short l1sel = *(unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_L1SEL];
        uint8_t slot = (l1sel >> 4) & 0x1F;
        uint8_t channel = l1sel & 0x0F;
        if (slot < MAX_CTDB_SLOTS && channel < 16) {
            value = emulated_driver.l1_delays[slot][channel];
        } else {
            value = 0;
        }
    } else {
        /* Direct memory read for other registers */
        value = *(unsigned short *)&emulated_driver.memory[_addr];
    }
    
    pthread_mutex_unlock(&emulated_driver.lock);

#ifdef DEBUG_SMC_EMULATOR
    printf("[SMC_EMU] RD16 0x%04X -> 0x%04X\n", _addr, value);
#endif

    return value;
}

/* Read 32-bit register */
unsigned int smc_rd32(unsigned int _addr)
{
    smc_assertIsOpen();
    
    pthread_mutex_lock(&emulated_driver.lock);
    
    /* Bounds check */
    if (_addr >= REGISTER_MEMORY_SIZE - 3) {
        pthread_mutex_unlock(&emulated_driver.lock);
        fprintf(stderr, "[SMC_EMU] ERROR: Address 0x%08X out of bounds\n", _addr);
        return 0xDEADBEAF;
    }
    
    unsigned int value = *(unsigned int *)&emulated_driver.memory[_addr];
    
    pthread_mutex_unlock(&emulated_driver.lock);
    
#ifdef DEBUG_SMC_EMULATOR
    printf("[SMC_EMU] RD32 0x%04X -> 0x%08X\n", _addr, value);
#endif
    
    return value;
}

/* Write 16-bit register */
void smc_wr16(unsigned int _addr, unsigned short _value)
{
    smc_assertIsOpen();
    
    pthread_mutex_lock(&emulated_driver.lock);
    
    /* Bounds check */
    if (_addr >= REGISTER_MEMORY_SIZE - 1) {
        pthread_mutex_unlock(&emulated_driver.lock);
        fprintf(stderr, "[SMC_EMU] ERROR: Address 0x%08X out of bounds\n", _addr);
        return;
    }
    
#ifdef DEBUG_SMC_EMULATOR
    printf("[SMC_EMU] WR16 0x%04X <- 0x%04X\n", _addr, _value);
#endif

    unsigned short old_value = *(unsigned short *)&emulated_driver.memory[_addr];
    
    /* Write to memory */
    *(unsigned short *)&emulated_driver.memory[_addr] = _value;
    
    /* Handle special register behavior */
    if (_addr == ADDR_CTA_L2CB_CTRL) {
        handle_ctrl_write(_value, old_value);
    } else if (_addr == ADDR_CTA_L2CB_SPAD) {
        handle_spad_write(_value);
    } else if (_addr == ADDR_CTA_L2CB_L1MSK) {
        unsigned short l1sel = *(unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_L1SEL];
        uint8_t slot = (l1sel >> 4) & 0x1F;
        if (slot < MAX_CTDB_SLOTS) {
            emulated_driver.l1_masks[slot] = _value;
        }
    } else if (_addr == ADDR_CTA_L2CB_L1DEL) {
        unsigned short l1sel = *(unsigned short *)&emulated_driver.memory[ADDR_CTA_L2CB_L1SEL];
        uint8_t slot = (l1sel >> 4) & 0x1F;
        uint8_t channel = l1sel & 0x0F;
        if (slot < MAX_CTDB_SLOTS && channel < 16) {
            emulated_driver.l1_delays[slot][channel] = _value;
        }
        handle_l1_delay_write();
    }
    /* STAT register is read-only, ignore writes */
    /* FREV register is read-only, ignore writes */
    
    pthread_mutex_unlock(&emulated_driver.lock);
}

/* Write 32-bit register */
void smc_wr32(unsigned int _addr, unsigned int _value)
{
    smc_assertIsOpen();
    
    pthread_mutex_lock(&emulated_driver.lock);
    
    /* Bounds check */
    if (_addr >= REGISTER_MEMORY_SIZE - 3) {
        pthread_mutex_unlock(&emulated_driver.lock);
        fprintf(stderr, "[SMC_EMU] ERROR: Address 0x%08X out of bounds\n", _addr);
        return;
    }
    
#ifdef DEBUG_SMC_EMULATOR
    printf("[SMC_EMU] WR32 0x%04X <- 0x%08X\n", _addr, _value);
#endif

    *(unsigned int *)&emulated_driver.memory[_addr] = _value;
    
    pthread_mutex_unlock(&emulated_driver.lock);
}

/* Additional helper functions for testing */

/* Set a CTDB register value (for test setup) */
void smc_emu_set_ctdb_register(uint8_t slot, uint8_t reg_addr, uint16_t value)
{
    if (!emulated_driver.is_open) return;
    if (slot >= MAX_CTDB_SLOTS || slot == 0) return;
    
    pthread_mutex_lock(&emulated_driver.lock);
    emulated_driver.ctdb_registers[slot][reg_addr] = value;
    pthread_mutex_unlock(&emulated_driver.lock);
    
#ifdef DEBUG_SMC_EMULATOR
    printf("[SMC_EMU] Set CTDB slot %d reg 0x%02X = 0x%04X\n", slot, reg_addr, value);
#endif
}

/* Get a CTDB register value (for test verification) */
uint16_t smc_emu_get_ctdb_register(uint8_t slot, uint8_t reg_addr)
{
    if (!emulated_driver.is_open) return 0;
    if (slot >= MAX_CTDB_SLOTS || slot == 0) return 0;
    
    pthread_mutex_lock(&emulated_driver.lock);
    uint16_t value = emulated_driver.ctdb_registers[slot][reg_addr];
    pthread_mutex_unlock(&emulated_driver.lock);
    
    return value;
}

/* Force SPI operation to complete immediately (for fast testing) */
void smc_emu_complete_spi(void)
{
    if (!emulated_driver.is_open) return;
    
    pthread_mutex_lock(&emulated_driver.lock);
    emulated_driver.spi_state.busy = 0;
    emulated_driver.delay_state.busy = 0;
    pthread_mutex_unlock(&emulated_driver.lock);
}
