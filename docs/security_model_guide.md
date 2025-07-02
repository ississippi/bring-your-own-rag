# Security Model Guide for Proprietary API Documentation

This guide outlines comprehensive security measures to protect proprietary API documentation in the MCP-based RAG system, ensuring only authorized developers can access sensitive information.

## 🛡️ Security Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Developer     │    │   MCP Server    │    │  Vector Store   │
│   (Cursor/IDE)  │◄──►│  + Auth Layer   │◄──►│  + Encryption   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         │              ┌─────────────────┐                │
         └─────────────►│  Auth Provider  │◄───────────────┘
                        │ (API Keys/OAuth) │
                        └─────────────────┘
```

## 🔐 Multi-Layer Security Model

### Layer 1: Authentication & Authorization
### Layer 2: Network Security
### Layer 3: Data Encryption
### Layer 4: Access Control & Multi-tenancy
### Layer 5: Audit & Monitoring

---

## 🔑 Layer 1: Authentication & Authorization

### API Key-Based Authentication

Create `secure_mcp_server.py`:

```python
#!/usr/bin/env python3
"""
Secure MCP Server with Authentication and Authorization
"""

import asyncio
import argparse
import hashlib
import hmac
import jwt
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from pathlib import Path
import json
import os

from mcp_server import APIDocumentationMCPServer, VectorStore
from mcp_server_container import ChromaContainerVectorStore
import mcp.types as types
from mcp.server import NotificationOptions, Server

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Custom security exception."""
    pass


class AuthManager:
    """Handles authentication and authorization."""
    
    def __init__(self, config_path: str = "auth_config.json"):
        self.config_path = config_path
        self.api_keys: Dict[str, Dict] = {}
        self.jwt_secret = os.getenv("JWT_SECRET", self._generate_secret())
        self.load_auth_config()
    
    def _generate_secret(self) -> str:
        """Generate a random JWT secret."""
        import secrets
        return secrets.token_urlsafe(32)
    
    def load_auth_config(self):
        """Load authentication configuration."""
        if Path(self.config_path).exists():
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                self.api_keys = config.get("api_keys", {})
        else:
            logger.warning(f"Auth config not found: {self.config_path}")
    
    def save_auth_config(self):
        """Save authentication configuration."""
        config = {
            "api_keys": self.api_keys,
            "created_at": datetime.utcnow().isoformat()
        }
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def create_api_key(self, user_id: str, organization: str, 
                      permissions: List[str], expires_days: int = 90) -> str:
        """Create a new API key for a user."""
        # Generate API key
        import secrets
        api_key = f"apidocs_{secrets.token_urlsafe(32)}"
        
        # Calculate expiration
        expires_at = datetime.utcnow() + timedelta(days=expires_days)
        
        # Store API key info
        self.api_keys[api_key] = {
            "user_id": user_id,
            "organization": organization,
            "permissions": permissions,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat(),
            "active": True,
            "last_used": None
        }
        
        self.save_auth_config()
        logger.info(f"Created API key for {user_id} from {organization}")
        return api_key
    
    def validate_api_key(self, api_key: str) -> Dict:
        """Validate an API key and return user info."""
        if not api_key or api_key not in self.api_keys:
            raise SecurityError("Invalid API key")
        
        key_info = self.api_keys[api_key]
        
        # Check if key is active
        if not key_info.get("active", False):
            raise SecurityError("API key is deactivated")
        
        # Check expiration
        expires_at = datetime.fromisoformat(key_info["expires_at"])
        if datetime.utcnow() > expires_at:
            raise SecurityError("API key has expired")
        
        # Update last used
        key_info["last_used"] = datetime.utcnow().isoformat()
        self.save_auth_config()
        
        return key_info
    
    def create_jwt_token(self, user_info: Dict) -> str:
        """Create a JWT token for a validated user."""
        payload = {
            "user_id": user_info["user_id"],
            "organization": user_info["organization"],
            "permissions": user_info["permissions"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600  # 1 hour expiration
        }
        
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def validate_jwt_token(self, token: str) -> Dict:
        """Validate a JWT token and return payload."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            raise SecurityError("Token has expired")
        except jwt.InvalidTokenError:
            raise SecurityError("Invalid token")
    
    def check_permission(self, user_info: Dict, required_permission: str) -> bool:
        """Check if user has required permission."""
        user_permissions = user_info.get("permissions", [])
        return required_permission in user_permissions or "admin" in user_permissions


