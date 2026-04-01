"""
l2trig_asyncua_server.py

OPC UA Server for L2 Trigger System
Exposes L2 trigger hardware control via OPC UA protocol

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
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
    logging.getLogger("asyncua.server.uaprocessor").setLevel(logging.WARNING)
    
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
        ("CrateFirmwareRevision", 0, ua.VariantType.UInt16, "L2CB board firmware version"),
        ("CrateTimestamp", datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc), ua.VariantType.DateTime, "L2CB hardware timestamp"),
        ("CrateRawTimestamp", 0, ua.VariantType.UInt64, "L2CB raw hardware timestamp counter"),
        ("BoardSlots", [], ua.VariantType.Int32, "List of crate slots enabled in this server"),
        ("BoardFirmwareRevision", [], ua.VariantType.UInt16, "CTDB firmware versions (one per active slot)"),
        ("BoardCurrent", [], ua.VariantType.Double, "CTDB board currents in mA (one per active slot)"),
        ("BoardCurrentSum", [], ua.VariantType.Double, "Total channel current per CTDB in mA (one per active slot)"),
        ("BoardCurrentLimitMin", [], ua.VariantType.Double, "Current limit minimum in mA (one per active slot)"),
        ("BoardCurrentLimitMax", [], ua.VariantType.Double, "Current limit maximum in mA (one per active slot)"),
        ("BoardHasErrors", [], ua.VariantType.Boolean, "Error status flag: true if under or over current flagged in this board, false otherwise (one per active slot)"),
        ("ModulePowerEnabled", [], ua.VariantType.Boolean, "Module power enable status: true if enabled, false otherwise (flattened: slot_idx*15 + ch-1)"),
        ("ModuleCurrent", [], ua.VariantType.Double, "Channel current readings in mA (flattened: slot_idx*15 + ch-1)"),
        ("ModuleState", [], ua.VariantType.String, "Channel state strings: \"on\", \"off\", \"error_over_current\", \"error_under_current\" or \"error_both\" (flattened: slot_idx*15 + ch-1)"),
        ("ModuleTriggerEnabled", [], ua.VariantType.Boolean, "Trigger enabled status (flattened: slot_idx*15 + ch)"),
        ("ModuleTriggerDelay", [], ua.VariantType.Double, "Trigger delay in ns (flattened: slot_idx*15 + ch)"),
    ]

    def __init__(self, 
                 opcua_endpoint: str = "opc.tcp://0.0.0.0:4840/l2trigger/",
                 opcua_root: str = None,
                 monitoring_path: str = None,
                 opcua_users: dict = None,
                 poll_interval: float = 1.0,
                 poll_ratio: int = 10,
                 enabled_slots: Optional[List[int]] = None):
        """
        Initialize OPC UA server
        """
        self.endpoint = opcua_endpoint
        self.opcua_root = opcua_root or self._DEFAULT_ROOT
        self.monitoring_path = monitoring_path or self._DEFAULT_MONITORING_PATH
        self.opcua_users = opcua_users or {}
        self.poll_interval = poll_interval
        self.poll_ratio = poll_ratio
        
        # Hardware interface
        self.system = L2TriggerSystem(
            enabled_slots=enabled_slots
        )
        self.active_slots = sorted(list(self.system.ctdbs.keys()))
        
        # OPC UA server
        self.server = Server()
        self.namespace_idx = None
        self._vars: Dict[str, Any] = {}
        
        # Update tasks
        self._update_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()
        
        # Statistics for watchdog
        self._powered_count = 0
        self._enabled_count = 0

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

    async def _set_node_description(self, node, text: str):
        """Helper to set the Description attribute of a node"""
        await node.write_attribute(
            ua.AttributeIds.Description,
            ua.DataValue(ua.Variant(ua.LocalizedText(text), ua.VariantType.LocalizedText))
        )

    async def _create_address_space(self):
        """Create the OPC UA address space structure with full descriptions"""
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
        await self._set_node_description(root_obj, "Root object for the L2 Trigger System control and monitoring.")

        # Create Monitoring folder
        mon_node_id = f"{self.opcua_root}.{self.monitoring_path}"
        mon_obj = await root_obj.add_object(
            ua.NodeId(mon_node_id, idx),
            ua.QualifiedName(self.monitoring_path, idx)
        )
        await self._set_node_description(mon_obj, "Folder containing real-time monitoring variables and system status.")
        
        # Create monitoring variables with dotted NodeIds
        fast_vars = {
            "CrateFirmwareRevision", "CrateTimestamp", "CrateRawTimestamp",
            "BoardCurrent", "BoardCurrentSum", "BoardHasErrors",
            "ModuleCurrent", "ModuleState"
        }
        fast_interval = float(self.poll_interval * 1000)
        slow_interval = float(self.poll_interval * self.poll_ratio * 1000)

        for name, initial, vtype, description in self._MONITORING_VARS:
            var_node_id = f"{mon_node_id}.{name}"
            var = await mon_obj.add_variable(
                ua.NodeId(var_node_id, idx),
                ua.QualifiedName(name, idx),
                initial,
                varianttype=vtype
            )
            await var.set_read_only()
            await self._set_node_description(var, description)
            
            # Set MinimumSamplingInterval
            if name == "BoardSlots":
                interval = 0.0  # Constant
            elif name in fast_vars:
                interval = fast_interval
            else:
                interval = slow_interval
            
            await var.write_attribute(ua.AttributeIds.MinimumSamplingInterval, ua.DataValue(interval))
            self._vars[name] = (var, vtype)

        # Create methods on root
        await self._create_methods(root_obj, idx)
        
        logger.info(f"Address space created with root {self.opcua_root}")

    async def _create_methods(self, parent, idx):
        """Create OPC UA methods and automatically apply their Python docstrings as descriptions"""
        
        def method_node_id(name):
            return ua.NodeId(f"{self.opcua_root}.{name}", idx)

        a = self._arg  # shorthand helper
        loop = asyncio.get_running_loop()

        async def add_described_method(name, func, inputs=None, outputs=None):
            """Helper to add a method and apply its docstring as the OPC UA Description"""
            node = await parent.add_method(
                method_node_id(name),
                ua.QualifiedName(name, idx),
                func,
                inputs or [],
                outputs or [a("result", ua.VariantType.String, "Result message")]
            )
            if func.__doc__:
                await self._set_node_description(node, func.__doc__.strip())
            return node

        # Emergency Shutdown
        @uamethod
        async def emergency_shutdown(parent_node):
            """Immediately disable all power channels on all CTDB boards for safety."""
            logger.warning("Emergency shutdown called via OPC UA")
            async with self._lock:
                await loop.run_in_executor(None, self.system.emergency_shutdown)
            await self._do_poll_full(datetime.datetime.now(datetime.timezone.utc))
            return "Emergency shutdown complete"
        
        await add_described_method("EmergencyShutdown", emergency_shutdown, 
                                   outputs=[a("result", ua.VariantType.String, "Status of the shutdown operation")])
        
        # Set All Power
        @uamethod
        async def set_all_power(parent_node, enabled: bool):
            """Global control to enable or disable power for all modules in the system."""
            logger.info(f"Setting all power to {'enabled' if enabled else 'disabled'}")
            async with self._lock:
                await loop.run_in_executor(None, self.system.set_all_power, enabled)
            await self._do_poll_full(datetime.datetime.now(datetime.timezone.utc))
            return f"All power {'enabled' if enabled else 'disabled'}"
        
        await add_described_method("SetAllPower", set_all_power,
                                   inputs=[a("enabled", ua.VariantType.Boolean, "True to enable all modules, False to disable all")])
        
        # Set Module Power
        @uamethod
        async def set_module_power(parent_node, module: int, enabled: bool):
            """Enable or disable power for a specific module identified by its 1-based index."""
            slot, channel = self._module_to_slot_channel(module)
            if slot not in self.system.ctdbs:
                raise ValueError(f"Slot {slot} (module {module}) not enabled in this server")
            logger.info(f"Setting power for module {module} (Slot {slot} Ch {channel+1}) to {'enabled' if enabled else 'disabled'}")
            async with self._lock:
                await loop.run_in_executor(None, self.system.set_slot_power, slot, channel + 1, enabled)
            await self._do_poll_full(datetime.datetime.now(datetime.timezone.utc))
            return f"Module {module} (Slot {slot} Ch {channel+1}) {'enabled' if enabled else 'disabled'}"
        
        await add_described_method("SetModulePower", set_module_power,
                                   inputs=[a("module", ua.VariantType.Int32, "Module number (1-270)"),
                                           a("enabled", ua.VariantType.Boolean, "True to enable, False to disable")])

        # Set Board Current Limits
        @uamethod
        async def set_board_current_limits(parent_node, board: int, min_ma: float, max_ma: float):
            """Configure safety current limits for an entire CTDB board identified by its sequence index."""
            if not 1 <= board <= len(self.active_slots):
                raise ValueError(f"Board index {board} out of range (1-{len(self.active_slots)})")
            slot = self.active_slots[board - 1]
            logger.info(f"Setting current limits for board {board} (Slot {slot}) to {min_ma}-{max_ma} mA")
            async with self._lock:
                min_ma, max_ma = await  loop.run_in_executor(None, self.system.ctdbs[slot].set_current_limits, min_ma, max_ma)
            await self._do_poll_full(datetime.datetime.now(datetime.timezone.utc))
            return f"Board {board} (Slot {slot}) limits set to {min_ma}-{max_ma} mA"

        await add_described_method("SetBoardCurrentLimits", set_board_current_limits,
                                   inputs=[a("board", ua.VariantType.Int32, f"Sequential board index (1 to {len(self.active_slots)})"),
                                           a("min_ma", ua.VariantType.Double, "Minimum current threshold in mA"),
                                           a("max_ma", ua.VariantType.Double, "Maximum current threshold in mA")])

        # Set Module Trigger Enabled
        @uamethod
        async def set_module_trigger_enabled(parent_node, module: int, enabled: bool):
            """Enable or disable the L1 trigger contribution for a specific module."""
            slot, channel = self._module_to_slot_channel(module)
            if slot not in self.system.ctdbs:
                raise ValueError(f"Slot {slot} (module {module}) not enabled in this server")
            logger.info(f"Setting trigger enabled for module {module} (Slot {slot} Ch {channel+1}) to {'enabled' if enabled else 'disabled'}")
            async with self._lock:
                await loop.run_in_executor(None, self.system.ctdbs[slot].set_trigger_enabled, channel, enabled)
            await self._do_poll_full(datetime.datetime.now(datetime.timezone.utc))
            return f"Module {module} (Slot {slot} Trigger Ch {channel}) {'enabled' if enabled else 'disabled'}"

        await add_described_method("SetModuleTriggerEnabled", set_module_trigger_enabled,
                                   inputs=[a("module", ua.VariantType.Int32, "Module number (1-270)"),
                                           a("enabled", ua.VariantType.Boolean, "True to enable trigger, False to disable trigger")])

        # Set Module Trigger Delay
        @uamethod
        async def set_module_trigger_delay(parent_node, module: int, delay_ns: float):
            """Adjust the fine-grained trigger delay for a module to synchronize signal timing."""
            slot, channel = self._module_to_slot_channel(module)
            if slot not in self.system.ctdbs:
                raise ValueError(f"Slot {slot} (module {module}) not enabled in this server")
            logger.info(f"Setting trigger delay for module {module} (Slot {slot} Ch {channel+1}) to {delay_ns} ns")
            async with self._lock:
                await loop.run_in_executor(None, self.system.ctdbs[slot].set_trigger_delay, channel, delay_ns)
            await self._do_poll_full(datetime.datetime.now(datetime.timezone.utc))
            return f"Module {module} (Slot {slot} Trigger Ch {channel}) delay set to {delay_ns} ns"

        await add_described_method("SetModuleTriggerDelay", set_module_trigger_delay,
                                   inputs=[a("module", ua.VariantType.Int32, "Module number (1-270)"),
                                           a("delay_ns", ua.VariantType.Double, "Delay in nanoseconds (0.0 to 5.0 ns)")])

        # Set All Trigger Enabled
        @uamethod
        async def set_all_trigger_enabled(parent_node, enabled: bool):
            """Global control to enable or disable triggers for all modules."""
            logger.info(f"Setting all trigger enabled status to {'enabled' if enabled else 'disabled'}")
            async with self._lock:
                await loop.run_in_executor(None, self.system.set_all_trigger_enabled, enabled)
            await self._do_poll_full(datetime.datetime.now(datetime.timezone.utc))
            return f"All triggers {'enabled' if enabled else 'disabled'}"

        await add_described_method("SetAllTriggerEnabled", set_all_trigger_enabled,
                                   inputs=[a("enabled", ua.VariantType.Boolean, "True to enable all triggers, False to disable all")])

        # Set All Trigger Delay
        @uamethod
        async def set_all_trigger_delay(parent_node, delay_ns: float):
            """Apply a uniform trigger delay to all modules in the system."""
            logger.info(f"Setting all trigger delays to {delay_ns} ns")
            async with self._lock:
                await loop.run_in_executor(None, self.system.set_all_trigger_delay, delay_ns)
            await self._do_poll_full(datetime.datetime.now(datetime.timezone.utc))
            return f"All trigger delays set to {delay_ns} ns"

        await add_described_method("SetAllTriggerDelay", set_all_trigger_delay,
                                   inputs=[a("delay_ns", ua.VariantType.Double, "Delay in nanoseconds (0.0 to 5.0 ns) for all modules")])
        
        # Health Check
        @uamethod
        async def health_check(parent_node):
            """Run a comprehensive diagnostic of the L2 Trigger System hardware."""
            logger.info("Running health check on L2 Trigger System")
            async with self._lock:
                health = await loop.run_in_executor(None, self.system.health_check)
            return f"Health: {health['overall']}. Errors: {health['errors']}"
        
        await add_described_method("HealthCheck", health_check,
                                   outputs=[a("result", ua.VariantType.String, "Summary of system health and detected errors")])

    async def _write_fast_data(self, l2cb_status, monitoring_results, now: datetime.datetime):
        """Update OPC UA variables with high-frequency data"""
        await self._set_var("CrateFirmwareRevision", l2cb_status.firmware_version, now)
        await self._set_var("CrateTimestamp", l2cb_status.timestamp_datetime, now)
        await self._set_var("CrateRawTimestamp", l2cb_status.timestamp, now)
        await self._set_var("BoardSlots", self.active_slots, now)

        ctdb_curr = []
        ctdb_total = []
        ctdb_err = []
        ch_curr = []
        ch_state = []

        for slot in self.active_slots:
            m_data = monitoring_results.get(slot)
            ctdb = self.system.ctdbs[slot]
            c_data = ctdb._cached_config 
            
            if m_data and c_data:
                ctdb_curr.append(float(m_data.ctdb_current_ma))
                ctdb_err.append(bool(m_data.over_current_errors or m_data.under_current_errors))
                
                total_ch_curr = 0.0
                for i in range(CHANNELS_PER_SLOT):
                    ch = i + 1
                    curr = float(m_data.channel_currents_ma[i])
                    ch_curr.append(curr)
                    
                    enabled = bool(c_data.power_enabled_mask & (1 << ch))
                    if enabled:
                        total_ch_curr += curr
                    
                    # Determine state
                    has_over = bool(m_data.over_current_errors & (1 << ch))
                    has_under = bool(m_data.under_current_errors & (1 << ch))
                    
                    if has_over and has_under:
                        state = "error_both"
                    elif has_over:
                        state = "error_over_current"
                    elif has_under:
                        state = "error_under_current"
                    elif enabled:
                        state = "on"
                    else:
                        state = "off"
                    ch_state.append(state)
                
                ctdb_total.append(total_ch_curr)
            else:
                # Error case
                ctdb_curr.append(0.0)
                ctdb_total.append(0.0)
                ctdb_err.append(True)
                for _ in range(CHANNELS_PER_SLOT):
                    ch_curr.append(0.0)
                    ch_state.append("offline")

        await self._set_var("BoardCurrent", ctdb_curr, now)
        await self._set_var("BoardCurrentSum", ctdb_total, now)
        await self._set_var("BoardHasErrors", ctdb_err, now)
        await self._set_var("ModuleCurrent", ch_curr, now)
        await self._set_var("ModuleState", ch_state, now)

    async def _write_slow_data(self, config_results, trigger_results, now: datetime.datetime):
        """Update OPC UA variables with low-frequency data"""
        ctdb_fw = []
        ctdb_min = []
        ctdb_max = []
        ch_enabled = []
        trig_enabled = []
        trig_delay = []

        powered_count = 0
        enabled_count = 0

        for slot in self.active_slots:
            c_data = config_results.get(slot)
            if c_data:
                ctdb_fw.append(c_data.firmware_version)
                ctdb_min.append(float(c_data.current_limit_min_ma))
                ctdb_max.append(float(c_data.current_limit_max_ma))
                for i in range(CHANNELS_PER_SLOT):
                    enabled = bool(c_data.power_enabled_mask & (1 << (i+1)))
                    ch_enabled.append(enabled)
                    if enabled:
                        powered_count += 1
            else:
                ctdb_fw.append(0)
                ctdb_min.append(0.0)
                ctdb_max.append(0.0)
                for _ in range(CHANNELS_PER_SLOT):
                    ch_enabled.append(False)
            
            t_data = trigger_results.get(slot)
            if t_data:
                for trig in t_data:
                    trig_enabled.append(trig.enabled)
                    trig_delay.append(float(trig.delay_ns))
                    if trig.enabled:
                        enabled_count += 1
            else:
                for _ in range(CHANNELS_PER_SLOT):
                    trig_enabled.append(False)
                    trig_delay.append(0.0)

        self._powered_count = powered_count
        self._enabled_count = enabled_count

        await self._set_var("BoardFirmwareRevision", ctdb_fw, now)
        await self._set_var("BoardCurrentLimitMin", ctdb_min, now)
        await self._set_var("BoardCurrentLimitMax", ctdb_max, now)
        await self._set_var("ModulePowerEnabled", ch_enabled, now)
        await self._set_var("ModuleTriggerEnabled", trig_enabled, now)
        await self._set_var("ModuleTriggerDelay", trig_delay, now)

    async def _do_poll_fast(self, now: datetime.datetime):
        """Perform high-frequency polling and update variables"""
        loop = asyncio.get_running_loop()
        async with self._lock:
            l2cb_status, monitoring_results = await loop.run_in_executor(None, self.system.get_fast_data)
        await self._write_fast_data(l2cb_status, monitoring_results, now)

    async def _do_poll_full(self, now: datetime.datetime):
        """Perform full polling and update all variables"""
        loop = asyncio.get_running_loop()
        async with self._lock:
            l2cb_status, monitoring_results, config_results, trigger_results = await loop.run_in_executor(
                None, self.system.get_full_data
            )
        await self._write_fast_data(l2cb_status, monitoring_results, now)
        await self._write_slow_data(config_results, trigger_results, now)

    async def _update_loop(self):
        """Background task to update OPC UA values from hardware"""
        logger.info("Update loop started")
        
        cycle_count = 0
        is_low_freq_cycle = True
        next_poll = time.monotonic()
        
        while self._running:
            try:                
                logger.debug(f"Executing polling cycle %d (%s)", cycle_count+1, "full" if is_low_freq_cycle else "partial")
                now = datetime.datetime.now(datetime.timezone.utc)
                if is_low_freq_cycle:
                    await self._do_poll_full(now)
                else:
                    await self._do_poll_fast(now)                
            except Exception as e:
                logger.error(f"Error in update loop: {e}", exc_info=True)
            
            # PLL: Calculate delay to maintain constant rate
            next_poll += self.poll_interval
            cycle_count += 1
            is_low_freq_cycle = (cycle_count % self.poll_ratio == 0)

            now = time.monotonic()
            while next_poll <= now:
                # We are behind schedule, skip missed cycles
                logger.info(f"Skipping missed polling cycle %d", cycle_count+1)
                next_poll += self.poll_interval
                cycle_count += 1
                is_low_freq_cycle = True if (cycle_count % self.poll_ratio == 0) else is_low_freq_cycle

            delay = next_poll - time.monotonic()
            await asyncio.sleep(delay)
        
        logger.info("Update loop stopped")

    async def _watchdog_loop(self):
        """Background task to print system status every 180 seconds"""
        logger.info("Watchdog loop started")
        while self._running:
            try:
                await asyncio.sleep(180)
                if not self._running:
                    break
                
                logger.info(
                    "Watchdog status: %d active boards, %d powered modules, %d enabled trigger modules",
                    len(self.active_slots),
                    self._powered_count,
                    self._enabled_count
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")

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
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            
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
        
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

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
    p.add_argument("--poll-ratio", type=int, default=10, 
                   help="Number of polling cycles between full status reads")
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
        poll_ratio=args.poll_ratio,
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
