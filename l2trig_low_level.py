"""
l2trig_low_level.py

Low-level ctypes wrapper for L2 Trigger HAL
Provides direct 1:1 mapping to C functions with error handling

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
"""

import ctypes
from ctypes import c_uint8, c_uint16, c_uint32, c_uint64, c_int, POINTER
from enum import IntEnum
from typing import Optional
import os

# ============================================================================
# Error Handling
# ============================================================================

class HALError(IntEnum):
    """Error codes from C HAL"""
    NO_ERROR = 0
    TIMEOUT = 1
    INVALID_PARAMETER = 2


class L2TrigError(Exception):
    """Base exception for L2 Trigger HAL errors"""
    pass


class TimeoutError(L2TrigError):
    """Hardware communication timeout"""
    pass


class InvalidParameterError(L2TrigError):
    """Invalid parameter passed to HAL function"""
    pass


def _check_error(err_code: int, context: str = "") -> None:
    """Convert C error codes to Python exceptions"""
    if err_code == HALError.TIMEOUT:
        raise TimeoutError(f"Hardware timeout: {context}")
    elif err_code == HALError.INVALID_PARAMETER:
        raise InvalidParameterError(f"Invalid parameter: {context}")
    elif err_code != HALError.NO_ERROR:
        raise L2TrigError(f"Unknown error {err_code}: {context}")


# ============================================================================
# Library Loading
# ============================================================================

# Try to load the shared library
_lib = None
_lib_path_candidates = [
    './libl2trig_hal.so',
    './hal/libl2trig_hal.so',
    '/usr/local/lib/libl2trig_hal.so',
    '/usr/lib/libl2trig_hal.so',
]

for path in _lib_path_candidates:
    if os.path.exists(path):
        try:
            _lib = ctypes.CDLL(path)
            break
        except OSError:
            continue

if _lib is None:
    raise RuntimeError(
        "Could not load libl2trig_hal.so. "
        "Please compile with: gcc -shared -fPIC -o libl2trig_hal.so l2trig_hal.c l2trig_hal_exports.c"
    )

# ============================================================================
# Function Signatures
# ============================================================================

# SPI Functions
_lib.cta_l2cb_spi_read.argtypes = [c_uint8, c_uint8, POINTER(c_uint16)]
_lib.cta_l2cb_spi_read.restype = c_int

_lib.cta_l2cb_spi_write.argtypes = [c_uint8, c_uint8, c_uint16]
_lib.cta_l2cb_spi_write.restype = c_int

_lib.cta_l2cb_spi_wait.argtypes = []
_lib.cta_l2cb_spi_wait.restype = c_int

_lib.cta_l2cb_spi_set_ctdb_delays_export.argtypes = [ctypes.c_int64, ctypes.c_int64, ctypes.c_int64]
_lib.cta_l2cb_spi_set_ctdb_delays_export.restype = None

_lib.cta_l2cb_spi_set_delay_delays_export.argtypes = [ctypes.c_int64, ctypes.c_int64, ctypes.c_int64]
_lib.cta_l2cb_spi_set_delay_delays_export.restype = None

# L2CB Functions
_lib.cta_l2cb_getFirmwareRevision_export.argtypes = []
_lib.cta_l2cb_getFirmwareRevision_export.restype = c_uint16

_lib.cta_l2cb_readTimestamp_export.argtypes = []
_lib.cta_l2cb_readTimestamp_export.restype = c_uint64

_lib.cta_l2cb_getControlState_export.argtypes = [POINTER(c_uint16), POINTER(c_uint16), POINTER(c_uint16)]
_lib.cta_l2cb_getControlState_export.restype = None

_lib.cta_l2cb_setMCFEnabled_export.argtypes = [c_uint16]
_lib.cta_l2cb_setMCFEnabled_export.restype = None

_lib.cta_l2cb_setBusyGlitchFilterEnabled_export.argtypes = [c_uint16]
_lib.cta_l2cb_setBusyGlitchFilterEnabled_export.restype = None

_lib.cta_l2cb_setTIBTriggerBusyBlockEnabled_export.argtypes = [c_uint16]
_lib.cta_l2cb_setTIBTriggerBusyBlockEnabled_export.restype = None

