#!/usr/bin/env python3
"""
l2trig_direct_client.py

Text-based command line interface for direct access to L2 Trigger HAL
Operates with raw values (no unit conversion).

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
"""

import sys
import argparse
import shlex

# Try to import readline for better interactive experience
try:
    import readline
except ImportError:
    readline = None

from l2trig_low_level import (
    get_l2cb_firmware_revision, get_l2cb_timestamp, get_l2cb_control_state,
    set_l2cb_mcf_enabled, set_l2cb_busy_glitch_filter_enabled, set_l2cb_tib_trigger_busy_block_enabled,
    get_l2cb_mcf_threshold, set_l2cb_mcf_threshold,
    get_l2cb_mcf_delay, set_l2cb_mcf_delay,
    get_l2cb_l1_deadtime, set_l2cb_l1_deadtime,
    set_l1_trigger_enabled, get_l1_trigger_enabled,
    set_l1_trigger_channel_enabled, get_l1_trigger_channel_enabled,
    set_l1_trigger_delay, get_l1_trigger_delay,
    set_power_enabled, get_power_enabled,
    set_power_channel_enabled, get_power_channel_enabled,
    set_power_enabled_all,
    set_power_current_max, get_power_current_max,
    set_power_current_min, get_power_current_min,
    get_power_current, get_power_current_raw, get_under_current_errors, get_over_current_errors,
    get_ctdb_firmware_revision, set_debug_pins, get_debug_pins,
    get_slave_register, set_slave_register,
    is_valid_slot, HALError, L2TrigError,
    current_raw_to_ma, delay_raw_to_ns, mcf_delay_raw_to_ns, l1_deadtime_raw_to_ns,
    smc_open, 
    smc_close
)

# ============================================================================
# Parsing Utilities
# ============================================================================

def parse_int(val: str) -> int:
    """Parse integer string supporting decimal and hex (0x...)"""
    if val.lower().startswith("0x"):
        return int(val, 16)
    return int(val)

def parse_bool(val: str) -> bool:
    """Parse boolean string supporting True/False, On/Off, Yes/No, 1/0"""
    v = val.lower()
    if v in ("true", "on", "yes", "1"):
        return True
    if v in ("false", "off", "no", "0"):
        return False
    raise ValueError(f"Invalid boolean value: {val}")

# ============================================================================
# Command Handlers
# ============================================================================