class SecureVectorStore:
    """Wrapper around vector store with security and multi-tenancy."""
    
    def __init__(self, base_vector_store: VectorStore, auth_manager: AuthManager):
        self.base_store = base_vector_store
        self.auth_manager = auth_manager
    
    def _get_tenant_collection_name(self, base_name: str, organization: str) -> str:
        """Generate tenant-specific collection name."""
        # Hash organization name for privacy
        org_hash = hashlib.sha256(organization.encode()).hexdigest()[:8]
        return f"{base_name}_{org_hash}"
    
    async def add_documents(self, chunks, user_info: Dict):
        """Add documents with tenant isolation."""
        # Check permissions
        if not self.auth_manager.check_permission(user_info, "write"):
            raise SecurityError("Insufficient permissions to add documents")
        
        # Add organization metadata to chunks
        for chunk in chunks:
            chunk.metadata["organization"] = user_info["organization"]
            chunk.metadata["uploaded_by"] = user_info["user_id"]
            chunk.metadata["upload_timestamp"] = datetime.utcnow().isoformat()
        
        await self.base_store.add_documents(chunks)
        
        # Log action
        logger.info(f"User {user_info['user_id']} added {len(chunks)} documents")
    
    async def search(self, query: str, user_info: Dict, limit: int = 5) -> List[Dict]:
        """Search with tenant isolation."""
        # Check permissions
        if not self.auth_manager.check_permission(user_info, "read"):
            raise SecurityError("Insufficient permissions to search documents")
        
        # Add organization filter
        filters = {"organization": user_info["organization"]}
        
        results = await self.base_store.search(query, limit, filters)
        
        # Log action (without logging query content for privacy)
        logger.info(f"User {user_info['user_id']} performed search, {len(results)} results")
        
        return results


