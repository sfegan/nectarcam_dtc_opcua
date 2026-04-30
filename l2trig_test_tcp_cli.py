"""
l2trig_test_tcp_cli.py

Comprehensive Test CLI for the TCP-based L2Trigger API.
Provides access to all protocol commands and detailed status info.

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
"""

import asyncio
import sys
import argparse
from l2trig_api import L2TriggerSystem, VALID_SLOTS

def print_help():
    print("\nSystem Commands:")
    print("  config                   - Send default active slots/immutable config")
    print("  config_default           - Activate all valid slots and set default immutable channels")
    print("  ramp <0|1>               - Trigger global power ramp")
    print("  emergency                - Trigger emergency shutdown")
    print("  keepalive <0|1>          - Toggle keepalive on/off (1=on, 0=off)")
    
    print("\nL2CB (Global) Commands:")
    print("  l2cb                     - Get L2CB status (Firmware, Uptime, Control bits, Params)")
    print("  mcf <0|1>                - Set MCF enable")
    print("  glitch <0|1>             - Set Busy Glitch Filter enable")
    print("  tib <0|1>                - Set TIB Trigger Busy Block enable")
    print("  thresh <val>             - Set MCF threshold (0-511)")
    print("  mcf_delay <val>          - Set MCF delay (0-15, in 5ns steps)")
    print("  deadtime <val>           - Set L1 deadtime (0-255, in 5ns steps)")
    
    print("\nCTDB (Per-Slot/Channel) Commands:")
    print("  mon <slot>               - Get monitoring for a slot (currents, errors, pwr mask)")
    print("  mon_all                  - Get monitoring for all active slots")
    print("  cfg <slot>               - Get configuration for a slot (fw, limits, trig mask/delays)")
    print("  pwr <slot> <ch> <0|1>    - Set channel power")
    print("  trig <slot> <ch> <0|1>   - Set channel trigger contribution")
    print("  trig_delay <slot> <ch> <v>- Set channel trigger delay (0-255, 37ps steps)")
    print("  limits <slot> <min> <max>- Set slot current limits (hex counts)")
    
    print("\nOther:")
    print("  help                     - Show this help")
    print("  quit                     - Exit")

