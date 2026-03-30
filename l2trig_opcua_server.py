"""
l2trig_opcua_server.py

OPC UA Server for L2 Trigger System
Exposes L2 trigger hardware control via OPC UA protocol
"""

import asyncio
import logging
from typing import Dict, Optional, List
from datetime import datetime

from asyncua import Server, ua
from asyncua.common.methods import uamethod

from l2trig_api import (
    L2TriggerSystem,
    CTDBController,
    CTDBStatus,
    PowerChannel,
    ChannelState,
    VALID_SLOTS,
    CHANNELS_PER_SLOT
)
import l2trig_low_level as hal

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# OPC UA Node References
# ============================================================================

class NodeRefs:
    """Storage for OPC UA node references"""
    def __init__(self):
        self.slots: Dict[int, 'SlotNodes'] = {}
        self.l2cb_nodes: Optional['L2CBNodes'] = None


class SlotNodes:
    """Node references for a single CTDB slot"""
    def __init__(self):
        self.object_node = None
        self.firmware_version = None
        self.ctdb_current = None
        self.total_current = None
        self.current_min = None
        self.current_max = None
        self.has_errors = None
        
        # Channel nodes
        self.channels: Dict[int, 'ChannelNodes'] = {}


class ChannelNodes:
    """Node references for a single power channel"""
    def __init__(self):
        self.enabled = None
        self.current = None
        self.state = None


class L2CBNodes:
    """Node references for L2CB board"""
    def __init__(self):
        self.object_node = None
        self.firmware_version = None
        self.timestamp = None


# ============================================================================
# OPC UA Server
# ============================================================================