class SecureAPIDocumentationMCPServer:
    """Secure MCP Server with authentication."""
    
    def __init__(self, vector_store: VectorStore, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        self.secure_vector_store = SecureVectorStore(vector_store, auth_manager)
        self.server = Server("secure-api-docs-rag")
        self.current_user: Optional[Dict] = None
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup MCP server handlers with authentication."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List available tools (requires authentication)."""
            if not self.current_user:
                return []
            
            tools = [
                types.Tool(
                    name="authenticate",
                    description="Authenticate with API key to access documentation tools",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "api_key": {
                                "type": "string",
                                "description": "Your API key for accessing documentation"
                            }
                        },
                        "required": ["api_key"]
                    }
                )
            ]
            
            # Add documentation tools if authenticated
            if self.current_user:
                tools.extend([
                    types.Tool(
                        name="search_api_docs",
                        description="Search through API documentation (requires authentication)",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"},
                                "limit": {"type": "integer", "default": 5}
                            },
                            "required": ["query"]
                        }
                    ),
                    types.Tool(
                        name="get_user_info",
                        description="Get current user information and permissions",
                        inputSchema={"type": "object", "properties": {}}
                    )
                ])
                
                # Add admin tools if user has admin permissions
                if self.auth_manager.check_permission(self.current_user, "admin"):
                    tools.append(
                        types.Tool(
                            name="load_documentation",
                            description="Load new documentation (admin only)",
                            inputSchema={
                                "type": "object",
                                "properties": {
                                    "url": {"type": "string"},
                                    "max_depth": {"type": "integer", "default": 2}
                                },
                                "required": ["url"]
                            }
                        )
                    )
            
            return tools
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls with authentication."""
            try:
                if name == "authenticate":
                    return await self._authenticate(arguments)
                
                # All other tools require authentication
                if not self.current_user:
                    return [types.TextContent(
                        type="text",
                        text="❌ Authentication required. Please use the 'authenticate' tool first."
                    )]
                
                if name == "search_api_docs":
                    return await self._secure_search(arguments)
                elif name == "get_user_info":
                    return await self._get_user_info(arguments)
                elif name == "load_documentation":
                    return await self._secure_load_docs(arguments)
                else:
                    raise SecurityError(f"Unknown tool: {name}")
                    
            except SecurityError as e:
                logger.warning(f"Security error: {e}")
                return [types.TextContent(type="text", text=f"🔒 Security Error: {str(e)}")]
            except Exception as e:
                logger.error(f"Error in tool {name}: {str(e)}")
                return [types.TextContent(type="text", text=f"❌ Error: {str(e)}")]
    
    async def _authenticate(self, arguments: dict) -> list[types.TextContent]:
        """Handle authentication."""
        api_key = arguments.get("api_key", "")
        
        try:
            user_info = self.auth_manager.validate_api_key(api_key)
            self.current_user = user_info
            
            return [types.TextContent(
                type="text",
                text=f"✅ Authenticated successfully!\n"
                     f"User: {user_info['user_id']}\n"
                     f"Organization: {user_info['organization']}\n"
                     f"Permissions: {', '.join(user_info['permissions'])}"
            )]
        
        except SecurityError as e:
            return [types.TextContent(
                type="text",
                text=f"🔒 Authentication failed: {str(e)}"
            )]
    
    async def _secure_search(self, arguments: dict) -> list[types.TextContent]:
        """Handle secure search."""
        query = arguments.get("query", "")
        limit = arguments.get("limit", 5)
        
        results = await self.secure_vector_store.search(query, self.current_user, limit)
        
        if not results:
            return [types.TextContent(
                type="text",
                text=f"No relevant documentation found for: '{query}'"
            )]
        
        response_parts = [
            f"🔍 Found {len(results)} results for: '{query}'\n",
            f"👤 Searched as: {self.current_user['user_id']} ({self.current_user['organization']})\n"
        ]
        
        for i, result in enumerate(results, 1):
            metadata = result.get("metadata", {})
            score = result.get("similarity_score", 0.0)
            
            response_parts.append(f"## Result {i} (Score: {score:.3f})")
            response_parts.append(f"**Title:** {metadata.get('title', 'Unknown')}")
            response_parts.append(f"**Section:** {metadata.get('section', 'main')}")
            response_parts.append(f"**Content:**\n{result['content']}\n")
        
        return [types.TextContent(type="text", text="\n".join(response_parts))]
    
    async def _get_user_info(self, arguments: dict) -> list[types.TextContent]:
        """Get current user information."""
        info = f"""## Current User Information
        
