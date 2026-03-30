# Makefile for L2 Trigger HAL Library

CC = gcc
CFLAGS = -Wall -fPIC -O2
LDFLAGS = -shared

# Optional: Set to 1 to build with dummy implementations for testing
DUMMY ?= 0
ifeq ($(DUMMY),1)
	CFLAGS += -DDUMMY
endif

# Source files
SOURCES = l2trig_hal.c l2trig_hal_exports.c smc.c
HEADERS = l2trig_hal.h bits.h

# Output library
TARGET = libl2trig_hal.so

# Installation paths
PREFIX ?= /usr/local
LIBDIR = $(PREFIX)/lib
INCLUDEDIR = $(PREFIX)/include

.PHONY: all clean install uninstall

all: $(TARGET)

$(TARGET): $(SOURCES) $(HEADERS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $(TARGET) $(SOURCES)
	@echo "Built $(TARGET)"

clean:
	rm -f $(TARGET)
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

# Test compilation (requires hardware or mock)
test: $(TARGET)
	$(CC) -o test_hal test_hal.c -L. -ll2trig_hal
	@echo "Built test executable"
