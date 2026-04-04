"""
l2trig_gui_tk.py

GUI Controller for L2 Trigger System OPC UA Server (Tkinter version)

Copyright 2026, Stephen Fegan <sfegan@llr.in2p3.fr>
Laboratoire Leprince-Ringuet, CNRS/IN2P3, Ecole Polytechnique, Institut Polytechnique de Paris
"""

import sys
import asyncio
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
from typing import Optional, List, Dict
from enum import Enum
import threading

from asyncua import Client
from asyncua.ua import UaStatusCodeError
from asyncua.common.subscription import DataChangeNotif

from l2trig_api import VALID_SLOTS


class DisplayMode(Enum):
    """Display mode for module matrix"""
    POWER = "Power Status"
    CURRENT = "Current (mA)"
    TRIGGER = "Trigger Enabled"
    DELAY = "Trigger Delay (ns)"
    STATE = "Module State"


class SubscriptionHandler:
    """Handler for OPC UA data change notifications"""
    
    def __init__(self, callback):
        self.callback = callback
        self.data_cache = {}
    
    async def datachange_notification(self, node, val, data: DataChangeNotif):
        """Called when subscribed data changes"""
        node_id = str(node)
        self.data_cache[node_id] = val
        # Call callback in thread-safe way
        self.callback(node_id, val)


class OPCUAClient:
    """Async OPC UA client wrapper"""
    
    def __init__(self, update_callback, log_callback=None):
        self.client: Optional[Client] = None
        self.namespace_idx: Optional[int] = None
        self.monitoring_vars: Dict[str, any] = {}
        self.monitoring_obj = None
        self.root_obj = None
        self.is_connected = False
        self.subscription = None
        self.handler = None
        self.var_name_map: Dict[str, str] = {}  # node_id -> variable name
        self.update_callback = update_callback
        self.log_callback = log_callback
        self.loop = None
        self.thread = None
        
    def _log(self, message):
        """Helper to call log callback if it exists"""
        if self.log_callback:
            self.log_callback(message)
        
    def start_loop(self):
        """Start the asyncio event loop in a separate thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    
    def run_async(self, coro):
        """Run a coroutine in the client's event loop"""
        if not self.loop:
            raise RuntimeError("Event loop not started")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)
    
    async def connect(self, endpoint: str, root: str = "L2Trigger", monitoring: str = "Monitoring"):
        """Connect to OPC UA server"""
        try:
            self.client = Client(endpoint)
            await self.client.connect()
            
            # Get namespace index
            uri = "http://cta.l2trigger.hal"
            self.namespace_idx = await self.client.get_namespace_index(uri)
            
            # Build path to root object
            root_path = f"0:Objects/{self.namespace_idx}:{root}"
            self.root_obj = await self.client.nodes.root.get_child(root_path.split("/"))
            
            # Build path to monitoring object
            monitoring_path = f"0:Objects/{self.namespace_idx}:{root}/{self.namespace_idx}:{monitoring}"
            self.monitoring_obj = await self.client.nodes.root.get_child(monitoring_path.split("/"))
            
            # Get all monitoring variables
            children = await self.monitoring_obj.get_children()
            for child in children:
                name = (await child.read_browse_name()).Name
                self.monitoring_vars[name] = child
                self.var_name_map[str(child)] = name
            
            # Create subscription
            self.handler = SubscriptionHandler(self._on_data_change)
            self.subscription = await self.client.create_subscription(100, self.handler)
            
            # Subscribe to all monitoring variables
            nodes_to_subscribe = list(self.monitoring_vars.values())
            await self.subscription.subscribe_data_change(nodes_to_subscribe)
            
            # Initial read of all variables
            for name, node in self.monitoring_vars.items():
                value = await node.read_value()
                self._on_data_change(str(node), value)
            
            self.is_connected = True
            return True
            
        except Exception as e:
            raise Exception(f"Connection failed: {e}")
    
    def _on_data_change(self, node_id: str, value):
        """Callback for subscription data changes"""
        var_name = self.var_name_map.get(node_id, node_id)
        # Call the update callback (will be scheduled on main thread)
        self.update_callback(var_name, value)
    
    async def disconnect(self):
        """Disconnect from OPC UA server"""
        if self.subscription:
            try:
                await self.subscription.delete()
            except:
                pass
            self.subscription = None
        
        if self.client:
            await self.client.disconnect()
            self.is_connected = False
    
    async def call_method(self, method_name: str, *args):
        """Call a method on the server"""
        try:
            if not self.is_connected:
                raise RuntimeError("Not connected to server")
            
            # Get method node from root object
            methods = await self.root_obj.get_methods()
            method_node = None
            for method in methods:
                name = (await method.read_browse_name()).Name
                if name == method_name:
                    method_node = method
                    break
            
            if not method_node:
                raise ValueError(f"Method {method_name} not found")
            
            # Call the method
            self._log(f"CMD: {method_name}({', '.join(map(str, args))})")
            result = await self.root_obj.call_method(method_node, *args)
            self._log(f"RES: {method_name} -> {result}")
            return result
            
        except UaStatusCodeError as e:
            self._log(f"ERR: {method_name} failed: {e}")
            raise RuntimeError(f"Method call failed: {e}")
        except Exception as e:
            self._log(f"ERR: {method_name} error: {e}")
            raise e
    
    async def read_variable(self, var_name: str):
        """Read a single variable value"""
        if var_name in self.monitoring_vars:
            return await self.monitoring_vars[var_name].read_value()
        return None


