# MCP Communication Protocols Guide

This guide explains the different communication protocols used by MCP servers depending on deployment mode, with focus on the stdio protocol used for local deployments.

## 📡 MCP Communication Protocols Overview

```
Local Deployment (stdio):
┌─────────────────┐    ┌─────────────────┐
│   Cursor/IDE    │◄──►│   MCP Server    │
│   (Parent)      │    │  (Subprocess)   │
│                 │    │                 │
│  stdin/stdout   │◄──►│  stdin/stdout   │
│   JSON-RPC      │    │   JSON-RPC      │
└─────────────────┘    └─────────────────┘

Remote Deployment (HTTP/SSE):
┌─────────────────┐    ┌─────────────────┐
│   Local Client  │    │  Remote Server  │
│   (MCP Adapter) │◄──►│   (HTTP API)    │
│                 │    │                 │
│  HTTPS/WSS      │◄──►│  HTTPS/WSS      │
│   JSON-RPC      │    │   JSON-RPC      │
└─────────────────┘    └─────────────────┘
```

---

## 🔌 Local Deployment: stdio Protocol

### How stdio Communication Works

**1. Process Spawning:**
When Cursor/VS Code starts, it reads the MCP configuration and spawns the server as a subprocess:

```bash
# What Cursor does internally:
python /path/to/mcp_server.py --collection-name api-docs --chroma-path ./db
```

**2. stdio Pipes:**
The IDE creates bidirectional pipes to communicate with the subprocess:
- **stdin** → IDE sends commands to server
- **stdout** → Server sends responses to IDE  
- **stderr** → Server logs (optional, for debugging)

**3. JSON-RPC Messages:**
All communication uses JSON-RPC 2.0 format over the stdio pipes.

### Implementation Details

Here's how the stdio protocol is implemented in the MCP server:

```python
#!/usr/bin/env python3
"""
MCP Server with stdio communication (local deployment)
"""

import asyncio
import json
import sys
from typing import Any, Dict, List
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server

class LocalMCPServer:
    """MCP Server using stdio for local communication."""
    
    def __init__(self):
        self.server = Server("local-api-docs")
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup MCP protocol handlers."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List available tools."""
            return [
                types.Tool(
                    name="search_api_docs",
                    description="Search API documentation",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls."""
            if name == "search_api_docs":
                query = arguments.get("query", "")
                # Perform search logic here
                result = f"Search results for: {query}"
                return [types.TextContent(type="text", text=result)]
            
            return [types.TextContent(type="text", text="Unknown tool")]
    
    async def run_stdio(self):
        """Run server using stdio transport."""
        # This creates the stdio server that communicates via stdin/stdout
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                NotificationOptions()
            )

async def main():
    """Main entry point for stdio server."""
    server = LocalMCPServer()
    
    # Run the server - this will block and handle stdio communication
    await server.run_stdio()

if __name__ == "__main__":
    # When run as subprocess, this starts stdio communication
    asyncio.run(main())
```

### Message Flow Example

**1. IDE starts server:**
```bash
# Cursor spawns subprocess
python mcp_server.py --collection-name my-docs
```

**2. Initialization handshake:**
```json
// IDE → Server (via stdin)
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "cursor",
      "version": "1.0.0"
    }
  }
}

// Server → IDE (via stdout)
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {}
    },
    "serverInfo": {
      "name": "api-docs-server",
      "version": "1.0.0"
    }
  }
}
```

**3. Tool discovery:**
```json
// IDE → Server
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list"
}

// Server → IDE
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "search_api_docs",
        "description": "Search API documentation",
        "inputSchema": {
          "type": "object",
          "properties": {
            "query": {"type": "string"}
          },
          "required": ["query"]
        }
      }
    ]
  }
}
```

**4. Tool execution:**
```json
// IDE → Server (when user asks AI a question)
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_api_docs",
    "arguments": {
      "query": "authentication examples"
    }
  }
}

// Server → IDE
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 5 authentication examples:\n\n1. OAuth 2.0 flow...\n2. API key authentication..."
      }
    ]
  }
}
```

### stdio vs Other Protocols

| Aspect | stdio (Local) | HTTP/SSE (Remote) | WebSocket (Remote) |
|--------|---------------|-------------------|-------------------|
| **Transport** | stdin/stdout pipes | HTTP requests | WebSocket frames |
| **Connection** | Subprocess | Network TCP | Network TCP |
| **Security** | Process isolation | TLS encryption | TLS encryption |
| **Latency** | Microseconds | Network latency | Network latency |
| **Setup** | Zero config | Server setup | Server setup |
| **Firewall** | No issues | Port configuration | Port configuration |
| **Debugging** | stderr logs | HTTP logs | WebSocket logs |

---

## 🔧 stdio Implementation Deep Dive

### How Cursor/VS Code Manages stdio