async def run_cli(host, port, keepalive_enabled):
    system = L2TriggerSystem(host, port)
    try:
        await system.connect()
        print(f"Connected to {host}:{port}")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    # Keepalive state and task
    keepalive_state = {"enabled": keepalive_enabled, "task": None}
    
    async def keepalive_loop():
        """Background task to send keepalive messages every second"""
        while keepalive_state["enabled"]:
            try:
                await asyncio.sleep(1.0)
                if keepalive_state["enabled"]:
                    await system.keepalive()
            except Exception as e:
                print(f"Keepalive error: {e}")
                # Don't break the loop, just continue
    
    # Start keepalive task if enabled
    if keepalive_enabled:
        keepalive_state["task"] = asyncio.create_task(keepalive_loop())
        print("Keepalive enabled (1s interval)")
    else:
        print("Keepalive disabled")

    print_help()
    
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, input, "> ")
            parts = line.split()
            if not parts:
                continue
            
            cmd = parts[0].lower()
            
            if cmd == "quit":
                break
            elif cmd == "help":
                print_help()
            
            elif cmd == "config":
                active = [1, 2, 21]
                imm = {21: 0xF800} 
                await system.set_config(active, imm)
                print("Configuration sent: Slots 1, 2, 21 active. S21C11-15 immutable.")

            elif cmd == "config_default":
                active = VALID_SLOTS
                imm = {21: 0xF800} 
                await system.set_config(active, imm)
                print(f"Default config: {len(active)} slots active, S21C11-15 immutable.")

            elif cmd == "ramp":
                val = int(parts[1])
                await system.ramp_power(val == 1)
                print(f"Ramp {'enabled' if val == 1 else 'disabled'} started.")

            elif cmd == "emergency":
                await system.emergency_shutdown()
                print("Emergency shutdown sent.")
            
            elif cmd == "keepalive":
                val = int(parts[1])
                was_enabled = keepalive_state["enabled"]
                keepalive_state["enabled"] = (val == 1)
                
                if not was_enabled and keepalive_state["enabled"]:
                    # Starting keepalive
                    keepalive_state["task"] = asyncio.create_task(keepalive_loop())
                    print("Keepalive enabled (1s interval)")
                elif was_enabled and not keepalive_state["enabled"]:
                    # Stopping keepalive
                    if keepalive_state["task"]:
                        keepalive_state["task"].cancel()
                        try:
                            await keepalive_state["task"]
                        except asyncio.CancelledError:
                            pass
                    print("Keepalive disabled")
                else:
                    print(f"Keepalive already {'enabled' if keepalive_state['enabled'] else 'disabled'}")

            elif cmd == "l2cb":
                s = await system.get_l2cb_status()
                print(f"L2CB Status:")
                print(f"  Firmware:  0x{s.firmware_version:04x}")
                print(f"  Uptime:    {s.uptime} ns")
                print(f"  Control:   MCF={s.mcf_enabled}, Glitch={s.busy_glitch_filter_enabled}, TIB_Block={s.tib_trigger_busy_block_enabled}")
                print(f"  MCF Thr:   {s.mcf_threshold}")
                print(f"  MCF Delay: {s.mcf_delay_ns} ns")
                print(f"  L1 Dead:   {s.l1_deadtime_ns} ns")

            elif cmd == "mcf":
                await system.set_mcf_enabled(int(parts[1]) == 1)
                print("MCF set.")
            elif cmd == "glitch":
                await system.set_glitch_filter_enabled(int(parts[1]) == 1)
                print("Glitch filter set.")
            elif cmd == "tib":
                await system.set_tib_block_enabled(int(parts[1]) == 1)
                print("TIB block set.")
            elif cmd == "thresh":
                await system.set_mcf_threshold(int(parts[1]))
                print("MCF threshold set.")
            elif cmd == "mcf_delay":
                await system.set_mcf_delay(int(parts[1]))
                print("MCF delay set.")
            elif cmd == "deadtime":
                await system.set_l1_deadtime(int(parts[1]))
                print("L1 deadtime set.")

            elif cmd == "mon":
                slot = int(parts[1])
                m = await system.get_ctdb_monitoring(slot)
                print(f"Slot {m.slot} Monitoring:")
                print(f"  CTDB Current: {m.ctdb_current_ma:.2f} mA")
                print(f"  Power Mask:   0x{m.power_enabled_mask:04x}")
                print(f"  Errors:       Over=0x{m.over_current_errors:04x}, Under=0x{m.under_current_errors:04x}")
                print(f"  Ch Currents:  " + ", ".join([f"{c:.1f}" for c in m.channel_currents_ma]))

            elif cmd == "mon_all":
                data = await system.get_all_monitoring()
                if not data:
                    print("No active slots monitored.")
                for slot in sorted(data.keys()):
                    m = data[slot]
                    err = m.over_current_errors | m.under_current_errors
                    print(f"Slot {slot:2d}: CTDB={m.ctdb_current_ma:6.1f} mA, Pwr=0x{m.power_enabled_mask:04x}, Err=0x{err:04x}")

            elif cmd == "cfg":
                slot = int(parts[1])
                c = await system.get_ctdb_config(slot)
                print(f"Slot {c.slot} Configuration:")
                print(f"  Firmware:     0x{c.firmware_version:04x}")
                print(f"  Limits:       {c.current_limit_min_ma:.1f} - {c.current_limit_max_ma:.1f} mA")
                print(f"  Trigger Mask: 0x{c.trig_enabled_mask:04x}")
                print(f"  Trig Delays:  " + ", ".join([f"{d:.2f}" for d in c.trig_delays_ns]))

            elif cmd == "pwr":
                await system.set_channel_power_enabled(int(parts[1]), int(parts[2]), int(parts[3]) == 1)
                print("Power command sent.")
            elif cmd == "trig":
                await system.set_channel_trigger_enabled(int(parts[1]), int(parts[2]), int(parts[3]) == 1)
                print("Trigger command sent.")
            elif cmd == "trig_delay":
                await system.set_channel_trigger_delay(int(parts[1]), int(parts[2]), int(parts[3]))
                print("Trigger delay command sent.")
            elif cmd == "limits":
                await system.set_ctdb_limits(int(parts[1]), int(parts[2]), int(parts[3]))
                print("Current limits sent.")

            else:
                print(f"Unknown command: {cmd}")

        except EOFError:
            break
        except IndexError:
            print("Missing arguments for command.")
        except Exception as e:
            print(f"Error: {e}")

    # Cleanup keepalive task
    keepalive_state["enabled"] = False
    if keepalive_state["task"]:
        keepalive_state["task"].cancel()
        try:
            await keepalive_state["task"]
        except asyncio.CancelledError:
            pass

    await system.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4242)
    parser.add_argument("--keepalive", action="store_true", default=True, 
                        help="Enable keepalive messages (default: on)")
    parser.add_argument("--no-keepalive", action="store_false", dest="keepalive",
                        help="Disable keepalive messages")
    args = parser.parse_args()
    
    asyncio.run(run_cli(args.host, args.port, args.keepalive))