# L1 Trigger Control
_lib.cta_l2cb_setL1TriggerEnabled_export.argtypes = [c_uint8, c_uint16]
_lib.cta_l2cb_setL1TriggerEnabled_export.restype = None

_lib.cta_l2cb_getL1TriggerEnabled_export.argtypes = [c_uint8]
_lib.cta_l2cb_getL1TriggerEnabled_export.restype = c_uint16

_lib.cta_l2cb_setL1TriggerChannelEnabled_export.argtypes = [c_uint8, c_uint8, c_uint16]
_lib.cta_l2cb_setL1TriggerChannelEnabled_export.restype = None

_lib.cta_l2cb_getL1TriggerChannelEnabled_export.argtypes = [c_uint8, c_uint8]
_lib.cta_l2cb_getL1TriggerChannelEnabled_export.restype = c_uint16

_lib.cta_l2cb_setL1TriggerDelay_export.argtypes = [c_uint8, c_uint8, c_uint16]
_lib.cta_l2cb_setL1TriggerDelay_export.restype = c_int

_lib.cta_l2cb_getL1TriggerDelay_export.argtypes = [c_uint8, c_uint8]
_lib.cta_l2cb_getL1TriggerDelay_export.restype = c_uint16

# CTDB Power Control
_lib.cta_ctdb_setPowerEnabled_export.argtypes = [c_uint8, c_uint16]
_lib.cta_ctdb_setPowerEnabled_export.restype = c_int

_lib.cta_ctdb_getPowerEnabled_export.argtypes = [c_uint8, POINTER(c_uint16)]
_lib.cta_ctdb_getPowerEnabled_export.restype = c_int

_lib.cta_ctdb_setPowerChannelEnabled_export.argtypes = [c_uint8, c_uint16, c_int]
_lib.cta_ctdb_setPowerChannelEnabled_export.restype = c_int

_lib.cta_ctdb_getPowerChannelEnabled_export.argtypes = [c_uint8, c_uint16, POINTER(c_int)]
_lib.cta_ctdb_getPowerChannelEnabled_export.restype = c_int

_lib.cta_ctdb_setPowerEnabledToAll_export.argtypes = [c_uint16]
_lib.cta_ctdb_setPowerEnabledToAll_export.restype = None

# CTDB Current Monitoring
_lib.cta_ctdb_setPowerCurrentMax_export.argtypes = [c_uint8, c_uint16]
_lib.cta_ctdb_setPowerCurrentMax_export.restype = c_int

_lib.cta_ctdb_getPowerCurrentMax_export.argtypes = [c_uint8, POINTER(c_uint16)]
_lib.cta_ctdb_getPowerCurrentMax_export.restype = c_int

_lib.cta_ctdb_setPowerCurrentMin_export.argtypes = [c_uint8, c_uint16]
_lib.cta_ctdb_setPowerCurrentMin_export.restype = c_int

_lib.cta_ctdb_getPowerCurrentMin_export.argtypes = [c_uint8, POINTER(c_uint16)]
_lib.cta_ctdb_getPowerCurrentMin_export.restype = c_int

_lib.cta_ctdb_getPowerCurrent_export.argtypes = [c_uint8, c_uint16, POINTER(c_uint16)]
_lib.cta_ctdb_getPowerCurrent_export.restype = c_int

_lib.cta_ctdb_getUnderCurrentErrors_export.argtypes = [c_uint8, POINTER(c_uint16)]
_lib.cta_ctdb_getUnderCurrentErrors_export.restype = c_int

_lib.cta_ctdb_getOverCurrentErrors_export.argtypes = [c_uint8, POINTER(c_uint16)]
_lib.cta_ctdb_getOverCurrentErrors_export.restype = c_int

# CTDB Utility
_lib.cta_ctdb_getFirmwareRevision_export.argtypes = [c_uint8, POINTER(c_uint16)]
_lib.cta_ctdb_getFirmwareRevision_export.restype = c_int

_lib.cta_ctdb_setDebugPins_export.argtypes = [c_uint8, c_uint16]
_lib.cta_ctdb_setDebugPins_export.restype = c_int

