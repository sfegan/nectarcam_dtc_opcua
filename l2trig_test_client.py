"""
l2trig_test_client.py

Interactive OPC UA client for L2 Trigger System
Allows reading monitoring variables and calling control methods from the terminal

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
"""

import argparse
import asyncio
import logging
import sys
from typing import List, Optional, Any

from asyncua import Client, ua
from asyncua.common.node import Node

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(level=logging.WARNING, format='%(message)s')
logger = logging.getLogger("l2trig.client")

# ============================================================================
# Client Class
# ============================================================================

class L2TrigTestClient:
    def __init__(self, endpoint: str, root_path: str, monitoring_name: str):
        self.endpoint = endpoint
        self.root_path = root_path
        self.monitoring_name = monitoring_name
        self.client = Client(url=endpoint)
        self.ns_idx: int = 0
        self.root_node: Optional[Node] = None
        self.monitoring_node: Optional[Node] = None

    async def connect(self):
        """Connect to server and find the L2Trigger root nodes"""
        await self.client.connect()
        logger.info(f"Connected to {self.endpoint}")

        # Find namespace index
        uri = "http://cta.l2trigger.hal"
        try:
            self.ns_idx = await self.client.get_namespace_index(uri)
        except ValueError:
            print(f"Warning: Namespace '{uri}' not found. Defaulting to index 2.")
            self.ns_idx = 2

        # Navigate to the root object
        # Note: server creates Objects/<root_path>/Monitoring
        objects = self.client.get_objects_node()
        path = self.root_path.split(".")
        
        current = objects
        for component in path:
            current = await current.get_child(f"{self.ns_idx}:{component}")
        
        self.root_node = current
        self.monitoring_node = await self.root_node.get_child(f"{self.ns_idx}:{self.monitoring_name}")
        print(f"Found root node: {self.root_path}")

    async def disconnect(self):
        await self.client.disconnect()

    async def list_variables(self):
        """List all variables in the Monitoring folder"""
        children = await self.monitoring_node.get_children()
        print("\nMonitoring Variables:")
        print(f"{'Variable Name':<30} | {'Value'}")
        print("-" * 60)
        for child in children:
            c_class = await child.read_node_class()
            if c_class == ua.NodeClass.Variable:
                name = (await child.read_browse_name()).Name
                val = await child.read_value()
                print(f"{name:<30} | {val}")
        print("")

    async def read_variable(self, name: str) -> Any:
        """Read a specific variable by name"""
        try:
            var_node = await self.monitoring_node.get_child(f"{self.ns_idx}:{name}")
            return await var_node.read_value()
        except Exception as e:
            print(f"Error reading {name}: {e}")
            return None

    async def print_summary(self):
        """Print a nice summary of the system state"""
        print("\n--- L2 Trigger System Summary ---")
        
        # Read essential variables
        slots = await self.read_variable("active_slots")
        if slots is None:
            print("Could not retrieve active slots.")
            return
        
        l2cb_fw = await self.read_variable("l2cb_firmware")
        l2cb_ts = await self.read_variable("l2cb_timestamp")
        print(f"L2CB Firmware: 0x{l2cb_fw:04X} | Timestamp: {l2cb_ts}")
        
        ctdb_fw = await self.read_variable("ctdb_firmware")
        ctdb_curr = await self.read_variable("ctdb_current_ma")
        ctdb_err = await self.read_variable("ctdb_has_errors")
        ctdb_min = await self.read_variable("ctdb_limit_min_ma")
        ctdb_max = await self.read_variable("ctdb_limit_max_ma")
        
        ch_enabled = await self.read_variable("ModulePowerEnabled")
        ch_curr = await self.read_variable("ModuleCurrent")
        ch_state = await self.read_variable("ModuleState")
        trig_enabled = await self.read_variable("ModuleTriggerEnabled")
        trig_delay = await self.read_variable("ModuleTriggerDelay")

        CHANNELS_PER_SLOT = 15

        for i, slot in enumerate(slots):
            status = "ERROR" if ctdb_err[i] else "OK"
            print(f"\nSlot {slot:2d} | FW: 0x{ctdb_fw[i]:04X} | Current: {ctdb_curr[i]:6.1f} mA | Status: {status}")
            print(f"        Limits: {ctdb_min[i]:.1f} - {ctdb_max[i]:.1f} mA")
            print(f"        {'Ch':<3} | {'Pwr':<4} | {'Current':<10} | {'State':<10} | {'Trig':<8} | {'Delay'}")
            print(f"        " + "-" * 68)
            
            for ch in range(CHANNELS_PER_SLOT):
                idx = i * CHANNELS_PER_SLOT + ch
                pwr = "ON" if ch_enabled[idx] else "OFF"
                en_status = "ENABLED" if trig_enabled[idx] else "DISABLED"
                print(f"        {ch+1:<3d} | {pwr:<4} | {ch_curr[idx]:8.1f} mA | {ch_state[idx]:<10} | {en_status:<8} | {trig_delay[idx]:.2f} ns")
        print("")

    async def list_methods(self):
        """List all methods on the root object"""
        children = await self.root_node.get_children()
        print("\nAvailable Methods:")
        for child in children:
            c_class = await child.read_node_class()
            if c_class == ua.NodeClass.Method:
                name = (await child.read_browse_name()).Name
                print(f" - {name}")
        print("")

    async def call_method(self, name: str, *args):
        """Call a method by name with arguments"""
        try:
            # Prepare arguments (simple heuristic to convert strings to numbers/bools)
            typed_args = []
            for arg in args:
                if isinstance(arg, str):
                    if arg.lower() in ["true", "on", "yes", "1"]:
                        typed_args.append(True)
                    elif arg.lower() in ["false", "off", "no", "0"]:
                        typed_args.append(False)
                    elif "." in arg:
                        typed_args.append(float(arg))
                    else:
                        try:
                            typed_args.append(int(arg))
                        except ValueError:
                            typed_args.append(arg)
                else:
                    typed_args.append(arg)

            res = await self.root_node.call_method(f"{self.ns_idx}:{name}", *typed_args)
            print(f"Result: {res}")
        except Exception as e:
            print(f"Error calling {name}: {e}")