**User ID:** {self.current_user['user_id']}
**Organization:** {self.current_user['organization']}
**Permissions:** {', '.join(self.current_user['permissions'])}
**API Key Created:** {self.current_user['created_at']}
**Last Used:** {self.current_user.get('last_used', 'Never')}
**Expires:** {self.current_user['expires_at']}
"""
        
        return [types.TextContent(type="text", text=info)]
    
    async def _secure_load_docs(self, arguments: dict) -> list[types.TextContent]:
        """Handle secure document loading (admin only)."""
        if not self.auth_manager.check_permission(self.current_user, "admin"):
            return [types.TextContent(
                type="text",
                text="🔒 Admin permissions required to load documentation"
            )]
        
        url = arguments.get("url", "")
        max_depth = arguments.get("max_depth", 2)
        
        # Load and add documents
        from mcp_server import DocumentLoader
        document_loader = DocumentLoader()
        
        chunks = document_loader.load_from_url(url, max_depth)
        await self.secure_vector_store.add_documents(chunks, self.current_user)
        
        return [types.TextContent(
            type="text",
            text=f"✅ Loaded {len(chunks)} documentation chunks from {url}"
        )]
    
    async def run(self):
        """Run the secure MCP server."""
        import mcp.server.stdio
        
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                NotificationOptions()
            )


async def main():
    """Main entry point for secure MCP server."""
    parser = argparse.ArgumentParser(description="Secure API Documentation RAG MCP Server")
    parser.add_argument("--collection-name", default="secure-api-docs")
    parser.add_argument("--chroma-host", default="localhost")
    parser.add_argument("--chroma-port", type=int, default=8000)
    parser.add_argument("--auth-config", default="auth_config.json")
    parser.add_argument("--setup-demo-users", action="store_true",
                       help="Create demo users for testing")
    
    args = parser.parse_args()
    
    # Initialize auth manager
    auth_manager = AuthManager(args.auth_config)
    
    # Setup demo users if requested
    if args.setup_demo_users:
        setup_demo_users(auth_manager)
    
    # Initialize vector store
    vector_store = ChromaContainerVectorStore(
        collection_name=args.collection_name,
        chroma_host=args.chroma_host,
        chroma_port=args.chroma_port
    )
    
    # Initialize secure MCP server
    secure_server = SecureAPIDocumentationMCPServer(vector_store, auth_manager)
    
    logger.info("Starting secure MCP server...")
    await secure_server.run()


def setup_demo_users(auth_manager: AuthManager):
    """Setup demo users for testing."""
    print("🔧 Setting up demo users...")
    
    # Create demo API keys
    users = [
        {
            "user_id": "john.developer",
            "organization": "acme-corp",
            "permissions": ["read", "write"]
        },
        {
            "user_id": "jane.admin", 
            "organization": "acme-corp",
            "permissions": ["read", "write", "admin"]
        },
        {
            "user_id": "bob.readonly",
            "organization": "beta-company", 
            "permissions": ["read"]
        }
    ]
    
    for user in users:
        api_key = auth_manager.create_api_key(
            user_id=user["user_id"],
            organization=user["organization"],
            permissions=user["permissions"],
            expires_days=30
        )
        print(f"Created API key for {user['user_id']}: {api_key}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🔒 Layer 2: Network Security

### TLS/SSL Configuration

Create `nginx.conf` for reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name api-docs-server.your-domain.com;
    
    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/m;
    limit_req zone=api burst=5 nodelay;
    
    location / {
        proxy_pass http://localhost:8001;  # MCP server
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Security headers
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
        add_header X-XSS-Protection "1; mode=block";
    }
}

# ChromaDB with authentication
server {
    listen 8443 ssl http2;
    server_name chroma-db.your-domain.com;
    
    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/private.key;
    
    # Basic auth for ChromaDB admin access
    auth_basic "ChromaDB Admin";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://localhost:8000;  # ChromaDB
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Docker Compose with Security

Create `docker-compose.secure.yml`:

```yaml
version: '3.8'

services:
  chromadb:
    image: chromadb/chroma:latest
    container_name: chromadb-secure
    ports:
      - "127.0.0.1:8000:8000"  # Bind to localhost only
    volumes:
      - ./chroma_data:/chroma/chroma
      - ./certs:/certs:ro
    environment:
      - CHROMA_SERVER_HOST=0.0.0.0
      - CHROMA_SERVER_HTTP_PORT=8000
      - CHROMA_SERVER_SSL_ENABLED=true
      - CHROMA_SERVER_SSL_CERT=/certs/server.crt
      - CHROMA_SERVER_SSL_KEY=/certs/server.key
      - CHROMA_SERVER_CORS_ALLOW_ORIGINS=[]
    networks:
      - api-docs-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "https://localhost:8000/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3

  mcp-server:
    build: .
    container_name: mcp-server-secure
    ports:
      - "127.0.0.1:8001:8001"  # Bind to localhost only
    environment:
      - CHROMA_HOST=chromadb
      - CHROMA_PORT=8000
      - JWT_SECRET=${JWT_SECRET}
    volumes:
      - ./auth_config.json:/app/auth_config.json
      - ./certs:/certs:ro
    depends_on:
      - chromadb
    networks:
      - api-docs-network
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    container_name: nginx-proxy
    ports:
      - "443:443"
      - "8443:8443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - ./certs:/etc/nginx/certs:ro
      - ./.htpasswd:/etc/nginx/.htpasswd:ro
    depends_on:
      - mcp-server
      - chromadb
    networks:
      - api-docs-network
    restart: unless-stopped

networks:
  api-docs-network:
    driver: bridge
    internal: true  # No external access except through nginx
```

---

## 🔐 Layer 3: Data Encryption

### Encryption at Rest

Create `encrypted_vector_store.py`:

```python
#!/usr/bin/env python3
"""
Encrypted vector store wrapper for sensitive data
"""

import hashlib
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import List, Dict, Optional
import os
import json

from mcp_server import DocumentChunk, VectorStore


class EncryptedVectorStore:
    """Vector store wrapper with encryption for sensitive data."""
    
    def __init__(self, base_store: VectorStore, encryption_key: str = None):
        self.base_store = base_store
        self.fernet = self._setup_encryption(encryption_key)
    
    def _setup_encryption(self, encryption_key: str = None) -> Fernet:
        """Setup encryption using Fernet."""
        if encryption_key is None:
            encryption_key = os.getenv("ENCRYPTION_KEY", "default-key-change-me")
        
        # Derive key from password
        password = encryption_key.encode()
        salt = b'stable_salt_for_api_docs'  # In production, use random salt per tenant
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return Fernet(key)
    
    def _encrypt_content(self, content: str) -> str:
        """Encrypt sensitive content."""
        encrypted_bytes = self.fernet.encrypt(content.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()
    
    def _decrypt_content(self, encrypted_content: str) -> str:
        """Decrypt content."""
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_content.encode())
        decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()
    
    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        """Add documents with encryption."""
        encrypted_chunks = []
        
        for chunk in chunks:
            # Encrypt the content
            encrypted_content = self._encrypt_content(chunk.content)
            
            # Create new chunk with encrypted content
            encrypted_chunk = DocumentChunk(
                content=encrypted_content,
                url=chunk.url,
                title=chunk.title,
                section=chunk.section,
                chunk_id=chunk.chunk_id,
                metadata={
                    **chunk.metadata,
                    "encrypted": True,
                    "encryption_version": "1.0"
                }
            )
            encrypted_chunks.append(encrypted_chunk)
        
        await self.base_store.add_documents(encrypted_chunks)
    
    async def search(self, query: str, limit: int = 5, filters: Optional[Dict] = None) -> List[Dict]:
        """Search and decrypt results."""
        # Note: This is a simplified approach. In production, you'd want to:
        # 1. Use searchable encryption or
        # 2. Store embeddings of encrypted content separately or
        # 3. Use homomorphic encryption
        
        results = await self.base_store.search(query, limit, filters)
        
        decrypted_results = []
        for result in results:
            if result.get("metadata", {}).get("encrypted"):
                try:
                    decrypted_content = self._decrypt_content(result["content"])
                    result["content"] = decrypted_content
                except Exception as e:
                    # Log decryption error but don't expose details
                    result["content"] = "[DECRYPTION ERROR]"
            
            decrypted_results.append(result)
        
        return decrypted_results
    
    async def get_collection_info(self) -> Dict[str, any]:
        """Get collection info."""
        info = await self.base_store.get_collection_info()
        info["encryption_enabled"] = True
        return info
```

---

## 🏢 Layer 4: Multi-tenancy & Access Control

### Tenant Isolation Strategy

Create `tenant_manager.py`:

```python
#!/usr/bin/env python3
"""
Multi-tenant management for API documentation
"""

import json
import hashlib
from typing import Dict, List, Set
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TenantConfig:
    """Configuration for a tenant (organization)."""
    organization_id: str
    organization_name: str
    max_documents: int
    max_users: int
    allowed_domains: List[str]
    features: List[str]
    created_at: datetime
    active: bool


class TenantManager:
    """Manages multi-tenant access and isolation."""
    
    def __init__(self, config_path: str = "tenant_config.json"):
        self.config_path = config_path
        self.tenants: Dict[str, TenantConfig] = {}
        self.load_tenant_config()
    
    def load_tenant_config(self):
        """Load tenant configuration."""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                for org_id, config in data.items():
                    self.tenants[org_id] = TenantConfig(
                        organization_id=org_id,
                        organization_name=config["organization_name"],
                        max_documents=config["max_documents"],
                        max_users=config["max_users"],
                        allowed_domains=config["allowed_domains"],
                        features=config["features"],
                        created_at=datetime.fromisoformat(config["created_at"]),
                        active=config["active"]
                    )
        except FileNotFoundError:
            pass
    
    def save_tenant_config(self):
        """Save tenant configuration."""
        data = {}
        for org_id, tenant in self.tenants.items():
            data[org_id] = {
                "organization_name": tenant.organization_name,
                "max_documents": tenant.max_documents,
                "max_users": tenant.max_users,
                "allowed_domains": tenant.allowed_domains,
                "features": tenant.features,
                "created_at": tenant.created_at.isoformat(),
                "active": tenant.active
            }
        
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_tenant(self, organization_name: str, max_documents: int = 10000,
                     max_users: int = 50, allowed_domains: List[str] = None,
                     features: List[str] = None) -> str:
        """Create a new tenant."""
        # Generate organization ID
        org_id = hashlib.sha256(organization_name.encode()).hexdigest()[:16]
        
        tenant = TenantConfig(
            organization_id=org_id,
            organization_name=organization_name,
            max_documents=max_documents,
            max_users=max_users,
            allowed_domains=allowed_domains or [],
            features=features or ["read", "search"],
            created_at=datetime.utcnow(),
            active=True
        )
        
        self.tenants[org_id] = tenant
        self.save_tenant_config()
        return org_id
    
    def validate_tenant(self, organization_id: str) -> TenantConfig:
        """Validate tenant access."""
        if organization_id not in self.tenants:
            raise SecurityError(f"Unknown organization: {organization_id}")
        
        tenant = self.tenants[organization_id]
        if not tenant.active:
            raise SecurityError(f"Organization {organization_id} is deactivated")
        
        return tenant
    
    def check_document_limit(self, organization_id: str, current_count: int) -> bool:
        """Check if tenant can add more documents."""
        tenant = self.validate_tenant(organization_id)
        return current_count < tenant.max_documents
    
    def check_feature_access(self, organization_id: str, feature: str) -> bool:
        """Check if tenant has access to a feature."""
        tenant = self.validate_tenant(organization_id)
        return feature in tenant.features
```

---

## 📊 Layer 5: Audit & Monitoring

### Audit Logging

Create `audit_logger.py`:

```python
#!/usr/bin/env python3
"""
Comprehensive audit logging for security events
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any
from pathlib import Path