_lib.cta_ctdb_getDebugPins_export.argtypes = [c_uint8, POINTER(c_uint16)]
_lib.cta_ctdb_getDebugPins_export.restype = c_int

_lib.cta_ctdb_getSlaveRegister_export.argtypes = [c_uint8, c_uint8, POINTER(c_uint16)]
_lib.cta_ctdb_getSlaveRegister_export.restype = c_int

_lib.cta_ctdb_setSlaveRegister_export.argtypes = [c_uint8, c_uint8, c_uint16]
_lib.cta_ctdb_setSlaveRegister_export.restype = c_int

_lib.cta_l2cb_isValidSlot_export.argtypes = [c_int]
_lib.cta_l2cb_isValidSlot_export.restype = c_int

# ============================================================================
# Constants
# ============================================================================

# Default timing in nanoseconds
DEFAULT_MIN_COMMAND_DELAY_NS = 0
DEFAULT_MIN_READ_DELAY_NS = 0
DEFAULT_TIMEOUT_NS = 100000  # 100 microseconds

CURRENT_CONVERSION_FACTOR = 0.485  # mA per ADC count
CURRENT_CODE_MAX = 0x0FFF  # Max raw ADC code (12 bits)
CURRENT_MAX = CURRENT_CODE_MAX * CURRENT_CONVERSION_FACTOR  # Max current corresponding to 12-bit ADC value

L1DELAY_CONVERSION_FACTOR = 0.037  # ns per raw step (37 ps steps)
L1DELAY_CODE_MAX = 0x7F # Max raw code for L1 delay (7 bits, 0-4.74ns range in 37 ps steps)
L1DELAY_MAX = L1DELAY_CODE_MAX * L1DELAY_CONVERSION_FACTOR  # Max delay corresponding to raw code

MCFDELAY_CONVERSION_FACTOR = 5  # ns per raw step
MCFDELAY_CODE_MAX = 0x0F # Max raw code for MCF delay (4 bits)
MCFDELAY_MAX = MCFDELAY_CODE_MAX * MCFDELAY_CONVERSION_FACTOR  # Max MCF delay corresponding to raw code

MCFTHRESHOLD_CODE_MAX = 0x7F # Max raw code for MCF threshold (7 bits)

L1DEADTIME_CONVERSION_FACTOR = 5  # ns per raw step
L1DEADTIME_CODE_MAX = 0xFF # Max raw code for L1 deadtime (8 bits)
L1DEADTIME_MAX = L1DEADTIME_CODE_MAX * L1DEADTIME_CONVERSION_FACTOR  # Max L1 deadtime corresponding to raw code

# ============================================================================
# Low-Level Python Wrappers
# ============================================================================

# --- SPI Functions ---

def set_ctdb_flowcontrol_parameters(min_command_delay_ns: int = DEFAULT_MIN_COMMAND_DELAY_NS, 
                        min_read_delay_ns: int = DEFAULT_MIN_READ_DELAY_NS, 
                        timeout_ns: int = DEFAULT_TIMEOUT_NS) -> None:
    """Configure flowcontrol delays and timeout for CTDB SPI operations"""
    _lib.cta_l2cb_spi_set_ctdb_delays_export(min_command_delay_ns, min_read_delay_ns, timeout_ns)


def set_delay_flowcontrol_parameters(min_command_delay_ns: int = DEFAULT_MIN_COMMAND_DELAY_NS, 
                         min_read_delay_ns: int = DEFAULT_MIN_READ_DELAY_NS, 
                         timeout_ns: int = DEFAULT_TIMEOUT_NS) -> None:
    """Configure flowcontrol delays and timeout for L1 Delay SPI operations"""
    _lib.cta_l2cb_spi_set_delay_delays_export(min_command_delay_ns, min_read_delay_ns, timeout_ns)


def spi_read(slot: int, register: int) -> int:
    """Read a register via SPI from CTDB at given slot"""
    value = c_uint16()
    err = _lib.cta_l2cb_spi_read(slot, register, ctypes.byref(value))
    _check_error(err, f"spi_read(slot={slot}, reg=0x{register:02X})")
    return value.value


