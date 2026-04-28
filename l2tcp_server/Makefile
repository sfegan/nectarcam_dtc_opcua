# Makefile for L2TCP Embedded Server

CC = gcc
CFLAGS = -Wall -O2 -I../hal
LDFLAGS = -L../hal -ll2trig_hal -Wl,-rpath,../hal

# Source files
SOURCES = l2tcp_server_main.c
HEADERS = l2tcp_protocol.h

# Output executable
TARGET = l2tcp_server

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
	LDFLAGS += -lrt
endif

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SOURCES) $(HEADERS)
	$(CC) $(CFLAGS) -o $(TARGET) $(SOURCES) $(LDFLAGS)
	@echo "Built $(TARGET)"

clean:
	rm -f $(TARGET)
	@echo "Cleaned l2tcp_server"
