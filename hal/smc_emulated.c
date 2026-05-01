/*
 * smc_emulated.c
 * 
 * Emulated SMC driver for testing the L2CB HAL without hardware.
 * Implements register-level simulation of the L2CB FPGA with file-backed persistence.
 * 
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <pthread.h>
#include <unistd.h>
#include <time.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>

#include "smc.h"

/* Enable emulation mode */
#define SMC_EMULATED 1

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

#define MAX_L2CB_REGISTERS      256
#define SMC_EMU_MAGIC           0x4C324342  /* "L2CB" */
#define SMCBUS_EMU_DEVICE       "l2trig_emulator_state.dat"

/* 
 * Persistent state structure mapped to file
 * 
 * NOTE: Distinction between PERSISTENT and VOLATILE state:
 * - PERSISTENT: Configuration that should survive across runs (register values, CTDB settings)
 * - VOLATILE: Runtime state that should reset on open (busy flags, timestamp counter)
 */
typedef struct {
    uint32_t magic;
    
    /* PERSISTENT: L2CB register memory (configuration survives across runs) */
    uint16_t registers[MAX_L2CB_REGISTERS];
    
    /* VOLATILE: SPI transaction state (always reset on open) */
    struct {
        int busy;
        struct timespec start_time;
        int duration_us;
        int is_read;
        uint8_t slot;
        uint8_t reg_addr;
        uint16_t data;
    } spi_state;
    
    /* VOLATILE: Delay adjustment state (always reset on open) */
    struct {
        int busy;
        struct timespec start_time;
        int duration_us;
    } delay_state;
    
    /* VOLATILE: Timestamp counter (always reset on open) */
    struct {
        uint64_t counter;
        int latched;
        struct timespec start_time;
    } timestamp;
    
    /* PERSISTENT: CTDB register arrays (configuration survives) */
    uint16_t ctdb_registers[MAX_CTDB_SLOTS][CTDB_REGISTER_SIZE];
    
    /* PERSISTENT: Per-slot L1 trigger state (configuration survives) */
    uint16_t l1_masks[MAX_CTDB_SLOTS];
    uint16_t l1_delays[MAX_CTDB_SLOTS][16];
    
    /* PERSISTENT: Random trip state (configuration survives) */
    uint16_t ctdb_tripped_under[MAX_CTDB_SLOTS];
    uint16_t ctdb_tripped_over[MAX_CTDB_SLOTS];
    
} smc_emu_state_t;

typedef struct {
    int is_open;
    int fd;
    pthread_mutex_t lock;
    smc_emu_state_t *state;
    size_t mapped_size;
} smc_emulated_t;

static smc_emulated_t emulated_driver = {0};

