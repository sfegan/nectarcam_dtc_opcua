"""
l2trig_api.py

High-level async API for L2 Trigger System (TCP version)
Communicates with the embedded C server via L2TCP protocol.

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
"""

import asyncio
import struct
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from enum import IntEnum

# ============================================================================
# Constants & Protocol Definitions
# ============================================================================

VALID_SLOTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14, 15, 16, 17, 18, 19, 20, 21]
CHANNELS_PER_SLOT = 15
DEFAULT_PORT = 4242

class L2TCPMsgType(IntEnum):
    ACK                 = 0x00
    ERROR               = 0xFF
    SYS_SET_CONFIG      = 0x01
    SYS_RAMP_POWER      = 0x02
    SYS_EMERGENCY_OFF   = 0x03
    SYS_SET_ALL_TRIG_EN = 0x04
    SYS_SET_ALL_TRIG_DELAY = 0x05
    SYS_KEEPALIVE       = 0x06
    HELLO               = 0x07
    L2CB_GET_STATE      = 0x10
    L2CB_SET_MCF_EN     = 0x11
    L2CB_SET_GLITCH_EN  = 0x12
    L2CB_SET_TIB_BLOCK_EN = 0x13
    L2CB_SET_MCF_THRESH = 0x14
    L2CB_SET_MCF_DELAY  = 0x15
    L2CB_SET_L1_DEADTIME = 0x16
    L2CB_SET_BUSY_ENABLE_MASK = 0x17
    L2CB_SET_BUSY_ENABLE_SLOT = 0x18
    L2CB_RESET_TIB_COUNT = 0x19
    CTDB_SET_CH_POWER   = 0x20
    CTDB_SET_CH_TRIG    = 0x21
    CTDB_SET_CH_DELAY   = 0x22
    CTDB_SET_LIMITS     = 0x23
    CTDB_GET_MONITORING = 0x30
    CTDB_GET_CONFIG     = 0x31
    BATCH_MONITOR_ALL   = 0x32

# Struct formats (Little Endian)
HEADER_FMT = "<BBH"  # Type, Seq, Len
HEADER_SIZE = struct.calcsize(HEADER_FMT)

logger = logging.getLogger(__name__)

# ================= ===========================================================
# Data Classes (Maintained for API compatibility)
# ============================================================================

@dataclass
class L2CBStatus:
    firmware_version: int
    uptime: int
    mcf_enabled: bool
    busy_glitch_filter_enabled: bool
    tib_trigger_busy_block_enabled: bool
    mcf_threshold: int
    mcf_delay_ns: float
    l1_deadtime_ns: float
    tib_event_count: int
    busy_mask: int
    busy_stuck: int

@dataclass
class CTDBMonitoringData:
    slot: int
    ctdb_current_ma: float
    channel_currents_ma: List[float]
    over_current_errors: int
    under_current_errors: int
    power_enabled_mask: int

@dataclass
class CTDBConfigData:
    slot: int
    firmware_version: int
    current_limit_min_ma: float
    current_limit_max_ma: float
    trig_enabled_mask: int
    trig_delays_ns: List[float]

# ============================================================================
# L2TriggerSystem (TCP Client)
# ============================================================================