def spi_write(slot: int, register: int, value: int) -> None:
    """Write a register via SPI to CTDB at given slot"""
    err = _lib.cta_l2cb_spi_write(slot, register, value)
    _check_error(err, f"spi_write(slot={slot}, reg=0x{register:02X}, val=0x{value:04X})")


def spi_wait() -> None:
    """Wait for SPI transfer to complete"""
    err = _lib.cta_l2cb_spi_wait()
    _check_error(err, "spi_wait")


# --- L2CB Functions ---

def get_l2cb_firmware_revision() -> int:
    """Get L2CB firmware revision"""
    return _lib.cta_l2cb_getFirmwareRevision_export()


def get_l2cb_timestamp() -> int:
    """Read the current timestamp (48-bit value)"""
    return _lib.cta_l2cb_readTimestamp_export()

def get_l2cb_control_state() -> dict:
    """Get the current control state (MCF enabled, busy glitch filter enabled, TIB trigger block enabled)"""
    mcf_enabled = c_uint16()
    busy_glitch_filter_enabled = c_uint16()
    tib_trigger_busy_block_enabled = c_uint16()
    _lib.cta_l2cb_getControlState_export(ctypes.byref(mcf_enabled), ctypes.byref(busy_glitch_filter_enabled), ctypes.byref(tib_trigger_busy_block_enabled))
    return {
        "mcf_enabled": bool(mcf_enabled.value),
        "busy_glitch_filter_enabled": bool(busy_glitch_filter_enabled.value),
        "tib_trigger_busy_block_enabled": bool(tib_trigger_busy_block_enabled.value)
    }

def set_l2cb_mcf_enabled(enabled: bool) -> None:
    """Set L2CB MCF enabled status"""
    _lib.cta_l2cb_setMCFEnabled_export(1 if enabled else 0)


def set_l2cb_busy_glitch_filter_enabled(enabled: bool) -> None:
    """Set L2CB busy glitch filter enabled status"""
    _lib.cta_l2cb_setBusyGlitchFilterEnabled_export(1 if enabled else 0)


def set_l2cb_tib_trigger_busy_block_enabled(enabled: bool) -> None:
    """Set L2CB TIB trigger block enabled status"""
    _lib.cta_l2cb_setTIBTriggerBusyBlockEnabled_export(1 if enabled else 0)

def get_l2cb_mcf_threshold() -> int:
    """Get L2CB MCF threshold (raw code, 0-127)"""
    return _lib.cta_l2cb_getMCFThreshold_export()

def set_l2cb_mcf_threshold(threshold: int) -> None:
    """Set L2CB MCF threshold (raw code, 0-127)"""
    _lib.cta_l2cb_setMCFThreshold_export(threshold)

def get_l2cb_mcf_delay() -> int:
    """Get L2CB MCF delay (raw code, 0-15)"""
    return _lib.cta_l2cb_getMCFDelay_export()

def set_l2cb_mcf_delay(delay: int) -> None:
    """Set L2CB MCF delay (raw code, 0-15)"""
    _lib.cta_l2cb_setMCFDelay_export(delay)

def get_l2cb_l1_deadtime() -> int:
    """Get L2CB L1 deadtime (raw code, 0-255)"""
    return _lib.cta_l2cb_getL1Deadtime_export()

def set_l2cb_l1_deadtime(deadtime: int) -> None:
    """Set L2CB L1 deadtime (raw code, 0-255)"""
    _lib.cta_l2cb_setL1Deadtime_export(deadtime)

# --- L1 Trigger Control ---

def set_l1_trigger_enabled(slot: int, enabled: int) -> None:
    """Set trigger enabled status for all channels of a slot"""
    _lib.cta_l2cb_setL1TriggerEnabled_export(slot, enabled)


def get_l1_trigger_enabled(slot: int) -> int:
    """Get trigger enabled status for all channels of a slot"""
    return _lib.cta_l2cb_getL1TriggerEnabled_export(slot)


def set_l1_trigger_channel_enabled(slot: int, channel: int, enabled: bool) -> None:
    """Set trigger enabled status for a specific channel"""
    _lib.cta_l2cb_setL1TriggerChannelEnabled_export(slot, channel, 1 if enabled else 0)