/* Update CTDB dynamic registers (current and errors) based on power state and limits */
static void update_ctdb_dynamic_registers(uint8_t slot)
{
    if (slot >= MAX_CTDB_SLOTS || slot == 0) return;
    
    uint16_t ponf = emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_PONF];
    uint16_t cur_min = emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MIN];
    uint16_t cur_max = emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MAX];
    
    /* Board current (base load) - around 500mA (raw ADC value ~1023) */
    emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_CUR_00] = 1023;
    
    uint16_t over_errors = 0;
    uint16_t under_errors = 0;
    
    /* Simulate per-channel current based on power state */
    for (int ch = 1; ch <= 15; ch++) {
        uint16_t current = 0;
        uint16_t bit = (1 << ch);
        
        if (ponf & bit) {
            /* Check if already tripped (random or previous deterministic) */
            if (!(emulated_driver.state->ctdb_tripped_under[slot] & bit) &&
                !(emulated_driver.state->ctdb_tripped_over[slot] & bit)) {
                
                /* Not tripped yet - simulate typical current draw of ~300mA (raw ADC ~619) */
                current = 619;
                
                /* Deterministic limit checking: if limits exceeded, it trips and current goes to 0 */
                if (current < cur_min) {
                    emulated_driver.state->ctdb_tripped_under[slot] |= bit;
                    current = 0;
                } else if (current > cur_max) {
                    emulated_driver.state->ctdb_tripped_over[slot] |= bit;
                    current = 0;
                }
            } else {
                /* Already in a tripped state (random or deterministic) */
                current = 0;
            }
        } else {
            /* Powered off - ensure trip state is cleared for this channel */
            emulated_driver.state->ctdb_tripped_under[slot] &= ~bit;
            emulated_driver.state->ctdb_tripped_over[slot] &= ~bit;
            current = 0;
        }
        
        /* Accumulate error bits for registers based on persistent trip state */
        if (emulated_driver.state->ctdb_tripped_under[slot] & bit) under_errors |= bit;
        if (emulated_driver.state->ctdb_tripped_over[slot] & bit) over_errors |= bit;
        
        /* Store current reading for this channel (registers 0x01-0x0F) */
        emulated_driver.state->ctdb_registers[slot][BASE_CTA_CTDB_CUR + ch - 1] = current;
    }
    
    /* Update error status registers */
    emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_OVER_CUR] = over_errors;
    emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_UNDER_CUR] = under_errors;
}

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
    if (!emulated_driver.state) return;

    /* Update SPI busy flag */
    if (emulated_driver.state->spi_state.busy) {
        if (check_operation_complete(&emulated_driver.state->spi_state.start_time, 
                                     emulated_driver.state->spi_state.duration_us)) {
            emulated_driver.state->spi_state.busy = 0;
            
            /* If it was a read operation, populate SPRX with data from CTDB */
            if (emulated_driver.state->spi_state.is_read) {
                uint8_t slot = emulated_driver.state->spi_state.slot;
                uint8_t reg = emulated_driver.state->spi_state.reg_addr;
                
                if (slot < MAX_CTDB_SLOTS && slot > 0) {
                    /* Update dynamic registers before reading */
                    update_ctdb_dynamic_registers(slot);
                    
                    /* Load value into SPRX register */
                    uint16_t value = emulated_driver.state->ctdb_registers[slot][reg];
                    emulated_driver.state->registers[ADDR_CTA_L2CB_SPRX >> 1] = value;
                }
            }
        }
    }
    
    /* Update delay adjustment busy flag */
    if (emulated_driver.state->delay_state.busy) {
        if (check_operation_complete(&emulated_driver.state->delay_state.start_time,
                                     emulated_driver.state->delay_state.duration_us)) {
            emulated_driver.state->delay_state.busy = 0;
        }
    }
    
    /* Update timestamp counter if not latched (free-running 125 MHz = 8ns period) */
    if (!emulated_driver.state->timestamp.latched) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        int64_t elapsed_ns = (now.tv_sec - emulated_driver.state->timestamp.start_time.tv_sec) * 1000000000LL +
                            (now.tv_nsec - emulated_driver.state->timestamp.start_time.tv_nsec);
        emulated_driver.state->timestamp.counter = elapsed_ns / 8;  /* 125 MHz clock */
    }
}

static unsigned short get_stat_register(void)
{
    update_dynamic_state();
    unsigned short stat = 0;
    
    if (emulated_driver.state->spi_state.busy) 
        stat |= (1 << BIT_STAT_SPIBUSY);
    if (emulated_driver.state->delay_state.busy) 
        stat |= (1 << BIT_STAT_DELAY_BUSY);
    /* TIB_BUSY is always 0 in simulation (could be made configurable) */
    
    return stat;
}

static void handle_ctrl_write(unsigned short value, unsigned short old_value)
{
    /* Check for 0->1 transition on bit 15 (timestamp latch) */
    if ((value & 0x8000) && !(old_value & 0x8000)) {
        update_dynamic_state();
        
        /* Latch current timestamp value into TSTMP0/1/2 registers */
        uint64_t ts = emulated_driver.state->timestamp.counter;
        emulated_driver.state->registers[ADDR_CTA_L2CB_TSTMP0 >> 1] = (unsigned short)(ts & 0xFFFF);
        emulated_driver.state->registers[ADDR_CTA_L2CB_TSTMP1 >> 1] = (unsigned short)((ts >> 16) & 0xFFFF);
        emulated_driver.state->registers[ADDR_CTA_L2CB_TSTMP2 >> 1] = (unsigned short)((ts >> 32) & 0xFFFF);
        emulated_driver.state->timestamp.latched = 1;
    }
    
    /* Clear latch on 1->0 transition */
    if (!(value & 0x8000) && (old_value & 0x8000)) {
        emulated_driver.state->timestamp.latched = 0;
    }
}

