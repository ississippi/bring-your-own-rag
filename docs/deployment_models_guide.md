# MCP Server Deployment Models Guide

This guide covers flexible deployment options for the MCP server, supporting both vendor-hosted remote deployments and local developer workstation setups depending on your security and operational requirements.

## 🏗️ Deployment Architecture Overview

```
📊 Remote Deployment (Vendor-Hosted)
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Developer     │    │   Vendor Cloud  │    │   Vector Store  │
│   Workstation   │◄──►│   MCP Server    │◄──►│   + API Docs    │
│  (Cursor/IDE)   │    │  + Security     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘

🖥️  Local Deployment (Developer-Hosted)
┌─────────────────┐    ┌─────────────────┐
│   Developer     │    │   Local Vector  │
│   Workstation   │◄──►│   Store + Docs  │
│  IDE + Server   │    │   (Chroma/etc)  │
└─────────────────┘    └─────────────────┘

🔄 Hybrid Deployment (Mixed)
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Developer     │    │   Internal      │    │   Vendor Cloud  │
│   Workstation   │◄──►│   MCP Server    │◄──►│   External APIs │
│  (Cursor/IDE)   │    │  + Private APIs │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 🌐 Remote Deployment (Vendor-Hosted)

**Use Cases:**
- External/public APIs distributed by vendors
- SaaS API documentation services
- When vendors want to maintain control
- Multi-customer deployments
- Centralized analytics and monitoring

### Remote Server Setup

Create `remote_mcp_server.py`:

```python
#!/usr/bin/env python3
"""
Remote MCP Server for vendor-hosted deployments
Supports HTTP/WebSocket connections from developer workstations
"""

import asyncio
import argparse
import logging
from typing import Dict, List, Optional
import json
import ssl
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import websockets
from websockets.server import serve
import jwt

from secure_mcp_server import SecureAPIDocumentationMCPServer, AuthManager
from mcp_server_container import ChromaContainerVectorStore
import mcp.types as types

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()


class RemoteMCPServer:
    """Remote MCP server with HTTP/WebSocket interface."""
    
    def __init__(self, auth_manager: AuthManager, vector_store):
        self.auth_manager = auth_manager
        self.secure_server = SecureAPIDocumentationMCPServer(vector_store, auth_manager)
        self.app = FastAPI(title="Remote API Documentation MCP Server")
        self.setup_fastapi()
    
    def setup_fastapi(self):
        """Setup FastAPI routes and middleware."""
        
        # CORS middleware for cross-origin requests
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure appropriately for production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @self.app.post("/authenticate")
        async def authenticate(credentials: dict):
            """Authenticate and return JWT token."""
            api_key = credentials.get("api_key")
            if not api_key:
                raise HTTPException(status_code=400, detail="API key required")
            
            try:
                user_info = self.auth_manager.validate_api_key(api_key)
                token = self.auth_manager.create_jwt_token(user_info)
                return {
                    "access_token": token,
                    "token_type": "bearer",
                    "user_info": {
                        "user_id": user_info["user_id"],
                        "organization": user_info["organization"],
                        "permissions": user_info["permissions"]
                    }
                }
            except Exception as e:
                raise HTTPException(status_code=401, detail=str(e))
        
        @self.app.get("/tools")
        async def list_tools(token: HTTPAuthorizationCredentials = Security(security)):
            """List available MCP tools."""
            try:
                user_info = self._validate_token(token.credentials)
                self.secure_server.current_user = user_info
                tools = await self.secure_server._get_available_tools()
                return {"tools": [tool.dict() for tool in tools]}
            except Exception as e:
                raise HTTPException(status_code=401, detail=str(e))
        
        @self.app.post("/tools/{tool_name}")
        async def call_tool(tool_name: str, arguments: dict, 
                           token: HTTPAuthorizationCredentials = Security(security)):
            """Call an MCP tool."""
            try:
                user_info = self._validate_token(token.credentials)
                self.secure_server.current_user = user_info
                
                result = await self.secure_server.server.call_tool(tool_name, arguments)
                return {"result": [content.dict() for content in result]}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "service": "remote-mcp-server"}
    
    def _validate_token(self, token: str) -> Dict:
        """Validate JWT token and return user info."""
        return self.auth_manager.validate_jwt_token(token)
    
    async def start_http_server(self, host: str = "0.0.0.0", port: int = 8080, 
                               ssl_cert: str = None, ssl_key: str = None):
        """Start HTTP server."""
        ssl_context = None
        if ssl_cert and ssl_key:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(ssl_cert, ssl_key)
        
        config = uvicorn.Config(
            self.app, 
            host=host, 
            port=port, 
            ssl_certfile=ssl_cert,
            ssl_keyfile=ssl_key,
            log_level="info"
        )
        
        server = uvicorn.Server(config)
        logger.info(f"Starting remote MCP server on {'https' if ssl_context else 'http'}://{host}:{port}")
        await server.serve()


