"""
l2trig_api.py

High-level async API for L2 Trigger System
Provides business logic layer with proper error handling and type safety
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from datetime import datetime
from enum import Enum
import logging

import l2trig_low_level as hal

# ============================================================================
# Constants
# ============================================================================

VALID_SLOTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14, 15, 16, 17, 18, 19, 20, 21]
CHANNELS_PER_SLOT = 15
DEFAULT_TIMEOUT_US = 10000

# ============================================================================
# System-Wide Hardware Lock
# ============================================================================

# Global lock for hardware access to ensure system-wide synchronization
# This ensures only one operation at a time can access the HAL layer
_hardware_lock = asyncio.Lock()

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
    masked: bool
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
    power_enable_mask: int
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
    timestamp: int
    timestamp_datetime: datetime


# ============================================================================
# CTDB Controller
# ============================================================================

class CTDBController:
    """High-level controller for a single CTDB board"""
    
    def __init__(self, slot: int, timeout_us: int = DEFAULT_TIMEOUT_US):
        """
        Initialize CTDB controller
        
        Args:
            slot: Slot number (1-9, 13-21)
            timeout_us: Default timeout in microseconds
        """
        if slot not in VALID_SLOTS:
            raise ValueError(f"Invalid slot {slot}. Valid slots: {VALID_SLOTS}")
        
        self.slot = slot
        self.timeout = timeout_us
        self._last_status: Optional[CTDBStatus] = None
        
        # Cached configuration data
        self._cached_config: Optional[CTDBConfigData] = None
        self._cached_trigger_status: Optional[List[TriggerChannel]] = None
    
    async def get_monitoring_data(self) -> CTDBMonitoringData:
        """
        Get high-frequency monitoring data (currents and errors)
        """
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            
            # Get CTDB board current (channel 0)
            ctdb_current = await loop.run_in_executor(
                None, hal.get_power_current, self.slot, 0, self.timeout
            )
            
            # Get all channel currents
            channel_currents = []
            for ch in range(1, CHANNELS_PER_SLOT + 1):
                current = await loop.run_in_executor(
                    None, hal.get_power_current, self.slot, ch, self.timeout
                )
                channel_currents.append(current)
            
            # Get error vectors
            over_current_errors = await loop.run_in_executor(
                None, hal.get_over_current_errors, self.slot, self.timeout
            )
            
            under_current_errors = await loop.run_in_executor(
                None, hal.get_under_current_errors, self.slot, self.timeout
            )
            
            return CTDBMonitoringData(
                slot=self.slot,
                ctdb_current_ma=ctdb_current,
                channel_currents_ma=channel_currents,
                over_current_errors=over_current_errors,
                under_current_errors=under_current_errors
            )

    async def get_configuration_data(self) -> CTDBConfigData:
        """
        Get low-frequency configuration data (firmware, limits, enable status)
        """
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            
            # Get firmware version
            fw_version = await loop.run_in_executor(
                None, hal.get_ctdb_firmware_revision, self.slot, self.timeout
            )
            
            # Get power enable register
            power_reg = await loop.run_in_executor(
                None, hal.get_power_enable, self.slot, self.timeout
            )
            
            # Get current limits
            limit_min_raw = await loop.run_in_executor(
                None, hal.get_power_current_min, self.slot, self.timeout
            )
            limit_max_raw = await loop.run_in_executor(
                None, hal.get_power_current_max, self.slot, self.timeout
            )
            
            config = CTDBConfigData(
                slot=self.slot,
                firmware_version=fw_version,
                power_enable_mask=power_reg,
                current_limit_min_ma=hal.current_raw_to_ma(limit_min_raw),
                current_limit_max_ma=hal.current_raw_to_ma(limit_max_raw)
            )
            self._cached_config = config
            return config

    async def get_status(self) -> CTDBStatus:
        """
        Get complete status of this CTDB
        
        Returns:
            CTDBStatus object with all current information
        """
        # For simplicity in this refactor, we just call the new methods
        config = await self.get_configuration_data()
        monitoring = await self.get_monitoring_data()
        
        channels = []
        for i in range(CHANNELS_PER_SLOT):
            ch = i + 1
            enabled = bool(config.power_enable_mask & (1 << ch))
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
    
    async def set_channel_power(self, channel: int, enabled: bool) -> None:
        """
        Enable or disable a single power channel
        
        Args:
            channel: Channel number (1-15)
            enabled: True to enable, False to disable
        """
        if not 1 <= channel <= CHANNELS_PER_SLOT:
            raise ValueError(f"Channel must be 1-{CHANNELS_PER_SLOT}")
        
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, hal.set_power_channel_enable, 
                self.slot, channel, enabled, self.timeout
            )
            
        logger.info(f"Slot {self.slot} Ch{channel}: Power {'enabled' if enabled else 'disabled'}")
    
    async def set_all_channels(self, enabled: bool) -> None:
        """
        Enable or disable all power channels
        
        Args:
            enabled: True to enable all, False to disable all
        """
        value = 0xFFFE if enabled else 0x0000  # bits 1-15
        
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, hal.set_power_enable, self.slot, value, self.timeout
            )
        
        logger.info(f"Slot {self.slot}: All channels {'enabled' if enabled else 'disabled'}")
    
    async def set_channels(self, channel_states: Dict[int, bool]) -> None:
        """
        Set multiple channels at once
        
        Args:
            channel_states: Dict mapping channel number to enable state
        """
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            
            # Read current state
            power_reg = await loop.run_in_executor(
                None, hal.get_power_enable, self.slot, self.timeout
            )
            
            # Modify bits
            for channel, enabled in channel_states.items():
                if not 1 <= channel <= CHANNELS_PER_SLOT:
                    raise ValueError(f"Channel must be 1-{CHANNELS_PER_SLOT}")
                
                if enabled:
                    power_reg |= (1 << channel)
                else:
                    power_reg &= ~(1 << channel)
            
            # Write back
            await loop.run_in_executor(
                None, hal.set_power_enable, self.slot, power_reg, self.timeout
            )
        
        logger.info(f"Slot {self.slot}: Set channels {channel_states}")
    
    async def set_current_limits(self, min_ma: float, max_ma: float) -> None:
        """
        Set current limits for all channels
        
        Args:
            min_ma: Minimum current in mA
            max_ma: Maximum current in mA
        """
        min_raw = hal.current_ma_to_raw(min_ma)
        max_raw = hal.current_ma_to_raw(max_ma)
        
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            
            await loop.run_in_executor(
                None, hal.set_power_current_min, self.slot, min_raw, self.timeout
            )
            
            await loop.run_in_executor(
                None, hal.set_power_current_max, self.slot, max_raw, self.timeout
            )
        
        logger.info(f"Slot {self.slot}: Current limits set to {min_ma:.1f}-{max_ma:.1f} mA")
    
    async def get_trigger_status(self) -> List[TriggerChannel]:
        """Get trigger configuration for all channels"""
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            
            # Get trigger mask
            mask = await loop.run_in_executor(
                None, hal.get_l1_trigger_mask, self.slot
            )
            
            channels = []
            for ch in range(CHANNELS_PER_SLOT):
                masked = bool(mask & (1 << ch))
                
                # Get delay
                delay_raw = await loop.run_in_executor(
                    None, hal.get_l1_trigger_delay, self.slot, ch
                )
                
                channels.append(TriggerChannel(
                    slot=self.slot,
                    channel=ch,
                    masked=masked,
                    delay_ns=hal.delay_raw_to_ns(delay_raw)
                ))
            
            return channels
    
    async def set_trigger_mask(self, channel: int, masked: bool) -> None:
        """Set trigger mask for a channel"""
        if not 0 <= channel < CHANNELS_PER_SLOT:
            raise ValueError(f"Channel must be 0-{CHANNELS_PER_SLOT-1}")
        
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, hal.set_l1_trigger_channel_mask, 
                self.slot, channel, not masked  # Note: API uses 'enabled' not 'masked'
            )
        
        logger.info(f"Slot {self.slot} Trigger Ch{channel}: {'Masked' if masked else 'Unmasked'}")
    
    async def set_trigger_delay(self, channel: int, delay_ns: float) -> None:
        """Set trigger delay for a channel"""
        if not 0 <= channel < CHANNELS_PER_SLOT:
            raise ValueError(f"Channel must be 0-{CHANNELS_PER_SLOT-1}")
        
        if not 0 <= delay_ns <= 5.0:
            raise ValueError("Delay must be 0-5 ns")
        
        delay_raw = hal.delay_ns_to_raw(delay_ns)
        
        async with _hardware_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, hal.set_l1_trigger_delay, 
                self.slot, channel, delay_raw, self.timeout
            )
        
        logger.info(f"Slot {self.slot} Trigger Ch{channel}: Delay set to {delay_ns:.3f} ns")


# ============================================================================
# L2 Trigger System Controller
# ============================================================================

class L2TriggerSystem:
    """High-level controller for entire L2 trigger system"""
    
    def __init__(self, timeout_us: int = DEFAULT_TIMEOUT_US, 
                 enabled_slots: Optional[List[int]] = None):
        """
        Initialize L2 trigger system
        
        Args:
            timeout_us: Default timeout in microseconds
            enabled_slots: List of slots to control (default: all valid slots)
        """
        if enabled_slots is None:
            enabled_slots = VALID_SLOTS
        
        # Validate slots
        invalid_slots = set(enabled_slots) - set(VALID_SLOTS)
        if invalid_slots:
            raise ValueError(f"Invalid slots: {invalid_slots}")
        
        self.timeout = timeout_us
        self.ctdbs = {
            slot: CTDBController(slot, timeout_us) 
            for slot in enabled_slots
        }
        self._monitoring_task: Optional[asyncio.Task] = None
        self._monitoring_interval: float = 1.0
        self._status_callbacks = []
    
    async def get_l2cb_status(self) -> L2CBStatus:
        """Get status of the L2CB controller board"""
        loop = asyncio.get_event_loop()
        
        fw_version = await loop.run_in_executor(
            None, hal.get_l2cb_firmware_revision
        )
        
        timestamp = await loop.run_in_executor(
            None, hal.read_timestamp
        )
        
        return L2CBStatus(
            firmware_version=fw_version,
            timestamp=timestamp,
            timestamp_datetime=datetime.now()
        )
    
    async def get_all_monitoring_data(self) -> Dict[int, CTDBMonitoringData]:
        """Get monitoring data for all CTDB boards"""
        tasks = [ctdb.get_monitoring_data() for ctdb in self.ctdbs.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        data = {}
        for slot, res in zip(self.ctdbs.keys(), results):
            if isinstance(res, Exception):
                logger.error(f"Error reading monitoring data from slot {slot}: {res}")
            else:
                data[slot] = res
        return data

    async def get_all_configuration_data(self) -> Dict[int, CTDBConfigData]:
        """Get configuration data for all CTDB boards"""
        tasks = [ctdb.get_configuration_data() for ctdb in self.ctdbs.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        data = {}
        for slot, res in zip(self.ctdbs.keys(), results):
            if isinstance(res, Exception):
                logger.error(f"Error reading configuration data from slot {slot}: {res}")
            else:
                data[slot] = res
        return data

    async def get_all_trigger_status(self) -> Dict[int, List[TriggerChannel]]:
        """Get trigger status for all CTDB boards"""
        tasks = [ctdb.get_trigger_status() for ctdb in self.ctdbs.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        data = {}
        for slot, res in zip(self.ctdbs.keys(), results):
            if isinstance(res, Exception):
                logger.error(f"Error reading trigger status from slot {slot}: {res}")
            else:
                data[slot] = res
        return data

    async def get_all_status(self) -> Dict[int, CTDBStatus]:
        """
        Get status of all CTDB boards
        
        Returns:
            Dict mapping slot number to CTDBStatus
        """
        tasks = [ctdb.get_status() for ctdb in self.ctdbs.values()]
        statuses = await asyncio.gather(*tasks, return_exceptions=True)
        
        result = {}
        for slot, status in zip(self.ctdbs.keys(), statuses):
            if isinstance(status, Exception):
                logger.error(f"Error reading slot {slot}: {status}")
            else:
                result[slot] = status
        
        return result
    
    async def get_slot_status(self, slot: int) -> CTDBStatus:
        """Get status of a specific slot"""
        if slot not in self.ctdbs:
            raise ValueError(f"Slot {slot} not enabled")
        
        return await self.ctdbs[slot].get_status()
    
    async def set_slot_power(self, slot: int, channel: int, enabled: bool) -> None:
        """Set power for a specific slot/channel"""
        if slot not in self.ctdbs:
            raise ValueError(f"Slot {slot} not enabled")
        
        await self.ctdbs[slot].set_channel_power(channel, enabled)
    
    async def set_all_power(self, enabled: bool) -> None:
        """Enable or disable all power channels on all boards"""
        tasks = [ctdb.set_all_channels(enabled) for ctdb in self.ctdbs.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"All power channels {'enabled' if enabled else 'disabled'}")

    async def set_all_trigger_mask(self, masked: bool) -> None:
        """Set trigger mask for all channels on all boards"""
        tasks = []
        for ctdb in self.ctdbs.values():
            for ch in range(CHANNELS_PER_SLOT):
                tasks.append(ctdb.set_trigger_mask(ch, masked))
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"All trigger channels {'masked' if masked else 'unmasked'}")

    async def set_all_trigger_delay(self, delay_ns: float) -> None:
        """Set trigger delay for all channels on all boards"""
        tasks = []
        for ctdb in self.ctdbs.values():
            for ch in range(CHANNELS_PER_SLOT):
                tasks.append(ctdb.set_trigger_delay(ch, delay_ns))
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"All trigger delays set to {delay_ns:.3f} ns")
    
    async def emergency_shutdown(self) -> None:
        """Emergency shutdown - turn off all power channels immediately"""
        logger.warning("EMERGENCY SHUTDOWN initiated")
        
        # Use low-level call for speed
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, hal.set_power_enable_all, False, self.timeout
        )
        
        logger.warning("EMERGENCY SHUTDOWN complete")
    
    async def set_current_limits_all(self, min_ma: float, max_ma: float) -> None:
        """Set current limits for all slots"""
        tasks = [
            ctdb.set_current_limits(min_ma, max_ma) 
            for ctdb in self.ctdbs.values()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"Current limits set to {min_ma:.1f}-{max_ma:.1f} mA on all slots")
    
    async def get_slots_with_errors(self) -> List[int]:
        """Get list of slots that have error conditions"""
        all_status = await self.get_all_status()
        return [slot for slot, status in all_status.items() if status.has_errors]
    
    def start_monitoring(self, interval: float = 1.0, 
                        callback=None) -> None:
        """
        Start background monitoring task
        
        Args:
            interval: Monitoring interval in seconds
            callback: Optional callback function(Dict[int, CTDBStatus])
        """
        if self._monitoring_task is not None:
            logger.warning("Monitoring already running")
            return
        
        self._monitoring_interval = interval
        if callback:
            self._status_callbacks.append(callback)
        
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info(f"Started monitoring (interval={interval}s)")
    
    def stop_monitoring(self) -> None:
        """Stop background monitoring task"""
        if self._monitoring_task is not None:
            self._monitoring_task.cancel()
            self._monitoring_task = None
            logger.info("Stopped monitoring")
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop"""
        while True:
            try:
                status = await self.get_all_status()
                
                # Call callbacks
                for callback in self._status_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(status)
                        else:
                            callback(status)
                    except Exception as e:
                        logger.error(f"Error in monitoring callback: {e}")
                
                # Check for errors
                errors = []
                for slot, slot_status in status.items():
                    if slot_status.has_errors:
                        errors.append(f"Slot {slot}: {len(slot_status.channels_with_errors)} channels with errors")
                
                if errors:
                    logger.warning("Errors detected: " + ", ".join(errors))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            await asyncio.sleep(self._monitoring_interval)
    
    async def health_check(self) -> Dict[str, any]:
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
            l2cb_status = await self.get_l2cb_status()
            health["l2cb_firmware"] = l2cb_status.firmware_version
            
            # Check all CTDBs
            all_status = await self.get_all_status()
            
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