static void handle_spad_write(unsigned short value)
{
    /* Decode SPI command format (see User Manual section 4.3, Table 2) */
    uint8_t reg_addr = value & 0xFF;           /* Bits 7:0 = register address */
    uint8_t slot = (value >> 8) & 0x1F;        /* Bits 12:8 = slot number */
    int is_write = (value >> 15) & 0x01;       /* Bit 15 = RD(0) / WR(1) */
    
    /* Start SPI transaction with realistic timing (~5.4µs per User Manual) */
    emulated_driver.state->spi_state.busy = 1;
    clock_gettime(CLOCK_MONOTONIC, &emulated_driver.state->spi_state.start_time);
    emulated_driver.state->spi_state.duration_us = 5;
    emulated_driver.state->spi_state.is_read = !is_write;
    emulated_driver.state->spi_state.slot = slot;
    emulated_driver.state->spi_state.reg_addr = reg_addr;
    
    if (is_write) {
        /* Write: Copy SPTX data to CTDB register */
        uint16_t sptx = emulated_driver.state->registers[ADDR_CTA_L2CB_SPTX >> 1];
        if (slot < MAX_CTDB_SLOTS && slot > 0) {
            uint16_t old_val = emulated_driver.state->ctdb_registers[slot][reg_addr];
            emulated_driver.state->ctdb_registers[slot][reg_addr] = sptx;
            
            /* Handle power-on transitions and random trips */
            if (reg_addr == ADDR_CTA_CTDB_PONF) {
                for (int ch = 1; ch <= 15; ch++) {
                    uint16_t bit = (1 << ch);
                    if ((sptx & bit) && !(old_val & bit)) {
                        /* 0->1 transition: roll 1/1024 chance to trip */
                        if ((rand() % 1024) == 0) {
                            /* Randomly pick under or over current trip */
                            if (rand() % 2) {
                                emulated_driver.state->ctdb_tripped_under[slot] |= bit;
                            } else {
                                emulated_driver.state->ctdb_tripped_over[slot] |= bit;
                            }
                        }
                    } else if (!(sptx & bit)) {
                        /* Disabling clears any tripped state */
                        emulated_driver.state->ctdb_tripped_under[slot] &= ~bit;
                        emulated_driver.state->ctdb_tripped_over[slot] &= ~bit;
                    }
                }
            }
        }
    }
    /* Read: Data will be loaded into SPRX when busy clears (see update_dynamic_state) */
}

static void handle_l1_delay_write(void)
{
    /* Simulate delay adjustment operation (takes time for hardware to apply) */
    emulated_driver.state->delay_state.busy = 1;
    clock_gettime(CLOCK_MONOTONIC, &emulated_driver.state->delay_state.start_time);
    emulated_driver.state->delay_state.duration_us = 100;  /* Arbitrary delay */
}

const char* smc_default_device(void)
{
    return SMCBUS_EMU_DEVICE;
}

