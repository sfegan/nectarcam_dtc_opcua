# Top-level Makefile for nectarcam_dtc_opcua project

.PHONY: all clean install uninstall test help dummy

# Optional: Set to 1 to build with dummy implementations for testing
DUMMY ?= 0

# Subdirectories to build
SUBDIRS = hal

# Build variables
ifeq ($(DUMMY),1)
	CFLAGS_EXTRA = -DDUMMY
	BUILD_SUFFIX = -dummy
else
	CFLAGS_EXTRA =
	BUILD_SUFFIX =
endif

all: build

build:
	@echo "Building HAL library$(BUILD_SUFFIX)..."
	@$(MAKE) -C hal DUMMY=$(DUMMY)

dummy:
	@echo "Building HAL library with EMULATESMC mode..."
	@$(MAKE) -C hal EMULATESMC=1

clean:
	@echo "Cleaning build artifacts..."
	@$(MAKE) -C hal clean
	rm -f l2trig_emulator_state.dat
	rm -rf __pycache__

install: build
	@echo "Installing HAL library..."
	@$(MAKE) -C hal install

uninstall:
	@echo "Uninstalling HAL library..."
	@$(MAKE) -C hal uninstall

help:
	@echo "nectarcam_dtc_opcua Build System"
	@echo "=================================="
	@echo ""
	@echo "Targets:"
	@echo "  all         - Build the project (default)"
	@echo "  build       - Build the HAL library"
	@echo "  dummy       - Build HAL library with dummy implementations for testing"
	@echo "  clean       - Clean build artifacts"
	@echo "  install     - Build and install the library"
	@echo "  uninstall   - Uninstall the library"
	@echo "  test        - Run tests (if available)"
	@echo "  help        - Show this help message"
	@echo ""
	@echo "Variables:"
	@echo "  DUMMY=1     - Build with dummy hardware implementations (for testing without hardware)"
	@echo "  PREFIX      - Installation prefix (default: /usr/local)"
	@echo ""
	@echo "Examples:"
	@echo "  make                    # Build normally"
	@echo "  make DUMMY=1            # Build with dummy implementations"
	@echo "  make dummy              # Same as DUMMY=1"
	@echo "  make install PREFIX=/opt/nectarcam  # Install to custom location"

test: dummy
	@echo "Testing with dummy implementations..."
	@$(MAKE) -C hal test

.DEFAULT_GOAL := all