class ModuleIndicator(tk.Canvas):
    """Individual module status indicator"""
    
    def __init__(self, parent, slot: int, channel: int, click_callback, width=50, height=50, **kwargs):
        self.module_width = width
        self.module_height = height
        # Calculate appropriate font size based on module size
        self.font_size = max(5, int(min(width, height) / 8))
        
        super().__init__(parent, width=width, height=height, highlightthickness=1, **kwargs)
        self.slot = slot
        self.channel = channel
        self.module_idx = None
        self.click_callback = click_callback
        
        self.power_enabled = False
        self.current = 0.0
        self.state = "off"
        self.trigger_enabled = False
        self.trigger_delay = 0.0
        
        # Create text item - will be updated dynamically
        self.text_id = self.create_text(width/2, height/2, text="", font=("Monospace", self.font_size), fill="white")
        
        self.bind("<Button-1>", self.on_click)
        self.update_display()
    
    def set_size(self, new_width, new_height):
        """Update the size of the indicator"""
        if new_width == self.module_width and new_height == self.module_height:
            return
        self.module_width = new_width
        self.module_height = new_height
        self.font_size = max(5, int(min(new_width, new_height) / 8))
        self.config(width=new_width, height=new_height)
        self.coords(self.text_id, new_width/2, new_height/2)
        self.itemconfig(self.text_id, font=("Monospace", self.font_size))
        self.update_display()
    
    def on_click(self, event):
        """Handle click event"""
        if self.click_callback:
            self.click_callback(self)
    
    def update_display(self, mode=DisplayMode.POWER):
        """Update visual appearance based on current mode and state"""
        if mode == DisplayMode.POWER:
            if self.state == "on":
                bg = "#00cc00"
                fg = "black"
                text = f"S{self.slot}\nC{self.channel}\nON"
            elif self.state in ("error_over_current", "error_under_current", "error_both"):
                bg = "#ff0000"
                fg = "white"
                text = f"S{self.slot}\nC{self.channel}\nERR"
            else:  # off
                bg = "#666666"
                fg = "white"
                text = f"S{self.slot}\nC{self.channel}\nOFF"
        
        elif mode == DisplayMode.CURRENT:
            # Map current 0-200mA to color
            # Blue (0) -> Green (50) -> Yellow (100) -> Red (200+)
            val = min(max(self.current, 0.0), 200.0)
            if val < 50:
                r, g, b = 0, int(val * 255 / 50), 255
            elif val < 100:
                r, g, b = int((val - 50) * 255 / 50), 255, 255 - int((val - 50) * 255 / 50)
            else:
                r, g, b = 255, 255 - int((val - 100) * 255 / 100), 0
            bg = f"#{r:02x}{g:02x}{b:02x}"
            fg = "white" if val > 100 else "black"
            text = f"S{self.slot}\nC{self.channel}\n{self.current:.1f}"
        
        elif mode == DisplayMode.TRIGGER:
            if self.trigger_enabled:
                bg = "#0099ff"
                fg = "white"
                text = f"S{self.slot}\nC{self.channel}\nEN"
            else:
                bg = "#666666"
                fg = "white"
                text = f"S{self.slot}\nC{self.channel}\nDIS"
        
        elif mode == DisplayMode.DELAY:
            # Map delay 0-5ns to color (Blue to Red)
            val = min(max(self.trigger_delay, 0.0), 5.0)
            r = int(val * 255 / 5.0)
            b = 255 - r
            bg = f"#{r:02x}00{b:02x}"
            fg = "white"
            text = f"S{self.slot}\nC{self.channel}\n{self.trigger_delay:.2f}"
        
        elif mode == DisplayMode.STATE:
            state_colors = {
                "on": "#00cc00",
                "off": "#666666",
                "error_over_current": "#ff0000",
                "error_under_current": "#ff8800",
                "error_both": "#cc0000"
            }
            bg = state_colors.get(self.state, "#666666")
            fg = "white"
            state_text = self.state.replace("error_", "").replace("_", "\n").upper()
            text = f"S{self.slot}\nC{self.channel}\n{state_text[:6]}"
        
        self.configure(bg=bg)
        self.itemconfig(self.text_id, text=text, fill=fg)