smc_driver_error_t smc_open(const char* devname)
{
    if (emulated_driver.is_open) smc_close();
    
    const char *filename = devname ? devname : smc_default_device();
    int fd = open(filename, O_RDWR | O_CREAT, 0666);
    if (fd < 0) {
        fprintf(stderr, "[SMC_EMU] ERROR: Failed to open %s\n", filename);
        return ERROR_OPENING_DEVICE;
    }
    
    /* Ensure file is large enough for our state structure */
    struct stat st;
    fstat(fd, &st);
    size_t size = sizeof(smc_emu_state_t);
    if (st.st_size < (off_t)size) {
        if (ftruncate(fd, size) != 0) {
            close(fd);
            fprintf(stderr, "[SMC_EMU] ERROR: Failed to resize file\n");
            return ERROR_OPENING_DEVICE;
        }
    }
    
    /* Memory-map the state file */
    void *ptr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (ptr == MAP_FAILED) {
        close(fd);
        fprintf(stderr, "[SMC_EMU] ERROR: mmap failed\n");
        return ERROR_OPENING_DEVICE;
    }
    
    emulated_driver.state = (smc_emu_state_t *)ptr;
    emulated_driver.fd = fd;
    emulated_driver.mapped_size = size;
    pthread_mutex_init(&emulated_driver.lock, NULL);
    
    /* Check if this is a new file or existing state */
    if (emulated_driver.state->magic != SMC_EMU_MAGIC) {
        /* First time initialization - set up default register values */
        memset(emulated_driver.state, 0, size);
        emulated_driver.state->magic = SMC_EMU_MAGIC;
        
        /* L2CB registers - defaults from User Manual */
        emulated_driver.state->registers[ADDR_CTA_L2CB_CTRL >> 1] = 0x3001;   /* Default CTRL */
        emulated_driver.state->registers[ADDR_CTA_L2CB_MUTHR >> 1] = 0x0014;  /* MCF threshold = 20 */
        emulated_driver.state->registers[ADDR_CTA_L2CB_MUDEL >> 1] = 0x000A;  /* MCF delay = 50ns */
        emulated_driver.state->registers[ADDR_CTA_L2CB_L1DT >> 1] = 0x0003;   /* L1 deadtime = 15ns */
        emulated_driver.state->registers[ADDR_CTA_L2CB_FREV >> 1] = DEFAULT_FIRMWARE_REV;
        
        /* Initialize per-slot L1 trigger configuration */
        for (int slot = 0; slot < MAX_CTDB_SLOTS; slot++) {
            emulated_driver.state->l1_masks[slot] = 0xFFFE;  /* All channels enabled (bit 0 unused) */
            for (int ch = 0; ch < 16; ch++) {
                emulated_driver.state->l1_delays[slot][ch] = 27;  /* Default ~1ns delay */
            }
            
            /* Initialize CTDB registers for valid slots */
            if (slot > 0) {
                emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MIN] = 206;   /* ~100mA */
                emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MAX] = 2000;  /* ~1000mA */
                emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_FREV] = 0x0100;   /* Firmware v1.0 */
                update_ctdb_dynamic_registers(slot);
            }
        }
        
        printf("[SMC_EMU] Created new emulator state file: %s\n", filename);
    } else {
        printf("[SMC_EMU] Loaded existing emulator state from: %s\n", filename);
    }
    
    /* ALWAYS reset volatile state on open (even for existing files) */
    emulated_driver.state->spi_state.busy = 0;
    emulated_driver.state->delay_state.busy = 0;
    emulated_driver.state->timestamp.latched = 0;
    emulated_driver.state->timestamp.counter = 0;
    clock_gettime(CLOCK_MONOTONIC, &emulated_driver.state->timestamp.start_time);
    
    /* Seed random number generator for trips */
    srand(time(NULL));
    
    emulated_driver.is_open = 1;
    printf("[SMC_EMU] Firmware revision: 0x%04X\n", DEFAULT_FIRMWARE_REV);
    return ERROR_NONE;
}

void smc_close(void)
{
    if (!emulated_driver.is_open) return;
    
    pthread_mutex_lock(&emulated_driver.lock);
    
    /* Unmap and close file */
    if (emulated_driver.state) {
        munmap(emulated_driver.state, emulated_driver.mapped_size);
        emulated_driver.state = NULL;
    }
    if (emulated_driver.fd >= 0) {
        close(emulated_driver.fd);
        emulated_driver.fd = -1;
    }
    
    emulated_driver.is_open = 0;
    
    pthread_mutex_unlock(&emulated_driver.lock);
    pthread_mutex_destroy(&emulated_driver.lock);
    
    printf("[SMC_EMU] Emulator closed\n");
}

int smc_isOpen(void) 
{ 
    return emulated_driver.is_open; 
}

void smc_assertIsOpen(void) 
{ 
    if (!smc_isOpen()) {
        fprintf(stderr, "[SMC_EMU] ERROR: Emulator not open!\n");
        exit(1);
    }
}

unsigned short smc_rd16(unsigned int _addr)
{
    smc_assertIsOpen();
    pthread_mutex_lock(&emulated_driver.lock);
    
    unsigned short value = 0;
    
    /* Bounds check (256 registers * 2 bytes = 512 byte address space) */
    if (_addr < (MAX_L2CB_REGISTERS << 1)) {
        /* Special dynamic registers */
        if (_addr == ADDR_CTA_L2CB_STAT) {
            value = get_stat_register();
            
        } else if (_addr == ADDR_CTA_L2CB_L1MSK) {
            /* L1MSK is per-slot, indexed by L1SEL */
            uint16_t l1sel = emulated_driver.state->registers[ADDR_CTA_L2CB_L1SEL >> 1];
            uint8_t slot = (l1sel >> 4) & 0x1F;  /* Bits 8:4 = slot number */
            value = (slot < MAX_CTDB_SLOTS) ? emulated_driver.state->l1_masks[slot] : 0;
            
        } else if (_addr == ADDR_CTA_L2CB_L1DEL) {
            /* L1DEL is per-slot per-channel, indexed by L1SEL */
            uint16_t l1sel = emulated_driver.state->registers[ADDR_CTA_L2CB_L1SEL >> 1];
            uint8_t slot = (l1sel >> 4) & 0x1F;  /* Bits 8:4 = slot */
            uint8_t ch = l1sel & 0x0F;           /* Bits 3:0 = channel */
            value = (slot < MAX_CTDB_SLOTS && ch < 16) ? emulated_driver.state->l1_delays[slot][ch] : 0;
            
        } else {
            /* Normal register access */
            value = emulated_driver.state->registers[_addr >> 1];
        }
    }
    /* else: out of range, return 0 */
    
    pthread_mutex_unlock(&emulated_driver.lock);
    return value;
}