def get_l1_trigger_channel_enabled(slot: int, channel: int) -> bool:
    """Get trigger enabled status for a specific channel"""
    return bool(_lib.cta_l2cb_getL1TriggerChannelEnabled_export(slot, channel))


def set_l1_trigger_delay(slot: int, channel: int, delay: int) -> None:
    """
    Set trigger delay for a channel
    delay: in 37 ps steps, 0-5ns range (0x00 to 0x7f)
    """
    err = _lib.cta_l2cb_setL1TriggerDelay_export(slot, channel, delay)
    _check_error(err, f"set_l1_trigger_delay(slot={slot}, ch={channel}, delay={delay})")


def get_l1_trigger_delay(slot: int, channel: int) -> int:
    """Get trigger delay for a channel (in 37 ps steps)"""
    return _lib.cta_l2cb_getL1TriggerDelay_export(slot, channel)


# --- CTDB Power Control ---

def set_power_enabled(slot: int, value: int) -> None:
    """Set power enable register (bits 1-15 = channels 1-15)"""
    err = _lib.cta_ctdb_setPowerEnabled_export(slot, value)
    _check_error(err, f"set_power_enable(slot={slot}, val=0x{value:04X})")


def get_power_enabled(slot: int) -> int:
    """Get power enable register (bits 1-15 = channels 1-15)"""
    value = c_uint16()
    err = _lib.cta_ctdb_getPowerEnabled_export(slot, ctypes.byref(value))
    _check_error(err, f"get_power_enable(slot={slot})")
    return value.value


def set_power_channel_enabled(slot: int, channel: int, enabled: bool) -> None:
    """Enable or disable a specific power channel"""
    err = _lib.cta_ctdb_setPowerChannelEnabled_export(slot, channel, 1 if enabled else 0)
    _check_error(err, f"set_power_channel_enable(slot={slot}, ch={channel}, en={enabled})")


def get_power_channel_enabled(slot: int, channel: int) -> bool:
    """Get enable status of a specific power channel"""
    is_on = c_int()
    err = _lib.cta_ctdb_getPowerChannelEnabled_export(slot, channel, ctypes.byref(is_on))
    _check_error(err, f"get_power_channel_enable(slot={slot}, ch={channel})")
    return bool(is_on.value)


def set_power_enabled_all(enabled: bool) -> None:
    """Enable or disable all power channels on all slots"""
    _lib.cta_ctdb_setPowerEnabledToAll_export(1 if enabled else 0)


# --- CTDB Current Monitoring ---

def set_power_current_max(slot: int, value_raw: int) -> None:
    """Set maximum current limit (raw ADC value, 0.485mA per count)"""
    err = _lib.cta_ctdb_setPowerCurrentMax_export(slot, value_raw)
    _check_error(err, f"set_power_current_max(slot={slot}, val={value_raw})")


def get_power_current_max(slot: int) -> int:
    """Get maximum current limit (raw ADC value)"""
    value = c_uint16()
    err = _lib.cta_ctdb_getPowerCurrentMax_export(slot, ctypes.byref(value))
    _check_error(err, f"get_power_current_max(slot={slot})")
    return value.value


def set_power_current_min(slot: int, value_raw: int) -> None:
    """Set minimum current limit (raw ADC value, 0.485mA per count)"""
    err = _lib.cta_ctdb_setPowerCurrentMin_export(slot, value_raw)
    _check_error(err, f"set_power_current_min(slot={slot}, val={value_raw})")


def get_power_current_min(slot: int) -> int:
    """Get minimum current limit (raw ADC value)"""
    value = c_uint16()
    err = _lib.cta_ctdb_getPowerCurrentMin_export(slot, ctypes.byref(value))
    _check_error(err, f"get_power_current_min(slot={slot})")
    return value.value


def get_power_current(slot: int, channel: int) -> float:
    """
    Get current reading for a channel
    channel 0: CTDB board itself
    channel 1-15: individual power channels
    Returns: current in mA
    """
    value = c_uint16()
    err = _lib.cta_ctdb_getPowerCurrent_export(slot, channel, ctypes.byref(value))
    _check_error(err, f"get_power_current(slot={slot}, ch={channel})")
    # Convert to mA: 0.485mA per count, mask to 12 bits
    return (value.value & 0x0FFF) * CURRENT_CONVERSION_FACTOR