class RemoteMCPClient:
    """Client for connecting to remote MCP server from developer workstation."""
    
    def __init__(self, server_url: str, api_key: str, verify_ssl: bool = True):
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.access_token = None
        self.session = None
    
    async def authenticate(self):
        """Authenticate with remote server."""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.server_url}/authenticate",
                json={"api_key": self.api_key},
                ssl=self.verify_ssl
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.access_token = data["access_token"]
                    logger.info("Successfully authenticated with remote server")
                    return data["user_info"]
                else:
                    error = await response.text()
                    raise Exception(f"Authentication failed: {error}")
    
    async def list_tools(self):
        """List available tools from remote server."""
        if not self.access_token:
            await self.authenticate()
        
        import aiohttp
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.server_url}/tools",
                headers=headers,
                ssl=self.verify_ssl
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["tools"]
                else:
                    error = await response.text()
                    raise Exception(f"Failed to list tools: {error}")
    
    async def call_tool(self, tool_name: str, arguments: dict):
        """Call a tool on the remote server."""
        if not self.access_token:
            await self.authenticate()
        
        import aiohttp
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.server_url}/tools/{tool_name}",
                json=arguments,
                headers=headers,
                ssl=self.verify_ssl
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["result"]
                else:
                    error = await response.text()
                    raise Exception(f"Tool call failed: {error}")


