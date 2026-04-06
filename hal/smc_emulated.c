/*
 * smc_emulated.c
 * 
 * Emulated SMC driver for testing the L2CB HAL without hardware.
 * Implements register-level simulation of the L2CB FPGA with file-backed persistence.
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

/* Peristent state structure mapped to file */
typedef struct {
    uint32_t magic;
    
    /* Simulated register memory (Fixed size) */
    uint16_t registers[MAX_L2CB_REGISTERS];
    
    /* SPI transaction state */
    struct {
        int busy;
        struct timespec start_time;
        int duration_us;
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
    
    /* Timestamp counter */
    struct {
        uint64_t counter;
        int latched;
        struct timespec start_time;
    } timestamp;
    
    /* Simulated CTDB registers */
    uint16_t ctdb_registers[MAX_CTDB_SLOTS][CTDB_REGISTER_SIZE];
    
    /* Simulated L2CB per-slot/channel trigger state */
    uint16_t l1_masks[MAX_CTDB_SLOTS];
    uint16_t l1_delays[MAX_CTDB_SLOTS][16];
    
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
    
    /* Board current (base load) - around 500mA (raw 1023) */
    emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_CUR_00] = 1023;
    
    uint16_t over_errors = 0;
    uint16_t under_errors = 0;
    
    for (int ch = 1; ch <= 15; ch++) {
        uint16_t current = 0;
        if (ponf & (1 << ch)) {
            current = 619;
            if (current < cur_min) under_errors |= (1 << ch);
            if (current > cur_max) over_errors |= (1 << ch);
        }
        emulated_driver.state->ctdb_registers[slot][BASE_CTA_CTDB_CUR + ch - 1] = current;
    }
    
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
            
            if (emulated_driver.state->spi_state.is_read) {
                uint8_t slot = emulated_driver.state->spi_state.slot;
                uint8_t reg = emulated_driver.state->spi_state.reg_addr;
                
                if (slot < MAX_CTDB_SLOTS && slot > 0) {
                    update_ctdb_dynamic_registers(slot);
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
    
    /* Update timestamp counter if not latched */
    if (!emulated_driver.state->timestamp.latched) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        int64_t elapsed_ns = (now.tv_sec - emulated_driver.state->timestamp.start_time.tv_sec) * 1000000000LL +
                            (now.tv_nsec - emulated_driver.state->timestamp.start_time.tv_nsec);
        emulated_driver.state->timestamp.counter = elapsed_ns / 8;
    }
}

static unsigned short get_stat_register(void)
{
    update_dynamic_state();
    unsigned short stat = 0;
    if (emulated_driver.state->spi_state.busy) stat |= (1 << BIT_STAT_SPIBUSY);
    if (emulated_driver.state->delay_state.busy) stat |= (1 << BIT_STAT_DELAY_BUSY);
    return stat;
}

static void handle_ctrl_write(unsigned short value, unsigned short old_value)
{
    if ((value & 0x8000) && !(old_value & 0x8000)) {
        update_dynamic_state();
        uint64_t ts = emulated_driver.state->timestamp.counter;
        emulated_driver.state->registers[ADDR_CTA_L2CB_TSTMP0 >> 1] = (unsigned short)(ts & 0xFFFF);
        emulated_driver.state->registers[ADDR_CTA_L2CB_TSTMP1 >> 1] = (unsigned short)((ts >> 16) & 0xFFFF);
        emulated_driver.state->registers[ADDR_CTA_L2CB_TSTMP2 >> 1] = (unsigned short)((ts >> 32) & 0xFFFF);
        emulated_driver.state->timestamp.latched = 1;
    }
    if (!(value & 0x8000) && (old_value & 0x8000)) {
        emulated_driver.state->timestamp.latched = 0;
    }
}

static void handle_spad_write(unsigned short value)
{
    uint8_t reg_addr = value & 0xFF;
    uint8_t slot = (value >> 8) & 0x1F;
    int is_write = (value >> 15) & 0x01;
    
    emulated_driver.state->spi_state.busy = 1;
    clock_gettime(CLOCK_MONOTONIC, &emulated_driver.state->spi_state.start_time);
    emulated_driver.state->spi_state.duration_us = 5;
    emulated_driver.state->spi_state.is_read = !is_write;
    emulated_driver.state->spi_state.slot = slot;
    emulated_driver.state->spi_state.reg_addr = reg_addr;
    
    if (is_write) {
        uint16_t sptx = emulated_driver.state->registers[ADDR_CTA_L2CB_SPTX >> 1];
        if (slot < MAX_CTDB_SLOTS && slot > 0) {
            emulated_driver.state->ctdb_registers[slot][reg_addr] = sptx;
        }
    }
}

static void handle_l1_delay_write(void)
{
    emulated_driver.state->delay_state.busy = 1;
    clock_gettime(CLOCK_MONOTONIC, &emulated_driver.state->delay_state.start_time);
    emulated_driver.state->delay_state.duration_us = 100;
}

smc_driver_error_t smc_open(const char* devname)
{
    if (emulated_driver.is_open) smc_close();
    
    const char *filename = devname ? devname : "l2trig_emulator_state.dat";
    int fd = open(filename, O_RDWR | O_CREAT, 0666);
    if (fd < 0) return ERROR_OPENING_DEVICE;
    
    struct stat st;
    fstat(fd, &st);
    size_t size = sizeof(smc_emu_state_t);
    if (st.st_size < size) {
        if (ftruncate(fd, size) != 0) {
            close(fd);
            return ERROR_OPENING_DEVICE;
        }
    }
    
    void *ptr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (ptr == MAP_FAILED) {
        close(fd);
        return ERROR_OPENING_DEVICE;
    }
    
    emulated_driver.state = (smc_emu_state_t *)ptr;
    emulated_driver.fd = fd;
    emulated_driver.mapped_size = size;
    pthread_mutex_init(&emulated_driver.lock, NULL);
    
    if (emulated_driver.state->magic != SMC_EMU_MAGIC) {
        memset(emulated_driver.state, 0, size);
        emulated_driver.state->magic = SMC_EMU_MAGIC;
        emulated_driver.state->registers[ADDR_CTA_L2CB_CTRL >> 1] = 0x3001;
        emulated_driver.state->registers[ADDR_CTA_L2CB_MUTHR >> 1] = 0x0014;
        emulated_driver.state->registers[ADDR_CTA_L2CB_MUDEL >> 1] = 0x000A;
        emulated_driver.state->registers[ADDR_CTA_L2CB_FREV >> 1] = DEFAULT_FIRMWARE_REV;
        clock_gettime(CLOCK_MONOTONIC, &emulated_driver.state->timestamp.start_time);
        
        for (int slot = 0; slot < MAX_CTDB_SLOTS; slot++) {
            emulated_driver.state->l1_masks[slot] = 0xFFFE;
            for (int ch = 0; ch < 16; ch++) emulated_driver.state->l1_delays[slot][ch] = 27;
            if (slot > 0) {
                emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MIN] = 206;
                emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_CUR_MAX] = 2000;
                emulated_driver.state->ctdb_registers[slot][ADDR_CTA_CTDB_FREV] = 0x0100;
                update_ctdb_dynamic_registers(slot);
            }
        }
    }
    
    emulated_driver.is_open = 1;
    printf("[SMC_EMU] Mapped emulator state to %s\n", filename);
    return ERROR_NONE;
}