async def example_usage():
    """Example usage of the L2 trigger system API"""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize system
    system = L2TriggerSystem()
    
    # Get L2CB status
    l2cb = await system.get_l2cb_status()
    print(f"L2CB Firmware: 0x{l2cb.firmware_version:04X}")
    print(f"Timestamp: {l2cb.timestamp}")
    
    # Get status of all boards
    print("\n=== Getting status of all boards ===")
    all_status = await system.get_all_status()
    
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
    await system.set_slot_power(slot=1, channel=5, enabled=True)
    
    # Set current limits
    await system.ctdbs[1].set_current_limits(min_ma=100, max_ma=2000)
    
    # Get trigger status
    print("\n=== Trigger Configuration ===")
    trigger_status = await system.ctdbs[1].get_trigger_status()
    for trig in trigger_status[:5]:  # Show first 5
        print(f"  Ch{trig.channel}: {'Masked' if trig.masked else 'Active'}, Delay={trig.delay_ns:.3f}ns")
    
    # Health check
    print("\n=== Health Check ===")
    health = await system.health_check()
    print(f"Overall: {health['overall']}")
    if health['errors']:
        print(f"Errors: {health['errors']}")
    
    # Example: Emergency shutdown (commented out for safety)
    # await system.emergency_shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())
