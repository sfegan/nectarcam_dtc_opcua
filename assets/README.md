# System Architecture Diagram

This directory contains the system architecture diagram for the L2 Trigger System.

## Diagram (Mermaid Source)

You can copy the code below into your `README.md` to display the diagram (supported by GitHub, GitLab, and many Markdown editors).

```mermaid
graph TD
    subgraph UserLayer ["<b><font size='4'>User Layer (Control PC)</font></b>"]
        direction TB
        User(("👤 User"))
        GUI["l2trig_gui.py<br/>(GUI Client)"]
        OPC_CLI["l2trig_test_opcua_cli.py<br/>(OPC UA CLI)"]
        TCP_CLI["l2trig_test_tcp_cli.py<br/>(TCP Test Client)"]
        
        %% Internal links
        User --- GUI
        User --- OPC_CLI
        User --- TCP_CLI
    end

    subgraph ControlLayer ["<b><font size='4'>Control Layer</font></b>"]
        Bridge["l2trig_asyncua_bridge.py<br/>(OPC UA Bridge)"]
    end

    subgraph EmbeddedLayer ["<b><font size='4'>Embedded Layer (ARM Board)</font></b>"]
        direction TB
        Backend["l2tcp_server_main.c<br/>(Backend TCP Server)"]
        DirectCLI["l2trig_direct_client.c<br/>(Direct CLI Tool)"]
        HAL["L2 Trigger HAL<br/>(smc.c / l2trig_hal.c)"]
        
        %% Internal links
        Backend --- HAL
        DirectCLI --- HAL
    end

    subgraph HardwareLayer ["<b><font size='4'>Hardware Layer</font></b>"]
        L2CB["L2CB FPGA"]
        CTDB["CTDB (x18)"]
        
        %% Internal links
        L2CB ---|SPI| CTDB
    end

    %% Cross-layer links
    User -.-|SSH| DirectCLI
    GUI ---|OPC UA| Bridge
    OPC_CLI ---|OPC UA| Bridge
    Bridge ---|TCP/IP| Backend
    TCP_CLI ---|TCP/IP| Backend
    HAL ---|Shared Registers| L2CB

    %% Styling
    style UserLayer fill:#f5f5f5,stroke:#333,stroke-width:2px
    style ControlLayer fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style EmbeddedLayer fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style HardwareLayer fill:#fff3e0,stroke:#e65100,stroke-width:2px
    
    style User fill:#ffffff,stroke:#333,stroke-width:2px
```

## Layer Descriptions

- **User Layer**: High-level clients for monitoring and control.
- **Telescope Control Layer**: The bridge between the standard OPC UA protocol and the custom backend TCP protocol.
- **Embedded Layer**: Software running directly on the ARM-based controller board.
- **Hardware Layer**: The physical L2CB and CTDB hardware components.