unsigned int smc_rd32(unsigned int _addr)
{
    /* Read as two 16-bit words (little-endian) */
    unsigned int val = smc_rd16(_addr);
    val |= (unsigned int)smc_rd16(_addr + 2) << 16;
    return val;
}

void smc_wr16(unsigned int _addr, unsigned short _value)
{
    smc_assertIsOpen();
    pthread_mutex_lock(&emulated_driver.lock);
    
    if (_addr < (MAX_L2CB_REGISTERS << 1)) {
        unsigned short old_value = emulated_driver.state->registers[_addr >> 1];
        
        /* Update register array */
        emulated_driver.state->registers[_addr >> 1] = _value;
        
        /* Handle special register side-effects */
        if (_addr == ADDR_CTA_L2CB_CTRL) {
            handle_ctrl_write(_value, old_value);
            
        } else if (_addr == ADDR_CTA_L2CB_SPAD) {
            handle_spad_write(_value);
            
        } else if (_addr == ADDR_CTA_L2CB_L1MSK) {
            /* Write to per-slot mask storage */
            uint16_t l1sel = emulated_driver.state->registers[ADDR_CTA_L2CB_L1SEL >> 1];
            uint8_t slot = (l1sel >> 4) & 0x1F;
            if (slot < MAX_CTDB_SLOTS) {
                emulated_driver.state->l1_masks[slot] = _value;
            }
            
        } else if (_addr == ADDR_CTA_L2CB_L1DEL) {
            /* Write to per-slot per-channel delay storage */
            uint16_t l1sel = emulated_driver.state->registers[ADDR_CTA_L2CB_L1SEL >> 1];
            uint8_t slot = (l1sel >> 4) & 0x1F;
            uint8_t ch = l1sel & 0x0F;
            if (slot < MAX_CTDB_SLOTS && ch < 16) {
                emulated_driver.state->l1_delays[slot][ch] = _value;
            }
            handle_l1_delay_write();
        }
    }
    /* else: out of range, ignore write */
    
    pthread_mutex_unlock(&emulated_driver.lock);
}

void smc_wr32(unsigned int _addr, unsigned int _value)
{
    /* Write as two 16-bit words (little-endian) */
    smc_wr16(_addr, _value & 0xFFFF);
    smc_wr16(_addr + 2, (_value >> 16) & 0xFFFF);
}

/* ============================================================================
 * Test Helper Functions
 * ============================================================================ */

void smc_emu_set_ctdb_register(uint8_t slot, uint8_t reg_addr, uint16_t value)
{
    if (!emulated_driver.is_open || slot >= MAX_CTDB_SLOTS || slot == 0) return;
    
    pthread_mutex_lock(&emulated_driver.lock);
    emulated_driver.state->ctdb_registers[slot][reg_addr] = value;
    pthread_mutex_unlock(&emulated_driver.lock);
}

uint16_t smc_emu_get_ctdb_register(uint8_t slot, uint8_t reg_addr)
{
    if (!emulated_driver.is_open || slot >= MAX_CTDB_SLOTS || slot == 0) return 0;
    
    pthread_mutex_lock(&emulated_driver.lock);
    uint16_t val = emulated_driver.state->ctdb_registers[slot][reg_addr];
    pthread_mutex_unlock(&emulated_driver.lock);
    return val;
}

void smc_emu_complete_spi(void)
{
    if (!emulated_driver.is_open) return;
    
    pthread_mutex_lock(&emulated_driver.lock);
    emulated_driver.state->spi_state.busy = 0;
    emulated_driver.state->delay_state.busy = 0;
    pthread_mutex_unlock(&emulated_driver.lock);
}