# ============================================================================
# Interactive Loop
# ============================================================================

async def interactive_loop(client: L2TrigTestClient):
    print("\nL2 Trigger OPC UA Test Client")
    print("Type 'help' for available commands.")

    while True:
        try:
            # Use to_thread to keep the loop responsive if needed, 
            # though here we just wait for input
            cmd_line = await asyncio.to_thread(input, "l2trig> ")
            if not cmd_line.strip():
                continue
            
            parts = cmd_line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ["exit", "quit"]:
                break
            elif cmd == "help":
                print("\nInquiry Commands:")
                print("  summary             Show full system status summary")
                print("  list                List all raw monitoring variables")
                print("  read <var>          Read a specific variable")
                print("  methods             List available methods")
                
                print("\nControl Commands:")
                print("  power <mod> <on|off> Set module power (1-270)")
                print("  allpower <on|off>    Set all modules power")
                print("  trig <mod> <on|off>  Enable or disable module trigger")
                print("  delay <mod> <ns>     Set module trigger delay (0-5.0)")
                print("  alltrig <on|off>     Enable or disable all triggers")
                print("  alldelay <ns>        Set all trigger delays")
                print("  limits <board> <min> <max> Set current limits for a board (1-based index)")
                print("  health               Perform health check")
                print("  shutdown             Emergency power shutdown")
                print("  call <name> [args]   Generic method call")
                
                print("\nGeneral:")
                print("  help                Show this help")
                print("  exit/quit           Close client")

            elif cmd == "summary":
                await client.print_summary()
            elif cmd == "list":
                await client.list_variables()
            elif cmd == "read":
                if not args:
                    print("Usage: read <variable_name>")
                else:
                    val = await client.read_variable(args[0])
                    if val is not None:
                        print(f"{args[0]} = {val}")
            elif cmd == "methods":
                await client.list_methods()
            elif cmd == "call":
                if not args:
                    print("Usage: call <method_name> [args...]")
                else:
                    await client.call_method(args[0], *args[1:])
            
            # Shortcut commands
            elif cmd == "power":
                if len(args) != 2: print("Usage: power <module> <on|off>")
                else: await client.call_method("SetModulePower", args[0], args[1])
            elif cmd == "allpower":
                if len(args) != 1: print("Usage: allpower <on|off>")
                else: await client.call_method("SetAllPower", args[0])
            elif cmd == "trig":
                if len(args) != 2: print("Usage: trig <module> <on|off>")
                else: await client.call_method("SetModuleTriggerEnabled", args[0], args[1])
            elif cmd == "delay":
                if len(args) != 2: print("Usage: delay <module> <ns>")
                else: await client.call_method("SetModuleTriggerDelay", args[0], args[1])
            elif cmd == "alltrig":
                if len(args) != 1: print("Usage: alltrig <on|off>")
                else: await client.call_method("SetAllTriggerEnabled", args[0])
            elif cmd == "alldelay":
                if len(args) != 1: print("Usage: alldelay <ns>")
                else: await client.call_method("SetAllTriggerDelay", args[0])
            elif cmd == "limits":
                if len(args) != 3: print("Usage: limits <board_index> <min_ma> <max_ma>")
                else: await client.call_method("SetBoardCurrentLimits", args[0], args[1], args[2])
            elif cmd == "health":
                await client.call_method("HealthCheck")
            elif cmd == "shutdown":
                await client.call_method("EmergencyShutdown")
            else:
                print(f"Unknown command: {cmd}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Unexpected error: {e}")

# ============================================================================
# Main
# ============================================================================

def _parse_args():
    p = argparse.ArgumentParser(description="L2 Trigger System OPC UA Test Client")
    p.add_argument("--endpoint", default="opc.tcp://localhost:4840/l2trigger/")
    p.add_argument("--root", default="L2Trigger", help="Browse path to root object")
    p.add_argument("--monitoring", default="Monitoring", help="Name of monitoring folder")
    return p.parse_args()

async def main():
    args = _parse_args()
    client = L2TrigTestClient(args.endpoint, args.root, args.monitoring)
    
    try:
        await client.connect()
        await interactive_loop(client)
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