class AuditLogger:
    """Audit logger for security events."""
    
    def __init__(self, log_file: str = "audit.log"):
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)
        
        # Create file handler
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def log_event(self, event_type: str, user_id: str, organization: str,
                  details: Dict[str, Any] = None):
        """Log an audit event."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "organization": organization,
            "details": details or {}
        }
        
        self.logger.info(json.dumps(event))
    
    def log_authentication(self, user_id: str, organization: str, success: bool,
                          ip_address: str = None):
        """Log authentication attempt."""
        self.log_event(
            "authentication",
            user_id,
            organization,
            {
                "success": success,
                "ip_address": ip_address
            }
        )
    
    def log_search(self, user_id: str, organization: str, query_hash: str,
                   results_count: int):
        """Log search query (without exposing query content)."""
        self.log_event(
            "search",
            user_id,
            organization,
            {
                "query_hash": query_hash,
                "results_count": results_count
            }
        )
    
    def log_document_access(self, user_id: str, organization: str,
                           document_id: str, action: str):
        """Log document access."""
        self.log_event(
            "document_access",
            user_id,
            organization,
            {
                "document_id": document_id,
                "action": action
            }
        )
    
    def log_admin_action(self, user_id: str, organization: str, action: str,
                        target: str = None):
        """Log administrative actions."""
        self.log_event(
            "admin_action",
            user_id,
            organization,
            {
                "action": action,
                "target": target
            }
        )


# Security monitoring
class SecurityMonitor:
    """Monitor for security anomalies."""
    
    def __init__(self):
        self.failed_attempts: Dict[str, int] = {}
        self.rate_limits: Dict[str, List[datetime]] = {}
    
    def check_brute_force(self, user_id: str, max_attempts: int = 5) -> bool:
        """Check for brute force attempts."""
        attempts = self.failed_attempts.get(user_id, 0)
        return attempts >= max_attempts
    
    def record_failed_attempt(self, user_id: str):
        """Record a failed authentication attempt."""
        self.failed_attempts[user_id] = self.failed_attempts.get(user_id, 0) + 1
    
    def reset_failed_attempts(self, user_id: str):
        """Reset failed attempts on successful login."""
        self.failed_attempts.pop(user_id, None)
    
    def check_rate_limit(self, user_id: str, max_requests: int = 100,
                        window_minutes: int = 60) -> bool:
        """Check rate limiting."""
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=window_minutes)
        
        # Clean old requests
        if user_id in self.rate_limits:
            self.rate_limits[user_id] = [
                req_time for req_time in self.rate_limits[user_id]
                if req_time > window_start
            ]
        else:
            self.rate_limits[user_id] = []
        
        # Check limit
        if len(self.rate_limits[user_id]) >= max_requests:
            return False
        
        # Record this request
        self.rate_limits[user_id].append(now)
        return True
```

---

## 🔧 Implementation Guide

### Step 1: Generate API Keys for Customers

```python
#!/usr/bin/env python3
"""
Script for vendors to generate customer API keys
"""

from secure_mcp_server import AuthManager

def create_customer_access():
    """Create API keys for a new customer."""
    auth_manager = AuthManager()
    
    # Customer details
    customer_org = "acme-corporation"
    users = [
        {"user_id": "john.doe", "permissions": ["read", "search"]},
        {"user_id": "jane.admin", "permissions": ["read", "search", "admin"]},
    ]
    
    print(f"Creating access for {customer_org}:")
    
    for user in users:
        api_key = auth_manager.create_api_key(
            user_id=user["user_id"],
            organization=customer_org,
            permissions=user["permissions"],
            expires_days=365
        )
        
        print(f"  {user['user_id']}: {api_key}")
    
    return auth_manager

if __name__ == "__main__":
    create_customer_access()
```

### Step 2: Customer Configuration Package

Create distribution package:

```bash
# vendor_package.sh
#!/bin/bash

CUSTOMER_NAME=$1
ORGANIZATION_ID=$2

if [ -z "$CUSTOMER_NAME" ] || [ -z "$ORGANIZATION_ID" ]; then
    echo "Usage: $0 <customer_name> <organization_id>"
    exit 1
fi

# Create customer package
mkdir -p "packages/${CUSTOMER_NAME}"
cd "packages/${CUSTOMER_NAME}"

# Copy secure server files
cp ../../secure_mcp_server.py .
cp ../../requirements.txt .

# Create customer-specific auth config
python -c "
from secure_mcp_server import AuthManager
import sys

auth = AuthManager('auth_config.json')

# Create API keys for customer
api_key = auth.create_api_key(
    user_id='${CUSTOMER_NAME}-admin',
    organization='${ORGANIZATION_ID}',
    permissions=['read', 'search', 'admin'],
    expires_days=365
)

print('API Key for ${CUSTOMER_NAME}:', api_key)
"

# Create IDE config
cat > .cursor/mcp.json << EOF
{
  "mcpServers": {
    "secure-api-docs": {
      "command": "python",
      "args": [
        "$(pwd)/secure_mcp_server.py",
        "--collection-name", "${ORGANIZATION_ID}-docs",
        "--auth-config", "$(pwd)/auth_config.json"
      ]
    }
  }
}
EOF

echo "Package created for ${CUSTOMER_NAME} in packages/${CUSTOMER_NAME}/"
```

---

## 🚨 Security Best Practices Summary

### For API Vendors:
1. **🔐 Strong Authentication**: Use API keys with expiration
2. **🏢 Tenant Isolation**: Separate data by organization
3. **🔒 Encryption**: Encrypt sensitive content at rest
4. **📊 Audit Everything**: Log all access and changes
5. **🚫 Rate Limiting**: Prevent abuse
6. **🔑 Key Rotation**: Regular API key renewal

### For Customers:
1. **🔐 Secure Key Storage**: Store API keys securely (env vars, secrets manager)
2. **👥 Principle of Least Privilege**: Only grant necessary permissions
3. **📝 Regular Audits**: Review access logs
4. **🔄 Key Rotation**: Rotate API keys regularly
5. **🖥️ Secure Workstations**: Protect developer machines

### Deployment Security:
1. **🌐 HTTPS Only**: All communication over TLS
2. **🏠 Network Isolation**: Use private networks
3. **🐳 Container Security**: Secure container configurations
4. **🔥 Firewall Rules**: Restrict network access
5. **📊 Monitoring**: Real-time security monitoring

This comprehensive security model ensures that proprietary API documentation remains protected while enabling seamless AI-assisted development for authorized users.
