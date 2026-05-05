"""
l2trig_tui.py

Text-based User Interface (TUI) for NectarCAM L2 Trigger System.
Real-time monitoring and control via OPC UA.

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
"""

import asyncio
import curses
import datetime
import argparse
import sys
import time
from typing import Dict, List, Optional, Any, Tuple

from asyncua import Client, ua
from asyncua.common.node import Node

# ============================================================================
# Constants & Layout Configuration
# ============================================================================

VALID_SLOTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14, 15, 16, 17, 18, 19, 20, 21]
CHANNELS_PER_SLOT = 15
SLOT_WIDTH = 4  # 3 chars + 1 space

# View Modes
VIEW_CURRENT = 0
VIEW_TRIGGER = 1
VIEW_DELAY = 2
VIEW_NAMES = ["Power and Current (mA)", "L1 Trigger Enabled", "L1 Trigger Delay (10ps)"]

# ============================================================================
# OPC UA State Container
# ============================================================================

class SystemState:
    def __init__(self):
        # Global stats
        self.device_host = ""
        self.device_port = 0
        self.device_connected = False
        self.fw_rev = 0
        self.uptime = 0
        self.tib_count = 0
        self.mcf_enabled = False
        self.glitch_enabled = False
        self.tib_block_enabled = False
        self.mcf_threshold = 0
        self.mcf_delay_ns = 0.0
        self.l1_deadtime_ns = 0.0
        self.conn_uptime_ms = 0.0
        self.conn_downtime_ms = 0.0
        
        # Per-Board stats (Arrays)
        self.board_slots = []
        self.board_fw = []
        self.board_busy_en = []
        self.board_busy_stuck = []
        self.board_base_curr = []
        self.board_limit_min = []
        self.board_limit_max = []
        
        # Per-Module stats (Arrays, flattened)
        self.mod_pwr_en = []
        self.mod_curr = []
        self.mod_state = []
        self.mod_trig_en = []
        self.mod_trig_delay = []
        self.mod_is_mutable = []

# ============================================================================
# TUI Application
# ============================================================================

