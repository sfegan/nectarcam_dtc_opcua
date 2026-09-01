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
import socket
import zlib
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set, Callable, Union, Iterable
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
    L2CB_SET_L1SCALERS_EN = 0x1A
    CTDB_SET_CH_POWER   = 0x20
    CTDB_SET_CH_TRIG    = 0x21
    CTDB_SET_CH_DELAY   = 0x22
    CTDB_SET_LIMITS     = 0x23
    CTDB_GET_MONITORING = 0x30
    CTDB_GET_CONFIG     = 0x31
    BATCH_MONITOR_ALL   = 0x32
    FAST_POLL           = 0x33
    SLOW_POLL           = 0x34
    L1SCALERS_POLL      = 0x35
    CLEAR_ARTIFACT      = 0x40
    APPEND_ARTIFACT     = 0x41
    VERIFY_ARTIFACT     = 0x42
    GET_ARTIFACT_STATUS = 0x43
    FLASH_CTDB_FW       = 0x44
    FLASH_L2CB_FW       = 0x45

ARTIFACT_CTDB = 0
ARTIFACT_L2CB = 1
MAX_ARTIFACT_BLOCK_SIZE = 1024

# Struct formats (Little Endian)
HEADER_FMT = "<HHHH"  # Type, Seq, Len, Reserved
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
    tib_input_count: int      # 32-bit input counter (v5+)
    tib_output_count: int     # 32-bit output counter (v5+)
    busy_mask: int
    busy_stuck: int

    @classmethod
    def disconnected(cls) -> 'L2CBStatus':
        """Create a status object representing hardware disconnection.
        
        All fields are set to zero/False values.
        """
        return cls(
            firmware_version=0,
            uptime=0,
            mcf_enabled=False,
            busy_glitch_filter_enabled=False,
            tib_trigger_busy_block_enabled=False,
            mcf_threshold=0,
            mcf_delay_ns=0.0,
            l1_deadtime_ns=0.0,
            tib_input_count=0,
            tib_output_count=0,
            busy_mask=0,
            busy_stuck=0
        )


@dataclass
class CTDBMonitoringData:
    slot: int
    ctdb_current_ma: float
    channel_currents_ma: List[float]
    over_current_errors: int
    under_current_errors: int
    power_enabled_mask: int
    l1scaler_active: bool

@dataclass
class CTDBConfigData:
    slot: int
    firmware_version: int
    current_limit_min_ma: float
    current_limit_max_ma: float
    trig_enabled_mask: int
    trig_delays_ns: List[float]

@dataclass
class L1ScalersData:
    slot: int
    l1a_slot_count: int
    l1_channel_counts: List[int]

@dataclass
class ArtifactStatus:
    artifact_id: int
    is_valid: bool
    total_bytes: int
    crc: int

# ============================================================================
# L2TriggerSystem (TCP Client)
# ============================================================================

