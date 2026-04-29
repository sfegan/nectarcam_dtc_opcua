"""
l2trig_asyncua_bridge.py

OPC UA Server Bridge for L2 Trigger System
Connects to an intermediary TCP server and exposes L2 trigger hardware control via OPC UA

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
from typing import Dict, Optional, List, Any, Tuple, Set

from asyncua import Server, ua
from asyncua.common.methods import uamethod
from asyncua.server.user_managers import UserManager, User, UserRole

from l2trig_api import (
    L2TriggerSystem,
    L2CBStatus,
    CTDBMonitoringData,
    CTDBConfigData,
    VALID_SLOTS,
    CHANNELS_PER_SLOT,
    DEFAULT_PORT
)

# ============================================================================
# Constants & Conversions
# ============================================================================

# Factors from l2trig_low_level.py
CURRENT_FACTOR = 0.485
L1DELAY_FACTOR = 0.037
MCFDELAY_FACTOR = 5.0
L1DEADTIME_FACTOR = 5.0

def current_ma_to_raw(ma: float) -> int:
    return int(ma / CURRENT_FACTOR)

def delay_ns_to_raw(ns: float) -> int:
    return int(ns / L1DELAY_FACTOR)

def mcf_delay_ns_to_raw(ns: float) -> int:
    return int(ns / MCFDELAY_FACTOR)

def l1_deadtime_ns_to_raw(ns: float) -> int:
    return int(ns / L1DEADTIME_FACTOR)

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

def _configure_logging(level: str, log_file: Optional[str]) -> None:
    formatter = logging.Formatter(_LOG_FORMAT)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    handlers = [stdout_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    logging.basicConfig(level=level, handlers=handlers, force=True)
    logging.getLogger("asyncua.server.address_space").setLevel(logging.WARNING)
    logging.getLogger("asyncua.server.internal_server").setLevel(logging.WARNING)
    logging.getLogger("asyncua.server.uaprocessor").setLevel(logging.WARNING)
    logging.getLogger("asyncua.server.address_space").addFilter(_SuppressUaStatusCodeTracebacks())

logger = logging.getLogger("cta.l2trigger.bridge")

# ============================================================================
# OPC UA Server Bridge
# ============================================================================

class L2TriggerBridgeServer:
    """OPC UA Server Bridge for L2 Trigger System"""
    
    _DEFAULT_ROOT = "L2Trigger"
    _DEFAULT_MONITORING_PATH = "Monitoring"

    # (name, initial value, OPC UA variant type, description)
    _MONITORING_VARS = [
        ("device_host", "", ua.VariantType.String, "Host or IP of the TCP bridge server"),
        ("device_port", 0, ua.VariantType.Int32, "Port of the TCP bridge server"),
        ("device_state", 0, ua.VariantType.Int32, "TCP connection state: 1 if connected, 0 otherwise"),
        ("CrateFirmwareRevision", 0, ua.VariantType.UInt16, "L2CB board firmware version"),
        ("CrateUpTime", 0, ua.VariantType.UInt64, "L2CB uptime in nanoseconds"),
        ("CrateMCFEnabled", False, ua.VariantType.Boolean, "L2CB MCF enabled status"),
        ("CrateBusyGlitchFilterEnabled", False, ua.VariantType.Boolean, "L2CB busy glitch filter enabled"),
        ("CrateTIBTriggerBusyBlockEnabled", False, ua.VariantType.Boolean, "L2CB TIB trigger blocking enabled"),
        ("CrateMCFThreshold", 0, ua.VariantType.Int16, "L2CB MCF threshold (0-512)"),
        ("CrateMCFDelay", 0.0, ua.VariantType.Double, "L2CB MCF delay in ns"),
        ("CrateL1Deadtime", 0.0, ua.VariantType.Double, "L2CB L1 deadtime in ns"),
        ("CrateNumMutableModules", 0, ua.VariantType.UInt16, "Total number of modules managed by this server"),
        ("CrateNumPoweredModules", 0, ua.VariantType.UInt16, "Total number of modules currently powered on"),
        ("CrateNumTriggerEnabledModules", 0, ua.VariantType.UInt16, "Total number of modules with trigger enabled"),
        ("BoardSlots", [], ua.VariantType.Int32, "List of crate slots enabled in this server"),
        ("BoardFirmwareRevision", [], ua.VariantType.UInt16, "CTDB firmware versions"),
        ("BoardCurrent", [], ua.VariantType.Double, "CTDB board currents in mA"),
        ("BoardCurrentSum", [], ua.VariantType.Double, "Total channel current per CTDB in mA"),
        ("BoardCurrentLimitMin", [], ua.VariantType.Double, "Current limit minimum in mA"),
        ("BoardCurrentLimitMax", [], ua.VariantType.Double, "Current limit maximum in mA"),
        ("BoardHasErrors", [], ua.VariantType.Boolean, "Error status flag per board"),
        ("ModulePowerEnabled", [], ua.VariantType.Boolean, "Module power enable status (flattened)"),
        ("ModuleCurrent", [], ua.VariantType.Double, "Channel current readings in mA (flattened)"),
        ("ModuleState", [], ua.VariantType.String, "Channel state strings (flattened)"),
        ("ModuleTriggerEnabled", [], ua.VariantType.Boolean, "Trigger enabled status (flattened)"),
        ("ModuleTriggerDelay", [], ua.VariantType.Double, "Trigger delay in ns (flattened)"),
        ("ModuleIsMutable", [], ua.VariantType.Boolean, "Flag whether module state can be modified (flattened)"),
    ]

    def __init__(self, 
                 device_host: str = "127.0.0.1",
                 device_port: int = DEFAULT_PORT,
                 variable_lifetime: float = 10.0,
                 opcua_endpoint: str = "opc.tcp://0.0.0.0:4840/l2trig/",
                 opcua_namespace: str = "http://cta-observatory.org/nectarcam/l2trig/",
                 opcua_root: str = "l2trig",
                 monitoring_path: str = None,
                 opcua_users: dict = None,
                 poll_interval: float = 1.0,
                 poll_ratio: int = 10,
                 reconnection_backoff_interval: float = 30.0,
                 enabled_slots: Optional[List[int]] = None,
                 immutable_channels: Optional[Set[Tuple[int, int]]] = None):
        
        self.device_host = device_host
        self.device_port = device_port
        self.variable_lifetime = variable_lifetime
        self.reconnection_backoff_interval = reconnection_backoff_interval
        self.endpoint = opcua_endpoint
        self.namespace_uri = opcua_namespace
        self.opcua_root = opcua_root or self._DEFAULT_ROOT
        self.monitoring_path = monitoring_path or self._DEFAULT_MONITORING_PATH
        self.opcua_users = opcua_users or {}
        self.poll_interval = poll_interval
        self.poll_ratio = poll_ratio
        self.immutable_channels = immutable_channels or set()
        
        self.active_slots = sorted(enabled_slots) if enabled_slots else sorted(VALID_SLOTS)
        self.nmodules = sum(1 for slot in self.active_slots 
                            for ch in range(1, CHANNELS_PER_SLOT + 1) 
                            if (slot, ch) not in self.immutable_channels)

        # TCP API client
        self.system = L2TriggerSystem(host=device_host, port=device_port)
        
        # Pre-calculate ModuleIsMutable vector
        self._module_is_mutable = []
        for slot in self.active_slots:
            for ch in range(1, CHANNELS_PER_SLOT + 1):
                self._module_is_mutable.append((slot, ch) not in self.immutable_channels)

        # Configure TCP server configuration mask
        self._immutable_masks = {}
        for slot, ch in self.immutable_channels:
            if slot not in self._immutable_masks:
                self._immutable_masks[slot] = 0
            self._immutable_masks[slot] |= (1 << ch)

        # OPC UA server
        self.server = Server()
        self.namespace_idx = None
        self._vars: Dict[str, Tuple[Any, ua.VariantType]] = {}
        
        # Connection tracking
        self._connected = False
        self._last_contact: Optional[float] = None
        self._next_reconnect: float = 0.0
        self._reconnect_delay: float = 1.0
        
        # Tasks
        self._update_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()
        self._need_slow_poll = False
        
        # Stats
        self._powered_count = 0
        self._enabled_count = 0

    def _module_to_slot_channel(self, module: int) -> Tuple[int, int]:
        max_module = len(self.active_slots) * CHANNELS_PER_SLOT
        if not 1 <= module <= max_module:
            raise ValueError(f"Module number {module} out of range (1-{max_module})")
        slot_idx = (module - 1) // CHANNELS_PER_SLOT
        slot = self.active_slots[slot_idx]
        channel = (module - 1) % CHANNELS_PER_SLOT + 1
        return slot, channel

    def _get_status_code(self) -> ua.StatusCode:
        now = time.monotonic()
        if self._connected:
            return ua.StatusCode(ua.StatusCodes.Good)
        if self._last_contact is None:
            return ua.StatusCode(ua.StatusCodes.BadWaitingForInitialData)
        if now - self._last_contact < self.variable_lifetime:
            return ua.StatusCode(ua.StatusCodes.UncertainLastUsableValue)
        return ua.StatusCode(ua.StatusCodes.BadNoCommunication)

    async def _ensure_connected(self):
        """Ensure TCP connection is established and configured"""
        if self.system.writer and not self.system.writer.transport.is_closing():
            return True
            
        now = time.monotonic()
        if now < self._next_reconnect:
            return False
            
        try:
            await self.system.connect()
            await self.system.set_config(self.active_slots, self._immutable_masks)
            logger.info("TCP server connected and configured")
            self._connected = True
            self._need_slow_poll = True
            self._reconnect_delay = 1.0
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to TCP server: {e}")
            self._connected = False
            self._next_reconnect = now + self._reconnect_delay
            self._reconnect_delay = min(self._reconnect_delay * 2, self.reconnection_backoff_interval)
            return False

    async def init(self):
        if self.opcua_users:
            creds = self.opcua_users
            class _Manager(UserManager):
                async def get_user(self, iserver, username=None, password=None, certificate=None):
                    return (User(role=UserRole.User) if creds.get(username) == password else None)
            self.server.set_user_manager(_Manager())

        await self.server.init(shelf_file=None)
        self.server.set_endpoint(self.endpoint)
        self.server.set_server_name("L2 Trigger System OPC UA Bridge")
        
        if self.opcua_users:
            self.server.set_security_IDs(["Anonymous", "Username"])

        self.namespace_idx = await self.server.register_namespace(self.namespace_uri)

        # Initial connection attempt
        await self._ensure_connected()
        
        await self._create_address_space()
        
        now = datetime.datetime.now(datetime.timezone.utc)
        await self._set_var("device_host", self.device_host, now)
        await self._set_var("device_port", self.device_port, now)
        await self._set_var("BoardSlots", self.active_slots, now)
        await self._set_var("CrateNumMutableModules", self.nmodules, now)
        await self._set_var("ModuleIsMutable", self._module_is_mutable, now)

        logger.info(f"OPC UA Bridge initialized at {self.endpoint}")

    @staticmethod
    def _arg(name: str, variant_type: ua.VariantType, description: str = "") -> ua.Argument:
        arg = ua.Argument()
        arg.Name = name
        arg.DataType = ua.NodeId(int(variant_type))
        arg.ValueRank = -1
        arg.ArrayDimensions = []
        arg.Description = ua.LocalizedText(description or name)
        return arg

    async def _set_node_description(self, node, text: str):
        await node.write_attribute(
            ua.AttributeIds.Description,
            ua.DataValue(ua.Variant(ua.LocalizedText(text), ua.VariantType.LocalizedText))
        )

    async def _create_address_space(self):
        idx = self.namespace_idx
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
        await self._set_node_description(root_obj, "Root object for the L2 Trigger System bridge.")

        mon_node_id = f"{self.opcua_root}.{self.monitoring_path}"
        mon_obj = await root_obj.add_object(
            ua.NodeId(mon_node_id, idx),
            ua.QualifiedName(self.monitoring_path, idx)
        )
        await self._set_node_description(mon_obj, "Folder containing real-time monitoring.")
        
        fast_vars = {
            "device_state", "CrateFirmwareRevision", "CrateUpTime", 
            "CrateMCFEnabled", "CrateBusyGlitchFilterEnabled", "CrateTIBTriggerBusyBlockEnabled",
            "CrateMCFThreshold", "CrateMCFDelay", "CrateL1Deadtime",
            "CrateNumPoweredModules", "BoardCurrent", "BoardCurrentSum", "BoardHasErrors",
            "ModuleCurrent", "ModuleState", "ModulePowerEnabled"
        }
        fast_interval = float(self.poll_interval * 1000)
        slow_interval = float(self.poll_interval * self.poll_ratio * 1000)

        for name, initial, vtype, description in self._MONITORING_VARS:
            var_node_id = f"{mon_node_id}.{name}"
            
            # Determine ValueRank and ArrayDimensions
            value_rank = ua.ValueRank.Scalar
            array_dims = []
            
            if isinstance(initial, list):
                value_rank = ua.ValueRank.OneDimension
                if "Module" in name:
                    array_dims = [len(self.active_slots) * CHANNELS_PER_SLOT]
                elif "Board" in name or name == "BoardSlots":
                    array_dims = [len(self.active_slots)]
            
            var = await mon_obj.add_variable(
                ua.NodeId(var_node_id, idx),
                ua.QualifiedName(name, idx),
                initial,
                varianttype=vtype
            )
            await var.set_read_only()
            await self._set_node_description(var, description)
            
            # Set ValueRank and ArrayDimensions
            await var.write_attribute(ua.AttributeIds.ValueRank, ua.DataValue(ua.Variant(value_rank, ua.VariantType.Int32)))
            if array_dims:
                await var.write_attribute(ua.AttributeIds.ArrayDimensions, ua.DataValue(ua.Variant(array_dims, ua.VariantType.UInt32)))

            interval = fast_interval if name in fast_vars else (0.0 if name in ("device_host", "device_port", "BoardSlots", "ModuleIsMutable") else slow_interval)
            await var.write_attribute(ua.AttributeIds.MinimumSamplingInterval, ua.DataValue(interval))
            self._vars[name] = (var, vtype)

        await self._create_methods(root_obj, idx)

    async def _create_methods(self, parent, idx):
        def method_node_id(name): return ua.NodeId(f"{self.opcua_root}.{name}", idx)
        a = self._arg

        async def add_described_method(name, func, inputs=None, outputs=None):
            node = await parent.add_method(method_node_id(name), ua.QualifiedName(name, idx), func, inputs or [], 
                                          outputs or [a("result", ua.VariantType.String, "Result message")])
            if func.__doc__: await self._set_node_description(node, func.__doc__.strip())
            return node

        @uamethod
        async def emergency_shutdown(parent_node):
            """Immediately disable all power channels."""
            logger.warning("Emergency shutdown called")
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.emergency_shutdown()
            return "OK: Emergency shutdown complete"
        await add_described_method("EmergencyShutdown", emergency_shutdown)

        @uamethod
        async def set_all_power_enabled(parent_node, enabled: bool):
            """Global control to enable or disable power for all modules using a ramp."""
            logger.info(f"Setting all power to {enabled}")
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.ramp_power(enabled)
            return f"OK: All power {'enable' if enabled else 'disable'} ramp triggered"
        await add_described_method("SetAllPowerEnabled", set_all_power_enabled, inputs=[a("enabled", ua.VariantType.Boolean)])

        @uamethod
        async def set_module_power(parent_node, module: int, enabled: bool):
            """Enable or disable power for a specific module."""
            try: slot, channel = self._module_to_slot_channel(module)
            except ValueError as e: return f"ERROR: {e}"
            if (slot, channel) in self.immutable_channels: return f"ERROR: Module {module} is immutable"
            logger.info(f"Setting power for module {module} to {enabled}")
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_channel_power_enabled(slot, channel, enabled)
            return f"OK: Module {module} {'enabled' if enabled else 'disabled'}"
        await add_described_method("SetModulePowerEnabled", set_module_power, 
                                   inputs=[a("module", ua.VariantType.Int32), a("enabled", ua.VariantType.Boolean)])

        @uamethod
        async def set_board_current_limits(parent_node, board: int, min_ma: float, max_ma: float):
            """Configure current limits for an entire CTDB board."""
            if not 1 <= board <= len(self.active_slots): return f"ERROR: Board index {board} out of range"
            slot = self.active_slots[board - 1]
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_ctdb_limits(slot, current_ma_to_raw(min_ma), current_ma_to_raw(max_ma))
                self._need_slow_poll = True
            return f"OK: Board {board} limits set"
        await add_described_method("SetBoardCurrentLimits", set_board_current_limits,
                                   inputs=[a("board", ua.VariantType.Int32), a("min_ma", ua.VariantType.Double), a("max_ma", ua.VariantType.Double)])

        @uamethod
        async def set_module_trigger_enabled(parent_node, module: int, enabled: bool):
            """Enable or disable trigger for a specific module."""
            try: slot, channel = self._module_to_slot_channel(module)
            except ValueError as e: return f"ERROR: {e}"
            if (slot, channel) in self.immutable_channels: return f"ERROR: Module {module} is immutable"
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_channel_trigger_enabled(slot, channel, enabled)
                self._need_slow_poll = True
            return f"OK: Module {module} trigger {'enabled' if enabled else 'disabled'}"
        await add_described_method("SetModuleTriggerEnabled", set_module_trigger_enabled,
                                   inputs=[a("module", ua.VariantType.Int32), a("enabled", ua.VariantType.Boolean)])

        @uamethod
        async def set_module_trigger_delay(parent_node, module: int, delay_ns: float):
            """Set trigger delay for a module."""
            try: slot, channel = self._module_to_slot_channel(module)
            except ValueError as e: return f"ERROR: {e}"
            if (slot, channel) in self.immutable_channels: return f"ERROR: Module {module} is immutable"
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_channel_trigger_delay(slot, channel, delay_ns_to_raw(delay_ns))
                self._need_slow_poll = True
            return f"OK: Module {module} delay set"
        await add_described_method("SetModuleTriggerDelay", set_module_trigger_delay,
                                   inputs=[a("module", ua.VariantType.Int32), a("delay_ns", ua.VariantType.Double)])

        @uamethod
        async def set_all_trigger_enabled(parent_node, enabled: bool):
            """Enable or disable triggers for all modules."""
            async with self._lock:
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_all_trigger_enabled(enabled)
                self._need_slow_poll = True
            return "OK: All triggers updated"
        await add_described_method("SetAllTriggerEnabled", set_all_trigger_enabled, inputs=[a("enabled", ua.VariantType.Boolean)])

        @uamethod
        async def set_all_trigger_delay(parent_node, delay_ns: float):
            """Apply uniform trigger delay to all modules."""
            raw = delay_ns_to_raw(delay_ns)
            async with self._lock:
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_all_trigger_delay(raw)
                self._need_slow_poll = True
            return "OK: All delays updated"
        await add_described_method("SetAllTriggerDelay", set_all_trigger_delay, inputs=[a("delay_ns", ua.VariantType.Double)])

        @uamethod
        async def set_mcf_enabled(parent_node, enabled: bool):
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_mcf_enabled(enabled)
            return "OK"
        await add_described_method("SetMCFEnabled", set_mcf_enabled, inputs=[a("enabled", ua.VariantType.Boolean)])

        @uamethod
        async def set_busy_glitch_filter_enabled(parent_node, enabled: bool):
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_glitch_filter_enabled(enabled)
            return "OK"
        await add_described_method("SetBusyGlitchFilterEnabled", set_busy_glitch_filter_enabled, inputs=[a("enabled", ua.VariantType.Boolean)])

        @uamethod
        async def set_tib_trigger_busy_block_enabled(parent_node, enabled: bool):
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_tib_block_enabled(enabled)
            return "OK"
        await add_described_method("SetTIBTriggerBusyBlockEnabled", set_tib_trigger_busy_block_enabled, inputs=[a("enabled", ua.VariantType.Boolean)])

        @uamethod
        async def set_mcf_delay(parent_node, delay: float):
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_mcf_delay(mcf_delay_ns_to_raw(delay))
            return "OK"
        await add_described_method("SetMCFDelay", set_mcf_delay, inputs=[a("delay", ua.VariantType.Double)])

        @uamethod
        async def set_mcf_threshold(parent_node, threshold: int):
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_mcf_threshold(threshold)
            return "OK"
        await add_described_method("SetMCFThreshold", set_mcf_threshold, inputs=[a("threshold", ua.VariantType.Int16)])

        @uamethod
        async def set_l1_deadtime(parent_node, deadtime: float):
            async with self._lock: 
                if not await self._ensure_connected(): return "ERROR: Device not connected"
                await self.system.set_l1_deadtime(l1_deadtime_ns_to_raw(deadtime))
            return "OK"
        await add_described_method("SetL1Deadtime", set_l1_deadtime, inputs=[a("deadtime", ua.VariantType.Double)])

    async def _write_fast_data(self, l2cb: L2CBStatus, monitoring: Dict[int, CTDBMonitoringData], now: datetime.datetime):
        sc = self._get_status_code()
        # device_state always has Good status as the server is authoritative
        await self._set_var("device_state", 1 if self._connected else 0, now, ua.StatusCode(ua.StatusCodes.Good))
        await self._set_var("CrateFirmwareRevision", l2cb.firmware_version, now, sc)
        await self._set_var("CrateUpTime", l2cb.uptime, now, sc)
        await self._set_var("CrateMCFEnabled", l2cb.mcf_enabled, now, sc)
        await self._set_var("CrateBusyGlitchFilterEnabled", l2cb.busy_glitch_filter_enabled, now, sc)
        await self._set_var("CrateTIBTriggerBusyBlockEnabled", l2cb.tib_trigger_busy_block_enabled, now, sc)
        await self._set_var("CrateMCFThreshold", l2cb.mcf_threshold, now, sc)
        await self._set_var("CrateMCFDelay", l2cb.mcf_delay_ns, now, sc)
        await self._set_var("CrateL1Deadtime", l2cb.l1_deadtime_ns, now, sc)

        bc, bcs, bhe = [], [], []
        mc, ms, mpe = [], [], []
        powered_count = 0

        for slot in self.active_slots:
            m = monitoring.get(slot)
            if m:
                bc.append(m.ctdb_current_ma)
                bhe.append(bool(m.over_current_errors or m.under_current_errors))
                slot_sum = 0.0
                for i in range(CHANNELS_PER_SLOT):
                    ch = i + 1
                    curr = m.channel_currents_ma[i]
                    mc.append(curr)
                    en = bool(m.power_enabled_mask & (1 << ch))
                    mpe.append(en)
                    if en: slot_sum += curr
                    
                    ov, un = bool(m.over_current_errors & (1 << ch)), bool(m.under_current_errors & (1 << ch))
                    if ov and un: state = "error_both"
                    elif ov: state = "error_over_current"
                    elif un: state = "error_under_current"
                    elif en: state = "on"; powered_count += 1
                    else: state = "off"
                    ms.append(state)
                bcs.append(slot_sum)
            else:
                bc.append(0.0); bcs.append(0.0); bhe.append(True)
                for _ in range(CHANNELS_PER_SLOT): mc.append(0.0); mpe.append(False); ms.append("offline")
        
        self._powered_count = powered_count
        await self._set_var("CrateNumPoweredModules", powered_count, now, sc)
        await self._set_var("BoardCurrent", bc, now, sc)
        await self._set_var("BoardCurrentSum", bcs, now, sc)
        await self._set_var("BoardHasErrors", bhe, now, sc)
        await self._set_var("ModuleCurrent", mc, now, sc)
        await self._set_var("ModuleState", ms, now, sc)
        await self._set_var("ModulePowerEnabled", mpe, now, sc)

    async def _write_slow_data(self, configs: Dict[int, CTDBConfigData], now: datetime.datetime):
        sc = self._get_status_code()
        bf, bmin, bmax = [], [], []
        te, td = [], []
        enabled_count = 0
        for slot in self.active_slots:
            c = configs.get(slot)
            if c:
                bf.append(c.firmware_version); bmin.append(c.current_limit_min_ma); bmax.append(c.current_limit_max_ma)
                for i in range(CHANNELS_PER_SLOT):
                    en = bool(c.trig_enabled_mask & (1 << (i + 1)))
                    te.append(en)
                    td.append(c.trig_delays_ns[i])
                    if en: enabled_count += 1
            else:
                bf.append(0); bmin.append(0.0); bmax.append(0.0)
                for _ in range(CHANNELS_PER_SLOT): te.append(False); td.append(0.0)
        
        self._enabled_count = enabled_count
        await self._set_var("CrateNumTriggerEnabledModules", enabled_count, now, sc)
        await self._set_var("BoardFirmwareRevision", bf, now, sc)
        await self._set_var("BoardCurrentLimitMin", bmin, now, sc)
        await self._set_var("BoardCurrentLimitMax", bmax, now, sc)
        await self._set_var("ModuleTriggerEnabled", te, now, sc)
        await self._set_var("ModuleTriggerDelay", td, now, sc)

    async def _do_poll_fast(self, now: datetime.datetime):
        """Perform high-frequency polling and update variables"""
        if not await self._ensure_connected():
            await self._write_fast_data(L2CBStatus(0,0,False,False,False,0,0,0), {}, now)
            await self._write_slow_data({}, now)
            return

        try:
            l2cb = await self.system.get_l2cb_status()
            mon = await self.system.get_all_monitoring()
            self._connected = True
            self._last_contact = time.monotonic()
            await self._write_fast_data(l2cb, mon, now)
        except Exception as e:
            logger.error(f"Fast poll error: {e}")
            self._connected = False
            await self._write_fast_data(L2CBStatus(0,0,False,False,False,0,0,0), {}, now)
            await self._write_slow_data({}, now)

    async def _do_poll_slow(self, now: datetime.datetime):
        """Perform slow polling of configurations and update variables"""
        if not await self._ensure_connected():
            await self._write_slow_data({}, now)
            return

        try:
            configs = {}
            for slot in self.active_slots:
                configs[slot] = await self.system.get_ctdb_config(slot)
            await self._write_slow_data(configs, now)
        except Exception as e:
            logger.error(f"Slow poll error: {e}")
            await self._write_slow_data({}, now)

    async def _update_loop(self):
        logger.info("Update loop started")
        cycle = 0
        next_poll = time.monotonic()
        while self._running:
            try:
                now_ts = datetime.datetime.now(datetime.timezone.utc)
                async with self._lock:
                    await self._do_poll_fast(now_ts)
                    if self._need_slow_poll or cycle % self.poll_ratio == 0:
                        await self._do_poll_slow(now_ts)
                        self._need_slow_poll = False
            except Exception as e:
                logger.error(f"Error in update loop: {e}", exc_info=True)
            
            cycle += 1
            next_poll += self.poll_interval
            await asyncio.sleep(max(0, next_poll - time.monotonic()))

    async def _watchdog_loop(self):
        while self._running:
            await asyncio.sleep(180)
            logger.info("Status: Connected=%s, Powered=%d, Trigger=%d", self._connected, self._powered_count, self._enabled_count)

    async def _set_var(self, name: str, value: Any, timestamp: datetime.datetime, status: Optional[ua.StatusCode] = None):
        if name not in self._vars: return
        node, vtype = self._vars[name]
        try:
            kwargs = {
                "Value": ua.Variant(value, vtype),
                "SourceTimestamp": timestamp
            }
            if status is not None:
                kwargs["StatusCode_"] = status
            
            dv = ua.DataValue(**kwargs)
            await node.write_value(dv)
        except Exception as e: logger.error(f"Update {name} failed: {e}")

    async def start(self):
        await self.init()
        async with self.server:
            self._running = True
            self._update_task = asyncio.create_task(self._update_loop())
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            loop = asyncio.get_running_loop()
            shutdown = loop.create_future()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, shutdown.set_result, sig)
            await shutdown
            await self.stop()

    async def stop(self):
        self._running = False
        for t in [self._update_task, self._watchdog_task]:
            if t: t.cancel()
        await self.system.disconnect()

def _parse_immutable_channels(inactive_str: str) -> Set[Tuple[int, int]]:
    """Parse comma-separated list of inactive slot/channel pairs (e.g. S1C1,S18C15)"""
    import re
    inactive = set()
    if not inactive_str:
        return inactive
    parts = inactive_str.split(",")
    for part in parts:
        part = part.strip().upper()
        if not part:
            continue
        m = re.match(r"S(\d+)C(\d+)", part)
        if m:
            slot = int(m.group(1))
            chan = int(m.group(2))
            inactive.add((slot, chan))
        else:
            logger.warning(f"Invalid inactive channel format: {part}")
    return inactive

def main():
    p = argparse.ArgumentParser(
        description="L2 Trigger System OPC UA Bridge",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("--device-host", default="127.0.0.1", help="Host or IP of the TCP bridge server")
    p.add_argument("--device-port", type=int, default=DEFAULT_PORT, help="Port of the TCP bridge server")
    p.add_argument("--variable-lifetime", type=float, default=10.0, help="Lifetime of variables after connection loss (seconds)")
    p.add_argument("--opcua-endpoint", default="opc.tcp://0.0.0.0:4840/l2trig/",
                   help="OPC UA server endpoint URL")
    p.add_argument("--opcua-namespace", default="http://cta-observatory.org/nectarcam/l2trig/",
                   help="OPC UA namespace URI")
    p.add_argument("--opcua-root", default="l2trig", metavar="PATH",
                   help="Root object path in the OPC UA address space (default: l2trig). Dot-separated components create nested browse levels.")
    p.add_argument("--monitoring-path", default="Monitoring",
                   help="Name of the monitoring object under the root")
    p.add_argument("--opcua-user", default=None, metavar="USER:PASS",
                   help="OPC UA username:password (disables anonymous access)")
    p.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds")
    p.add_argument("--poll-ratio", type=int, default=10, help="Ratio of fast to slow polling cycles")
    p.add_argument("--reconnection-backoff-interval", type=float, default=30.0, help="Maximum delay between reconnection attempts (seconds)")
    p.add_argument("--timeout-us", type=int, default=10000, help="Hardware timeout in microseconds (passed to TCP server)")
    p.add_argument("--slots", help="Comma-separated list of slots to enable; if omitted, all slots are enabled")
    p.add_argument("--immutable-channels", default="S21C11,S21C12,S21C13,S21C14,S21C15",
                   help="Comma-separated list of inactive slot/channel pairs whose state should not be modified (e.g. S1C1,S18C15)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Set the logging level")
    p.add_argument("--log-file", help="Optional log file path")
    args = p.parse_args()
    _configure_logging(args.log_level, args.log_file)
    
    opcua_users = {}
    if args.opcua_user:
        if ":" not in args.opcua_user:
            logger.error("Invalid --opcua-user (expected USER:PASS): %r", args.opcua_user)
            return 1
        user, _, pw = args.opcua_user.partition(":")
        opcua_users[user] = pw

    enabled_slots = None
    if args.slots:
        try:
            enabled_slots = [int(s.strip()) for s in args.slots.split(",")]
        except ValueError:
            logger.error(f"Invalid slots argument: {args.slots}")
            return 1

    immutable_channels = _parse_immutable_channels(args.immutable_channels)

    # Validate inactive channels
    if enabled_slots is not None:
        active_slots_set = set(enabled_slots)
    else:
        active_slots_set = set(VALID_SLOTS)

    invalid_inactive = [(s, c) for (s, c) in immutable_channels 
                        if s not in active_slots_set or not (1 <= c <= CHANNELS_PER_SLOT)]

    if invalid_inactive:
        logger.info(f"Ignoring invalid inactive channels: {invalid_inactive}")
        immutable_channels = immutable_channels - set(invalid_inactive)
    
    server = L2TriggerBridgeServer(
        device_host=args.device_host,
        device_port=args.device_port,
        variable_lifetime=args.variable_lifetime,
        opcua_endpoint=args.opcua_endpoint,
        opcua_namespace=args.opcua_namespace,
        opcua_root=args.opcua_root,
        monitoring_path=args.monitoring_path,
        opcua_users=opcua_users,
        poll_interval=args.poll_interval,
        poll_ratio=args.poll_ratio,
        reconnection_backoff_interval=args.reconnection_backoff_interval,
        enabled_slots=enabled_slots,
        immutable_channels=immutable_channels
    )
    asyncio.run(server.start())

if __name__ == "__main__":
    main()