# Remote MCP Server for IDE integration
class RemoteMCPServerAdapter:
    """Adapter to make remote server work with local MCP protocol."""
    
    def __init__(self, remote_client: RemoteMCPClient):
        self.remote_client = remote_client
        self.server = Server("remote-api-docs")
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup MCP protocol handlers that proxy to remote server."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List tools from remote server."""
            try:
                tools_data = await self.remote_client.list_tools()
                tools = []
                for tool_data in tools_data:
                    tool = types.Tool(
                        name=tool_data["name"],
                        description=tool_data["description"],
                        inputSchema=tool_data["inputSchema"]
                    )
                    tools.append(tool)
                return tools
            except Exception as e:
                logger.error(f"Failed to list remote tools: {e}")
                return []
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Call tool on remote server."""
            try:
                result_data = await self.remote_client.call_tool(name, arguments)
                return [
                    types.TextContent(type="text", text=content["text"])
                    for content in result_data
                ]
            except Exception as e:
                logger.error(f"Remote tool call failed: {e}")
                return [types.TextContent(
                    type="text",
                    text=f"Remote server error: {str(e)}"
                )]
    
    async def run(self):
        """Run the adapter server."""
        import mcp.server.stdio
        from mcp.server import NotificationOptions
        
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                NotificationOptions()
            )


async def main():
    """Main entry point for remote server."""
    parser = argparse.ArgumentParser(description="Remote MCP Server")
    parser.add_argument("--mode", choices=["server", "client"], required=True,
                       help="Run as server or client")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--ssl-cert", help="SSL certificate file")
    parser.add_argument("--ssl-key", help="SSL private key file")
    parser.add_argument("--server-url", help="Remote server URL (client mode)")
    parser.add_argument("--api-key", help="API key (client mode)")
    parser.add_argument("--collection-name", default="remote-api-docs")
    parser.add_argument("--auth-config", default="auth_config.json")
    
    args = parser.parse_args()
    
    if args.mode == "server":
        # Run as remote server
        auth_manager = AuthManager(args.auth_config)
        vector_store = ChromaContainerVectorStore(args.collection_name)
        
        remote_server = RemoteMCPServer(auth_manager, vector_store)
        await remote_server.start_http_server(
            host=args.host,
            port=args.port,
            ssl_cert=args.ssl_cert,
            ssl_key=args.ssl_key
        )
    
    elif args.mode == "client":
        # Run as client adapter
        if not args.server_url or not args.api_key:
            print("Error: --server-url and --api-key required for client mode")
            return
        
        remote_client = RemoteMCPClient(args.server_url, args.api_key)
        adapter = RemoteMCPServerAdapter(remote_client)
        await adapter.run()


if __name__ == "__main__":
    asyncio.run(main())
```

### Remote Deployment Configuration

Create `docker-compose.remote.yml`:

```yaml
version: '3.8'

services:
  chromadb:
    image: chromadb/chroma:latest
    container_name: chromadb-remote
    volumes:
      - ./chroma_data:/chroma/chroma
    networks:
      - remote-network
    restart: unless-stopped

  remote-mcp-server:
    build: .
    container_name: remote-mcp-server
    ports:
      - "443:8080"
    environment:
      - CHROMA_HOST=chromadb
      - CHROMA_PORT=8000
      - JWT_SECRET=${JWT_SECRET}
    volumes:
      - ./auth_config.json:/app/auth_config.json
      - ./certs:/app/certs:ro
    depends_on:
      - chromadb
    networks:
      - remote-network
    restart: unless-stopped
    command: python remote_mcp_server.py --mode server --host 0.0.0.0 --port 8080 --ssl-cert /app/certs/server.crt --ssl-key /app/certs/server.key

  nginx:
    image: nginx:alpine
    container_name: nginx-remote
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx-remote.conf:/etc/nginx/conf.d/default.conf
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - remote-mcp-server
    networks:
      - remote-network
    restart: unless-stopped

networks:
  remote-network:
    driver: bridge
```

### Client Configuration for Cursor

Create `.cursor/mcp.json` for remote connection:

```json
{
  "mcpServers": {
    "remote-api-docs": {
      "command": "python",
      "args": [
        "/path/to/remote_mcp_server.py",
        "--mode", "client",
        "--server-url", "https://api-docs.vendor.com",
        "--api-key", "${API_KEY}"
      ],
      "env": {
        "API_KEY": "your-api-key-here"
      }
    }
  }
}
```

---

## 🖥️ Local Deployment (Developer Workstation)

**Use Cases:**
- Internal/private company APIs
- Air-gapped environments
- Maximum security requirements
- No external dependencies
- Full developer control

### Local Setup Script

Create `local_deployment.py`:

```python
#!/usr/bin/env python3
"""
Local deployment setup for developer workstations
Sets up everything needed to run MCP server locally
"""

import asyncio
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
import requests
import zipfile


class LocalDeploymentManager:
    """Manages local deployment of MCP server."""
    
    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir)
        self.config = {}
    
    def setup_local_environment(self):
        """Set up local development environment."""
        print("🏠 Setting up local MCP server environment...")
        
        # Create necessary directories
        (self.project_dir / "data").mkdir(exist_ok=True)
        (self.project_dir / "logs").mkdir(exist_ok=True)
        (self.project_dir / ".cursor").mkdir(exist_ok=True)
        (self.project_dir / ".vscode").mkdir(exist_ok=True)
        
        # Install dependencies
        self._install_dependencies()
        
        # Setup local vector store
        self._setup_local_vectorstore()
        
        # Create configurations
        self._create_local_configs()
        
        print("✅ Local environment setup complete!")
    
    def _install_dependencies(self):
        """Install required Python packages."""
        print("📦 Installing dependencies...")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
            ])
            print("   ✅ Dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Failed to install dependencies: {e}")
            sys.exit(1)
    
    def _setup_local_vectorstore(self):
        """Setup local vector store (Chroma)."""
        print("🗄️  Setting up local vector store...")
        
        # Create local Chroma configuration
        local_docker_compose = f"""
version: '3.8'

services:
  chromadb-local:
    image: chromadb/chroma:latest
    container_name: chromadb-local
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - {self.project_dir}/data/chroma:/chroma/chroma
    environment:
      - CHROMA_SERVER_HOST=0.0.0.0
      - CHROMA_SERVER_HTTP_PORT=8000
      - CHROMA_SERVER_CORS_ALLOW_ORIGINS=["http://localhost:*"]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3