class ModuleMatrix(tk.Frame):
    """Matrix of module indicators arranged by slot"""
    
    def __init__(self, parent, slots: List[int], opcua_client, **kwargs):
        super().__init__(parent, **kwargs)
        self.slots = sorted(slots)
        self.display_mode = DisplayMode.POWER
        self.modules: List[ModuleIndicator] = []
        self.opcua_client = opcua_client
        self.min_module_width = 10
        self.min_module_height = 10
        
        self.init_ui()
        self.bind("<Configure>", self.on_resize)
    
    def calculate_module_size(self):
        """Calculate appropriate module dimensions based on available space"""
        if not self.slots:
            return 40, 40
        
        # Get the size of this frame
        self.update_idletasks()
        available_width = self.winfo_width()
        available_height = self.winfo_height()
        
        # If window hasn't been rendered yet, use default
        if available_width <= 1 or available_height <= 1:
            return 40, 40
        
        # Each slot needs: module width + 2*padx + LabelFrame overhead
        slot_overhead_w = 20  # Total overhead per slot frame width
        num_slots = len(self.slots)
        
        # Calculate available width for each module
        total_overhead_w = num_slots * slot_overhead_w
        available_for_modules_w = max(0, available_width - total_overhead_w)
        width_per_slot = available_for_modules_w // num_slots if num_slots > 0 else 40
        
        # Each channel needs: module height + 2*pady + LabelFrame overhead
        # 15 channels per slot
        slot_overhead_h = 40  # Overhead for LabelFrame title and borders
        available_for_modules_h = max(0, available_height - slot_overhead_h)
        height_per_ch = available_for_modules_h // 15
        
        # Constrain to reasonable bounds
        target_w = max(self.min_module_width, width_per_slot)
        target_h = max(self.min_module_height, height_per_ch)
        
        return target_w, target_h
    
    def on_resize(self, event=None):
        """Handle frame resize event"""
        new_w, new_h = self.calculate_module_size()
        for module in self.modules:
            module.set_size(new_w, new_h)
    
    def init_ui(self):
        """Initialize the module matrix UI"""
        # Configure columns for expansion
        for col_idx in range(len(self.slots)):
            self.columnconfigure(col_idx, weight=1)
        self.rowconfigure(0, weight=1)

        # Use a reasonable default size for initial layout
        initial_w, initial_h = 40, 40
        
        for slot in self.slots:
            try:
                slot_col = self.slots.index(slot)
                slot_idx = VALID_SLOTS.index(slot)
            except ValueError:
                print(f"Warning: Slot {slot} not in VALID_SLOTS")
                continue

            slot_frame = ttk.LabelFrame(self, text=f"S{slot}")
            slot_frame.grid(row=0, column=slot_col, padx=1, pady=1, sticky=tk.NSEW)
            
            # Configure slot_frame to expand its rows
            for row_idx in range(15):
                slot_frame.rowconfigure(row_idx, weight=1)
            slot_frame.columnconfigure(0, weight=1)

            for ch in range(1, 16):  # Channels 1-15
                indicator = ModuleIndicator(
                    slot_frame, slot, ch, self.on_module_clicked, width=initial_w, height=initial_h
                )
                indicator.module_idx = slot_idx * 15 + ch
                indicator.grid(row=ch-1, column=0, padx=1, pady=1, sticky=tk.NSEW)
                self.modules.append(indicator)
    
    def set_display_mode(self, mode: DisplayMode):
        """Change the display mode for all modules"""
        self.display_mode = mode
        for module in self.modules:
            module.update_display(mode)
    
    def on_module_clicked(self, indicator: ModuleIndicator):
        """Handle module click - toggle power or trigger based on mode"""
        if self.display_mode == DisplayMode.POWER or self.display_mode == DisplayMode.CURRENT:
            # Toggle power
            new_state = not indicator.power_enabled
            self.opcua_client.run_async(
                self.opcua_client.call_method("SetModulePowerEnabled", 
                                             indicator.module_idx, new_state)
            )
        
        elif self.display_mode == DisplayMode.TRIGGER:
            # Toggle trigger
            new_state = not indicator.trigger_enabled
            self.opcua_client.run_async(
                self.opcua_client.call_method("SetModuleTriggerEnabled",
                                             indicator.module_idx, new_state)
            )
            
        elif self.display_mode == DisplayMode.DELAY:
            # Ask for new delay
            new_delay = simpledialog.askfloat(
                "Trigger Delay",
                f"Enter new trigger delay for Slot {indicator.slot} Ch {indicator.channel} (ns):",
                initialvalue=indicator.trigger_delay,
                minvalue=0.0, maxvalue=5.0
            )
            if new_delay is not None:
                self.opcua_client.run_async(
                    self.opcua_client.call_method("SetModuleTriggerDelay",
                                                 indicator.module_idx, float(new_delay))
                )
    
    def update_from_data(self, var_name: str, value):
        """Update module states from OPC UA data"""
        if var_name == "ModulePowerEnabled":
            try:
                for idx, val in enumerate(value):
                    if idx < len(self.modules):
                        self.modules[idx].power_enabled = bool(val)
                        self.modules[idx].update_display(self.display_mode)
            except TypeError:
                pass
        
        elif var_name == "ModuleCurrent":
            try:
                for idx, val in enumerate(value):
                    if idx < len(self.modules):
                        self.modules[idx].current = float(val)
                        self.modules[idx].update_display(self.display_mode)
            except TypeError:
                pass
        
        elif var_name == "ModuleState":
            try:
                for idx, val in enumerate(value):
                    if idx < len(self.modules):
                        self.modules[idx].state = str(val)
                        self.modules[idx].update_display(self.display_mode)
            except TypeError:
                pass
        
        elif var_name == "ModuleTriggerEnabled":
            try:
                for idx, val in enumerate(value):
                    if idx < len(self.modules):
                        self.modules[idx].trigger_enabled = bool(val)
                        self.modules[idx].update_display(self.display_mode)
            except TypeError:
                pass

        elif var_name == "ModuleTriggerDelay":
            try:
                for idx, val in enumerate(value):
                    if idx < len(self.modules):
                        self.modules[idx].trigger_delay = float(val)
                        self.modules[idx].update_display(self.display_mode)
            except TypeError:
                pass