def get_under_current_errors(slot: int) -> int:
    """Get under-current error vector (bits 1-15 = channels 1-15)"""
    value = c_uint16()
    err = _lib.cta_ctdb_getUnderCurrentErrors_export(slot, ctypes.byref(value))
    _check_error(err, f"get_under_current_errors(slot={slot})")
    return value.value


def get_over_current_errors(slot: int) -> int:
    """Get over-current error vector (bits 1-15 = channels 1-15)"""
    value = c_uint16()
    err = _lib.cta_ctdb_getOverCurrentErrors_export(slot, ctypes.byref(value))
    _check_error(err, f"get_over_current_errors(slot={slot})")
    return value.value


# --- CTDB Utility ---

def get_ctdb_firmware_revision(slot: int) -> int:
    """Get CTDB firmware revision"""
    value = c_uint16()
    err = _lib.cta_ctdb_getFirmwareRevision_export(slot, ctypes.byref(value))
    _check_error(err, f"get_ctdb_firmware_revision(slot={slot})")
    return value.value


def set_debug_pins(slot: int, value: int) -> None:
    """Set debug pins (bits 0-3 = SEL0-3)"""
    err = _lib.cta_ctdb_setDebugPins_export(slot, value)
    _check_error(err, f"set_debug_pins(slot={slot}, val={value})")


def get_debug_pins(slot: int) -> int:
    """Get debug pins (bits 0-3 = SEL0-3)"""
    value = c_uint16()
    err = _lib.cta_ctdb_getDebugPins_export(slot, ctypes.byref(value))
    _check_error(err, f"get_debug_pins(slot={slot})")
    return value.value


def get_slave_register(slot: int, address: int) -> int:
    """Read arbitrary slave register"""
    value = c_uint16()
    err = _lib.cta_ctdb_getSlaveRegister_export(slot, address, ctypes.byref(value))
    _check_error(err, f"get_slave_register(slot={slot}, addr=0x{address:02X})")
    return value.value


def set_slave_register(slot: int, address: int, value: int) -> None:
    """Write arbitrary slave register"""
    err = _lib.cta_ctdb_setSlaveRegister_export(slot, address, value)
    _check_error(err, f"set_slave_register(slot={slot}, addr=0x{address:02X}, val=0x{value:04X})")


# --- Validation ---

def is_valid_slot(slot: int) -> bool:
    """Check if a slot number is valid (1-9, 13-21)"""
    return bool(_lib.cta_l2cb_isValidSlot_export(slot))


# ============================================================================
# Convenience Functions
# ============================================================================

def current_ma_to_raw(current_ma: float) -> int:
    """Convert current in mA to raw ADC value"""
    return int(current_ma / CURRENT_CONVERSION_FACTOR)


def current_raw_to_ma(raw_value: int) -> float:
    """Convert raw ADC value to current in mA"""
    return (raw_value & 0x0FFF) * CURRENT_CONVERSION_FACTOR


def delay_ns_to_raw(delay_ns: float) -> int:
    """Convert delay in nanoseconds to raw value (37 ps steps)"""
    return int(delay_ns / 0.037)


def delay_raw_to_ns(raw_value: int) -> float:
    """Convert raw delay value to nanoseconds"""
    return (raw_value & 0x7F) * 0.037

def mcf_delay_ns_to_raw(delay_ns: float) -> int:
    """Convert MCF delay in nanoseconds to raw value (5 ns steps)"""
    return int(delay_ns / 5)

def mcf_delay_raw_to_ns(raw_value: int) -> float:
    """Convert raw MCF delay value to nanoseconds"""
    return (raw_value & 0x0F) * 5

def l1_deadtime_ns_to_raw(deadtime_ns: float) -> int:
    """Convert L1 deadtime in nanoseconds to raw value (5 ns steps)"""
    return int(deadtime_ns / 5)

def l1_deadtime_raw_to_ns(raw_value: int) -> float:
    """Convert raw L1 deadtime value to nanoseconds"""
    return (raw_value & 0xFF) * 5