"""
        
        (self.project_dir / "docker-compose.local.yml").write_text(local_docker_compose)
        
        # Start ChromaDB
        try:
            subprocess.run([
                "docker-compose", "-f", "docker-compose.local.yml", "up", "-d"
            ], cwd=self.project_dir, check=True)
            print("   ✅ Local ChromaDB started")
        except subprocess.CalledProcessError:
            print("   ⚠️  Docker not available, will use file-based storage")
    
    def _create_local_configs(self):
        """Create local IDE configurations."""
        print("⚙️  Creating IDE configurations...")
        
        server_script = self.project_dir / "mcp_server.py"
        
        # Cursor configuration
        cursor_config = {
            "mcpServers": {
                "local-api-docs": {
                    "command": "python",
                    "args": [
                        str(server_script.absolute()),
                        "--collection-name", "local-api-docs",
                        "--chroma-path", str((self.project_dir / "data" / "chroma").absolute())
                    ],
                    "env": {
                        "PYTHONPATH": str(self.project_dir.absolute())
                    }
                }
            }
        }
        
        cursor_config_path = self.project_dir / ".cursor" / "mcp.json"
        cursor_config_path.write_text(json.dumps(cursor_config, indent=2))
        
        # VS Code configuration  
        vscode_config_path = self.project_dir / ".vscode" / "mcp.json"
        vscode_config_path.write_text(json.dumps(cursor_config, indent=2))
        
        print("   ✅ IDE configurations created")
    
    def load_documentation(self, sources: list):
        """Load documentation from various sources."""
        print("📚 Loading documentation...")
        
        for source in sources:
            if source["type"] == "url":
                self._load_from_url(source["url"], source.get("name", "unknown"))
            elif source["type"] == "file":
                self._load_from_file(source["path"], source.get("name", "unknown"))
            elif source["type"] == "directory":
                self._load_from_directory(source["path"], source.get("name", "unknown"))
    
    def _load_from_url(self, url: str, name: str):
        """Load documentation from URL."""
        print(f"   📄 Loading {name} from {url}")
        
        try:
            # Use the MCP server to load documentation
            cmd = [
                sys.executable, "mcp_server.py",
                "--load-url", url,
                "--collection-name", "local-api-docs"
            ]
            subprocess.run(cmd, cwd=self.project_dir, check=True)
            print(f"   ✅ Loaded {name}")
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Failed to load {name}: {e}")
    
    def _load_from_file(self, file_path: str, name: str):
        """Load documentation from file."""
        print(f"   📄 Loading {name} from {file_path}")
        # Implementation for file loading
        pass
    
    def _load_from_directory(self, dir_path: str, name: str):
        """Load documentation from directory."""
        print(f"   📁 Loading {name} from {dir_path}")
        # Implementation for directory loading
        pass
    
    def create_startup_script(self):
        """Create a startup script for easy launching."""
        startup_script = f"""#!/bin/bash
# Local API Documentation Assistant Startup Script

echo "🚀 Starting Local API Documentation Assistant"

# Start ChromaDB if not running
if ! docker ps | grep -q chromadb-local; then
    echo "📊 Starting ChromaDB..."
    docker-compose -f docker-compose.local.yml up -d
    sleep 5
fi

# Check if ChromaDB is healthy
if curl -s http://localhost:8000/api/v1/heartbeat > /dev/null; then
    echo "✅ ChromaDB is running"
else
    echo "❌ ChromaDB failed to start"
    exit 1
fi

