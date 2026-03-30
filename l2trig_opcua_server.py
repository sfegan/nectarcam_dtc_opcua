"""
l2trig_opcua_server.py

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
from typing import Dict, Optional, List, Any

from asyncua import Server, ua
from asyncua.common.methods import uamethod

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
    logging.basicConfig(level=level, handlers=handlers, force=True)

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
    ]

    def __init__(self, 
                 opcua_endpoint: str = "opc.tcp://0.0.0.0:4840/l2trigger/",
                 opcua_root: str = None,
                 monitoring_path: str = None,
                 poll_interval: float = 1.0,
                 timeout_us: int = 10000,
                 enabled_slots: Optional[List[int]] = None):
        """
        Initialize OPC UA server
        """
        self.endpoint = opcua_endpoint
        self.opcua_root = opcua_root or self._DEFAULT_ROOT
        self.monitoring_path = monitoring_path or self._DEFAULT_MONITORING_PATH
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

    async def init(self):
        """Initialize the OPC UA server"""
        await self.server.init()
        self.server.set_endpoint(self.endpoint)
        self.server.set_server_name("L2 Trigger System OPC UA Server")
        
        uri = "http://cta.l2trigger.hal"
        self.namespace_idx = await self.server.register_namespace(uri)
        
        # Create address space
        await self._create_address_space()
        
        logger.info(f"OPC UA Server initialized at {self.endpoint}")

    async def _create_address_space(self):
        """Create the OPC UA address space structure"""
        idx = self.namespace_idx
        
        # Build root object
        components = self.opcua_root.split(".")
        parent = self.server.nodes.objects
        for component in components:
            parent = await parent.add_object(idx, component)
        root_obj = parent

        # Create Monitoring folder
        mon_obj = await root_obj.add_object(idx, self.monitoring_path)
        
        # Create monitoring variables
        for name, initial, vtype, description in self._MONITORING_VARS:
            var = await mon_obj.add_variable(idx, name, initial, varianttype=vtype)
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
        
        # Emergency shutdown method
        @uamethod
        async def emergency_shutdown(parent_node):
            """Emergency shutdown - disable all power channels"""
            logger.warning("Emergency shutdown called via OPC UA")
            await self.system.emergency_shutdown()
            return "Emergency shutdown complete"
        
        await parent.add_method(
            idx, "EmergencyShutdown", emergency_shutdown,
            [], [ua.VariantType.String]
        )
        
        # Set all power method
        @uamethod
        async def set_all_power(parent_node, enabled: bool):
            """Enable or disable all power channels"""
            await self.system.set_all_power(enabled)
            return f"All power {'enabled' if enabled else 'disabled'}"
        
        await parent.add_method(
            idx, "SetAllPower", set_all_power,
            [ua.VariantType.Boolean], [ua.VariantType.String]
        )
        
        # Set channel power method
        @uamethod
        async def set_channel_power(parent_node, slot: int, channel: int, enabled: bool):
            """Enable or disable a specific power channel"""
            await self.system.set_slot_power(slot, channel, enabled)
            return f"Slot {slot} Ch {channel} {'enabled' if enabled else 'disabled'}"
        
        await parent.add_method(
            idx, "SetChannelPower", set_channel_power,
            [ua.VariantType.Int32, ua.VariantType.Int32, ua.VariantType.Boolean], 
            [ua.VariantType.String]
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
            idx, "SetCurrentLimits", set_current_limits,
            [ua.VariantType.Int32, ua.VariantType.Double, ua.VariantType.Double],
            [ua.VariantType.String]
        )
        
        # Health check method
        @uamethod
        async def health_check(parent_node):
            """Perform system health check"""
            health = await self.system.health_check()
            return f"Health: {health['overall']}. Errors: {health['errors']}"
        
        await parent.add_method(
            idx, "HealthCheck", health_check,
            [], [ua.VariantType.String]
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
                all_status = await self.system.get_all_status()
                
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
                
                for slot in self.active_slots:
                    status = all_status.get(slot)
                    if status:
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
                        # Placeholder for offline slot
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

                await self._set_var("ctdb_firmware", ctdb_fw, now)
                await self._set_var("ctdb_current_ma", ctdb_curr, now)
                await self._set_var("ctdb_total_channel_current_ma", ctdb_total, now)
                await self._set_var("ctdb_limit_min_ma", ctdb_min, now)
                await self._set_var("ctdb_limit_max_ma", ctdb_max, now)
                await self._set_var("ctdb_has_errors", ctdb_err, now)
                
                await self._set_var("channel_enabled", ch_enabled, now)
                await self._set_var("channel_current_ma", ch_curr, now)
                await self._set_var("channel_state", ch_state, now)
                
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
