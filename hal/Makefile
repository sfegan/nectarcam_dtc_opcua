# Makefile for L2 Trigger HAL Library

CC = gcc
CFLAGS = -Wall -fPIC -O2
LDFLAGS = -shared

# Source files
SOURCES = l2trig_hal.c l2trig_hal_exports.c
HEADERS = l2trig_hal.h bits.h

# Output library
TARGET_LIBRARY = libl2trig_hal.so
TARGET = $(TARGET_LIBRARY)

EMULATESMC ?= 0

ifeq ($(EMULATESMC),1)
	SOURCES += smc_emulated.c
	TARGET += test_smc_emulation
else
	SOURCES += smc.c
endif


# Installation paths
PREFIX ?= /usr/local
LIBDIR = $(PREFIX)/lib
INCLUDEDIR = $(PREFIX)/include

.PHONY: all clean install uninstall

all: $(TARGET)

$(TARGET_LIBRARY): $(SOURCES) $(HEADERS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $(TARGET_LIBRARY) $(SOURCES)
	@echo "Built $(TARGET_LIBRARY)"

test_smc_emulation: test_smc_emulation.c $(HEADERS) $(TARGET_LIBRARY)
	$(CC) $(CFLAGS) -o $@ $< -L. -ll2trig_hal
	@echo "Built SMC emulation test executable"

clean:
	rm -f $(TARGET) test_smc_emulation test_hal
	@echo "Cleaned build artifacts"

install: $(TARGET)
	install -d $(LIBDIR)
	install -m 755 $(TARGET) $(LIBDIR)
	install -d $(INCLUDEDIR)
	install -m 644 l2trig_hal.h $(INCLUDEDIR)
	ldconfig
	@echo "Installed to $(PREFIX)"

uninstall:
	rm -f $(LIBDIR)/$(TARGET)
	rm -f $(INCLUDEDIR)/l2trig_hal.h
	ldconfig
	@echo "Uninstalled from $(PREFIX)"

test: test_smc_emulation
	./test_smc_emulation