echo "💡 Your local API documentation assistant is ready!"
echo "📖 Open Cursor or VS Code and start coding"
echo "🛑 To stop: docker-compose -f docker-compose.local.yml down"
"""
        
        script_path = self.project_dir / "start_local_assistant.sh"
        script_path.write_text(startup_script)
        script_path.chmod(0o755)
        
        print(f"   ✅ Startup script created: {script_path}")


async def main():
    """Main local deployment setup."""
    parser = argparse.ArgumentParser(description="Local MCP Server Deployment")
    parser.add_argument("--project-dir", default=".", help="Project directory")
    parser.add_argument("--config-file", help="Configuration file with documentation sources")
    parser.add_argument("--setup-only", action="store_true", help="Only setup environment")
    
    args = parser.parse_args()
    
    manager = LocalDeploymentManager(args.project_dir)
    
    # Setup local environment
    manager.setup_local_environment()
    
    if not args.setup_only and args.config_file:
        # Load documentation sources
        with open(args.config_file) as f:
            config = json.load(f)
        
        sources = config.get("documentation_sources", [])
        manager.load_documentation(sources)
    
    # Create startup script
    manager.create_startup_script()
    
    print("\n🎉 Local deployment complete!")
    print("\n📋 Next steps:")
    print("1. Run: ./start_local_assistant.sh")
    print("2. Open Cursor or VS Code")
    print("3. Start coding with AI assistance!")


if __name__ == "__main__":
    asyncio.run(main())
```

### Local Configuration Example

Create `local_config.json`:

```json
{
  "documentation_sources": [
    {
      "type": "url",
      "url": "https://docs.internal-api.company.com",
      "name": "Internal REST API"
    },
    {
      "type": "url", 
      "url": "https://graphql.internal.company.com/docs",
      "name": "Internal GraphQL API"
    },
    {
      "type": "directory",
      "path": "./docs/api",
      "name": "Local API Documentation"
    },
    {
      "type": "file",
      "path": "./openapi.yaml",
      "name": "OpenAPI Specification"
    }
  ],
  "settings": {
    "collection_name": "company-internal-apis",
    "max_documents": 50000,
    "embedding_model": "all-MiniLM-L6-v2"
  }
}
```

---

## 🔄 Hybrid Deployment

**Use Cases:**
- Mix of internal and external APIs
- Gradual migration strategies
- Different security requirements per API
- Multi-vendor environments

### Hybrid Configuration

Create `.cursor/mcp.json` for hybrid setup:

```json
{
  "mcpServers": {
    "internal-apis": {
      "command": "python",
      "args": [
        "/path/to/mcp_server.py",
        "--collection-name", "internal-apis",
        "--chroma-path", "./local-data/internal"
      ]
    },
    "vendor-a-apis": {
      "command": "python", 
      "args": [
        "/path/to/remote_mcp_server.py",
        "--mode", "client",
        "--server-url", "https://docs.vendor-a.com",
        "--api-key", "${VENDOR_A_API_KEY}"
      ]
    },
    "vendor-b-apis": {
      "command": "python",
      "args": [
        "/path/to/remote_mcp_server.py", 
        "--mode", "client",
        "--server-url", "https://api-docs.vendor-b.com",
        "--api-key", "${VENDOR_B_API_KEY}"
      ]
    }
  }
}
```

---

## 📊 Deployment Comparison

| Aspect | Remote (Vendor-Hosted) | Local (Developer) | Hybrid |
|--------|----------------------|------------------|---------|
| **Security** | Vendor-controlled | Full control | Mixed |
| **Setup Complexity** | Simple for developers | More complex | Moderate |
| **Dependencies** | Internet required | Self-contained | Mixed |
| **Performance** | Network latency | Local speed | Mixed |
| **Scalability** | Vendor manages | Limited by hardware | Mixed |
| **Cost** | Vendor pricing | Hardware costs | Mixed |
| **Privacy** | Shared with vendor | Fully private | Mixed |
| **Maintenance** | Vendor responsibility | Self-managed | Mixed |

---

## 🔒 Security Considerations by Deployment

### Remote Deployment Security
- ✅ **TLS encryption** for all communications
- ✅ **API key authentication** 
- ✅ **Rate limiting** and monitoring
- ✅ **Audit logging** of all access
- ⚠️ **Trust vendor** with API access patterns

### Local Deployment Security  
- ✅ **Complete data control** - never leaves premises
- ✅ **No external dependencies** once set up
- ✅ **Air-gap compatible** environments
- ⚠️ **Self-managed security** updates
- ⚠️ **Local backup** responsibility

### Hybrid Security
- ✅ **Granular control** per API type
- ✅ **Risk segmentation** by sensitivity
- ⚠️ **Complex configuration** management
- ⚠️ **Multiple security** models to maintain

---

## 🚀 Quick Start Commands

### Remote Deployment (Vendor)
```bash
# Setup vendor-hosted server
docker-compose -f docker-compose.remote.yml up -d

# Create customer API keys
python create_customer_access.py customer-name

# Monitor server
docker-compose logs -f remote-mcp-server
```

### Local Deployment (Developer)
```bash
# Setup local environment
python local_deployment.py --config-file local_config.json

# Start local assistant
./start_local_assistant.sh

# Add more documentation
python mcp_server.py --load-url https://internal-docs.company.com
```

### Hybrid Deployment
```bash
# Setup local internal APIs
python local_deployment.py --setup-only

# Configure external vendor connections
export VENDOR_A_API_KEY="your-key"
export VENDOR_B_API_KEY="your-key"

# Start hybrid environment
./start_local_assistant.sh
```

---

## 🎯 Use Case Recommendations

### Choose **Remote Deployment** when:
- 📈 **Distributing APIs to external customers**
- 🏢 **SaaS/vendor business model**
- 📊 **Want usage analytics and monitoring**
- 🔧 **Prefer vendor-managed infrastructure**
- 🌐 **APIs are public or semi-public**

### Choose **Local Deployment** when:
- 🔒 **Maximum security requirements**
- 🏠 **Internal/private company APIs**
- 🚫 **Air-gapped environments**
- 💰 **Cost control over infrastructure**
- ⚡ **Lowest latency requirements**

### Choose **Hybrid Deployment** when:
- 🔄 **Mix of internal and external APIs**
- 📊 **Different security levels per API**
- 🎯 **Gradual migration strategies**
- 🏢 **Multiple vendor relationships**
- 🔧 **Complex enterprise environments**

This flexible deployment model ensures that the MCP server can adapt to any organizational security, operational, or business requirements while maintaining the same great developer experience.