class L2TrigTUI:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.client = Client(url=endpoint)
        self.state = SystemState()
        self.ns_idx = 0
        self.root_node = None
        self.mon_node = None
        
        # UI Selection
        self.sel_slot_idx = 0
        self.sel_chan = 1
        self.view_mode_right = VIEW_TRIGGER
        self.view_mode_narrow = VIEW_CURRENT
        
        self._running = True
        self._lock = asyncio.Lock()
        self._redraw_event = asyncio.Event()

    async def connect(self):
        await self.client.connect()
        uri = "http://cta-observatory.org/nectarcam/l2trig/"
        try:
            self.ns_idx = await self.client.get_namespace_index(uri)
        except ValueError:
            self.ns_idx = 2
            
        objects = self.client.get_objects_node()
        self.root_node = await objects.get_child(f"{self.ns_idx}:L2Trigger")
        self.mon_node = await self.root_node.get_child(f"{self.ns_idx}:Monitoring")

    async def update_state(self):
        """Fetch all monitoring variables from OPC UA"""
        if not self.mon_node:
            return
            
        try:
            # We fetch everything in one go for consistency
            nodes = await self.mon_node.get_children()
            var_map = {}
            for node in nodes:
                name = (await node.read_browse_name()).Name
                var_map[name] = node

            async def read(name):
                if name in var_map:
                    return await var_map[name].read_value()
                return None

            s = self.state
            s.device_host = await read("device_host")
            s.device_port = await read("device_port")
            s.device_connected = await read("device_connected")
            s.fw_rev = await read("CrateFirmwareRevision")
            s.uptime = await read("CrateUpTime")
            s.tib_count = await read("CrateTIBEventCount")
            s.mcf_enabled = await read("CrateMCFEnabled")
            s.glitch_enabled = await read("CrateBusyGlitchFilterEnabled")
            s.tib_block_enabled = await read("CrateTIBTriggerBusyBlockEnabled")
            s.mcf_threshold = await read("CrateMCFThreshold")
            s.mcf_delay_ns = await read("CrateMCFDelay")
            s.l1_deadtime_ns = await read("CrateL1Deadtime")
            s.conn_uptime_ms = await read("device_connection_uptime")
            s.conn_downtime_ms = await read("device_connection_downtime")
            
            s.board_slots = await read("BoardSlotId") or []
            s.board_fw = await read("BoardFirmwareRevision") or []
            s.board_busy_en = await read("BoardBusyEnabled") or []
            s.board_busy_stuck = await read("BoardBusyStuckStatus") or []
            s.board_base_curr = await read("BoardBaseCurrent") or []
            s.board_limit_min = await read("BoardCurrentLimitMin") or []
            s.board_limit_max = await read("BoardCurrentLimitMax") or []
            
            s.mod_pwr_en = await read("ModulePowerEnabled") or []
            s.mod_curr = await read("ModuleCurrent") or []
            s.mod_state = await read("ModuleState") or []
            s.mod_trig_en = await read("ModuleTriggerEnabled") or []
            s.mod_trig_delay = await read("ModuleTriggerDelay") or []
            s.mod_is_mutable = await read("ModuleIsMutable") or []

        except Exception:
            # Silence background errors to avoid flickering
            pass

    async def call(self, method_name: str, *args):
        try:
            await self.root_node.call_method(f"{self.ns_idx}:{method_name}", *args)
        except Exception:
            pass

    def draw(self, stdscr):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        s = self.state
        
        # Color pairs
        curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)   # Low current
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Normal current / Trigger ON
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)    # High current
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_RED)    # ERR status
        curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selection / Coordinate highlight
        curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)   # Header / Labels
        
        # 1. Header Zone
        conn_str = "CONNECTED" if s.device_connected else "DISCONNECTED"
        conn_dur = s.conn_uptime_ms if s.device_connected else s.conn_downtime_ms
        stdscr.addstr(0, 0, f"DTC TUI | {s.device_host}:{s.device_port} | {conn_str} for {conn_dur/1000:,.0f}s", curses.color_pair(6) | curses.A_BOLD)
        stdscr.addstr(1, 0, f"FW: 0x{s.fw_rev:04X} | Uptime: {s.uptime/1e9:,.1f}s | TIB event count: {s.tib_count:,}")
        mcf_str = f"MCF: {'ON' if s.mcf_enabled else 'OFF'} (Thr: {s.mcf_threshold}, Del: {s.mcf_delay_ns:.0f}ns)"
        tib_str = f"Glitch: {'ON' if s.glitch_enabled else 'OFF'} | TIB Block: {'ON' if s.tib_block_enabled else 'OFF'} | Deadtime: {s.l1_deadtime_ns:.0f}ns"
        stdscr.addstr(2, 0, f"{mcf_str} | {tib_str}")
        
        if not s.board_slots:
            stdscr.addstr(5, 0, "Waiting for initial data...")
            return

        # 2. Matrix Zone
        num_slots = len(s.board_slots)
        matrix_w = num_slots * SLOT_WIDTH + 4
        
        # Adaptive Layout Logic
        show_current = True
        show_trigger = False
        show_delay = False
        
        if w >= 240:
            show_trigger = True
            show_delay = True
            off_trig = matrix_w + 3
            off_delay = off_trig + matrix_w + 3
        elif w >= 160:
            show_trigger = (self.view_mode_right == VIEW_TRIGGER)
            show_delay = (self.view_mode_right == VIEW_DELAY)
            off_trig = matrix_w + 3
            off_delay = matrix_w + 3
        else:
            show_current = (self.view_mode_narrow == VIEW_CURRENT)
            show_trigger = (self.view_mode_narrow == VIEW_TRIGGER)
            show_delay = (self.view_mode_narrow == VIEW_DELAY)

        def draw_matrix(y_off, x_off, mode):
            # Title
            title = VIEW_NAMES[mode]
            stdscr.addstr(y_off - 1, x_off + 4, title, curses.color_pair(6) | curses.A_BOLD)
            
            # Headers (S1, S2, ...) - Flush right in 3 chars
            for idx, slot in enumerate(s.board_slots):
                attr = curses.A_UNDERLINE
                if idx == self.sel_slot_idx:
                    attr |= curses.color_pair(5)
                stdscr.addstr(y_off, x_off + 4 + idx * SLOT_WIDTH, f"{'S'+str(slot):>3}", attr)

            for ch in range(1, 16):
                attr = curses.A_NORMAL
                if ch == self.sel_chan:
                    attr |= curses.color_pair(5)
                stdscr.addstr(y_off + ch, x_off, f"C{ch:02d}", attr)
                
                for idx, slot in enumerate(s.board_slots):
                    m_idx = idx * 15 + (ch - 1)
                    if m_idx >= len(s.mod_pwr_en): continue
                    
                    val_str = "???"
                    attr = curses.A_NORMAL
                    
                    if mode == VIEW_CURRENT:
                        state = s.mod_state[m_idx]
                        if "error" in state:
                            val_str = "ERR"
                            attr = curses.color_pair(4) | curses.A_BOLD
                        elif not s.mod_pwr_en[m_idx]:
                            val_str = "off"
                            attr = curses.A_DIM
                        else:
                            ma = s.mod_curr[m_idx]
                            val_str = f"{int(ma):3d}"
                            if ma < 200: attr = curses.color_pair(1)
                            elif ma <= 450: attr = curses.color_pair(2)
                            else: attr = curses.color_pair(3)
                    elif mode == VIEW_TRIGGER:
                        if s.mod_trig_en[m_idx]:
                            val_str = " ON"
                            attr = curses.color_pair(2) | curses.A_BOLD
                        else:
                            val_str = "off"
                            attr = curses.A_DIM
                    elif mode == VIEW_DELAY:
                        # 10ps units to fit 3 chars (e.g. 5ns = 500 * 10ps)
                        val_str = f"{int(s.mod_trig_delay[m_idx] * 100):3d}"
                    
                    # Highlight Cursor using REVERSE
                    if idx == self.sel_slot_idx and ch == self.sel_chan:
                        attr |= curses.A_REVERSE
                        
                    stdscr.addstr(y_off + ch, x_off + 4 + idx * SLOT_WIDTH, val_str, attr)

        y_mat = 5
        if show_current: draw_matrix(y_mat, 0, VIEW_CURRENT)
        if show_trigger: draw_matrix(y_mat, off_trig if w >= 160 else 0, VIEW_TRIGGER)
        if show_delay:   draw_matrix(y_mat, off_delay if w >= 160 else 0, VIEW_DELAY)

        # 3. Board Stats Zone (Footer of matrix, with 1-line gap)
        y_board = y_mat + 18
        stdscr.addstr(y_board,     0, "Firmware Rev     : ")
        stdscr.addstr(y_board + 1, 0, "Base Current (mA): ")
        stdscr.addstr(y_board + 2, 0, "TIB Busy Stuck   : ")
        stdscr.addstr(y_board + 3, 0, "TIB Busy Enabled : ")
        stdscr.addstr(y_board + 4, 0, "Current Min (mA) : ")
        stdscr.addstr(y_board + 5, 0, "Current Max (mA) : ")

        label_width = 19
        for i, slot in enumerate(s.board_slots):
            x = label_width + i * SLOT_WIDTH
            # Highlight only columns corresponding to the current selection
            col_attr = curses.color_pair(5) if i == self.sel_slot_idx else curses.A_NORMAL
            
            # Firmware (ANDed 0x0FFF) - NO CURSOR HIGHLIGHT
            bfw = s.board_fw[i] if i < len(s.board_fw) else 0
            stdscr.addstr(y_board, x, f"{bfw & 0x0FFF:3X}")

            # Base Current - NO CURSOR HIGHLIGHT
            b_curr = s.board_base_curr[i] if i < len(s.board_base_curr) else 0.0
            stdscr.addstr(y_board + 1, x, f"{int(b_curr):3d}")
            
            # Busy Stuck - NO CURSOR HIGHLIGHT
            stuck = s.board_busy_stuck[i] if i < len(s.board_busy_stuck) else False
            stdscr.addstr(y_board + 2, x, "ERR" if stuck else "...", (curses.color_pair(4) | curses.A_BOLD) if stuck else curses.A_DIM)
            
            # Busy Enabled - HIGHLIGHT IF SELECTED USING REVERSE
            ben = s.board_busy_en[i] if i < len(s.board_busy_en) else False
            ben_attr = (curses.color_pair(2) | curses.A_BOLD) if ben else curses.A_DIM
            if i == self.sel_slot_idx:
                ben_attr |= curses.A_REVERSE
            stdscr.addstr(y_board + 3, x, " ON" if ben else "off", ben_attr)
            
            # Trip Limits - HIGHLIGHT IF SELECTED
            min_val = f"{int(s.board_limit_min[i]):3d}" if i < len(s.board_limit_min) else "???"
            stdscr.addstr(y_board + 4, x, min_val, col_attr)
            max_val = f"{int(s.board_limit_max[i]):3d}" if i < len(s.board_limit_max) else "???"
            stdscr.addstr(y_board + 5, x, max_val, col_attr)

        # 4. Menu Zone
        y_menu = y_board + 7
        if h > y_menu:
            slot_id = s.board_slots[self.sel_slot_idx]
            menu_lines = [
                "Global: [P/p] All Pwr ON/OFF, [T/t] All Trig, [B/b] All Busy, [M/m] MCF, [R] Reset TIB, [E] Emergency",
                "Params: [</>] MCF Thr, [{/}] MCF Delay, [+/-] L1 Deadtime",
                f"Module: S{slot_id:02d} C{self.sel_chan:02d} | [O/o] Pwr, [Y/y] Trig, [D/d] Delay, [I/i] Immutable",
                f"Board : S{slot_id:02d}     | [K/k] TIB busy enabled, [N/n] Current min, [X/x] Current max",
                "Menu:   [c] Cycle View, [q] Quit"
            ]
            for i, line in enumerate(menu_lines):
                if y_menu + i < h:
                    stdscr.addstr(y_menu + i, 0, line[:w-1], curses.color_pair(6))

    async def handle_input(self, stdscr):
        stdscr.nodelay(True)
        while self._running:
            ch = stdscr.getch()
            if ch == -1:
                await asyncio.sleep(0.05)
                continue
            
            s = self.state
            num_slots = len(s.board_slots)
            
            # Arrow Navigation
            if ch == curses.KEY_LEFT:
                self.sel_slot_idx = (self.sel_slot_idx - 1) % num_slots
                self._redraw_event.set()
            elif ch == curses.KEY_RIGHT:
                self.sel_slot_idx = (self.sel_slot_idx + 1) % num_slots
                self._redraw_event.set()
            elif ch == curses.KEY_UP:
                self.sel_chan = (self.sel_chan - 2) % 15 + 1
                self._redraw_event.set()
            elif ch == curses.KEY_DOWN:
                self.sel_chan = (self.sel_chan) % 15 + 1
                self._redraw_event.set()
            
            # Global Commands
            elif ch == ord('q'): self._running = False
            elif ch == ord('E'): await self.call("EmergencyShutdown"); self._redraw_event.set()
            elif ch == ord('P'): await self.call("SetAllPowerEnabled", True); self._redraw_event.set()
            elif ch == ord('p'): await self.call("SetAllPowerEnabled", False); self._redraw_event.set()
            elif ch == ord('T'): await self.call("SetAllTriggerEnabled", True); self._redraw_event.set()
            elif ch == ord('t'): await self.call("SetAllTriggerEnabled", False); self._redraw_event.set()
            elif ch == ord('B'): await self.call("SetAllBusyEnabled", True); self._redraw_event.set()
            elif ch == ord('b'): await self.call("SetAllBusyEnabled", False); self._redraw_event.set()
            elif ch == ord('M'): await self.call("SetMCFEnabled", True); self._redraw_event.set()
            elif ch == ord('m'): await self.call("SetMCFEnabled", False); self._redraw_event.set()
            elif ch == ord('R'): await self.call("ResetTIBEventCount"); self._redraw_event.set()
            
            # Matrix Cycle
            elif ch == ord('c'):
                h, w = stdscr.getmaxyx()
                if w >= 160:
                    self.view_mode_right = (self.view_mode_right + 1) % 3
                    if self.view_mode_right == VIEW_CURRENT: self.view_mode_right = VIEW_TRIGGER
                else:
                    self.view_mode_narrow = (self.view_mode_narrow + 1) % 3
                self._redraw_event.set()

            # Parameters
            elif ch == ord('>'): await self.call("SetMCFThreshold", s.mcf_threshold + 1); self._redraw_event.set()
            elif ch == ord('<'): await self.call("SetMCFThreshold", max(0, s.mcf_threshold - 1)); self._redraw_event.set()
            elif ch == ord('}'): await self.call("SetMCFDelay", s.mcf_delay_ns + 5.0); self._redraw_event.set()
            elif ch == ord('{'): await self.call("SetMCFDelay", max(0.0, s.mcf_delay_ns - 5.0)); self._redraw_event.set()
            elif ch == ord('+'): await self.call("SetL1Deadtime", s.l1_deadtime_ns + 5.0); self._redraw_event.set()
            elif ch == ord('-'): await self.call("SetL1Deadtime", max(0.0, s.l1_deadtime_ns - 5.0)); self._redraw_event.set()
            
            # Targeted Commands
            target_slot = s.board_slots[self.sel_slot_idx] if s.board_slots else None
            module_idx = self.sel_slot_idx * 15 + (self.sel_chan - 1)
            
            if target_slot is not None:
                if ch == ord('O'): await self.call("SetSlotChannelPowerEnabled", target_slot, self.sel_chan, True); self._redraw_event.set()
                elif ch == ord('o'): await self.call("SetSlotChannelPowerEnabled", target_slot, self.sel_chan, False); self._redraw_event.set()
                elif ch == ord('Y'): await self.call("SetSlotChannelTriggerEnabled", target_slot, self.sel_chan, True); self._redraw_event.set()
                elif ch == ord('y'): await self.call("SetSlotChannelTriggerEnabled", target_slot, self.sel_chan, False); self._redraw_event.set()
                elif ch == ord('K'): await self.call("SetSlotBusyEnabled", target_slot, True); self._redraw_event.set()
                elif ch == ord('k'): await self.call("SetSlotBusyEnabled", target_slot, False); self._redraw_event.set()
                elif ch == ord('I'): await self.call("SetSlotChannelIsImmutable", target_slot, self.sel_chan, True); self._redraw_event.set()
                elif ch == ord('i'): await self.call("SetSlotChannelIsImmutable", target_slot, self.sel_chan, False); self._redraw_event.set()
                
                # Delay Step (up/down)
                elif ch == ord('D') or ch == ord('d'):
                    current_delay = s.mod_trig_delay[module_idx]
                    step = 0.037 if ch == ord('D') else -0.037
                    await self.call("SetSlotChannelTriggerDelay", target_slot, self.sel_chan, max(0.0, current_delay + step))
                    self._redraw_event.set()
                
                # Current Limits Step (up/down)
                elif ch in (ord('N'), ord('n'), ord('X'), ord('x')):
                    board_idx = self.sel_slot_idx
                    c_min = s.board_limit_min[board_idx]
                    c_max = s.board_limit_max[board_idx]
                    step = 10.0 # 10mA steps for TUI
                    
                    if ch == ord('N'): c_min += step
                    elif ch == ord('n'): c_min = max(0.0, c_min - step)
                    elif ch == ord('X'): c_max += step
                    elif ch == ord('x'): c_max = max(c_min, c_max - step)
                    
                    await self.call("SetSlotCurrentLimits", target_slot, c_min, c_max)
                    self._redraw_event.set()

    async def run(self, stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        
        try:
            await self.connect()
        except Exception as e:
            stdscr.addstr(0, 0, f"Connection Error: {e}")
            stdscr.addstr(1, 0, "Press any key to exit...")
            stdscr.nodelay(False)
            stdscr.getch()
            return

        input_task = asyncio.create_task(self.handle_input(stdscr))
        
        last_update = 0
        while self._running:
            now = time.monotonic()
            # Polling update (every 0.5s)
            if now - last_update > 0.5:
                await self.update_state()
                last_update = now
                self._redraw_event.set()

            if self._redraw_event.is_set():
                self.draw(stdscr)
                stdscr.refresh()
                self._redraw_event.clear()
            
            # Wait for next poll or immediate trigger from input
            try:
                await asyncio.wait_for(self._redraw_event.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                pass

        input_task.cancel()
        await self.client.disconnect()

def main():
    parser = argparse.ArgumentParser(description="L2 Trigger OPC UA TUI")
    parser.add_argument("--endpoint", default="opc.tcp://localhost:4840/l2trig/", help="OPC UA endpoint")
    args = parser.parse_args()

    tui = L2TrigTUI(args.endpoint)
    
    def _run_curses(stdscr):
        asyncio.run(tui.run(stdscr))

    try:
        curses.wrapper(_run_curses)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