class CommandClient:
    def __init__(self):
        self.commands = {
            "l2cb_fw": (self.do_l2cb_fw, "Get L2CB firmware revision"),
            "ts": (self.do_ts, "Get L2CB timestamp"),
            "state": (self.do_state, "Get L2CB control state"),
            "mcf": (self.do_mcf, "mcf <on|off> : Set MCF enabled"),
            "glitch": (self.do_glitch, "glitch <on|off> : Set busy glitch filter enabled"),
            "tibblock": (self.do_tibblock, "tibblock <on|off> : Set TIB trigger busy block enabled"),
            "mcfthr": (self.do_mcfthr, "mcfthr [val] : Get or set MCF threshold (L1 counts)"),
            "mcfdel": (self.do_mcfdel, "mcfdel [val] : Get or set MCF delay (5ns/step)"),
            "deadtime": (self.do_deadtime, "deadtime [val] : Get or set L1 deadtime (5ns/step)"),
            "trigmask": (self.do_trigmask, "trigmask <slot> [mask] : Get or set trigger mask (bit 0 masked)"),
            "trig": (self.do_trig, "trig <slot> <ch> [on|off] : Get or set trigger for channel"),
            "alltrig": (self.do_alltrig, "alltrig <on|off> : Set all trigger masks to 0xFFFE or 0x0000"),
            "delay": (self.do_delay, "delay <slot> <ch> [val] : Get or set trigger delay for channel (37ps/step)"),
            "alldelay": (self.do_alldelay, "alldelay <val> : Set trigger delay for all channels in all slots (37ps/step)"),
            "powermask": (self.do_powermask, "powermask <slot> [mask] : Get or set power mask (bit 0 masked)"),
            "power": (self.do_power, "power <slot> <ch> [on|off] : Get or set power for channel"),
            "allpower": (self.do_allpower, "allpower <on|off> : Set all power channels on all slots"),
            "curmax": (self.do_curmax, "curmax <slot> [val] : Get or set max current limit (0.485mA/step)"),
            "allcurmax": (self.do_allcurmax, "allcurmax <val> : Set max current limit for all slots (0.485mA/step)"),
            "curmin": (self.do_curmin, "curmin <slot> [val] : Get or set min current limit (0.485mA/step)"),
            "allcurmin": (self.do_allcurmin, "allcurmin <val> : Set min current limit for all slots (0.485mA/step)"),
            "cur": (self.do_cur, "cur <slot> <ch> : Get channel current (code & mA)"),
            "under": (self.do_under, "under <slot> : Get under-current error mask"),
            "over": (self.do_over, "over <slot> : Get over-current error mask"),
            "ctdb_fw": (self.do_ctdb_fw, "ctdb_fw <slot> : Get CTDB firmware revision"),
            "debug": (self.do_debug, "debug <slot> [val] : Get or set debug pins"),
            "reg": (self.do_reg, "reg <slot> <addr> [val] : Read or write slave register"),
            "help": (self.do_help, "Show this help message"),
            "?": (self.do_help, "Show this help message"),
            "exit": (self.do_exit, "Exit client"),
            "quit": (self.do_exit, "Exit client"),
        }

    def run_command(self, line: str):
        try:
            # comments=True enables stripping of anything from '#' to the end of the line
            parts = shlex.split(line, comments=True)
        except ValueError as e:
            print(f"Error parsing line: {e}")
            return

        if not parts:
            return

        cmd_name = parts[0].lower()
        args = parts[1:]

        if cmd_name in self.commands:
            handler, _ = self.commands[cmd_name]
            try:
                handler(args)
            except Exception as e:
                print(f"Error: {e}")
                # traceback.print_exc()
        else:
            print(f"Unknown command: {cmd_name}. Type 'help' for available commands.")

    def do_l2cb_fw(self, args):
        print(f"L2CB Firmware Revision: 0x{get_l2cb_firmware_revision():04X}")

    def do_ts(self, args):
        print(f"L2CB Timestamp: {get_l2cb_timestamp()}")

    def do_state(self, args):
        state = get_l2cb_control_state()
        print(f"MCF Enabled: {state['mcf_enabled']}")
        print(f"Busy Glitch Filter Enabled: {state['busy_glitch_filter_enabled']}")
        print(f"TIB Trigger Busy Block Enabled: {state['tib_trigger_busy_block_enabled']}")

    def do_mcf(self, args):
        if not args:
            print("Usage: mcf <on|off>")
            return
        set_l2cb_mcf_enabled(parse_bool(args[0]))

    def do_glitch(self, args):
        if not args:
            print("Usage: glitch <on|off>")
            return
        set_l2cb_busy_glitch_filter_enabled(parse_bool(args[0]))

    def do_tibblock(self, args):
        if not args:
            print("Usage: tibblock <on|off>")
            return
        set_l2cb_tib_trigger_busy_block_enabled(parse_bool(args[0]))

    def do_mcfthr(self, args):
        if args:
            set_l2cb_mcf_threshold(parse_int(args[0]))
        else:
            val = get_l2cb_mcf_threshold()
            print(f"MCF Threshold: {val} (L1 counts)")

    def do_mcfdel(self, args):
        if args:
            set_l2cb_mcf_delay(parse_int(args[0]))
        else:
            val = get_l2cb_mcf_delay()
            print(f"MCF Delay: {val} ({mcf_delay_raw_to_ns(val):.1f} ns)")

    def do_deadtime(self, args):
        if args:
            set_l2cb_l1_deadtime(parse_int(args[0]))
        else:
            val = get_l2cb_l1_deadtime()
            print(f"L1 Deadtime: {val} ({l1_deadtime_raw_to_ns(val):.1f} ns)")

    def do_trigmask(self, args):
        if not args:
            print("Usage: trigmask <slot> [mask]")
            return
        slot = parse_int(args[0])
        if len(args) > 1:
            mask = parse_int(args[1]) & 0xFFFE  # Mask off bit-0
            set_l1_trigger_enabled(slot, mask)
        else:
            print(f"Slot {slot} Trigger Mask: 0x{get_l1_trigger_enabled(slot):04X}")

    def do_trig(self, args):
        if len(args) < 2:
            print("Usage: trig <slot> <ch> [on|off]")
            return
        slot = parse_int(args[0])
        ch = parse_int(args[1])
        if len(args) > 2:
            set_l1_trigger_channel_enabled(slot, ch, parse_bool(args[2]))
        else:
            print(f"Slot {slot} Ch {ch} Trigger: {'ON' if get_l1_trigger_channel_enabled(slot, ch) else 'OFF'}")

    def do_alltrig(self, args):
        if not args:
            print("Usage: alltrig <on|off>")
            return
        enabled = parse_bool(args[0])
        mask = 0xFFFE if enabled else 0x0000
        for slot in range(1, 22):
            if is_valid_slot(slot):
                set_l1_trigger_enabled(slot, mask)

    def do_delay(self, args):
        if len(args) < 2:
            print("Usage: delay <slot> <ch> [val]")
            return
        slot = parse_int(args[0])
        ch = parse_int(args[1])
        if len(args) > 2:
            set_l1_trigger_delay(slot, ch, parse_int(args[2]))
        else:
            val = get_l1_trigger_delay(slot, ch)
            print(f"Slot {slot} Ch {ch} Delay: {val} ({delay_raw_to_ns(val)*1000:.0f} ps)")

    def do_alldelay(self, args):
        if not args:
            print("Usage: alldelay <val>")
            return
        val = parse_int(args[0])
        for slot in range(1, 22):
            if is_valid_slot(slot):
                for ch in range(1, 16):
                    set_l1_trigger_delay(slot, ch, val)

    def do_powermask(self, args):
        if not args:
            print("Usage: powermask <slot> [mask]")
            return
        slot = parse_int(args[0])
        if len(args) > 1:
            mask = parse_int(args[1]) & 0xFFFE  # Mask off bit-0 as requested
            set_power_enabled(slot, mask)
        else:
            print(f"Slot {slot} Power Mask: 0x{get_power_enabled(slot):04X}")

    def do_power(self, args):
        if len(args) < 2:
            print("Usage: power <slot> <ch> [on|off]")
            return
        slot = parse_int(args[0])
        ch = parse_int(args[1])
        if len(args) > 2:
            set_power_channel_enabled(slot, ch, parse_bool(args[2]))
        else:
            print(f"Slot {slot} Ch {ch} Power: {'ON' if get_power_channel_enabled(slot, ch) else 'OFF'}")

    def do_allpower(self, args):
        if not args:
            print("Usage: allpower <on|off>")
            return
        set_power_enabled_all(parse_bool(args[0]))

    def do_curmax(self, args):
        if not args:
            print("Usage: curmax <slot> [val]")
            return
        slot = parse_int(args[0])
        if len(args) > 1:
            set_power_current_max(slot, parse_int(args[1]))
        else:
            val = get_power_current_max(slot)
            print(f"Slot {slot} Max Current Limit: {val} ({current_raw_to_ma(val):.2f} mA)")

    def do_allcurmax(self, args):
        if not args:
            print("Usage: allcurmax <val>")
            return
        val = parse_int(args[0])
        for slot in range(1, 22):
            if is_valid_slot(slot):
                set_power_current_max(slot, val)

    def do_curmin(self, args):
        if not args:
            print("Usage: curmin <slot> [val]")
            return
        slot = parse_int(args[0])
        if len(args) > 1:
            set_power_current_min(slot, parse_int(args[1]))
        else:
            val = get_power_current_min(slot)
            print(f"Slot {slot} Min Current Limit: {val} ({current_raw_to_ma(val):.2f} mA)")

    def do_allcurmin(self, args):
        if not args:
            print("Usage: allcurmin <val>")
            return
        val = parse_int(args[0])
        for slot in range(1, 22):
            if is_valid_slot(slot):
                set_power_current_min(slot, val)

    def do_cur(self, args):
        if len(args) < 2:
            print("Usage: cur <slot> <ch>")
            return
        slot = parse_int(args[0])
        ch = parse_int(args[1])
        raw = get_power_current_raw(slot, ch)
        ma = current_raw_to_ma(raw)
        print(f"Slot {slot} Ch {ch} Current: {raw} ({ma:.2f} mA)")

    def do_under(self, args):
        if not args:
            print("Usage: under <slot>")
            return
        slot = parse_int(args[0])
        print(f"Slot {slot} Under-current Errors: 0x{get_under_current_errors(slot):04X}")

    def do_over(self, args):
        if not args:
            print("Usage: over <slot>")
            return
        slot = parse_int(args[0])
        print(f"Slot {slot} Over-current Errors: 0x{get_over_current_errors(slot):04X}")

    def do_ctdb_fw(self, args):
        if not args:
            print("Usage: ctdb_fw <slot>")
            return
        slot = parse_int(args[0])
        print(f"Slot {slot} CTDB Firmware Revision: 0x{get_ctdb_firmware_revision(slot):04X}")

    def do_debug(self, args):
        if not args:
            print("Usage: debug <slot> [val]")
            return
        slot = parse_int(args[0])
        if len(args) > 1:
            set_debug_pins(slot, parse_int(args[1]))
        else:
            print(f"Slot {slot} Debug Pins: 0x{get_debug_pins(slot):04X}")

    def do_reg(self, args):
        if len(args) < 2:
            print("Usage: reg <slot> <addr> [val]")
            return
        slot = parse_int(args[0])
        addr = parse_int(args[1])
        if len(args) > 2:
            set_slave_register(slot, addr, parse_int(args[2]))
        else:
            print(f"Slot {slot} Reg 0x{addr:02X}: 0x{get_slave_register(slot, addr):04X}")

    def do_help(self, args):
        print("\nAvailable Commands:")
        for name in sorted(self.commands.keys()):
            if name == "?": continue
            _, help_text = self.commands[name]
            print(f"  {name:12} : {help_text}")
        print("\nNote: Values can be decimal or hex (0x...). Booleans: on/off, true/false, 1/0, yes/no.")

    def do_exit(self, args):
        sys.exit(0)

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="L2 Trigger Direct CLI Client")
    parser.add_argument("file", nargs="?", help="Optional file containing commands to execute")
    args = parser.parse_args()


    client = CommandClient()

    if args.file:
        try:
            with open(args.file, "r") as f:
                for line in f:
                    client.run_command(line.strip())
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
    elif not sys.stdin.isatty():
        # Pipe input
        for line in sys.stdin:
            client.run_command(line.strip())
    else:
        # Interactive mode
        print("L2 Trigger Direct CLI Client")
        print("Type 'help' for available commands or 'exit' to quit.")
        
        while True:
            try:
                line = input("l2trig_direct> ")
                client.run_command(line)
            except EOFError:
                print("\nExiting.")
                break
            except KeyboardInterrupt:
                print("\nUse 'exit' or Ctrl-D to quit.")
            except Exception as e:
                print(f"Unexpected error: {e}")

if __name__ == "__main__":
    try:
        smc_open()
    except Exception as e:
        print(f"CRITICAL: Failed to initialize hardware interface: {e}")
        sys.exit(1)

    try:
        main()
    finally:
        smc_close()