class L2TriggerSystem:
    PROTOCOL_VERSION = 2

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, 
                 connect_timeout: float = 5.0, recv_timeout: float = 5.0):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._seq = 0
        self._lock = asyncio.Lock()
        self.connect_timeout = connect_timeout
        self.recv_timeout = recv_timeout

    async def connect(self):
        """Establish connection to the embedded server"""
        async with self._lock:
            await self._connect_unlocked()
            await self._negotiate_unlocked()

    async def _connect_unlocked(self):
        """Internal connect without locking"""
        if self.writer and not self.writer.transport.is_closing():
            return

        logger.info(f"Connecting to L2Trigger server at {self.host}:{self.port} (timeout: {self.connect_timeout}s)")
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.connect_timeout
            )
        except Exception as e:
            logger.error(f"Connection failed to {self.host}:{self.port}: {e}")
            self.reader = None
            self.writer = None
            if isinstance(e, asyncio.TimeoutError):
                raise RuntimeError(f"Connection timeout to {self.host}:{self.port}")
            raise

    async def disconnect(self):
        """Close connection"""
        async with self._lock:
            await self._disconnect_unlocked()

    async def _disconnect_unlocked(self):
        """Internal disconnect without locking"""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.reader = None
        self.writer = None

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    async def _negotiate_unlocked(self):
        """Perform version negotiation handshake"""
        logger.info(f"Negotiating protocol version (client version: {self.PROTOCOL_VERSION})")
        
        # 1. Send our version
        payload = struct.pack("<H", self.PROTOCOL_VERSION)
        rtype, rpayload = await self._send_recv_unlocked(L2TCPMsgType.HELLO, payload)
        
        server_version = struct.unpack("<H", rpayload)[0]
        logger.info(f"Server protocol version: {server_version}")

        if server_version != self.PROTOCOL_VERSION:
            logger.warning(f"Protocol version mismatch: client={self.PROTOCOL_VERSION}, server={server_version}. Adapting to server.")
            # 2. Adapt to server version as requested: send HELLO with server's version
            payload = struct.pack("<H", server_version)
            rtype, rpayload = await self._send_recv_unlocked(L2TCPMsgType.HELLO, payload)
            
            final_version = struct.unpack("<H", rpayload)[0]
            if final_version != server_version:
                raise RuntimeError(f"Failed to negotiate version: server keeps changing version! ({server_version} -> {final_version})")
            
            logger.info("Negotiation successful (adapted to server)")
        else:
            logger.info("Negotiation successful (version match)")

    async def _send_recv(self, msg_type: L2TCPMsgType, payload: bytes = b"") -> Tuple[L2TCPMsgType, bytes]:
        async with self._lock:
            if not self.writer or self.writer.transport.is_closing():
                await self._connect_unlocked()
                await self._negotiate_unlocked()

            return await self._send_recv_unlocked(msg_type, payload)

    async def _send_recv_unlocked(self, msg_type: L2TCPMsgType, payload: bytes = b"") -> Tuple[L2TCPMsgType, bytes]:
        try:
            seq = self._next_seq()
            header = struct.pack(HEADER_FMT, msg_type, seq, len(payload))
            self.writer.write(header + payload)
            await self.writer.drain()

            # Read response header with timeout
            try:
                resp_hdr_data = await asyncio.wait_for(
                    self.reader.readexactly(HEADER_SIZE),
                    timeout=self.recv_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"Header recv timeout after {self.recv_timeout}s")
                await self._disconnect_unlocked()
                raise RuntimeError(f"Server response timeout after {self.recv_timeout}s")
            
            rtype, rseq, rlen = struct.unpack(HEADER_FMT, resp_hdr_data)
            
            # Read payload with timeout
            rpayload = b""
            if rlen > 0:
                try:
                    rpayload = await asyncio.wait_for(
                        self.reader.readexactly(rlen),
                        timeout=self.recv_timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Payload recv timeout after {self.recv_timeout}s")
                    await self._disconnect_unlocked()
                    raise RuntimeError(f"Server payload timeout after {self.recv_timeout}s")

            if rseq != seq:
                raise RuntimeError(f"Sequence mismatch: expected {seq}, got {rseq}")

            if rtype == L2TCPMsgType.ERROR:
                code = rpayload[0]
                msg = rpayload[1:].decode('ascii').strip('\x00')
                raise RuntimeError(f"Server error {code}: {msg}")

            return L2TCPMsgType(rtype), rpayload
        except (asyncio.IncompleteReadError, ConnectionError, OSError) as e:
            # Connection lost or broken, reset state so we try to reconnect next time
            logger.error(f"Connection error: {e}")
            await self._disconnect_unlocked()
            raise

    # --- System Control ---

    async def keepalive(self):
        """Send keepalive message to keep connection alive"""
        await self._send_recv(L2TCPMsgType.SYS_KEEPALIVE)

    async def set_config(self, active_slots: List[int], immutable_masks: Dict[int, int]):
        """Configure active slots and immutable channels"""
        # Validate slots
        for s in active_slots:
            if s not in VALID_SLOTS:
                raise ValueError(f"Invalid slot {s}, must be one of {VALID_SLOTS}")

        active_mask = 0
        for s in active_slots:
            active_mask |= (1 << s)
        
        imm_masks = [0] * 22
        for s, m in immutable_masks.items():
            if 1 <= s <= 21:
                imm_masks[s] = m
        
        payload = struct.pack("<I" + "H" * 22, active_mask, *imm_masks)
        await self._send_recv(L2TCPMsgType.SYS_SET_CONFIG, payload)

    async def ramp_power(self, enable: bool):
        """Trigger global power ramp"""
        payload = struct.pack("<B", 1 if enable else 0)
        await self._send_recv(L2TCPMsgType.SYS_RAMP_POWER, payload)

    async def emergency_shutdown(self):
        """Immediate global power off"""
        await self._send_recv(L2TCPMsgType.SYS_EMERGENCY_OFF)

    async def set_all_trigger_enabled(self, enabled: bool):
        """Global control to enable or disable trigger for all modules"""
        payload = struct.pack("<H", 1 if enabled else 0)
        await self._send_recv(L2TCPMsgType.SYS_SET_ALL_TRIG_EN, payload)

    async def set_all_trigger_delay(self, delay_raw: int):
        """Apply uniform trigger delay to all modules"""
        payload = struct.pack("<H", delay_raw)
        await self._send_recv(L2TCPMsgType.SYS_SET_ALL_TRIG_DELAY, payload)

    # --- L2CB Controls ---

    async def get_l2cb_status(self) -> L2CBStatus:
        _, data = await self._send_recv(L2TCPMsgType.L2CB_GET_STATE)
        # fw(u16), ts(u64), ctrl(u16), thresh(u16), delay(u16), dt(u16), tib(u16), bmask(u32), bstuck(u32)
        fw, ts, ctrl, thresh, delay, dt, tib, bmask, bstuck = struct.unpack("<HQHHHHHII", data)
        return L2CBStatus(
            firmware_version=fw,
            uptime=ts * 8, # convert to ns
            mcf_enabled=bool(ctrl & 0x1),
            busy_glitch_filter_enabled=bool(ctrl & 0x2),
            tib_trigger_busy_block_enabled=bool(ctrl & 0x4),
            mcf_threshold=thresh,
            mcf_delay_ns=float(delay * 5),
            l1_deadtime_ns=float(dt * 5),
            tib_event_count=tib,
            busy_mask=bmask,
            busy_stuck=bstuck
        )

    async def set_mcf_enabled(self, enabled: bool):
        await self._send_recv(L2TCPMsgType.L2CB_SET_MCF_EN, struct.pack("<H", 1 if enabled else 0))

    async def set_glitch_filter_enabled(self, enabled: bool):
        await self._send_recv(L2TCPMsgType.L2CB_SET_GLITCH_EN, struct.pack("<H", 1 if enabled else 0))

    async def set_tib_block_enabled(self, enabled: bool):
        await self._send_recv(L2TCPMsgType.L2CB_SET_TIB_BLOCK_EN, struct.pack("<H", 1 if enabled else 0))

    async def set_mcf_threshold(self, threshold: int):
        await self._send_recv(L2TCPMsgType.L2CB_SET_MCF_THRESH, struct.pack("<H", threshold))

    async def set_mcf_delay(self, delay_raw: int):
        await self._send_recv(L2TCPMsgType.L2CB_SET_MCF_DELAY, struct.pack("<H", delay_raw))

    async def set_l1_deadtime(self, deadtime_raw: int):
        await self._send_recv(L2TCPMsgType.L2CB_SET_L1_DEADTIME, struct.pack("<H", deadtime_raw))

    async def set_busy_enable_mask(self, mask: int):
        """Set the unified 32-bit busy enable mask"""
        await self._send_recv(L2TCPMsgType.L2CB_SET_BUSY_ENABLE_MASK, struct.pack("<I", mask))

    async def set_busy_enable_slot(self, slot: int, enabled: bool):
        """Enable or disable busy for a specific slot"""
        payload = struct.pack("<BB", slot, 1 if enabled else 0)
        await self._send_recv(L2TCPMsgType.L2CB_SET_BUSY_ENABLE_SLOT, payload)

    async def reset_tib_event_count(self):
        """Reset the TIB event counter"""
        await self._send_recv(L2TCPMsgType.L2CB_RESET_TIB_COUNT)

    # --- CTDB Controls ---

    async def set_channel_power_enabled(self, slot: int, channel: int, enabled: bool):
        payload = struct.pack("<BBB", slot, channel, 1 if enabled else 0)
        await self._send_recv(L2TCPMsgType.CTDB_SET_CH_POWER, payload)

    async def set_channel_trigger_enabled(self, slot: int, channel: int, enabled: bool):
        payload = struct.pack("<BBB", slot, channel, 1 if enabled else 0)
        await self._send_recv(L2TCPMsgType.CTDB_SET_CH_TRIG, payload)

    async def set_channel_trigger_delay(self, slot: int, channel: int, delay_raw: int):
        payload = struct.pack("<BBH", slot, channel, delay_raw)
        await self._send_recv(L2TCPMsgType.CTDB_SET_CH_DELAY, payload)

    async def set_ctdb_limits(self, slot: int, min_raw: int, max_raw: int):
        payload = struct.pack("<BHH", slot, min_raw, max_raw)
        await self._send_recv(L2TCPMsgType.CTDB_SET_LIMITS, payload)

    # --- Monitoring ---

    def _parse_monitoring(self, data: bytes) -> CTDBMonitoringData:
        # slot(u8), ctdb_curr(u16), ch_curr(u16*15), over(u16), under(u16), pwr(u16)
        slot, ctdb_curr = struct.unpack_from("<BH", data, 0)
        ch_curr = list(struct.unpack_from("<" + "H" * 15, data, 3))
        over, under, pwr = struct.unpack_from("<HHH", data, 3 + 30)
        
        return CTDBMonitoringData(
            slot=slot,
            ctdb_current_ma=ctdb_curr * 0.485,
            channel_currents_ma=[c * 0.485 for c in ch_curr],
            over_current_errors=over,
            under_current_errors=under,
            power_enabled_mask=pwr
        )

    async def get_ctdb_monitoring(self, slot: int) -> CTDBMonitoringData:
        _, data = await self._send_recv(L2TCPMsgType.CTDB_GET_MONITORING, struct.pack("<B", slot))
        return self._parse_monitoring(data)

    async def get_all_monitoring(self) -> Dict[int, CTDBMonitoringData]:
        _, data = await self._send_recv(L2TCPMsgType.BATCH_MONITOR_ALL)
        count = data[0]
        res = {}
        offset = 1
        mon_size = struct.calcsize("<BH" + "H" * 15 + "HHH")
        for _ in range(count):
            mon = self._parse_monitoring(data[offset:offset+mon_size])
            res[mon.slot] = mon
            offset += mon_size
        return res

    async def get_ctdb_config(self, slot: int) -> CTDBConfigData:
        _, data = await self._send_recv(L2TCPMsgType.CTDB_GET_CONFIG, struct.pack("<B", slot))
        # slot(u8), fw(u16), min(u16), max(u16), trig_mask(u16), trig_delays(u16*15)
        slot, fw, cmin, cmax, tmask = struct.unpack_from("<BHHHH", data, 0)
        tdelays = list(struct.unpack_from("<" + "H" * 15, data, 9))
        
        return CTDBConfigData(
            slot=slot,
            firmware_version=fw,
            current_limit_min_ma=cmin * 0.485,
            current_limit_max_ma=cmax * 0.485,
            trig_enabled_mask=tmask,
            trig_delays_ns=[d * 0.037 for d in tdelays]
        )
