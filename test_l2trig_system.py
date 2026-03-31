"""
test_l2trig_system.py

Test suite for L2 Trigger System
Includes unit tests and integration tests with hardware mocking
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, DEFAULT
from typing import Dict

# Import modules to test
import l2trig_low_level as hal
from l2trig_api import (
    CTDBController,
    L2TriggerSystem,
    PowerChannel,
    ChannelState,
    CTDBStatus,
    VALID_SLOTS,
    CHANNELS_PER_SLOT
)

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_hal():
    """Mock the low-level HAL module"""
    with patch.multiple(
        'l2trig_low_level',
        get_power_enable=DEFAULT,
        set_power_enable=DEFAULT,
        get_power_current=DEFAULT,
        get_ctdb_firmware_revision=DEFAULT,
        get_over_current_errors=DEFAULT,
        get_under_current_errors=DEFAULT,
        get_power_current_min=DEFAULT,
        get_power_current_max=DEFAULT,
        set_power_channel_enable=DEFAULT,
        set_power_enable_all=DEFAULT,
        get_l1_trigger_mask=DEFAULT,
        get_l1_trigger_delay=DEFAULT,
        set_l1_trigger_channel_mask=DEFAULT,
        set_l1_trigger_delay=DEFAULT,
        get_l2cb_firmware_revision=DEFAULT,
        read_timestamp=DEFAULT,
    ) as mocks:
        mocks['get_power_enable'].return_value = 0xFFFE
        mocks['get_power_current'].return_value = 100.0
        mocks['get_ctdb_firmware_revision'].return_value = 0x0123
        mocks['get_over_current_errors'].return_value = 0x0000
        mocks['get_under_current_errors'].return_value = 0x0000
        mocks['get_power_current_min'].return_value = 100
        mocks['get_power_current_max'].return_value = 2000
        mocks['get_l1_trigger_mask'].return_value = 0x0000
        mocks['get_l1_trigger_delay'].return_value = 27
        mocks['get_l2cb_firmware_revision'].return_value = 0x0100
        mocks['read_timestamp'].return_value = 123456789
        yield mocks


@pytest.fixture
def ctdb_controller(mock_hal):
    """Create a CTDB controller with mocked hardware"""
    return CTDBController(slot=1, timeout_us=1000)


@pytest.fixture
def l2_system(mock_hal):
    """Create L2 system with mocked hardware"""
    return L2TriggerSystem(timeout_us=1000, enabled_slots=[1, 2, 3])


# ============================================================================
# Unit Tests - Low Level HAL
# ============================================================================

class TestLowLevelHAL:
    """Test low-level HAL wrapper functions"""
    
    def test_error_handling_timeout(self, mock_hal):
        """Test that timeout errors are converted to exceptions"""
        with patch('l2trig_low_level._lib') as mock_lib:
            mock_lib.cta_l2cb_spi_read.return_value = hal.HALError.TIMEOUT
            
            with pytest.raises(hal.TimeoutError):
                hal.spi_read(1, 0x00)
    
    def test_error_handling_invalid_param(self, mock_hal):
        """Test that invalid parameter errors are converted"""
        with patch('l2trig_low_level._lib') as mock_lib:
            mock_lib.cta_l2cb_spi_read.return_value = hal.HALError.INVALID_PARAMETER
            
            with pytest.raises(hal.InvalidParameterError):
                hal.spi_read(1, 0x00)
    
    def test_current_conversion(self):
        """Test current conversion functions"""
        # Test mA to raw
        raw = hal.current_ma_to_raw(485.0)
        assert raw == 1000
        
        # Test raw to mA
        ma = hal.current_raw_to_ma(1000)
        assert abs(ma - 485.0) < 0.1
    
    def test_delay_conversion(self):
        """Test delay conversion functions"""
        # Test ns to raw
        raw = hal.delay_ns_to_raw(1.0)
        assert raw == 27  # 1ns / 37ps ≈ 27
        
        # Test raw to ns
        ns = hal.delay_raw_to_ns(27)
        assert abs(ns - 0.999) < 0.01
    
    def test_valid_slot_check(self):
        """Test slot validation"""
        # Valid slots
        for slot in VALID_SLOTS:
            assert hal.is_valid_slot(slot)
        
        # Invalid slots
        for slot in [0, 10, 11, 12, 22, 100]:
            assert not hal.is_valid_slot(slot)


# ============================================================================
# Unit Tests - CTDB Controller
# ============================================================================

class TestCTDBController:
    """Test CTDB controller"""
    
    def test_initialization(self):
        """Test CTDB controller initialization"""
        controller = CTDBController(slot=1)
        assert controller.slot == 1
        assert controller.timeout > 0
    
    def test_invalid_slot(self):
        """Test that invalid slots raise error"""
        with pytest.raises(ValueError):
            CTDBController(slot=10)  # Invalid slot
    
    def test_get_status(self, ctdb_controller, mock_hal):
        """Test getting CTDB status"""
        status = ctdb_controller.get_status()
        
        assert isinstance(status, CTDBStatus)
        assert status.slot == 1
        assert status.firmware_version == 0x0123
        assert len(status.power_channels) == CHANNELS_PER_SLOT
        assert status.ctdb_current_ma == 100.0
    
    def test_set_channel_power(self, ctdb_controller, mock_hal):
        """Test enabling/disabling a channel"""
        ctdb_controller.set_channel_power(5, True)
        mock_hal['set_power_channel_enable'].assert_called()
        
        # Test invalid channel
        with pytest.raises(ValueError):
            ctdb_controller.set_channel_power(20, True)
    
    def test_set_all_channels(self, ctdb_controller, mock_hal):
        """Test enabling/disabling all channels"""
        ctdb_controller.set_all_channels(True)
        mock_hal['set_power_enable'].assert_called_with(1, 0xFFFE, 1000)
        
        ctdb_controller.set_all_channels(False)
        mock_hal['set_power_enable'].assert_called_with(1, 0x0000, 1000)
    
    def test_set_channels_multiple(self, ctdb_controller, mock_hal):
        """Test setting multiple channels at once"""
        channel_states = {1: True, 3: False, 5: True}
        ctdb_controller.set_channels(channel_states)
        
        mock_hal['set_power_enable'].assert_called()
    
    def test_set_current_limits(self, ctdb_controller, mock_hal):
        """Test setting current limits"""
        with patch('l2trig_low_level.set_power_current_min') as mock_min, \
             patch('l2trig_low_level.set_power_current_max') as mock_max:
            
            ctdb_controller.set_current_limits(100.0, 2000.0)
            
            mock_min.assert_called()
            mock_max.assert_called()


# ============================================================================
# Unit Tests - L2 Trigger System
# ============================================================================

class TestL2TriggerSystem:
    """Test L2 trigger system"""
    
    def test_initialization(self, l2_system):
        """Test system initialization"""
        assert len(l2_system.ctdbs) == 3
        assert 1 in l2_system.ctdbs
        assert 2 in l2_system.ctdbs
        assert 3 in l2_system.ctdbs
    
    def test_get_all_status(self, l2_system, mock_hal):
        """Test getting status of all boards"""
        all_status = l2_system.get_all_status()
        
        assert len(all_status) == 3
        assert all(isinstance(s, CTDBStatus) for s in all_status.values())
    
    def test_get_slot_status(self, l2_system, mock_hal):
        """Test getting status of specific slot"""
        status = l2_system.get_slot_status(1)
        
        assert isinstance(status, CTDBStatus)
        assert status.slot == 1
        
        # Test invalid slot
        with pytest.raises(ValueError):
            l2_system.get_slot_status(99)
    
    def test_set_all_power(self, l2_system, mock_hal):
        """Test setting all power"""
        l2_system.set_all_power(True)
        # Should call set_all_channels for each CTDB
        
    def test_emergency_shutdown(self, l2_system, mock_hal):
        """Test emergency shutdown"""
        l2_system.emergency_shutdown()
        mock_hal['set_power_enable_all'].assert_called_with(False, 1000)
    
    def test_health_check(self, l2_system, mock_hal):
        """Test system health check"""
        health = l2_system.health_check()
        
        assert 'overall' in health
        assert 'slots' in health
        assert health['overall'] in ['healthy', 'degraded', 'error']


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests with simulated hardware"""
    
    def test_power_cycle(self, l2_system, mock_hal):
        """Test complete power cycle"""
        # Get initial status
        initial_status = l2_system.get_slot_status(1)
        
        # Turn off all channels
        l2_system.ctdbs[1].set_all_channels(False)
        
        # Turn on specific channel
        l2_system.ctdbs[1].set_channel_power(5, True)
        
        # Get final status
        final_status = l2_system.get_slot_status(1)
    
    def test_error_detection(self, mock_hal):
        """Test error detection in status"""
        # Mock over-current error
        with patch('l2trig_low_level.get_over_current_errors', return_value=0x0020):  # Channel 5
            controller = CTDBController(slot=1)
            status = controller.get_status()
            
            # Channel 5 should have error
            ch5 = next(ch for ch in status.power_channels if ch.channel == 5)
            assert ch5.state == ChannelState.ERROR_OVER_CURRENT
            assert status.has_errors
    
    def test_concurrent_access(self, l2_system, mock_hal):
        """Test concurrent access to multiple slots"""
        # Since it is synchronous now, it will be sequential but let's test it works
        results = [
            l2_system.get_slot_status(1),
            l2_system.get_slot_status(2),
            l2_system.get_slot_status(3)
        ]
        
        assert len(results) == 3
        assert all(isinstance(r, CTDBStatus) for r in results)


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Performance tests"""
    
    def test_status_read_time(self, ctdb_controller, mock_hal):
        """Test that status reads are reasonably fast"""
        import time
        
        start = time.time()
        ctdb_controller.get_status()
        duration = time.time() - start
        
        # Should complete in under 1 second even with mocked delays
        assert duration < 1.0
    
    def test_sequential_reads(self, l2_system, mock_hal):
        """Test sequential reads from multiple boards"""
        import time
        
        start = time.time()
        l2_system.get_all_status()
        duration = time.time() - start
        
        assert duration < 2.0


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