class ControlPanel(tk.Frame):
    """Control panel for crate-level settings"""
    
    def __init__(self, parent, opcua_client, **kwargs):
        super().__init__(parent, **kwargs)
        self.opcua_client = opcua_client
        self.init_ui()
    
    def init_ui(self):
        """Initialize control panel UI"""
        # Crate controls group
        crate_frame = ttk.LabelFrame(self, text="Crate Controls", padding=5)
        crate_frame.pack(fill=tk.X, padx=2, pady=2)  # fill X only, no expand
        
        row = 0
        
        # MCF Enabled
        self.mcf_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(
            crate_frame, text="MCF Enabled", 
            variable=self.mcf_enabled_var,
            command=self.on_mcf_enabled_changed
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=1)
        row += 1
        
        # Busy Glitch Filter
        self.busy_filter_var = tk.BooleanVar()
        ttk.Checkbutton(
            crate_frame, text="Busy Glitch Filter",
            variable=self.busy_filter_var,
            command=self.on_busy_filter_changed
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=1)
        row += 1
        
        # TIB Trigger Busy Block
        self.tib_block_var = tk.BooleanVar()
        ttk.Checkbutton(
            crate_frame, text="TIB Trigger Busy Block",
            variable=self.tib_block_var,
            command=self.on_tib_block_changed
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=1)
        row += 1
        
        # MCF Threshold
        ttk.Label(crate_frame, text="MCF Threshold:").grid(row=row, column=0, sticky=tk.W, pady=1)
        self.mcf_threshold_var = tk.IntVar(value=0)
        threshold_spin = ttk.Spinbox(
            crate_frame, from_=0, to=512, textvariable=self.mcf_threshold_var,
            width=8, command=self.on_mcf_threshold_changed
        )
        threshold_spin.grid(row=row, column=1, sticky=tk.EW, pady=1)
        threshold_spin.bind('<Return>', lambda e: self.on_mcf_threshold_changed())
        row += 1
        
        # MCF Delay
        ttk.Label(crate_frame, text="MCF Delay (ns):").grid(row=row, column=0, sticky=tk.W, pady=1)
        self.mcf_delay_var = tk.DoubleVar(value=0.0)
        delay_spin = ttk.Spinbox(
            crate_frame, from_=0, to=75.0, increment=5.0,
            textvariable=self.mcf_delay_var, width=8,
            command=self.on_mcf_delay_changed
        )
        delay_spin.grid(row=row, column=1, sticky=tk.EW, pady=1)
        delay_spin.bind('<Return>', lambda e: self.on_mcf_delay_changed())
        row += 1
        
        # L1 Deadtime
        ttk.Label(crate_frame, text="L1 Deadtime (ns):").grid(row=row, column=0, sticky=tk.W, pady=1)
        self.l1_deadtime_var = tk.DoubleVar(value=0.0)
        deadtime_spin = ttk.Spinbox(
            crate_frame, from_=0, to=1275.0, increment=5.0,
            textvariable=self.l1_deadtime_var, width=8,
            command=self.on_l1_deadtime_changed
        )
        deadtime_spin.grid(row=row, column=1, sticky=tk.EW, pady=1)
        deadtime_spin.bind('<Return>', lambda e: self.on_l1_deadtime_changed())
        row += 1
        
        # Configure column to expand
        crate_frame.columnconfigure(1, weight=1)
        
        # Power control group
        power_frame = ttk.LabelFrame(self, text="Power Control", padding=5)
        power_frame.pack(fill=tk.X, padx=2, pady=2)  # fill X only, no expand
        
        ttk.Button(
            power_frame, text="Ramp Up All Power",
            command=self.on_ramp_up
        ).pack(fill=tk.X, pady=1)
        
        ttk.Button(
            power_frame, text="Ramp Down All Power",
            command=self.on_ramp_down
        ).pack(fill=tk.X, pady=1)
        
        emergency_btn = tk.Button(
            power_frame, text="EMERGENCY STOP",
            command=self.on_emergency_stop,
            bg="white", fg="red", font=("TkDefaultFont", 10, "bold")
        )
        emergency_btn.pack(fill=tk.X, pady=1)
        
        # Trigger control group
        trigger_frame = ttk.LabelFrame(self, text="Trigger Control", padding=5)
        trigger_frame.pack(fill=tk.X, padx=2, pady=2)  # fill X only, no expand
        
        ttk.Button(
            trigger_frame, text="Enable All Triggers",
            command=self.on_enable_all_triggers
        ).pack(fill=tk.X, pady=1)
        
        ttk.Button(
            trigger_frame, text="Disable All Triggers",
            command=self.on_disable_all_triggers
        ).pack(fill=tk.X, pady=1)
    
    def on_mcf_enabled_changed(self):
        self.opcua_client.run_async(
            self.opcua_client.call_method("SetMCFEnabled", self.mcf_enabled_var.get())
        )
    
    def on_busy_filter_changed(self):
        self.opcua_client.run_async(
            self.opcua_client.call_method("SetBusyGlitchFilterEnabled", self.busy_filter_var.get())
        )
    
    def on_tib_block_changed(self):
        self.opcua_client.run_async(
            self.opcua_client.call_method("SetTIBTriggerBusyBlockEnabled", self.tib_block_var.get())
        )
    
    def on_mcf_threshold_changed(self):
        self.opcua_client.run_async(
            self.opcua_client.call_method("SetMCFThreshold", self.mcf_threshold_var.get())
        )
    
    def on_mcf_delay_changed(self):
        self.opcua_client.run_async(
            self.opcua_client.call_method("SetMCFDelay", self.mcf_delay_var.get())
        )
    
    def on_l1_deadtime_changed(self):
        self.opcua_client.run_async(
            self.opcua_client.call_method("SetL1Deadtime", self.l1_deadtime_var.get())
        )
    
    def on_ramp_up(self):
        if messagebox.askyesno("Confirm Ramp Up", 
                               "Are you sure you want to ramp up all module power?"):
            self.opcua_client.run_async(
                self.opcua_client.call_method("SetAllPowerEnabled", True)
            )
    
    def on_ramp_down(self):
        if messagebox.askyesno("Confirm Ramp Down",
                               "Are you sure you want to ramp down all module power?"):
            self.opcua_client.run_async(
                self.opcua_client.call_method("SetAllPowerEnabled", False)
            )
    
    def on_emergency_stop(self):
        if messagebox.askyesno("EMERGENCY STOP",
                               "This will immediately disable all module power!\n\nAre you sure?",
                               icon='warning'):
            self.opcua_client.run_async(
                self.opcua_client.call_method("EmergencyShutdown")
            )
    
    def on_enable_all_triggers(self):
        if messagebox.askyesno("Enable All Triggers",
                               "Are you sure you want to enable triggers on all modules?"):
            self.opcua_client.run_async(
                self.opcua_client.call_method("SetAllTriggerEnabled", True)
            )
    
    def on_disable_all_triggers(self):
        if messagebox.askyesno("Disable All Triggers",
                               "Are you sure you want to disable triggers on all modules?"):
            self.opcua_client.run_async(
                self.opcua_client.call_method("SetAllTriggerEnabled", False)
            )
    
    def update_from_data(self, var_name: str, value):
        """Update controls from OPC UA data"""
        if var_name == "CrateMCFEnabled":
            self.mcf_enabled_var.set(bool(value))
        elif var_name == "CrateBusyGlitchFilterEnabled":
            self.busy_filter_var.set(bool(value))
        elif var_name == "CrateTIBTriggerBusyBlockEnabled":
            self.tib_block_var.set(bool(value))
        elif var_name == "CrateMCFThreshold":
            self.mcf_threshold_var.set(int(value))
        elif var_name == "CrateMCFDelay":
            self.mcf_delay_var.set(float(value))
        elif var_name == "CrateL1Deadtime":
            self.l1_deadtime_var.set(float(value))