void smc_close(void)
{
    if (!emulated_driver.is_open) return;
    pthread_mutex_lock(&emulated_driver.lock);
    munmap(emulated_driver.state, emulated_driver.mapped_size);
    close(emulated_driver.fd);
    emulated_driver.state = NULL;
    emulated_driver.is_open = 0;
    pthread_mutex_unlock(&emulated_driver.lock);
    pthread_mutex_destroy(&emulated_driver.lock);
}

int smc_isOpen(void) { return emulated_driver.is_open; }
void smc_assertIsOpen(void) { if (!smc_isOpen()) exit(1); }

unsigned short smc_rd16(unsigned int _addr)
{
    smc_assertIsOpen();
    pthread_mutex_lock(&emulated_driver.lock);
    unsigned short value = 0;
    if (_addr < (MAX_L2CB_REGISTERS << 1)) {
        if (_addr == ADDR_CTA_L2CB_STAT) {
            value = get_stat_register();
        } else if (_addr == ADDR_CTA_L2CB_L1MSK) {
            uint8_t slot = (emulated_driver.state->registers[ADDR_CTA_L2CB_L1SEL >> 1] >> 4) & 0x1F;
            value = (slot < MAX_CTDB_SLOTS) ? emulated_driver.state->l1_masks[slot] : 0;
        } else if (_addr == ADDR_CTA_L2CB_L1DEL) {
            uint16_t l1sel = emulated_driver.state->registers[ADDR_CTA_L2CB_L1SEL >> 1];
            uint8_t slot = (l1sel >> 4) & 0x1F, ch = l1sel & 0x0F;
            value = (slot < MAX_CTDB_SLOTS && ch < 16) ? emulated_driver.state->l1_delays[slot][ch] : 0;
        } else {
            value = emulated_driver.state->registers[_addr >> 1];
        }
    }
    pthread_mutex_unlock(&emulated_driver.lock);
    return value;
}

unsigned int smc_rd32(unsigned int _addr)
{
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
        emulated_driver.state->registers[_addr >> 1] = _value;
        if (_addr == ADDR_CTA_L2CB_CTRL) handle_ctrl_write(_value, old_value);
        else if (_addr == ADDR_CTA_L2CB_SPAD) handle_spad_write(_value);
        else if (_addr == ADDR_CTA_L2CB_L1MSK) {
            uint8_t slot = (emulated_driver.state->registers[ADDR_CTA_L2CB_L1SEL >> 1] >> 4) & 0x1F;
            if (slot < MAX_CTDB_SLOTS) emulated_driver.state->l1_masks[slot] = _value;
        } else if (_addr == ADDR_CTA_L2CB_L1DEL) {
            uint16_t l1sel = emulated_driver.state->registers[ADDR_CTA_L2CB_L1SEL >> 1];
            uint8_t slot = (l1sel >> 4) & 0x1F, ch = l1sel & 0x0F;
            if (slot < MAX_CTDB_SLOTS && ch < 16) emulated_driver.state->l1_delays[slot][ch] = _value;
            handle_l1_delay_write();
        }
    }
    pthread_mutex_unlock(&emulated_driver.lock);
}

void smc_wr32(unsigned int _addr, unsigned int _value)
{
    smc_wr16(_addr, _value & 0xFFFF);
    smc_wr16(_addr + 2, (_value >> 16) & 0xFFFF);
}

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