class L2TriggerSystem:
    PROTOCOL_VERSION = 7

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
            
            # Disable Nagle algorithm for low latency
            sock = self.writer.get_extra_info('socket')
            if sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
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
        self.active_mask = 0

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
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
            header = struct.pack(HEADER_FMT, msg_type, seq, len(payload), 0)
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
            
            rtype, rseq, rlen, rres = struct.unpack(HEADER_FMT, resp_hdr_data)
            
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
                code = struct.unpack("<H", rpayload[:2])[0]
                msg = rpayload[2:].decode('ascii').strip('\x00')
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
        self.active_mask = active_mask
        
        imm_masks = [0] * 22
        for s, m in immutable_masks.items():
            if 1 <= s <= 21:
                imm_masks[s] = m
        
        payload = struct.pack("<I" + "H" * 22, active_mask, *imm_masks)
        await self._send_recv(L2TCPMsgType.SYS_SET_CONFIG, payload)

    async def ramp_power(self, enable: bool):
        """Trigger global power ramp"""
        payload = struct.pack("<H", 1 if enable else 0)
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

    def _parse_l2cb(self, data: bytes) -> L2CBStatus:
        # ts(u64), bmask(u32), bstuck(u32), tib_in(u32), tib_out(u32), fw(u16), ctrl(u16), thresh(u16), delay(u16), dt(u16), res(u16)
        ts, bmask, bstuck, tib_in, tib_out, fw, ctrl, thresh, delay, dt, _ = struct.unpack("<QIIIIHHHHHH", data)
        
        return L2CBStatus(
            firmware_version=fw,
            uptime=ts * 8, # convert to ns
            mcf_enabled=bool(ctrl & 0x1),
            busy_glitch_filter_enabled=bool(ctrl & 0x2),
            tib_trigger_busy_block_enabled=bool(ctrl & 0x4),
            mcf_threshold=thresh,
            mcf_delay_ns=float(delay * 20.0), # Multiples of 20ns for v14+ (v027+)
            l1_deadtime_ns=float(dt * 5),
            tib_input_count=tib_in,
            tib_output_count=tib_out,
            busy_mask=bmask,
            busy_stuck=bstuck
        )

    async def get_l2cb_status(self) -> L2CBStatus:
        _, data = await self._send_recv(L2TCPMsgType.L2CB_GET_STATE)
        return self._parse_l2cb(data)

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
        payload = struct.pack("<HH", slot, 1 if enabled else 0)
        await self._send_recv(L2TCPMsgType.L2CB_SET_BUSY_ENABLE_SLOT, payload)

    async def reset_tib_event_count(self):
        """Reset the TIB event counter"""
        await self._send_recv(L2TCPMsgType.L2CB_RESET_TIB_COUNT)

    async def set_l1_scalers_enabled(self, enabled: bool):
        """Enable or disable L1 counters on all slots"""
        await self._send_recv(L2TCPMsgType.L2CB_SET_L1SCALERS_EN, struct.pack("<H", 1 if enabled else 0))

    # --- CTDB Controls ---

    async def set_channel_power_enabled(self, slot: int, channel: int, enabled: bool):
        payload = struct.pack("<HHH", slot, channel, 1 if enabled else 0)
        await self._send_recv(L2TCPMsgType.CTDB_SET_CH_POWER, payload)

    async def set_channel_trigger_enabled(self, slot: int, channel: int, enabled: bool):
        payload = struct.pack("<HHH", slot, channel, 1 if enabled else 0)
        await self._send_recv(L2TCPMsgType.CTDB_SET_CH_TRIG, payload)

    async def set_channel_trigger_delay(self, slot: int, channel: int, delay_raw: int):
        payload = struct.pack("<HHH", slot, channel, delay_raw)
        await self._send_recv(L2TCPMsgType.CTDB_SET_CH_DELAY, payload)

    async def set_ctdb_limits(self, slot: int, min_raw: int, max_raw: int):
        payload = struct.pack("<HHH", slot, min_raw, max_raw)
        await self._send_recv(L2TCPMsgType.CTDB_SET_LIMITS, payload)

    # --- Monitoring ---

    def _parse_monitoring(self, data: bytes) -> CTDBMonitoringData:
        # slot(u16), ctdb_curr(u16), ch_curr(u16*15), over(u16), under(u16), pwr(u16), ctrl(u16), stat(u16)
        slot, ctdb_curr = struct.unpack_from("<HH", data, 0)
        ch_curr = list(struct.unpack_from("<" + "H" * 15, data, 4))
        over, under, pwr, ctrl, stat = struct.unpack_from("<HHHHH", data, 4 + 30)
        
        return CTDBMonitoringData(
            slot=slot,
            ctdb_current_ma=ctdb_curr * 0.485,
            channel_currents_ma=[c * 0.485 for c in ch_curr],
            over_current_errors=over,
            under_current_errors=under,
            power_enabled_mask=pwr,
            l1scaler_active=bool(ctrl & 0x2000)
        )

    async def get_ctdb_monitoring(self, slot: int) -> CTDBMonitoringData:
        _, data = await self._send_recv(L2TCPMsgType.CTDB_GET_MONITORING, struct.pack("<H", slot))
        return self._parse_monitoring(data)

    async def get_all_monitoring(self) -> Dict[int, CTDBMonitoringData]:
        _, data = await self._send_recv(L2TCPMsgType.BATCH_MONITOR_ALL)
        count = struct.unpack("<H", data[:2])[0]
        res = {}
        offset = 2
        mon_size = struct.calcsize("<HH" + "H" * 15 + "HHHHH")
        for _ in range(count):
            mon = self._parse_monitoring(data[offset:offset+mon_size])
            res[mon.slot] = mon
            offset += mon_size
        return res

    async def get_fast_poll(self) -> Tuple[L2CBStatus, Dict[int, CTDBMonitoringData]]:
        _, data = await self._send_recv(L2TCPMsgType.FAST_POLL)
        l2cb_size = struct.calcsize("<QIIIIHHHHHH")
        l2cb = self._parse_l2cb(data[:l2cb_size])
        
        mon_data = data[l2cb_size:]
        count = struct.unpack("<H", mon_data[:2])[0]
        res = {}
        offset = 2
        mon_size = struct.calcsize("<HH" + "H" * 15 + "HHHHH")
        for _ in range(count):
            mon = self._parse_monitoring(mon_data[offset:offset+mon_size])
            res[mon.slot] = mon
            offset += mon_size
        return l2cb, res

    def _parse_config(self, data: bytes) -> CTDBConfigData:
        # slot(u16), fw(u16), min(u16), max(u16), trig_mask(u16), trig_delays(u16*15)
        slot, fw, cmin, cmax, tmask = struct.unpack_from("<HHHHH", data, 0)
        tdelays = list(struct.unpack_from("<" + "H" * 15, data, 10))
        
        return CTDBConfigData(
            slot=slot,
            firmware_version=fw,
            current_limit_min_ma=cmin * 0.485,
            current_limit_max_ma=cmax * 0.485,
            trig_enabled_mask=tmask,
            trig_delays_ns=[d * 0.037 for d in tdelays]
        )

    async def get_ctdb_config(self, slot: int) -> CTDBConfigData:
        _, data = await self._send_recv(L2TCPMsgType.CTDB_GET_CONFIG, struct.pack("<H", slot))
        return self._parse_config(data)

    async def get_slow_poll(self) -> Dict[int, CTDBConfigData]:
        _, data = await self._send_recv(L2TCPMsgType.SLOW_POLL)
        count = struct.unpack("<H", data[:2])[0]
        res = {}
        offset = 2
        cfg_size = struct.calcsize("<HHHHH" + "H" * 15)
        for _ in range(count):
            cfg = self._parse_config(data[offset:offset+cfg_size])
            res[cfg.slot] = cfg
            offset += cfg_size
        return res

    def _parse_l1scalers(self, data: bytes) -> L1ScalersData:
        # slot(u32), l1a(u32), l1(u32*15)
        slot, l1a = struct.unpack_from("<II", data, 0)
        l1_counts = list(struct.unpack_from("<" + "I" * 15, data, 8))
        return L1ScalersData(
            slot=slot,
            l1a_slot_count=l1a,
            l1_channel_counts=l1_counts
        )

    async def get_l1_scalers(self) -> Dict[int, L1ScalersData]:
        """Poll L1 scalers for all active slots"""
        _, data = await self._send_recv(L2TCPMsgType.L1SCALERS_POLL)
        count = struct.unpack("<I", data[:4])[0]
        res = {}
        offset = 4
        scaler_size = struct.calcsize("<II" + "I" * 15)
        for _ in range(count):
            scaler = self._parse_l1scalers(data[offset:offset+scaler_size])
            res[scaler.slot] = scaler
            offset += scaler_size
        return res

    # --- Artifact & Firmware Management ---

    async def clear_artifact(self, artifact_id: int):
        """Clear artifact buffer on server and free its blocks"""
        payload = struct.pack("<H", artifact_id)
        await self._send_recv(L2TCPMsgType.CLEAR_ARTIFACT, payload)

    async def append_artifact_block(self, artifact_id: int, address: int, data: bytes):
        """Append a data block (up to 1024 bytes) to artifact"""
        if len(data) > MAX_ARTIFACT_BLOCK_SIZE:
            raise ValueError(f"Block length ({len(data)}) exceeds maximum allowable ({MAX_ARTIFACT_BLOCK_SIZE})")
        payload = struct.pack("<IHH", address, artifact_id, len(data)) + data
        await self._send_recv(L2TCPMsgType.APPEND_ARTIFACT, payload)

    async def verify_artifact(self, artifact_id: int, crc: int):
        """Verify artifact integrity using CRC32"""
        payload = struct.pack("<IHH", crc & 0xFFFFFFFF, artifact_id, 0)
        await self._send_recv(L2TCPMsgType.VERIFY_ARTIFACT, payload)

    async def get_artifact_status(self, artifact_id: int) -> ArtifactStatus:
        """Get artifact upload status and CRC validation flag"""
        payload = struct.pack("<H", artifact_id)
        _, data = await self._send_recv(L2TCPMsgType.GET_ARTIFACT_STATUS, payload)
        total_bytes, crc, r_id, is_valid = struct.unpack("<IIHH", data)
        return ArtifactStatus(
            artifact_id=r_id,
            is_valid=bool(is_valid),
            total_bytes=total_bytes,
            crc=crc
        )

    async def upload_artifact(self, artifact_id: int, data: bytes, starting_address: int = 0,
                              block_size: int = MAX_ARTIFACT_BLOCK_SIZE,
                              progress_callback: Optional[Callable[[int, int], None]] = None) -> ArtifactStatus:
        """Upload complete binary data as artifact blocks, verify CRC, and return status"""
        await self.clear_artifact(artifact_id)
        total_len = len(data)
        running_crc = 0
        offset = 0

        if total_len == 0:
            addr = starting_address
            await self.append_artifact_block(artifact_id, addr, b"")
            running_crc = zlib.crc32(struct.pack("<I", addr), running_crc) & 0xFFFFFFFF
            if progress_callback:
                progress_callback(0, 0)
        else:
            while offset < total_len:
                chunk = data[offset:offset + block_size]
                addr = starting_address + offset
                await self.append_artifact_block(artifact_id, addr, chunk)
                block_crc_data = struct.pack("<I", addr) + chunk
                running_crc = zlib.crc32(block_crc_data, running_crc) & 0xFFFFFFFF
                offset += len(chunk)
                if progress_callback:
                    progress_callback(offset, total_len)

        await self.verify_artifact(artifact_id, running_crc)
        return await self.get_artifact_status(artifact_id)

    async def upload_artifact_mcs(self, artifact_id: int, mcs_source: Union[str, Iterable[str]],
                                  progress_callback: Optional[Callable[[int], None]] = None) -> ArtifactStatus:
        """Parse an Intel MCS/HEX file, chunk contiguous bytes into 1024-byte blocks,
        upload them with extended addresses, verify checksum and EOF, and validate artifact.
        
        If any checksum fails, or EOF is missing/invalid, clears artifact and raises exception.
        """
        await self.clear_artifact(artifact_id)
        
        lines = []
        if isinstance(mcs_source, str):
            if "\n" not in mcs_source and os.path.exists(mcs_source):
                with open(mcs_source, "r", encoding="ascii", errors="replace") as f:
                    lines = f.readlines()
            else:
                lines = mcs_source.splitlines()
        else:
            lines = list(mcs_source)

        extended_addr = 0
        current_chunk_addr: Optional[int] = None
        current_chunk_data = bytearray()
        total_uploaded_bytes = 0
        running_crc = 0
        eof_seen = False

        async def _flush_blocks(force_all: bool = False):
            nonlocal current_chunk_addr, current_chunk_data, running_crc, total_uploaded_bytes
            while current_chunk_data and (force_all or len(current_chunk_data) >= MAX_ARTIFACT_BLOCK_SIZE):
                chunk_len = min(len(current_chunk_data), MAX_ARTIFACT_BLOCK_SIZE)
                chunk = bytes(current_chunk_data[:chunk_len])
                addr = current_chunk_addr
                await self.append_artifact_block(artifact_id, addr, chunk)
                block_crc_data = struct.pack("<I", addr) + chunk
                running_crc = zlib.crc32(block_crc_data, running_crc) & 0xFFFFFFFF
                total_uploaded_bytes += len(chunk)
                current_chunk_addr += chunk_len
                current_chunk_data = current_chunk_data[chunk_len:]
                if progress_callback:
                    progress_callback(total_uploaded_bytes)

        try:
            for line_num, raw_line in enumerate(lines, 1):
                line = raw_line.strip()
                if not line:
                    continue
                if not line.startswith(":"):
                    continue

                try:
                    record_bytes = bytes.fromhex(line[1:])
                except ValueError as e:
                    raise ValueError(f"Invalid hex encoding on line {line_num}: {e}")

                if (sum(record_bytes) & 0xFF) != 0:
                    raise ValueError(f"MCS record checksum error on line {line_num}")

                count = record_bytes[0]
                offset = (record_bytes[1] << 8) | record_bytes[2]
                rectype = record_bytes[3]
                data = record_bytes[4:4+count]

                if len(data) != count:
                    raise ValueError(f"Truncated MCS record on line {line_num}: expected {count} bytes, got {len(data)}")

                if rectype == 0x00:  # Data Record
                    if eof_seen:
                        raise ValueError(f"Data record after EOF on line {line_num}")
                    line_addr = extended_addr + offset
                    if current_chunk_addr is None:
                        current_chunk_addr = line_addr
                        current_chunk_data = bytearray(data)
                    else:
                        expected_addr = current_chunk_addr + len(current_chunk_data)
                        if line_addr == expected_addr:
                            current_chunk_data.extend(data)
                        else:
                            # Address gap: flush existing buffered chunk
                            await _flush_blocks(force_all=True)
                            current_chunk_addr = line_addr
                            current_chunk_data = bytearray(data)

                    await _flush_blocks(force_all=False)

                elif rectype == 0x01:  # End of File Record
                    eof_seen = True
                    await _flush_blocks(force_all=True)
                    current_chunk_addr = None

                elif rectype == 0x02:  # Extended Segment Address Record
                    if count != 2:
                        raise ValueError(f"Invalid extended segment address length on line {line_num}")
                    await _flush_blocks(force_all=True)
                    current_chunk_addr = None
                    seg = (data[0] << 8) | data[1]
                    extended_addr = seg << 4

                elif rectype == 0x04:  # Extended Linear Address Record
                    if count != 2:
                        raise ValueError(f"Invalid extended linear address length on line {line_num}")
                    await _flush_blocks(force_all=True)
                    current_chunk_addr = None
                    upper = (data[0] << 8) | data[1]
                    extended_addr = upper << 16

                elif rectype in (0x03, 0x05):  # Start Segment / Start Linear Address
                    pass
                else:
                    raise ValueError(f"Unsupported MCS record type 0x{rectype:02X} on line {line_num}")

            if not eof_seen:
                raise ValueError("MCS file does not contain a valid End-Of-File (01) record")

            if total_uploaded_bytes == 0:
                raise ValueError("MCS file contains no data records")

            # Validate artifact with server using computed CRC
            await self.verify_artifact(artifact_id, running_crc)
            return await self.get_artifact_status(artifact_id)

        except Exception as e:
            logger.error(f"MCS upload failed: {e}. Clearing artifact {artifact_id}.")
            try:
                await self.clear_artifact(artifact_id)
            except Exception:
                pass
            raise

    async def flash_ctdb_firmware(self, slot: int):
        """Trigger flashing of CTDB firmware artifact to target slot"""
        payload = struct.pack("<H", slot)
        await self._send_recv(L2TCPMsgType.FLASH_CTDB_FW, payload)

    async def flash_l2cb_firmware(self):
        """Trigger flashing of L2CB firmware artifact"""
        await self._send_recv(L2TCPMsgType.FLASH_L2CB_FW)