class StatusPanel(tk.Frame):
    """Status display panel"""
    
    def __init__(self, parent, opcua_client, **kwargs):
        super().__init__(parent, **kwargs)
        self.opcua_client = opcua_client
        self.init_ui()
    
    def init_ui(self):
        """Initialize status panel UI"""
        # Crate status
        crate_frame = ttk.LabelFrame(self, text="Crate Status", padding=5)  # Reduced padding
        crate_frame.pack(fill=tk.X, padx=2, pady=2)  # Reduced padding
        
        ttk.Label(crate_frame, text="Firmware:").grid(row=0, column=0, sticky=tk.W, pady=1)
        self.fw_label = ttk.Label(crate_frame, text="--")
        self.fw_label.grid(row=0, column=1, sticky=tk.W, pady=1)
        
        ttk.Label(crate_frame, text="Uptime:").grid(row=1, column=0, sticky=tk.W, pady=1)
        self.uptime_label = ttk.Label(crate_frame, text="--")
        self.uptime_label.grid(row=1, column=1, sticky=tk.W, pady=1)
        
        ttk.Label(crate_frame, text="Powered Modules:").grid(row=2, column=0, sticky=tk.W, pady=1)
        self.powered_label = ttk.Label(crate_frame, text="--")
        self.powered_label.grid(row=2, column=1, sticky=tk.W, pady=1)
        
        ttk.Label(crate_frame, text="Trigger Enabled:").grid(row=3, column=0, sticky=tk.W, pady=1)
        self.trigger_label = ttk.Label(crate_frame, text="--")
        self.trigger_label.grid(row=3, column=1, sticky=tk.W, pady=1)
    
    def update_from_data(self, var_name: str, value):
        """Update status displays from OPC UA data"""
        if var_name == "CrateFirmwareRevision":
            self.fw_label.config(text=str(value))
        
        elif var_name == "CrateUpTime":
            seconds = value / 1e9
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            minutes = int((seconds % 3600) // 60)
            self.uptime_label.config(text=f"{days}d {hours:02d}h {minutes:02d}m")
        
        elif var_name == "CrateNumPoweredModules":
            self.powered_label.config(text=str(value))
        
        elif var_name == "CrateNumTriggerEnabledModules":
            self.trigger_label.config(text=str(value))


class MainWindow:
    """Main application window"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("L2 Trigger System Control")
        self.root.geometry("1400x900")

        # OPC UA client with update callback
        self.opcua_client = OPCUAClient(self.on_data_updated, self.on_log_message)

        # Start the asyncio loop in a separate thread
        self.opcua_client.thread = threading.Thread(
            target=self.opcua_client.start_loop, daemon=True
        )
        self.opcua_client.thread.start()

        self.module_matrix = None
        self.control_panel = None
        self.status_panel = None

        self.init_ui()

    def init_ui(self):
        """Initialize the main UI"""
        # Top connection panel
        conn_frame = ttk.Frame(self.root)
        conn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(conn_frame, text="Endpoint:").pack(side=tk.LEFT, padx=5)

        self.endpoint_var = tk.StringVar(value="opc.tcp://localhost:4840/l2trigger/")
        endpoint_entry = ttk.Entry(conn_frame, textvariable=self.endpoint_var, width=40)
        endpoint_entry.pack(side=tk.LEFT, padx=5)

        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.on_connect)
        self.connect_btn.pack(side=tk.LEFT, padx=5)

        self.disconnect_btn = ttk.Button(conn_frame, text="Disconnect", command=self.on_disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)

        ttk.Label(conn_frame, text="Display Mode:").pack(side=tk.LEFT, padx=5)

        self.mode_var = tk.StringVar(value=DisplayMode.POWER.value)
        mode_combo = ttk.Combobox(
            conn_frame, textvariable=self.mode_var,
            values=[mode.value for mode in DisplayMode],
            state="readonly", width=20
        )
        mode_combo.pack(side=tk.LEFT, padx=5)
        mode_combo.bind("<<ComboboxSelected>>", self.on_mode_changed)

        # Status label
        self.status_label = ttk.Label(conn_frame, text="Disconnected", foreground="red")
        self.status_label.pack(side=tk.RIGHT, padx=5)

        # Main content area
        content_frame = ttk.Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        content_frame.columnconfigure(0, weight=5)  # Module matrix gets all expanding space
        content_frame.columnconfigure(1, weight=0, minsize=300)  # Right panel fixed to natural width
        content_frame.rowconfigure(0, weight=1)

        # C1 (Left): Module matrix - fits directly into frame to allow resizing
        matrix_frame = ttk.Frame(content_frame)
        matrix_frame.grid(row=0, column=0, sticky=tk.NSEW)
        self.matrix_container = matrix_frame

        # Initialize matrix directly in the frame
        self.module_matrix = ModuleMatrix(
            self.matrix_container,
            VALID_SLOTS,
            self.opcua_client
        )
        self.module_matrix.pack(fill=tk.BOTH, expand=True)

        # C2 (Right panel): Status and Controls stacked vertically
        c2 = ttk.Frame(content_frame)
        c2.grid(row=0, column=1, sticky=tk.NSEW, padx=(5, 0))

        c2.columnconfigure(0, weight=1)
        c2.rowconfigure(0, weight=0)  # Status panel - fixed height
        c2.rowconfigure(1, weight=0)  # Controls panel - fixed height
        c2.rowconfigure(2, weight=1)  # Log panel - takes remaining space

        # Status Panel
        self.status_panel = StatusPanel(c2, self.opcua_client)
        self.status_panel.grid(row=0, column=0, sticky=tk.EW, pady=(0, 2))

        # Control Panel - No scrollbar
        self.control_panel = ControlPanel(c2, self.opcua_client)
        self.control_panel.grid(row=1, column=0, sticky=tk.NSEW, pady=2)

        # Log Panel
        log_frame = ttk.LabelFrame(c2, text="System Log")
        log_frame.grid(row=2, column=0, sticky=tk.NSEW, pady=(2, 0))
        
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        # Set width=1 to allow the log to be as narrow as the other widgets in the column
        self.log_text = scrolledtext.ScrolledText(log_frame, height=5, width=1, font=("Monospace", 8), state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW, padx=2, pady=2)
    def on_log_message(self, message):
        """Handle log message (runs on background thread, schedules on main)"""
        if self.root:
            self.root.after(0, lambda: self._add_log(message))
            
    def _add_log(self, message):
        """Append message to log window"""
        self.log_text.config(state=tk.NORMAL)
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # Keep log from growing indefinitely
        try:
            num_lines = int(self.log_text.index('end-1c').split('.')[0])
            if num_lines > 1000:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.delete('1.0', '200.0')
                self.log_text.config(state=tk.DISABLED)
        except:
            pass
    
    def on_connect(self):
        """Connect to OPC UA server"""
        endpoint = self.endpoint_var.get()
        self.status_label.config(text="Connecting...", foreground="orange")
        
        def connect_async():
            try:
                future = self.opcua_client.run_async(
                    self.opcua_client.connect(endpoint)
                )
                result = future.result(timeout=10)
                
                # Update UI on main thread
                self.root.after(0, self.on_connection_success)
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self.on_connection_error(error_msg))
        
        threading.Thread(target=connect_async, daemon=True).start()
    
    def on_connection_success(self):
        """Handle successful connection"""
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Connected", foreground="green")
        
        # Request all current state variables
        self.opcua_client.run_async(self.opcua_client.call_method("HealthCheck"))

        # Update slot configuration
        def update_slots():
            try:
                future = self.opcua_client.run_async(
                    self.opcua_client.read_variable("BoardSlots")
                )
                slots = future.result(timeout=5)
                if slots:
                    self.root.after(0, lambda: self.update_slot_configuration(slots))
            except Exception as e:
                print(f"Error reading slots: {e}")
        
        threading.Thread(target=update_slots, daemon=True).start()
    
    def on_connection_error(self, error_msg):
        """Handle connection error"""
        self.status_label.config(text="Connection Failed", foreground="red")
        messagebox.showerror("Connection Error", error_msg)
    
    def update_slot_configuration(self, slots):
        """Update module matrix based on active slots from server"""
        # Get current slot configuration from the existing module_matrix
        current_slots = []
        if self.module_matrix and self.module_matrix.slots:
            current_slots = self.module_matrix.slots

        # If slots are the same, no need to recreate.
        # The pending _update_ui calls should handle updating the existing modules.
        if sorted(slots) == sorted(current_slots):
            # print("Slots are the same, not recreating module matrix.") # Optional: for debugging
            return

        # print(f"Slots changed from {current_slots} to {slots}. Recreating module matrix.") # Optional: for debugging

        # Destroy old matrix
        if self.module_matrix:
            self.module_matrix.destroy()
            self.module_matrix = None # Ensure it's properly nulled out

        # Create new matrix with correct slots
        self.module_matrix = ModuleMatrix(
            self.matrix_container, slots, self.opcua_client
        )
        self.module_matrix.pack(fill=tk.BOTH, expand=True)
        
        self.matrix_container.update_idletasks()

        # The _update_ui calls scheduled from on_data_updated will now target the new module_matrix
        # and update its indicators with the correct initial data.

    
    def on_disconnect(self):
        """Disconnect from OPC UA server"""
        def disconnect_async():
            try:
                future = self.opcua_client.run_async(
                    self.opcua_client.disconnect()
                )
                future.result(timeout=5)
                self.root.after(0, self.on_disconnection_success)
            except Exception as e:
                print(f"Disconnect error: {e}")
                self.root.after(0, self.on_disconnection_success)
        
        threading.Thread(target=disconnect_async, daemon=True).start()
    
    def on_disconnection_success(self):
        """Handle successful disconnection"""
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Disconnected", foreground="red")
    
    def on_mode_changed(self, event=None):
        """Handle display mode change"""
        mode_name = self.mode_var.get()
        mode = next((m for m in DisplayMode if m.value == mode_name), DisplayMode.POWER)
        if self.module_matrix:
            self.module_matrix.set_display_mode(mode)
    
    def on_data_updated(self, var_name: str, value):
        """Handle data update from OPC UA subscription (called from background thread)"""
        # Log the update
        if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
            try:
                val_list = list(value)
                if len(val_list) > 3:
                    val_str = f"[{val_list[0]}, {val_list[1]}, {val_list[2]}, ... ({len(val_list)} items)]"
                else:
                    val_str = str(val_list)
            except:
                val_str = str(value)
        else:
            val_str = str(value)
            
        self.on_log_message(f"SUB: {var_name} = {val_str}")
        
        # Schedule update on main thread
        self.root.after(0, lambda: self._update_ui(var_name, value))
    
    def _update_ui(self, var_name: str, value):
        """Update UI components (runs on main thread)"""
        if self.module_matrix:
            self.module_matrix.update_from_data(var_name, value)
        if self.control_panel:
            self.control_panel.update_from_data(var_name, value)
        if self.status_panel:
            self.status_panel.update_from_data(var_name, value)
    
    def on_close(self):
        """Handle window close"""
        if self.opcua_client.is_connected:
            self.opcua_client.run_async(self.opcua_client.disconnect())
        
        if self.opcua_client.loop:
            self.opcua_client.loop.call_soon_threadsafe(self.opcua_client.loop.stop)
        
        self.root.destroy()


def main():
    """Main entry point"""
    root = tk.Tk()
    app = MainWindow(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
