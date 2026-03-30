"""
l2trig_test_client.py

Interactive OPC UA client for L2 Trigger System
Allows reading monitoring variables and calling control methods from the terminal
"""

import argparse
import asyncio
import logging
import sys
from typing import List, Optional

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
            c_class = await child.get_node_class()
            if c_class == ua.NodeClass.Variable:
                name = (await child.read_browse_name()).Name
                val = await child.read_value()
                print(f"{name:<30} | {val}")
        print("")

    async def read_variable(self, name: str):
        """Read a specific variable by name"""
        try:
            var_node = await self.monitoring_node.get_child(f"{self.ns_idx}:{name}")
            val = await var_node.read_value()
            print(f"{name} = {val}")
        except Exception as e:
            print(f"Error reading {name}: {e}")

    async def list_methods(self):
        """List all methods on the root object"""
        children = await self.root_node.get_children()
        print("\nAvailable Methods:")
        for child in children:
            c_class = await child.get_node_class()
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
                if arg.lower() == "true":
                    typed_args.append(True)
                elif arg.lower() == "false":
                    typed_args.append(False)
                elif "." in arg:
                    typed_args.append(float(arg))
                else:
                    try:
                        typed_args.append(int(arg))
                    except ValueError:
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
                print("\nCommands:")
                print("  list                List all monitoring variables")
                print("  read <var>          Read a specific variable")
                print("  methods             List available methods")
                print("  call <name> [args]  Call a method (e.g., 'call SetAllPower True')")
                print("  help                Show this help")
                print("  exit/quit           Close client")
            elif cmd == "list":
                await client.list_variables()
            elif cmd == "read":
                if not args:
                    print("Usage: read <variable_name>")
                else:
                    await client.read_variable(args[0])
            elif cmd == "methods":
                await client.list_methods()
            elif cmd == "call":
                if not args:
                    print("Usage: call <method_name> [args...]")
                else:
                    await client.call_method(args[0], *args[1:])
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
