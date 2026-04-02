"""
l2trig_api.py

High-level async API for L2 Trigger System
Provides business logic layer with proper error handling and type safety

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
from enum import Enum
import logging

import l2trig_low_level as hal

# ============================================================================
# Constants
# ============================================================================

VALID_SLOTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14, 15, 16, 17, 18, 19, 20, 21]
CHANNELS_PER_SLOT = 15

# ============================================================================
# Logging
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# Data Classes
# ============================================================================

class ChannelState(Enum):
    """Power channel state"""
    OFF = "off"
    ON = "on"
    ERROR_OVER_CURRENT = "error_over_current"
    ERROR_UNDER_CURRENT = "error_under_current"
    ERROR_BOTH = "error_both"


@dataclass
class PowerChannel:
    """Power status for a single channel"""
    slot: int
    channel: int
    enabled: bool
    current_ma: float
    state: ChannelState
    
    @property
    def has_error(self) -> bool:
        """Check if channel has any error"""
        return self.state in (
            ChannelState.ERROR_OVER_CURRENT,
            ChannelState.ERROR_UNDER_CURRENT,
            ChannelState.ERROR_BOTH
        )


@dataclass
class TriggerChannel:
    """Trigger configuration for a single channel"""
    slot: int
    channel: int
    enabled: bool
    delay_ns: float


@dataclass
class CTDBMonitoringData:
    """High-frequency monitoring data for one CTDB board"""
    slot: int
    ctdb_current_ma: float
    channel_currents_ma: List[float]
    over_current_errors: int
    under_current_errors: int
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CTDBConfigData:
    """Low-frequency configuration data for one CTDB board"""
    slot: int
    firmware_version: int
    power_enabled_mask: int
    current_limit_min_ma: float
    current_limit_max_ma: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CTDBStatus:
    """Complete status for one CTDB board"""
    slot: int
    firmware_version: int
    power_channels: List[PowerChannel]
    ctdb_current_ma: float
    current_limit_min_ma: float
    current_limit_max_ma: float
    over_current_errors: int
    under_current_errors: int
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def has_errors(self) -> bool:
        """Check if any channel has errors"""
        return any(ch.has_error for ch in self.power_channels)
    
    @property
    def channels_with_errors(self) -> List[PowerChannel]:
        """Get list of channels with errors"""
        return [ch for ch in self.power_channels if ch.has_error]
    
    @property
    def total_current_ma(self) -> float:
        """Total current of all enabled channels"""
        return sum(ch.current_ma for ch in self.power_channels if ch.enabled)


@dataclass
class L2CBStatus:
    """Status of the L2CB controller board"""
    firmware_version: int
    uptime: int
    mcf_enabled: bool
    busy_glitch_filter_enabled: bool
    tib_trigger_block_enabled: bool


# ============================================================================
# CTDB Controller
# ============================================================================

class CTDBController:
    """High-level controller for a single CTDB board"""
    
    def __init__(self, slot: int):
        """
        Initialize CTDB controller
        
        Args:
            slot: Slot number (1-9, 13-21)
        """
        if slot not in VALID_SLOTS:
            raise ValueError(f"Invalid slot {slot}. Valid slots: {VALID_SLOTS}")
        
        self.slot = slot
        
        self._last_status: Optional[CTDBStatus] = None
        
        # Cached configuration data
        self._cached_config: Optional[CTDBConfigData] = None
        self._cached_trigger_status: Optional[List[TriggerChannel]] = None
    
    def get_monitoring_data(self) -> CTDBMonitoringData:
        """
        Get high-frequency monitoring data (currents and errors)
        """
        # Get CTDB board current (channel 0)
        ctdb_current = hal.get_power_current(self.slot, 0)
        
        # Get all channel currents
        channel_currents = []
        for ch in range(1, CHANNELS_PER_SLOT + 1):
            current = hal.get_power_current(self.slot, ch)
            channel_currents.append(current)
        
        # Get error vectors
        over_current_errors = hal.get_over_current_errors(self.slot)
        under_current_errors = hal.get_under_current_errors(self.slot)
        
        return CTDBMonitoringData(
            slot=self.slot,
            ctdb_current_ma=ctdb_current,
            channel_currents_ma=channel_currents,
            over_current_errors=over_current_errors,
            under_current_errors=under_current_errors
        )

    def get_configuration_data(self) -> CTDBConfigData:
        """
        Get low-frequency configuration data (firmware, limits, enable status)
        """
        # Get firmware version
        fw_version = hal.get_ctdb_firmware_revision(self.slot)
        
        # Get power enable register
        power_reg = hal.get_power_enabled(self.slot)
        
        # Get current limits
        limit_min_raw = hal.get_power_current_min(self.slot)
        limit_max_raw = hal.get_power_current_max(self.slot)
        
        config = CTDBConfigData(
            slot=self.slot,
            firmware_version=fw_version,
            power_enabled_mask=power_reg,
            current_limit_min_ma=hal.current_raw_to_ma(limit_min_raw),
            current_limit_max_ma=hal.current_raw_to_ma(limit_max_raw)
        )
        self._cached_config = config
        return config

    def get_status(self) -> CTDBStatus:
        """
        Get complete status of this CTDB
        
        Returns:
            CTDBStatus object with all current information
        """
        config = self.get_configuration_data()
        monitoring = self.get_monitoring_data()
        
        channels = []
        for i in range(CHANNELS_PER_SLOT):
            ch = i + 1
            enabled = bool(config.power_enabled_mask & (1 << ch))
            current = monitoring.channel_currents_ma[i]
            
            # Determine state
            has_over = bool(monitoring.over_current_errors & (1 << ch))
            has_under = bool(monitoring.under_current_errors & (1 << ch))
            
            if has_over and has_under:
                state = ChannelState.ERROR_BOTH
            elif has_over:
                state = ChannelState.ERROR_OVER_CURRENT
            elif has_under:
                state = ChannelState.ERROR_UNDER_CURRENT
            elif enabled:
                state = ChannelState.ON
            else:
                state = ChannelState.OFF
            
            channels.append(PowerChannel(
                slot=self.slot,
                channel=ch,
                enabled=enabled,
                current_ma=current,
                state=state
            ))
        
        status = CTDBStatus(
            slot=self.slot,
            firmware_version=config.firmware_version,
            power_channels=channels,
            ctdb_current_ma=monitoring.ctdb_current_ma,
            current_limit_min_ma=config.current_limit_min_ma,
            current_limit_max_ma=config.current_limit_max_ma,
            over_current_errors=monitoring.over_current_errors,
            under_current_errors=monitoring.under_current_errors
        )
        
        self._last_status = status
        return status
    
    def set_channel_power_enabled(self, channel: int, enabled: bool) -> None:
        """
        Enable or disable a single power channel
        
        Args:
            channel: Channel number (1-15)
            enabled: True to enable, False to disable
        """
        if not 1 <= channel <= CHANNELS_PER_SLOT:
            raise ValueError(f"Channel must be 1-{CHANNELS_PER_SLOT}")
        
        hal.set_power_channel_enabled( 
            self.slot, channel, enabled
        )
            
        logger.debug(f"Slot {self.slot} Ch{channel}: Power {'enabled' if enabled else 'disabled'}")
    
    def set_all_power_enabled(self, enabled: bool) -> None:
        """
        Enable or disable all power channels
        
        Args:
            enabled: True to enable all, False to disable all
        """
        value = 0xFFFE if enabled else 0x0000  # bits 1-15
        
        hal.set_power_enabled(self.slot, value)
        
        logger.debug(f"Slot {self.slot}: All channels {'enabled' if enabled else 'disabled'}")
    
    def set_some_power_enabled(self, channel_states: Dict[int, bool]) -> None:
        """
        Set multiple channels at once
        
        Args:
            channel_states: Dict mapping channel number to enable state
        """
        # Read current state
        power_reg = hal.get_power_enabled(self.slot)
        
        # Modify bits
        for channel, enabled in channel_states.items():
            if not 1 <= channel <= CHANNELS_PER_SLOT:
                raise ValueError(f"Channel must be 1-{CHANNELS_PER_SLOT}")
            
            if enabled:
                power_reg |= (1 << channel)
            else:
                power_reg &= ~(1 << channel)
        
        # Write back
        hal.set_power_enabled(self.slot, power_reg)
        
        logger.debug(f"Slot {self.slot}: Set channels {channel_states}")
    
    def set_current_limits(self, min_ma: float, max_ma: float) -> None:
        """
        Set current limits for all channels
        
        Args:
            min_ma: Minimum current in mA
            max_ma: Maximum current in mA
        """

        if min_ma < 0:
            logger.warning(f"Requested under-current {min_ma} mA is negative, setting to 0")
            min_ma = 0.0
        if min_ma > hal.CURRENT_MAX:
            logger.warning(f"Requested under-current {min_ma} mA exceeds max {hal.CURRENT_MAX:.1f} mA, setting to max")
            min_ma = hal.CURRENT_MAX
        if max_ma < min_ma  :
            logger.warning(f"Requested over-current {max_ma} mA is less than requested minimum {min_ma} mA, setting to minimum")   
            max_ma = min_ma
        if max_ma > hal.CURRENT_MAX:
            logger.warning(f"Requested over-current {max_ma} mA exceeds max {hal.CURRENT_MAX:.1f} mA, setting to max")
            max_ma = hal.CURRENT_MAX

        min_raw = hal.current_ma_to_raw(min_ma)
        max_raw = hal.current_ma_to_raw(max_ma)
        
        hal.set_power_current_min(self.slot, min_raw)
        hal.set_power_current_max(self.slot, max_raw)
        
        logger.debug(f"Slot {self.slot}: Current limits set to {min_ma:.1f}-{max_ma:.1f} mA (raw: {min_raw}-{max_raw})")
    
        return min_ma, max_ma

    def get_trigger_status(self) -> List[TriggerChannel]:
        """Get trigger configuration for all channels"""
        # Get trigger enabled status
        mask = hal.get_l1_trigger_enabled(self.slot)
        
        channels = []
        for ch in range(1,CHANNELS_PER_SLOT+1):
            enabled = bool(mask & (1 << ch))
            
            # Get delay
            delay_raw = hal.get_l1_trigger_delay(self.slot, ch)
            
            channels.append(TriggerChannel(
                slot=self.slot,
                channel=ch,
                enabled=enabled,
                delay_ns=hal.delay_raw_to_ns(delay_raw)
            ))
        
        return channels
    
    def set_channel_trigger_enabled(self, channel: int, enabled: bool) -> None:
        """Set trigger enabled status for a channel"""
        if not 1 <= channel <= CHANNELS_PER_SLOT:
            raise ValueError(f"Channel must be 1-{CHANNELS_PER_SLOT}")
        
        hal.set_l1_trigger_channel_enabled( 
            self.slot, channel, enabled
        )
        
        logger.debug(f"Slot {self.slot} Trigger Ch{channel}: {'Enabled' if enabled else 'Disabled'}")

    def set_all_trigger_enabled(self, enabled: bool) -> None:
        """Set trigger enabled status for all channels on this board"""
        mask = 0x7FFF if enabled else 0x0000
        hal.set_l1_trigger_enabled(self.slot, mask)
        logger.debug(f"Slot {self.slot}: All trigger channels {'enabled' if enabled else 'disabled'}")
    
    def set_channel_trigger_delay(self, channel: int, delay_ns: float) -> None:
        """Set trigger delay for a channel"""
        if not 1 <= channel <= CHANNELS_PER_SLOT:
            raise ValueError(f"Channel must be 1-{CHANNELS_PER_SLOT}")
    
        if delay_ns < 0:
            logger.warning(f"Requested delay {delay_ns} ns is negative, setting to 0")
            delay_ns = 0.0
        elif delay_ns > hal.L1DELAY_MAX:
            logger.warning(f"Requested delay {delay_ns} ns exceeds max {hal.L1DELAY_MAX:.1f} ns, setting to max")
            delay_ns = hal.L1DELAY_MAX
        
        delay_raw = hal.delay_ns_to_raw(delay_ns)
        
        hal.set_l1_trigger_delay( 
            self.slot, channel, delay_raw
        )
        
        logger.debug(f"Slot {self.slot} Trigger Ch{channel}: Delay set to {delay_ns:.3f} ns")


# ============================================================================
# L2 Trigger System Controller
# ============================================================================

class L2TriggerSystem:
    """High-level controller for entire L2 trigger system"""
    
    def __init__(self, enabled_slots: Optional[List[int]] = None):
        """
        Initialize L2 trigger system
        
        Args:
            enabled_slots: List of slots to control (default: all valid slots)
        """
        if enabled_slots is None:
            enabled_slots = VALID_SLOTS
        
        # Validate slots
        invalid_slots = set(enabled_slots) - set(VALID_SLOTS)
        if invalid_slots:
            raise ValueError(f"Invalid slots: {invalid_slots}")
        
        self.ctdbs = {
            slot: CTDBController(slot) 
            for slot in enabled_slots
        }

    def get_l2cb_status(self) -> L2CBStatus:
        """Get status of the L2CB controller board"""
        fw_version = hal.get_l2cb_firmware_revision()
        uptime = hal.get_l2cb_timestamp()
        
        control = hal.get_l2cb_control_state()

        return L2CBStatus(
            firmware_version=fw_version,
            uptime=uptime,
            mcf_enabled=control["mcf_enabled"],
            busy_glitch_filter_enabled=control["busy_glitch_filter_enabled"],
            tib_trigger_block_enabled=control["tib_trigger_block_enabled"]
        )

    def set_mcf_enabled(self, enabled: bool) -> None:
        """Enable or disable L2CB MCF trigger propagation"""
        hal.set_l2cb_mcf_enabled(enabled)
        logger.info(f"L2CB MCF trigger propagation {'enabled' if enabled else 'disabled'}")

    def set_busy_glitch_filter_enabled(self, enabled: bool) -> None:
        """Enable or disable L2CB busy glitch filter"""
        hal.set_l2cb_busy_glitch_filter_enabled(enabled)
        logger.info(f"L2CB busy glitch filter {'enabled' if enabled else 'disabled'}")

    def set_tib_trigger_block_enabled(self, enabled: bool) -> None:
        """Enable or disable L2CB TIB trigger blocking"""
        hal.set_l2cb_tib_trigger_block_enabled(enabled)
        logger.info(f"L2CB TIB trigger blocking {'enabled' if enabled else 'disabled'}")
    
    def get_all_monitoring_data(self) -> Dict[int, CTDBMonitoringData]:
        """Get monitoring data for all CTDB boards"""
        data = {}
        for slot, ctdb in self.ctdbs.items():
            try:
                data[slot] = ctdb.get_monitoring_data()
            except Exception as e:
                logger.error(f"Error reading monitoring data from slot {slot}: {e}")
        return data

    def get_all_configuration_data(self) -> Dict[int, CTDBConfigData]:
        """Get configuration data for all CTDB boards"""
        data = {}
        for slot, ctdb in self.ctdbs.items():
            try:
                data[slot] = ctdb.get_configuration_data()
            except Exception as e:
                logger.error(f"Error reading configuration data from slot {slot}: {e}")
        return data

    def get_all_trigger_status(self) -> Dict[int, List[TriggerChannel]]:
        """Get trigger status for all CTDB boards"""
        data = {}
        for slot, ctdb in self.ctdbs.items():
            try:
                data[slot] = ctdb.get_trigger_status()
            except Exception as e:
                logger.error(f"Error reading trigger status from slot {slot}: {e}")
        return data

    def get_fast_data(self) -> Tuple[L2CBStatus, Dict[int, CTDBMonitoringData]]:
        """Consolidated high-frequency data collection"""
        l2cb = self.get_l2cb_status()
        mon = self.get_all_monitoring_data()
        return l2cb, mon

    def get_slow_data(self) -> Tuple[Dict[int, CTDBConfigData], Dict[int, List[TriggerChannel]]]:
        """Consolidated low-frequency data collection"""
        config = self.get_all_configuration_data()
        trigger = self.get_all_trigger_status()
        return config, trigger

    def get_full_data(self) -> Tuple[L2CBStatus, Dict[int, CTDBMonitoringData], 
                                     Dict[int, CTDBConfigData], Dict[int, List[TriggerChannel]]]:
        """Complete system data collection"""
        l2cb, mon = self.get_fast_data()
        config, trigger = self.get_slow_data()
        return l2cb, mon, config, trigger

    def get_all_status(self) -> Dict[int, CTDBStatus]:
        """
        Get status of all CTDB boards
        
        Returns:
            Dict mapping slot number to CTDBStatus
        """
        result = {}
        for slot, ctdb in self.ctdbs.items():
            try:
                result[slot] = ctdb.get_status()
            except Exception as e:
                logger.error(f"Error reading slot {slot}: {e}")
        
        return result
    
    def get_slot_status(self, slot: int) -> CTDBStatus:
        """Get status of a specific slot"""
        if slot not in self.ctdbs:
            raise ValueError(f"Slot {slot} not enabled")
        
        return self.ctdbs[slot].get_status()
    
    def set_channel_power_enabled(self, slot: int, channel: int, enabled: bool) -> None:
        """Set power for a specific slot/channel"""
        if slot not in self.ctdbs:
            raise ValueError(f"Slot {slot} not enabled")
        
        self.ctdbs[slot].set_channel_power_enabled(channel, enabled)
    
    def set_all_power_enabled(self, enabled: bool) -> None:
        """Enable or disable all power channels on all boards"""
        for ctdb in self.ctdbs.values():
            try:
                ctdb.set_all_power_enabled(enabled)
            except Exception as e:
                logger.error(f"Error setting power on slot {ctdb.slot}: {e}")
        
        logger.debug(f"All power channels {'enabled' if enabled else 'disabled'}")

    def set_all_trigger_enabled(self, enabled: bool) -> None:
        """Set trigger enabled status for all channels on all boards"""
        for ctdb in self.ctdbs.values():
            try:
                ctdb.set_all_trigger_enabled(enabled)
            except Exception as e:
                logger.error(f"Error setting trigger enabled on slot {ctdb.slot}: {e}")
        logger.debug(f"All trigger channels {'enabled' if enabled else 'disabled'}")

    def set_all_trigger_delay(self, delay_ns: float) -> None:
        """Set trigger delay for all channels on all boards"""
        for ctdb in self.ctdbs.values():
            for ch in range(CHANNELS_PER_SLOT):
                try:
                    ctdb.set_channel_trigger_delay(ch, delay_ns)
                except Exception as e:
                    logger.error(f"Error setting trigger delay on slot {ctdb.slot} ch {ch}: {e}")
        logger.debug(f"All trigger delays set to {delay_ns:.3f} ns")
    
    def emergency_shutdown(self) -> None:
        """Emergency shutdown - turn off all power channels immediately"""
        logger.warning("EMERGENCY SHUTDOWN initiated")
        
        # Use low-level call for speed
        hal.set_power_enabled_all(False)
        
        logger.warning("EMERGENCY SHUTDOWN complete")
    
    def set_current_limits_all(self, min_ma: float, max_ma: float) -> None:
        """Set current limits for all slots"""
        for ctdb in self.ctdbs.values():
            try:
                min_ma, max_ma = ctdb.set_current_limits(min_ma, max_ma)
            except Exception as e:
                logger.error(f"Error setting current limits on slot {ctdb.slot}: {e}")
        
        logger.debug(f"Current limits set to {min_ma:.1f}-{max_ma:.1f} mA on all slots")
    
    def get_slots_with_errors(self) -> List[int]:
        """Get list of slots that have error conditions"""
        all_status = self.get_all_status()
        return [slot for slot, status in all_status.items() if status.has_errors]
    
    def health_check(self) -> Dict[str, any]:
        """
        Perform system health check
        
        Returns:
            Dict with health information
        """
        health = {
            "overall": "healthy",
            "slots": {},
            "errors": [],
            "warnings": []
        }
        
        try:
            # Check L2CB
            l2cb_status = self.get_l2cb_status()
            health["l2cb_firmware"] = l2cb_status.firmware_version
            
            # Check all CTDBs
            all_status = self.get_all_status()
            
            for slot, status in all_status.items():
                slot_health = {
                    "firmware": status.firmware_version,
                    "ctdb_current_ma": status.ctdb_current_ma,
                    "total_current_ma": status.total_current_ma,
                    "errors": []
                }
                
                if status.has_errors:
                    health["overall"] = "degraded"
                    for ch in status.channels_with_errors:
                        error_msg = f"Ch{ch.channel}: {ch.state.value}"
                        slot_health["errors"].append(error_msg)
                        health["errors"].append(f"Slot {slot} {error_msg}")
                
                health["slots"][slot] = slot_health
            
        except Exception as e:
            health["overall"] = "error"
            health["errors"].append(f"Health check failed: {str(e)}")
        
        return health


# ============================================================================
# Example Usage
# ============================================================================

def example_usage():
    """Example usage of the L2 trigger system API"""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize system
    system = L2TriggerSystem()
    
    # Get L2CB status
    l2cb = system.get_l2cb_status()
    print(f"L2CB Firmware: 0x{l2cb.firmware_version:04X}")
    print(f"Timestamp: {l2cb.timestamp}")
    
    # Get status of all boards
    print("\n=== Getting status of all boards ===")
    all_status = system.get_all_status()
    
    for slot, status in all_status.items():
        print(f"\nSlot {slot}:")
        print(f"  Firmware: 0x{status.firmware_version:04X}")
        print(f"  CTDB Current: {status.ctdb_current_ma:.2f} mA")
        print(f"  Total Channel Current: {status.total_current_ma:.2f} mA")
        print(f"  Current Limits: {status.current_limit_min_ma:.1f} - {status.current_limit_max_ma:.1f} mA")
        
        if status.has_errors:
            print(f"  ERRORS:")
            for ch in status.channels_with_errors:
                print(f"    Ch{ch.channel}: {ch.state.value} ({ch.current_ma:.2f} mA)")
        
        # Show enabled channels
        enabled = [ch.channel for ch in status.power_channels if ch.enabled]
        if enabled:
            print(f"  Enabled channels: {enabled}")
    
    # Control specific channel
    print("\n=== Controlling power ===")
    system.set_channel_power_enabled(slot=1, channel=5, enabled=True)
    
    # Set current limits
    system.ctdbs[1].set_current_limits(min_ma=100, max_ma=2000)
    
    # Get trigger status
    print("\n=== Trigger Configuration ===")
    trigger_status = system.ctdbs[1].get_trigger_status()
    for trig in trigger_status[:5]:  # Show first 5
        print(f"  Ch{trig.channel}: {'Enabled' if trig.enabled else 'Disabled'}, Delay={trig.delay_ns:.3f}ns")
    
    # Health check
    print("\n=== Health Check ===")
    health = system.health_check()
    print(f"Overall: {health['overall']}")
    if health['errors']:
        print(f"Errors: {health['errors']}")
    
    # Example: Emergency shutdown (commented out for safety)
    # system.emergency_shutdown()


if __name__ == "__main__":
    example_usage()