class L2TriggerOPCUAServer:
    """OPC UA Server for L2 Trigger System"""
    
    def __init__(self, endpoint: str = "opc.tcp://0.0.0.0:4840/l2trigger/",
                 update_interval: float = 1.0,
                 timeout_us: int = 10000,
                 enabled_slots: Optional[List[int]] = None):
        """
        Initialize OPC UA server
        
        Args:
            endpoint: OPC UA endpoint URL
            update_interval: How often to update values (seconds)
            timeout_us: Hardware timeout in microseconds
            enabled_slots: List of slots to expose (default: all)
        """
        self.endpoint = endpoint
        self.update_interval = update_interval
        
        # Hardware interface
        self.system = L2TriggerSystem(
            timeout_us=timeout_us,
            enabled_slots=enabled_slots
        )
        
        # OPC UA server
        self.server = Server()
        self.namespace_idx = None
        self.node_refs = NodeRefs()
        
        # Update task
        self._update_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def init(self):
        """Initialize the OPC UA server"""
        await self.server.init()
        self.server.set_endpoint(self.endpoint)
        
        # Set server properties
        self.server.set_server_name("L2 Trigger System OPC UA Server")
        
        # Setup security (optional - can be enabled for production)
        # self.server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
        
        # Register namespace
        uri = "http://cta.l2trigger.hal"
        self.namespace_idx = await self.server.register_namespace(uri)
        
        # Create address space
        await self._create_address_space()
        
        logger.info(f"OPC UA Server initialized at {self.endpoint}")
    
    async def _create_address_space(self):
        """Create the OPC UA address space structure"""
        idx = self.namespace_idx
        objects = self.server.get_objects_node()
        
        # Create L2 Trigger System root folder
        l2trig_folder = await objects.add_folder(idx, "L2TriggerSystem")
        
        # Create L2CB node
        await self._create_l2cb_nodes(l2trig_folder, idx)
        
        # Create CTDB folder
        ctdb_folder = await l2trig_folder.add_folder(idx, "CTDB_Boards")
        
        # Create node for each slot
        for slot in self.system.ctdbs.keys():
            await self._create_slot_nodes(ctdb_folder, slot, idx)
        
        # Create methods
        await self._create_methods(l2trig_folder, idx)
        
        logger.info("Address space created")
    
    async def _create_l2cb_nodes(self, parent, idx):
        """Create nodes for L2CB board"""
        l2cb_obj = await parent.add_object(idx, "L2CB_Controller")
        
        nodes = L2CBNodes()
        nodes.object_node = l2cb_obj
        
        nodes.firmware_version = await l2cb_obj.add_variable(
            idx, "FirmwareVersion", 0, varianttype=ua.VariantType.UInt16
        )
        
        nodes.timestamp = await l2cb_obj.add_variable(
            idx, "Timestamp", 0, varianttype=ua.VariantType.UInt64
        )
        
        self.node_refs.l2cb_nodes = nodes
    
    async def _create_slot_nodes(self, parent, slot: int, idx):
        """Create nodes for a single CTDB slot"""
        slot_obj = await parent.add_object(idx, f"Slot_{slot:02d}")
        
        nodes = SlotNodes()
        nodes.object_node = slot_obj
        
        # Slot-level variables
        nodes.firmware_version = await slot_obj.add_variable(
            idx, "FirmwareVersion", 0, varianttype=ua.VariantType.UInt16
        )
        
        nodes.ctdb_current = await slot_obj.add_variable(
            idx, "CTDB_Current_mA", 0.0, varianttype=ua.VariantType.Float
        )
        
        nodes.total_current = await slot_obj.add_variable(
            idx, "TotalChannelCurrent_mA", 0.0, varianttype=ua.VariantType.Float
        )
        
        nodes.current_min = await slot_obj.add_variable(
            idx, "CurrentLimit_Min_mA", 0.0, varianttype=ua.VariantType.Float
        )
        await nodes.current_min.set_writable()
        
        nodes.current_max = await slot_obj.add_variable(
            idx, "CurrentLimit_Max_mA", 0.0, varianttype=ua.VariantType.Float
        )
        await nodes.current_max.set_writable()
        
        nodes.has_errors = await slot_obj.add_variable(
            idx, "HasErrors", False, varianttype=ua.VariantType.Boolean
        )
        
        # Create channel nodes
        channels_folder = await slot_obj.add_folder(idx, "Channels")
        
        for ch in range(1, CHANNELS_PER_SLOT + 1):
            ch_nodes = await self._create_channel_nodes(channels_folder, ch, idx)
            nodes.channels[ch] = ch_nodes
        
        self.node_refs.slots[slot] = nodes
    
    async def _create_channel_nodes(self, parent, channel: int, idx) -> ChannelNodes:
        """Create nodes for a single power channel"""
        ch_obj = await parent.add_object(idx, f"Channel_{channel:02d}")
        
        nodes = ChannelNodes()
        
        # Power enable (writable)
        nodes.enabled = await ch_obj.add_variable(
            idx, "Enabled", False, varianttype=ua.VariantType.Boolean
        )
        await nodes.enabled.set_writable()
        
        # Current reading (read-only)
        nodes.current = await ch_obj.add_variable(
            idx, "Current_mA", 0.0, varianttype=ua.VariantType.Float
        )
        
        # State (read-only)
        nodes.state = await ch_obj.add_variable(
            idx, "State", "off", varianttype=ua.VariantType.String
        )
        
        return nodes
    
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
        
        # Health check method
        @uamethod
        async def health_check(parent_node):
            """Perform system health check"""
            health = await self.system.health_check()
            return health['overall']
        
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
                await self._update_l2cb_status()
                
                # Update all CTDB statuses
                all_status = await self.system.get_all_status()
                
                for slot, status in all_status.items():
                    await self._update_slot_status(slot, status)
                
            except Exception as e:
                logger.error(f"Error in update loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.update_interval)
        
        logger.info("Update loop stopped")
    
    async def _update_l2cb_status(self):
        """Update L2CB node values"""
        try:
            status = await self.system.get_l2cb_status()
            nodes = self.node_refs.l2cb_nodes
            
            await nodes.firmware_version.write_value(status.firmware_version)
            await nodes.timestamp.write_value(status.timestamp)
            
        except Exception as e:
            logger.error(f"Error updating L2CB status: {e}")
    
    async def _update_slot_status(self, slot: int, status: CTDBStatus):
        """Update OPC UA nodes for a slot"""
        try:
            nodes = self.node_refs.slots[slot]
            
            # Update slot-level values
            await nodes.firmware_version.write_value(status.firmware_version)
            await nodes.ctdb_current.write_value(status.ctdb_current_ma)
            await nodes.total_current.write_value(status.total_current_ma)
            await nodes.current_min.write_value(status.current_limit_min_ma)
            await nodes.current_max.write_value(status.current_limit_max_ma)
            await nodes.has_errors.write_value(status.has_errors)
            
            # Update channel values
            for ch in status.power_channels:
                ch_nodes = nodes.channels[ch.channel]
                await ch_nodes.enabled.write_value(ch.enabled)
                await ch_nodes.current.write_value(ch.current_ma)
                await ch_nodes.state.write_value(ch.state.value)
            
        except Exception as e:
            logger.error(f"Error updating slot {slot} status: {e}")
    
    async def _handle_write_callbacks(self):
        """Monitor writable nodes and handle changes"""
        # This would be implemented with DataChange subscriptions
        # For now, we'll use a simpler polling approach
        pass
    
    async def start(self):
        """Start the OPC UA server"""
        await self.init()
        
        async with self.server:
            logger.info("OPC UA Server started")
            
            self._running = True
            self._update_task = asyncio.create_task(self._update_loop())
            
            # Keep server running
            try:
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
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

async def main():
    """Main entry point"""
    
    # Configuration
    endpoint = "opc.tcp://0.0.0.0:4840/l2trigger/"
    update_interval = 1.0  # seconds
    
    # Create and start server
    server = L2TriggerOPCUAServer(
        endpoint=endpoint,
        update_interval=update_interval
    )
    
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
