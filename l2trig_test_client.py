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
import os
import sys
from typing import List, Optional, Any, Dict, Set

from asyncua import Client, ua
from asyncua.common.node import Node

# ============================================================================
# Subscription Handler
# ============================================================================

class SubscriptionHandler:
    """
    Handler for OPC UA data change notifications.
    """
    async def datachange_notification(self, node: Node, val: Any, data):
        try:
            name = (await node.read_browse_name()).Name
            # Use carriage return and print the prompt again to keep it looking clean
            sys.stdout.write(f"\r[MONITOR] {name} = {val}\nl2trig> ")
            sys.stdout.flush()
        except Exception:
            sys.stdout.write(f"\r[MONITOR] {node} = {val}\nl2trig> ")
            sys.stdout.flush()

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
        self.subscription = None
        self.sub_handles: Dict[Node, Any] = {}
        self.subscribed_names: Set[str] = set()

    async def connect(self):
        """Connect to server and find the L2Trigger root nodes"""
        try:
            await self.client.connect()
        except Exception as e:
            logger.error(f"Failed to connect to {self.endpoint}: {e}")
            raise
        
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

    async def ensure_connected(self):
        """Check if connected and attempt to reconnect if not"""
        try:
            # Check connection with a simple node browse
            await self.client.nodes.root.get_children()
            return
        except Exception:
            pass

        print("Connection lost. Reconnecting...")
        await self.reconnect()

    async def reconnect(self):
        """Force a reconnection and restore subscriptions"""
        old_subs = list(self.subscribed_names)
        try:
            await self.disconnect()
        except:
            pass
        
        # Reset nodes as they are session-specific
        self.root_node = None
        self.monitoring_node = None
        self.subscription = None
        self.sub_handles.clear()
        self.subscribed_names.clear()
        
        # Try to reconnect
        await self.connect()

        # Restore subscriptions
        for name in old_subs:
            await self.subscribe(name)

    async def disconnect(self):
        """Disconnect and cleanup subscriptions"""
        try:
            if self.subscription is not None:
                await self.subscription.delete()
                self.subscription = None
            self.sub_handles.clear()
            self.subscribed_names.clear()
            await self.client.disconnect()
        except:
            pass

    async def subscribe(self, name: str):
        """Subscribe to a specific variable or 'all' variables"""
        if self.subscription is None:
            self.subscription = await self.client.create_subscription(500, SubscriptionHandler())
        
        if name.lower() == "all":
            self.subscribed_names.add("all")
            children = await self.monitoring_node.get_children()
            count = 0
            for child in children:
                c_class = await child.read_node_class()
                if c_class == ua.NodeClass.Variable:
                    if await self._subscribe_node(child):
                        count += 1
            print(f"Subscribed to {count} variables")
        else:
            try:
                var_node = await self.monitoring_node.get_child(f"{self.ns_idx}:{name}")
                if await self._subscribe_node(var_node):
                    self.subscribed_names.add(name)
                    print(f"Subscribed to {name}")
            except Exception as e:
                print(f"Error subscribing to {name}: {e}")

    async def _subscribe_node(self, node: Node) -> bool:
        """Internal method to subscribe to a node"""
        if node in self.sub_handles:
            return False
        
        handle = await self.subscription.subscribe_data_change(node)
        self.sub_handles[node] = handle
        return True

    async def unsubscribe(self, name: str):
        """Unsubscribe from a specific variable or 'all' variables"""
        if self.subscription is None:
            print("No active subscriptions.")
            return
        
        if name.lower() == "all":
            await self.subscription.delete()
            self.subscription = None
            self.sub_handles.clear()
            self.subscribed_names.clear()
            print("Unsubscribed from all variables")
        else:
            try:
                var_node = await self.monitoring_node.get_child(f"{self.ns_idx}:{name}")
                if var_node in self.sub_handles:
                    await self.subscription.unsubscribe(self.sub_handles[var_node])
                    del self.sub_handles[var_node]
                    self.subscribed_names.discard(name)
                    print(f"Unsubscribed from {name}")
                else:
                    print(f"Not subscribed to {name}")
            except Exception as e:
                print(f"Error unsubscribing from {name}: {e}")

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
        slots = await self.read_variable("BoardSlots")
        if slots is None:
            print("Could not retrieve BoardSlots.")
            return
        
        l2cb_fw = await self.read_variable("CrateFirmwareRevision")
        l2cb_uptime = await self.read_variable("CrateUpTime")
        l2cb_mcf = await self.read_variable("CrateMCFEnabled")
        l2cb_glitch = await self.read_variable("CrateBusyGlitchFilterEnabled")
        l2cb_tib = await self.read_variable("CrateTIBTriggerBusyBlockEnabled")
        l2cb_deadtime = await self.read_variable("CrateL1Deadtime")
        
        print(f"L2CB Firmware: 0x{l2cb_fw:04X} | Uptime: {l2cb_uptime/1e9:.3f} s")
        print(f"L2CB Status: MCF={'ON' if l2cb_mcf else 'OFF'}, BusyGlitchFilter={'ON' if l2cb_glitch else 'OFF'}, TIBTriggerBusyBlock={'ON' if l2cb_tib else 'OFF'}, L1Deadtime={l2cb_deadtime:.1f} ns")
        
        ctdb_fw = await self.read_variable("BoardFirmwareRevision")
        ctdb_curr = await self.read_variable("BoardCurrent")
        ctdb_err = await self.read_variable("BoardHasErrors")
        ctdb_min = await self.read_variable("BoardCurrentLimitMin")
        ctdb_max = await self.read_variable("BoardCurrentLimitMax")
        
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
            
            # Ensure we are connected before executing the command
            await client.ensure_connected()
            
            parts = cmd_line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ["exit", "quit", "bye"]:
                break
            elif cmd in ["help", "?"]:
                print("\nInquiry Commands:")
                print("  summary             Show full system status summary")
                print("  list                List all raw monitoring variables")
                print("  read <var>          Read a specific variable")
                print("  methods             List available methods")
                print("  subscribe <var|all> Subscribe to variable(s) change notifications")
                print("  unsubscribe <var|all> Unsubscribe from notifications")
                
                print("\nControl Commands:")
                print("  power <mod> <on|off> Set module power (1-270)")
                print("  allpower <on|off>    Set all modules power")
                print("  trig <mod> <on|off>  Enable or disable module trigger")
                print("  delay <mod> <ns>     Set module trigger delay (0-5.0)")
                print("  alltrig <on|off>     Enable or disable all triggers")
                print("  alldelay <ns>        Set all trigger delays")
                print("  limits <board> <min> <max> Set current limits for a board (1-based index)")
                print("  mcf <on|off>         Set L2CB MCF enabled status")
                print("  mcfdelay <ns>        Set L2CB MCF delay (0-75 ns)")
                print("  mcfthreshold <val>   Set L2CB MCF threshold (0-512)")
                print("  deadtime <ns>        Set L2CB L1 deadtime (0-1275 ns)")
                print("  glitch <on|off>      Set L2CB busy glitch filter enabled status")
                print("  tibblock <on|off>    Set L2CB TIB trigger block enabled status")
                print("  health               Perform health check")
                print("  shutdown             Emergency power shutdown")
                print("  call <name> [args]   Generic method call")
                
                print("\nGeneral:")
                print("  reconnect           Reconnect to the server")
                print("  cls                 Clear screen")
                print("  help / ?            Show this help")
                print("  exit/quit           Close client (or Ctrl-D)")

            elif cmd == "summary":
                await client.print_summary()
            elif cmd == "list":
                await client.list_variables()
            elif cmd in ("read", "get"):
                if not args:
                    print("Usage: read <variable_name>")
                else:
                    val = await client.read_variable(args[0])
                    if val is not None:
                        print(f"{args[0]} = {val}")
            elif cmd == "methods":
                await client.list_methods()
            elif cmd in ("subscribe", "sub", "monitor", "mon"):
                if not args: print("Usage: subscribe <variable_name|all>")
                else: await client.subscribe(args[0])
            elif cmd in ("unsubscribe", "unsub", "unmonitor", "unmon"):
                if not args: print("Usage: unsubscribe <variable_name|all>")
                else: await client.unsubscribe(args[0])
            elif cmd in ("reconnect", "restart"):
                await client.reconnect()
            elif cmd == "cls":
                os.system('cls' if os.name == 'nt' else 'clear')
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
            elif cmd == "mcf":
                if len(args) != 1: print("Usage: mcf <on|off>")
                else: await client.call_method("SetMCFEnabled", args[0])
            elif cmd == "mcfdelay":
                if len(args) != 1: print("Usage: mcfdelay <ns>")
                else: await client.call_method("SetMCFDelay", args[0])
            elif cmd == "mcfthreshold":
                if len(args) != 1: print("Usage: mcfthreshold <val>")
                else: await client.call_method("SetMCFThreshold", args[0])
            elif cmd == "deadtime":
                if len(args) != 1: print("Usage: deadtime <ns>")
                else: await client.call_method("SetL1Deadtime", args[0])
            elif cmd == "glitch":
                if len(args) != 1: print("Usage: glitch <on|off>")
                else: await client.call_method("SetBusyGlitchFilterEnabled", args[0])
            elif cmd == "tibblock":
                if len(args) != 1: print("Usage: tibblock <on|off>")
                else: await client.call_method("SetTIBTriggerBusyBlockEnabled", args[0])
            else:
                print(f"Unknown command: {cmd}")

        except (KeyboardInterrupt, EOFError):
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