**Process Lifecycle:**
```python
# Pseudocode of what Cursor does internally

class MCPServerManager:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.stdin_writer = None
        self.stdout_reader = None
    
    async def start_server(self):
        """Start MCP server subprocess."""
        # Spawn the subprocess
        self.process = await asyncio.create_subprocess_exec(
            self.config["command"],
            *self.config["args"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.config.get("env", {})
        )
        
        # Setup communication streams
        self.stdin_writer = self.process.stdin
        self.stdout_reader = self.process.stdout
        
        # Start message handling
        await self.initialize_server()
    
    async def send_message(self, message):
        """Send JSON-RPC message to server."""
        json_data = json.dumps(message) + '\n'
        self.stdin_writer.write(json_data.encode())
        await self.stdin_writer.drain()
    
    async def read_message(self):
        """Read JSON-RPC message from server."""
        line = await self.stdout_reader.readline()
        return json.loads(line.decode())
```

### Error Handling in stdio

**Server-side error handling:**
```python
import sys
import logging

# Setup logging to stderr (doesn't interfere with stdio communication)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # Important: use stderr, not stdout
)

logger = logging.getLogger(__name__)

class StdioMCPServer:
    async def handle_tool_call(self, name: str, arguments: dict):
        """Handle tool call with proper error handling."""
        try:
            # Tool logic here
            result = await self.execute_tool(name, arguments)
            return result
        
        except Exception as e:
            # Log error to stderr (visible in IDE logs)
            logger.error(f"Tool execution failed: {e}")
            
            # Return error to client via stdout
            return [types.TextContent(
                type="text",
                text=f"Error: {str(e)}"
            )]
```

### stdio Message Framing

**Line-delimited JSON:**
Each JSON-RPC message is sent as a single line followed by `\n`:

```
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}\n
{"jsonrpc":"2.0","id":1,"result":{...}}\n
{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n
```

**Why line-delimited?**
- Simple parsing
- No need for Content-Length headers (like HTTP)
- Natural message boundaries
- Easy debugging

---

## 🌐 Remote Protocols (For Comparison)

### HTTP/SSE (Server-Sent Events)

```python
# Remote server using HTTP/SSE
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.post("/mcp/tools/call")
async def call_tool(request: dict):
    """HTTP endpoint for tool calls."""
    return {"result": await execute_tool(request)}

@app.get("/mcp/events")
async def event_stream():
    """SSE endpoint for real-time updates."""
    async def generate():
        while True:
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(1)
    
    return StreamingResponse(generate(), media_type="text/plain")
```

### WebSocket

```python
# Remote server using WebSocket
import websockets

async def handle_websocket(websocket, path):
    """Handle WebSocket MCP communication."""
    async for message in websocket:
        request = json.loads(message)
        response = await handle_mcp_request(request)
        await websocket.send(json.dumps(response))

start_server = websockets.serve(handle_websocket, "localhost", 8765)
```

---

## 🔍 Debugging stdio Communication

### Enable MCP Debugging in Cursor

**Method 1: Environment Variable**
```bash
export MCP_DEBUG=1
cursor
```

**Method 2: VS Code Settings**
```json
{
  "mcp.debug": true,
  "mcp.logLevel": "debug"
}
```

### Debug the MCP Server

**Add debug logging:**
```python
import sys
import json
import logging

# Setup debug logging to stderr
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

logger = logging.getLogger(__name__)

class DebugMCPServer:
    async def run_stdio(self):
        """Run with debug logging."""
        logger.info("Starting MCP server with stdio transport")
        
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logger.info("stdio streams established")
            await self.server.run(read_stream, write_stream, NotificationOptions())
```

### Manual Testing

**Test server directly:**
```bash
# Start server manually
python mcp_server.py

# Send test message (type this and press Enter)
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}

# Server should respond with initialization result
```

---

## 📊 Protocol Performance Comparison

| Metric | stdio (Local) | HTTP (Remote) | WebSocket (Remote) |
|--------|---------------|---------------|-------------------|
| **Latency** | ~0.1ms | ~10-100ms | ~10-50ms |
| **Throughput** | Very High | Moderate | High |
| **Connection Overhead** | None | HTTP headers | WebSocket handshake |
| **Multiplexing** | Single stream | Multiple requests | Single connection |
| **Caching** | N/A | HTTP caching | N/A |
| **Error Handling** | Process signals | HTTP status codes | Close codes |

---

## 🎯 When to Use Each Protocol

### Use **stdio** for:
- ✅ **Local deployments** on developer workstations
- ✅ **Maximum performance** (lowest latency)
- ✅ **Simple configuration** (no network setup)
- ✅ **Process isolation** and security
- ✅ **No external dependencies**

### Use **HTTP/SSE** for:
- ✅ **Remote deployments** across networks
- ✅ **RESTful integration** with existing systems
- ✅ **Load balancing** and scaling
- ✅ **HTTP caching** for performance
- ✅ **Standard web security** (TLS, etc.)

### Use **WebSocket** for:
- ✅ **Real-time bidirectional** communication
- ✅ **Lower overhead** than HTTP for frequent calls
- ✅ **Persistent connections** across sessions
- ✅ **Custom protocols** over WebSocket

The **stdio protocol is the standard and recommended approach for local MCP deployments** because it provides the best performance, simplest setup, and strongest security through process isolation.
