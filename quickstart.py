#!/usr/bin/env python3
"""
quickstart.py

Quick start example for L2 Trigger System
Demonstrates basic usage patterns
"""

import asyncio
import logging
from l2trig_api import L2TriggerSystem, VALID_SLOTS

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print("=" * 60)
    print("L2 Trigger System - Quick Start Example")
    print("=" * 60)
    
    # Initialize system with first 3 slots only for testing
    print("\n1. Initializing system...")
    system = L2TriggerSystem(enabled_slots=[1, 2, 3])
    
    # Get L2CB status
    print("\n2. Reading L2CB controller status...")
    try:
        l2cb_status = system.get_l2cb_status()
        print(f"   L2CB Firmware: 0x{l2cb_status.firmware_version:04X}")
        print(f"   Timestamp: {l2cb_status.timestamp}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Get status of all configured boards
    print("\n3. Reading CTDB board statuses...")
    all_status = system.get_all_status()
    
    for slot, status in all_status.items():
        print(f"\n   Slot {slot}:")
        print(f"   ├─ Firmware: 0x{status.firmware_version:04X}")
        print(f"   ├─ CTDB Current: {status.ctdb_current_ma:.2f} mA")
        print(f"   ├─ Total Channel Current: {status.total_current_ma:.2f} mA")
        print(f"   ├─ Current Limits: {status.current_limit_min_ma:.1f} - "
              f"{status.current_limit_max_ma:.1f} mA")
        
        if status.has_errors:
            print(f"   ├─ ⚠️  ERRORS DETECTED:")
            for ch in status.channels_with_errors:
                print(f"   │  ├─ Channel {ch.channel}: {ch.state.value} "
                      f"({ch.current_ma:.2f} mA)")
        
        # Show enabled channels
        enabled = [ch.channel for ch in status.power_channels if ch.enabled]
        if enabled:
            print(f"   └─ Enabled channels: {enabled}")
        else:
            print(f"   └─ All channels disabled")
    
    # Demonstrate power control
    print("\n4. Demonstrating power control...")
    print("   Enabling channel 5 on slot 1...")
    try:
        system.set_slot_power(slot=1, channel=5, enabled=True)
        print("   ✓ Channel enabled")
        
        # Read back status
        import time
        time.sleep(0.1)
        status = system.get_slot_status(1)
        ch5 = next(ch for ch in status.power_channels if ch.channel == 5)
        print(f"   Current reading: {ch5.current_ma:.2f} mA")
        print(f"   State: {ch5.state.value}")
        
    except Exception as e:
        print(f"   Error: {e}")
    
    # Demonstrate current limit configuration
    print("\n5. Setting current limits on slot 1...")
    try:
        system.ctdbs[1].set_current_limits(min_ma=100.0, max_ma=2000.0)
        print("   ✓ Current limits set to 100-2000 mA")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Demonstrate trigger configuration
    print("\n6. Reading trigger configuration for slot 1...")
    try:
        trigger_status = system.ctdbs[1].get_trigger_status()
        print("   First 5 trigger channels:")
        for trig in trigger_status[:5]:
            status_str = "Enabled" if trig.enabled else "Disabled"
            print(f"   ├─ Channel {trig.channel}: {status_str}, "
                  f"Delay={trig.delay_ns:.3f}ns")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Health check
    print("\n7. Performing system health check...")
    health = system.health_check()
    print(f"   Overall Status: {health['overall'].upper()}")
    
    if health['errors']:
        print("   Errors detected:")
        for error in health['errors']:
            print(f"   ├─ {error}")
    else:
        print("   ✓ No errors detected")
    
    # Show summary
    print("\n8. Summary:")
    print(f"   ├─ Monitored slots: {list(system.ctdbs.keys())}")
    print(f"   ├─ Total CTDBs: {len(system.ctdbs)}")
    print(f"   ├─ Channels per CTDB: 15")
    print(f"   └─ Overall health: {health['overall']}")
    
    print("\n" + "=" * 60)
    print("Quick start complete!")
    print("=" * 60)
    
    # Optional: Demonstrate emergency shutdown (COMMENTED OUT FOR SAFETY)
    # print("\n⚠️  Emergency shutdown demonstration (uncomment to test)")
    # system.emergency_shutdown()
    # print("All power channels shut down")


if __name__ == "__main__":
    # Run quick start
    main()
