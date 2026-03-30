"""
l2trig_asyncua_server.py

OPC UA Server for L2 Trigger System
Exposes L2 trigger hardware control via OPC UA protocol
"""

import argparse
import asyncio
import datetime
import logging
import signal
import sys
import time
from typing import Dict, Optional, List, Any, Tuple

from asyncua import Server, ua
from asyncua.common.methods import uamethod
from asyncua.server.user_managers import UserManager, User, UserRole

from l2trig_api import (
    L2TriggerSystem,
    CTDBStatus,
    VALID_SLOTS,
    CHANNELS_PER_SLOT
)

# ============================================================================
# Logging
# ============================================================================

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

class _SuppressUaStatusCodeTracebacks(logging.Filter):
    """Downgrade OPC UA method-failure log records; strip their tracebacks."""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and isinstance(record.exc_info[1], ua.UaStatusCodeError):
            logger.warning("OPC UA method returned Bad status: %s", record.exc_info[1])
            return False
        return True

def _configure_logging(level: str, log_file: str | None) -> None:
    """Configure the root logger."""
    formatter = logging.Formatter(_LOG_FORMAT)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    handlers = [stdout_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(level=level, handlers=handlers, force=True)
    
    # Suppress noisy asyncua initialization logs
    logging.getLogger("asyncua.server.address_space").setLevel(logging.WARNING)
    logging.getLogger("asyncua.server.internal_server").setLevel(logging.WARNING)
    
    # Add filter for method failures
    logging.getLogger("asyncua.server.address_space").addFilter(
        _SuppressUaStatusCodeTracebacks()
    )

logger = logging.getLogger("cta.l2trigger.server")

# ============================================================================
# OPC UA Server
# ============================================================================

class L2TriggerOPCUAServer:
    """OPC UA Server for L2 Trigger System"""
    
    _DEFAULT_ROOT = "L2Trigger"
    _DEFAULT_MONITORING_PATH = "Monitoring"

    # OPC UA Status Codes
    STATUS_GOOD = ua.StatusCode(ua.StatusCodes.Good)
    STATUS_WAITING = ua.StatusCode(ua.StatusCodes.BadWaitingForInitialData)

    # (name, initial value, OPC UA variant type, description)
    _MONITORING_VARS = [
        ("l2cb_firmware", 0, ua.VariantType.UInt16, "L2CB board firmware version"),
        ("l2cb_timestamp", 0, ua.VariantType.UInt64, "L2CB hardware timestamp"),
        ("active_slots", [], ua.VariantType.Int32, "List of slots enabled in this server"),
        ("ctdb_firmware", [], ua.VariantType.UInt16, "CTDB firmware versions (one per active slot)"),
        ("ctdb_current_ma", [], ua.VariantType.Double, "CTDB board currents in mA (one per active slot)"),
        ("ctdb_total_channel_current_ma", [], ua.VariantType.Double, "Total channel current per CTDB in mA (one per active slot)"),
        ("ctdb_limit_min_ma", [], ua.VariantType.Double, "Current limit minimum in mA (one per active slot)"),
        ("ctdb_limit_max_ma", [], ua.VariantType.Double, "Current limit maximum in mA (one per active slot)"),
        ("ctdb_has_errors", [], ua.VariantType.Boolean, "Error status flag (one per active slot)"),
        ("channel_enabled", [], ua.VariantType.Boolean, "Channel power enable status (flattened: slot_idx*15 + ch-1)"),
        ("channel_current_ma", [], ua.VariantType.Double, "Channel current readings in mA (flattened: slot_idx*15 + ch-1)"),
        ("channel_state", [], ua.VariantType.String, "Channel state strings (flattened: slot_idx*15 + ch-1)"),
        ("trigger_masked", [], ua.VariantType.Boolean, "Trigger mask status (flattened: slot_idx*15 + ch)"),
        ("trigger_delay_ns", [], ua.VariantType.Double, "Trigger delay in ns (flattened: slot_idx*15 + ch)"),
    ]

    def __init__(self, 
                 opcua_endpoint: str = "opc.tcp://0.0.0.0:4840/l2trigger/",
                 opcua_root: str = None,
                 monitoring_path: str = None,
                 opcua_users: dict = None,
                 poll_interval: float = 1.0,
                 timeout_us: int = 10000,
                 enabled_slots: Optional[List[int]] = None):
        """
        Initialize OPC UA server
        """
        self.endpoint = opcua_endpoint
        self.opcua_root = opcua_root or self._DEFAULT_ROOT
        self.monitoring_path = monitoring_path or self._DEFAULT_MONITORING_PATH
        self.opcua_users = opcua_users or {}
        self.poll_interval = poll_interval
        
        # Hardware interface
        self.system = L2TriggerSystem(
            timeout_us=timeout_us,
            enabled_slots=enabled_slots
        )
        self.active_slots = sorted(list(self.system.ctdbs.keys()))
        
        # OPC UA server
        self.server = Server()
        self.namespace_idx = None
        self._vars: Dict[str, Any] = {}
        
        # Update task
        self._update_task: Optional[asyncio.Task] = None
        self._running = False

    def _module_to_slot_channel(self, module: int) -> Tuple[int, int]:
        """Convert 1-based module number to (slot, channel)."""
        if not 1 <= module <= len(VALID_SLOTS) * CHANNELS_PER_SLOT:
            raise ValueError(f"Module number {module} out of range (1-270)")
        
        slot_idx = (module - 1) // CHANNELS_PER_SLOT
        slot = VALID_SLOTS[slot_idx]
        channel = (module - 1) % CHANNELS_PER_SLOT
        return slot, channel

    async def init(self):
        """Initialize the OPC UA server"""
        # Set up user manager if users are provided
        if self.opcua_users:
            creds = self.opcua_users
            class _Manager(UserManager):
                async def get_user(self, iserver, username=None, password=None, certificate=None):
                    return (User(role=UserRole.User) if creds.get(username) == password else None)
            self.server.set_user_manager(_Manager())

        # shelf_file=None disables asyncua's address-space persistence cache.
        await self.server.init(shelf_file=None)
        self.server.set_endpoint(self.endpoint)
        self.server.set_server_name("L2 Trigger System OPC UA Server")
        
        if self.opcua_users:
            self.server.set_security_IDs(["Anonymous", "Username"])

        uri = "http://cta.l2trigger.hal"
        self.namespace_idx = await self.server.register_namespace(uri)
        
        # Create address space
        await self._create_address_space()
        
        logger.info(f"OPC UA Server initialized at {self.endpoint}")

    @staticmethod
    def _arg(name: str, variant_type: ua.VariantType, description: str = "") -> ua.Argument:
        """Build a named, typed OPC UA method argument descriptor."""
        arg = ua.Argument()
        arg.Name = name
        arg.DataType = ua.NodeId(int(variant_type))
        arg.ValueRank = -1
        arg.ArrayDimensions = []
        arg.Description = ua.LocalizedText(description or name)
        return arg

    async def _create_address_space(self):
        """Create the OPC UA address space structure"""
        idx = self.namespace_idx
        
        # Build root object with dotted NodeIds
        components = self.opcua_root.split(".")
        node_id_prefix = ""
        parent = self.server.nodes.objects
        for component in components:
            node_id_prefix = f"{node_id_prefix}.{component}" if node_id_prefix else component
            parent = await parent.add_object(
                ua.NodeId(node_id_prefix, idx),
                ua.QualifiedName(component, idx)
            )
        root_obj = parent

        # Create Monitoring folder
        mon_node_id = f"{self.opcua_root}.{self.monitoring_path}"
        mon_obj = await root_obj.add_object(
            ua.NodeId(mon_node_id, idx),
            ua.QualifiedName(self.monitoring_path, idx)
        )
        
        # Create monitoring variables with dotted NodeIds
        for name, initial, vtype, description in self._MONITORING_VARS:
            var_node_id = f"{mon_node_id}.{name}"
            var = await mon_obj.add_variable(
                ua.NodeId(var_node_id, idx),
                ua.QualifiedName(name, idx),
                initial,
                varianttype=vtype
            )
            await var.set_read_only()
            # Set description
            await var.write_attribute(
                ua.AttributeIds.Description,
                ua.DataValue(ua.Variant(ua.LocalizedText(description), ua.VariantType.LocalizedText))
            )
            self._vars[name] = (var, vtype)

        # Create methods on root
        await self._create_methods(root_obj, idx)
        
        logger.info(f"Address space created with root {self.opcua_root}")

    async def _create_methods(self, parent, idx):
        """Create OPC UA methods for system control"""
        
        def method_node_id(name):
            return ua.NodeId(f"{self.opcua_root}.{name}", idx)

        a = self._arg  # shorthand
        res_arg = [a("result", ua.VariantType.String, "Status message")]

        # Emergency shutdown method
        @uamethod
        async def emergency_shutdown(parent_node):
            """Emergency shutdown - disable all power channels"""
            logger.warning("Emergency shutdown called via OPC UA")
            await self.system.emergency_shutdown()
            return "Emergency shutdown complete"
        
        await parent.add_method(
            method_node_id("EmergencyShutdown"),
            ua.QualifiedName("EmergencyShutdown", idx),
            emergency_shutdown,
            [], res_arg
        )
        
        # Set all power method
        @uamethod
        async def set_all_power(parent_node, enabled: bool):
            """Enable or disable all power channels"""
            await self.system.set_all_power(enabled)
            return f"All power {'enabled' if enabled else 'disabled'}"
        
        await parent.add_method(
            method_node_id("SetAllPower"),
            ua.QualifiedName("SetAllPower", idx),
            set_all_power,
            [a("enabled", ua.VariantType.Boolean, "True to enable, False to disable")], 
            res_arg
        )
        
        # Set module power method
        @uamethod
        async def set_module_power(parent_node, module: int, enabled: bool):
            """Enable or disable power for a specific module"""
            slot, channel = self._module_to_slot_channel(module)
            if slot not in self.system.ctdbs:
                raise ValueError(f"Slot {slot} (module {module}) not enabled in this server")
            await self.system.set_slot_power(slot, channel + 1, enabled)
            return f"Module {module} (Slot {slot} Ch {channel+1}) {'enabled' if enabled else 'disabled'}"
        
        await parent.add_method(
            method_node_id("SetModulePower"),
            ua.QualifiedName("SetModulePower", idx),
            set_module_power,
            [a("module", ua.VariantType.Int32, "Module number (1-270)"),
             a("enabled", ua.VariantType.Boolean, "True to enable, False to disable")], 
            res_arg
        )

        # Set current limits method
        @uamethod
        async def set_current_limits(parent_node, slot: int, min_ma: float, max_ma: float):
            """Set current limits for a specific slot"""
            if slot not in self.system.ctdbs:
                raise ValueError(f"Slot {slot} not enabled")
            await self.system.ctdbs[slot].set_current_limits(min_ma, max_ma)
            return f"Slot {slot} limits set to {min_ma}-{max_ma} mA"

        await parent.add_method(
            method_node_id("SetCurrentLimits"),
            ua.QualifiedName("SetCurrentLimits", idx),
            set_current_limits,
            [a("slot", ua.VariantType.Int32, "Slot number"),
             a("min_ma", ua.VariantType.Double, "Minimum current in mA"),
             a("max_ma", ua.VariantType.Double, "Maximum current in mA")],
            res_arg
        )

        # Set module trigger mask method
        @uamethod
        async def set_module_trigger_mask(parent_node, module: int, masked: bool):
            """Set trigger mask for a specific module"""
            slot, channel = self._module_to_slot_channel(module)
            if slot not in self.system.ctdbs:
                raise ValueError(f"Slot {slot} (module {module}) not enabled in this server")
            await self.system.ctdbs[slot].set_trigger_mask(channel, masked)
            return f"Module {module} (Slot {slot} Trigger Ch {channel}) {'masked' if masked else 'active'}"

        await parent.add_method(
            method_node_id("SetModuleTriggerMask"),
            ua.QualifiedName("SetModuleTriggerMask", idx),
            set_module_trigger_mask,
            [a("module", ua.VariantType.Int32, "Module number (1-270)"),
             a("masked", ua.VariantType.Boolean, "True to mask, False to unmask")],
            res_arg
        )

        # Set module trigger delay method
        @uamethod
        async def set_module_trigger_delay(parent_node, module: int, delay_ns: float):
            """Set trigger delay for a specific module"""
            slot, channel = self._module_to_slot_channel(module)
            if slot not in self.system.ctdbs:
                raise ValueError(f"Slot {slot} (module {module}) not enabled in this server")
            await self.system.ctdbs[slot].set_trigger_delay(channel, delay_ns)
            return f"Module {module} (Slot {slot} Trigger Ch {channel}) delay set to {delay_ns} ns"

        await parent.add_method(
            method_node_id("SetModuleTriggerDelay"),
            ua.QualifiedName("SetModuleTriggerDelay", idx),
            set_module_trigger_delay,
            [a("module", ua.VariantType.Int32, "Module number (1-270)"),
             a("delay_ns", ua.VariantType.Double, "Delay in ns (0-5 ns)")],
            res_arg
        )

        # Set all trigger mask method
        @uamethod
        async def set_all_trigger_mask(parent_node, masked: bool):
            """Set trigger mask for all channels"""
            await self.system.set_all_trigger_mask(masked)
            return f"All triggers {'masked' if masked else 'unmasked'}"

        await parent.add_method(
            method_node_id("SetAllTriggerMask"),
            ua.QualifiedName("SetAllTriggerMask", idx),
            set_all_trigger_mask,
            [a("masked", ua.VariantType.Boolean, "True to mask, False to unmask")],
            res_arg
        )

        # Set all trigger delay method
        @uamethod
        async def set_all_trigger_delay(parent_node, delay_ns: float):
            """Set trigger delay for all channels"""
            await self.system.set_all_trigger_delay(delay_ns)
            return f"All trigger delays set to {delay_ns} ns"

        await parent.add_method(
            method_node_id("SetAllTriggerDelay"),
            ua.QualifiedName("SetAllTriggerDelay", idx),
            set_all_trigger_delay,
            [a("delay_ns", ua.VariantType.Double, "Delay in ns (0-5 ns)")],
            res_arg
        )
        
        # Health check method
        @uamethod
        async def health_check(parent_node):
            """Perform system health check"""
            health = await self.system.health_check()
            return f"Health: {health['overall']}. Errors: {health['errors']}"
        
        await parent.add_method(
            method_node_id("HealthCheck"),
            ua.QualifiedName("HealthCheck", idx),
            health_check,
            [], res_arg
        )

    async def _update_loop(self):
        """Background task to update OPC UA values from hardware"""
        logger.info("Update loop started")
        
        while self._running:
            try:
                # Update L2CB status
                l2cb_status = await self.system.get_l2cb_status()
                now = datetime.datetime.now(datetime.timezone.utc)
                
                await self._set_var("l2cb_firmware", l2cb_status.firmware_version, now)
                await self._set_var("l2cb_timestamp", l2cb_status.timestamp, now)
                await self._set_var("active_slots", self.active_slots, now)
                
                # Update all CTDB statuses
                status_tasks = [self.system.ctdbs[slot].get_status() for slot in self.active_slots]
                trigger_tasks = [self.system.ctdbs[slot].get_trigger_status() for slot in self.active_slots]
                
                # Run all updates in parallel
                statuses = await asyncio.gather(*status_tasks, return_exceptions=True)
                triggers = await asyncio.gather(*trigger_tasks, return_exceptions=True)
                
                # Prepare vectors
                ctdb_fw = []
                ctdb_curr = []
                ctdb_total = []
                ctdb_min = []
                ctdb_max = []
                ctdb_err = []
                
                ch_enabled = []
                ch_curr = []
                ch_state = []
                
                trig_masked = []
                trig_delay = []
                
                for i, slot in enumerate(self.active_slots):
                    status = statuses[i]
                    trigger = triggers[i]
                    
                    if not isinstance(status, Exception):
                        ctdb_fw.append(status.firmware_version)
                        ctdb_curr.append(float(status.ctdb_current_ma))
                        ctdb_total.append(float(status.total_current_ma))
                        ctdb_min.append(float(status.current_limit_min_ma))
                        ctdb_max.append(float(status.current_limit_max_ma))
                        ctdb_err.append(status.has_errors)
                        
                        for ch in status.power_channels:
                            ch_enabled.append(ch.enabled)
                            ch_curr.append(float(ch.current_ma))
                            ch_state.append(ch.state.value)
                    else:
                        logger.error(f"Error fetching status for slot {slot}: {status}")
                        ctdb_fw.append(0)
                        ctdb_curr.append(0.0)
                        ctdb_total.append(0.0)
                        ctdb_min.append(0.0)
                        ctdb_max.append(0.0)
                        ctdb_err.append(True)
                        for _ in range(CHANNELS_PER_SLOT):
                            ch_enabled.append(False)
                            ch_curr.append(0.0)
                            ch_state.append("offline")
                            
                    if not isinstance(trigger, Exception):
                        for trig in trigger:
                            trig_masked.append(trig.masked)
                            trig_delay.append(float(trig.delay_ns))
                    else:
                        logger.error(f"Error fetching trigger for slot {slot}: {trigger}")
                        for _ in range(CHANNELS_PER_SLOT):
                            trig_masked.append(True)
                            trig_delay.append(0.0)

                await self._set_var("ctdb_firmware", ctdb_fw, now)
                await self._set_var("ctdb_current_ma", ctdb_curr, now)
                await self._set_var("ctdb_total_channel_current_ma", ctdb_total, now)
                await self._set_var("ctdb_limit_min_ma", ctdb_min, now)
                await self._set_var("ctdb_limit_max_ma", ctdb_max, now)
                await self._set_var("ctdb_has_errors", ctdb_err, now)
                
                await self._set_var("channel_enabled", ch_enabled, now)
                await self._set_var("channel_current_ma", ch_curr, now)
                await self._set_var("channel_state", ch_state, now)
                
                await self._set_var("trigger_masked", trig_masked, now)
                await self._set_var("trigger_delay_ns", trig_delay, now)
                
            except Exception as e:
                logger.error(f"Error in update loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.poll_interval)
        
        logger.info("Update loop stopped")

    async def _set_var(self, name: str, value: Any, timestamp: datetime.datetime):
        """Helper to write variable value with timestamp"""
        if name not in self._vars:
            return
        node, vtype = self._vars[name]
        try:
            await node.write_value(
                ua.DataValue(
                    Value=ua.Variant(value, vtype),
                    SourceTimestamp=timestamp
                )
            )
        except Exception as e:
            logger.error(f"Failed to update {name}: {e}")

    async def start(self):
        """Start the OPC UA server"""
        await self.init()
        
        async with self.server:
            logger.info("OPC UA Server started")
            
            self._running = True
            self._update_task = asyncio.create_task(self._update_loop())
            
            # Keep server running
            loop = asyncio.get_running_loop()
            shutdown = loop.create_future()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, shutdown.set_result, sig)
            
            try:
                sig = await shutdown
                logger.info(f"Received {sig.name}, shutting down.")
            finally:
                await self.stop()

    async def stop(self):
        """Stop the OPC UA server"""
        logger.info("Stopping OPC UA server...")
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("OPC UA server stopped")


# ============================================================================
# Main Entry Point
# ============================================================================

def _parse_args():
    p = argparse.ArgumentParser(description="L2 Trigger System OPC UA Server")
    p.add_argument("--opcua-endpoint", default="opc.tcp://0.0.0.0:4840/l2trigger/")
    p.add_argument("--opcua-root", default="L2Trigger", 
                   help="Root object path (e.g. L2Trigger or Camera.L2Trigger)")
    p.add_argument("--monitoring-path", default="Monitoring",
                   help="Name of the monitoring object under the root")
    p.add_argument("--opcua-user", action="append", metavar="USER:PASS")
    p.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds")
    p.add_argument("--timeout-us", type=int, default=10000, help="Hardware timeout in microseconds")
    p.add_argument("--slots", help="Comma-separated list of slots to enable (default: all)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--log-file", help="Optional log file path")
    return p.parse_args()

async def main():
    """Main entry point"""
    args = _parse_args()
    _configure_logging(args.log_level, args.log_file)
    
    opcua_users = {}
    for pair in args.opcua_user or []:
        if ":" not in pair:
            logger.error("Invalid --opcua-user (expected USER:PASS): %r", pair)
            return 1
        user, _, pw = pair.partition(":")
        opcua_users[user] = pw

    enabled_slots = None
    if args.slots:
        try:
            enabled_slots = [int(s.strip()) for s in args.slots.split(",")]
        except ValueError:
            logger.error(f"Invalid slots argument: {args.slots}")
            return 1

    server = L2TriggerOPCUAServer(
        opcua_endpoint=args.opcua_endpoint,
        opcua_root=args.opcua_root,
        monitoring_path=args.monitoring_path,
        opcua_users=opcua_users,
        poll_interval=args.poll_interval,
        timeout_us=args.timeout_us,
        enabled_slots=enabled_slots
    )
    
    try:
        await server.start()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
