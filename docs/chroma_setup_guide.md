# ChromaDB Container Setup Guide

This guide walks you through setting up ChromaDB in a Docker container and ingesting test API documentation for use with the MCP server.

## 📋 Prerequisites

- Docker and Docker Compose installed
- Python 3.8+ with pip
- The MCP server project files (see main README.md)

## 🐳 Step 1: Set Up ChromaDB Container

### Option A: Using Docker Compose (Recommended)

Create a `docker-compose.yml` file in your project directory:

```yaml
services:
  chromadb:
    image: chromadb/chroma:latest
    container_name: chromadb-server
    ports:
      - "8000:8000"
    volumes:
      - ./chroma_data:/chroma/chroma
    environment:
      - CHROMA_SERVER_HOST=0.0.0.0
      - CHROMA_SERVER_HTTP_PORT=8000
      - CHROMA_SERVER_CORS_ALLOW_ORIGINS=["*"]
    command: uvicorn chromadb.app:app --host 0.0.0.0 --port 8000 --log-level info
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Start the container:

```bash
# Start ChromaDB
docker-compose up -d

# Check if it's running
docker-compose ps

# View logs
docker-compose logs chromadb
```

### Option B: Using Docker Run

```bash
# Create data directory
mkdir -p ./chroma_data

# Run ChromaDB container
docker run -d \
  --name chromadb-server \
  -p 8000:8000 \
  -v $(pwd)/chroma_data:/chroma/chroma \
  -e CHROMA_SERVER_HOST=0.0.0.0 \
  -e CHROMA_SERVER_HTTP_PORT=8000 \
  chromadb/chroma:latest

# Check container status
docker ps | grep chromadb
```

### Verify ChromaDB is Running

```bash
# Test the API endpoint
curl http://localhost:8000/api/v2/heartbeat

# Should return: {"nanosecond heartbeat": <timestamp>}
```

Or visit http://localhost:8000 in your browser.

## 🔧 Step 2: Update MCP Server for Container Connection

Create a modified version of the MCP server that connects to the containerized ChromaDB:

### Create `mcp_server_container.py`

```python
#!/usr/bin/env python3
"""
MCP Server configured for containerized ChromaDB
"""

import asyncio
import argparse
import logging
from pathlib import Path
import chromadb
from chromadb.config import Settings

# Import our existing classes
from mcp_server import DocumentLoader, APIDocumentationMCPServer, VectorStore, DocumentChunk
from typing import Dict, List, Optional, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChromaContainerVectorStore(VectorStore):
    """ChromaDB vector store that connects to a containerized instance."""
    
    def __init__(self, collection_name: str, chroma_host: str = "localhost", chroma_port: int = 8000):
        self.collection_name = collection_name
        self.chroma_host = chroma_host
        self.chroma_port = chroma_port
        
        # Initialize Chroma client for HTTP connection
        self.client = chromadb.HttpClient(
            host=chroma_host,
            port=chroma_port,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(
                name=collection_name,
                embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            )
            logger.info(f"Connected to existing collection: {collection_name}")
        except ValueError:
            self.collection = self.client.create_collection(
                name=collection_name,
                embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            )
            logger.info(f"Created new collection: {collection_name}")
    
    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        """Add document chunks to ChromaDB collection."""
        if not chunks:
            return
        
        documents = [chunk.content for chunk in chunks]
        metadatas = [
            {
                "url": chunk.url,
                "title": chunk.title,
                "section": chunk.section,
                **chunk.metadata
            }
            for chunk in chunks
        ]
        ids = [chunk.chunk_id for chunk in chunks]
        
        # Add to collection in batches
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i + batch_size]
            batch_metas = metadatas[i:i + batch_size]
            batch_ids = ids[i:i + batch_size]
            
            self.collection.add(
                documents=batch_docs,
                metadatas=batch_metas,
                ids=batch_ids
            )
        
        logger.info(f"Added {len(chunks)} document chunks to collection '{self.collection_name}'")
    
    async def search(self, query: str, limit: int = 5, filters: Optional[Dict] = None) -> List[Dict]:
        """Search for similar documents in ChromaDB."""
        where_clause = None
        if filters:
            where_clause = filters
        
        results = self.collection.query(
            query_texts=[query],
            n_results=limit,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )
        
        search_results = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                result = {
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "similarity_score": 1 - results["distances"][0][i] if results["distances"] else 0.0
                }
                search_results.append(result)
        
        return search_results
    
    async def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the ChromaDB collection."""
        count = self.collection.count()
        return {
            "collection_name": self.collection_name,
            "document_count": count,
            "vector_store_type": "chroma-container",
            "chroma_host": self.chroma_host,
            "chroma_port": self.chroma_port
        }


async def main():
    """Main entry point for containerized ChromaDB version."""
    parser = argparse.ArgumentParser(description="API Documentation RAG MCP Server (Container Version)")
    parser.add_argument("--collection-name", default="api-docs", help="Name of the vector store collection")
    parser.add_argument("--chroma-host", default="localhost", help="ChromaDB container host")
    parser.add_argument("--chroma-port", type=int, default=8000, help="ChromaDB container port")
    parser.add_argument("--load-url", help="Optional: URL to load documentation from on startup")
    
    args = parser.parse_args()
    
    # Initialize vector store
    vector_store = ChromaContainerVectorStore(
        collection_name=args.collection_name,
        chroma_host=args.chroma_host,
        chroma_port=args.chroma_port
    )
    
    # Initialize MCP server
    mcp_server = APIDocumentationMCPServer(vector_store)
    
    # Optionally load documentation on startup
    if args.load_url:
        logger.info(f"Loading documentation from: {args.load_url}")
        try:
            chunks = mcp_server.document_loader.load_from_url(args.load_url)
            await vector_store.add_documents(chunks)
            logger.info(f"Successfully loaded {len(chunks)} chunks")
        except Exception as e:
            logger.error(f"Failed to load documentation: {e}")
    
    # Run the server
    logger.info(f"Starting MCP server with collection: {args.collection_name}")
    logger.info(f"Connected to ChromaDB at: {args.chroma_host}:{args.chroma_port}")
    
    import mcp.server.stdio
    from mcp.server import NotificationOptions
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await mcp_server.server.run(
            read_stream,
            write_stream,
            NotificationOptions()
        )


if __name__ == "__main__":
    asyncio.run(main())
```

## 📚 Step 3: Ingest Test API Documentation

Clear existing collection and ingest specific YAML files:
```
python ingest_docs_yaml.py --yaml-files example_files.yaml exocoin_openapi_spec.yaml --collection-name test-collection --chroma-host localhost --chroma-port 8000 --clear-collection
```
or ingest all YAMl files:
```
python ingest_docs_yaml.py --yaml-dir . --collection-name test-collection --chroma-host localhost --chroma-port 8000
```
Print a sample of the collection:
```
python print_collection_sample.py
```

### Recommended Test URLs

Here are some good public API documentation sources for testing:

1. **JSONPlaceholder API** (Simple REST API)
   ```bash
   https://jsonplaceholder.typicode.com/guide/
   ```

2. **GitHub API Documentation**
   ```bash
   https://docs.github.com/en/rest
   ```

3. **OpenWeatherMap API**
   ```bash
   https://openweathermap.org/api
   ```

4. **Stripe API Documentation** (Well-structured)
   ```bash
   https://stripe.com/docs/api
   ```

### Method 1: Command Line Ingestion

```bash
# Install dependencies if not already done
pip install -r requirements.txt

# Ingest JSONPlaceholder documentation (lightweight test)
python mcp_server_container.py \
  --collection-name jsonplaceholder-api \
  --load-url https://jsonplaceholder.typicode.com/guide/ \
  --chroma-host localhost \
  --chroma-port 8000
```

### Method 2: Manual Ingestion Script

Create `ingest_docs.py`:

```python
#!/usr/bin/env python3
"""
Script to ingest API documentation into containerized ChromaDB
"""

import asyncio
import sys
from mcp_server_container import ChromaContainerVectorStore
from mcp_server import DocumentLoader

async def ingest_documentation():
    """Ingest documentation from multiple sources."""
    
    # Test URLs with descriptions
    test_urls = [
        ("https://jsonplaceholder.typicode.com/guide/", "JSONPlaceholder API Guide"),
        ("https://httpbin.org/", "HTTPBin Testing Service"),
        # Add more URLs as needed
    ]
    
    # Initialize vector store
    vector_store = ChromaContainerVectorStore(
        collection_name="test-api-docs",
        chroma_host="localhost",
        chroma_port=8000
    )
    
    # Initialize document loader
    document_loader = DocumentLoader()
    
    total_chunks = 0
    
    for url, description in test_urls:
        print(f"\n📄 Loading: {description}")
        print(f"    URL: {url}")
        
        try:
            chunks = document_loader.load_from_url(url, max_depth=2)
            if chunks:
                await vector_store.add_documents(chunks)
                print(f"    ✅ Loaded {len(chunks)} documentation chunks")
                total_chunks += len(chunks)
            else:
                print(f"    ⚠️  No content extracted from {url}")
        
        except Exception as e:
            print(f"    ❌ Error loading {url}: {e}")
    
    print(f"\n📊 Ingestion Summary:")
    print(f"   Total chunks loaded: {total_chunks}")
    
    # Get collection info
    info = await vector_store.get_collection_info()
    print(f"   Collection: {info['collection_name']}")
    print(f"   Total documents in DB: {info['document_count']}")
    
    # Test search
    print(f"\n🔍 Testing search functionality...")
    results = await vector_store.search("API authentication", limit=3)
    print(f"   Search results for 'API authentication': {len(results)} found")
    
    if results:
        print(f"   Top result preview: {results[0]['content'][:100]}...")

if __name__ == "__main__":
    asyncio.run(ingest_documentation())
```

Run the ingestion:

```bash
python ingest_docs.py
```

## 🧪 Step 4: Test the Setup

### Test 1: Verify ChromaDB Content

```bash
# Check collection directly via ChromaDB API
curl "http://localhost:8000/api/v2/collections" | python -m json.tool

# Get collection details
curl "http://localhost:8000/api/v2/collections/test-api-docs" | python -m json.tool
```

### Test 2: Test MCP Server Connection

```bash
# Start the MCP server in test mode
python mcp_server_container.py \
  --collection-name test-api-docs \
  --chroma-host localhost \
  --chroma-port 8000
```

### Test 3: Manual Search Test

Create `test_search.py`:

```python
#!/usr/bin/env python3
"""
Test search functionality with containerized ChromaDB
"""

import asyncio
from mcp_server_container import ChromaContainerVectorStore

async def test_search():
    """Test search functionality."""
    
    # Connect to vector store
    vector_store = ChromaContainerVectorStore(
        collection_name="test-api-docs",
        chroma_host="localhost",
        chroma_port=8000
    )
    
    # Get collection info
    info = await vector_store.get_collection_info()
    print(f"📊 Collection Info:")
    for key, value in info.items():
        print(f"   {key}: {value}")
    
    # Test queries
    test_queries = [
        "API authentication",
        "HTTP methods",
        "error handling",
        "REST endpoints",
        "JSON response format"
    ]
    
    print(f"\n🔍 Testing Search Queries:")
    print("=" * 40)
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        results = await vector_store.search(query, limit=2)
        
        if results:
            for i, result in enumerate(results, 1):
                score = result.get('similarity_score', 0)
                content_preview = result['content'][:100] + "..."
                metadata = result.get('metadata', {})
                
                print(f"  Result {i} (score: {score:.3f}):")
                print(f"    Source: {metadata.get('title', 'Unknown')}")
                print(f"    Preview: {content_preview}")
        else:
            print(f"  No results found")

if __name__ == "__main__":
    asyncio.run(test_search())
```

Run the test:

```bash
python test_search.py
```

## ⚙️ Step 5: Configure IDE Integration

### Update Cursor Configuration

Create `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "api-docs-container": {
      "command": "python",
      "args": [
        "/path/to/your/mcp_server_container.py",
        "--collection-name", "test-api-docs",
        "--chroma-host", "localhost",
        "--chroma-port", "8000"
      ],
      "env": {
        "PYTHONPATH": "/path/to/your/project"
      }
    }
  }
}
```

### Update VS Code Configuration

Create `.vscode/mcp.json`:

```json
{
  "mcpServers": {
    "api-docs-container": {
      "command": "python",
      "args": [
        "/path/to/your/mcp_server_container.py",
        "--collection-name", "test-api-docs",
        "--chroma-host", "localhost",
        "--chroma-port", "8000"
      ]
    }
  }
}
```

## 🔧 Troubleshooting

### ChromaDB Container Issues

```bash
# Check container logs
docker-compose logs chromadb

# Restart container
docker-compose restart chromadb

# Check if port is accessible
telnet localhost 8000
```

### Connection Issues

```bash
# Test ChromaDB API directly
curl http://localhost:8000/api/v1/heartbeat

# Check Python ChromaDB client
python -c "import chromadb; client = chromadb.HttpClient(host='localhost', port=8000); print('Connected:', client.heartbeat())"
```

### Data Persistence Issues

```bash
# Check data directory
ls -la ./chroma_data/

# Verify Docker volume mount
docker inspect chromadb-server | grep Mounts -A 10
```

### Performance Issues

```bash
# Monitor container resources
docker stats chromadb-server

# Check ChromaDB collection size
curl "http://localhost:8000/api/v1/collections/test-api-docs" | jq '.metadata'
```

## 📊 Step 6: Monitoring and Maintenance

### Health Checks

Create `health_check.py`:

```python
#!/usr/bin/env python3
"""
Health check script for ChromaDB container setup
"""

import requests
import chromadb
from chromadb.config import Settings

def check_chromadb_health():
    """Check ChromaDB container health."""
    try:
        # Test HTTP endpoint
        response = requests.get("http://localhost:8000/api/v1/heartbeat", timeout=10)
        response.raise_for_status()
        
        # Test client connection
        client = chromadb.HttpClient(host="localhost", port=8000)
        collections = client.list_collections()
        
        print("✅ ChromaDB container is healthy")
        print(f"   Available collections: {[c.name for c in collections]}")
        return True
        
    except Exception as e:
        print(f"❌ ChromaDB health check failed: {e}")
        return False

if __name__ == "__main__":
    check_chromadb_health()
```

### Backup Data

```bash
# Create backup of ChromaDB data
docker-compose stop chromadb
tar -czf chroma_backup_$(date +%Y%m%d_%H%M%S).tar.gz ./chroma_data/
docker-compose start chromadb
```

## 🎉 Success Verification

If everything is set up correctly, you should be able to:

1. ✅ Access ChromaDB at http://localhost:8000
2. ✅ See collections via API: `curl http://localhost:8000/api/v1/collections`
3. ✅ Run search tests successfully: `python test_search.py`
4. ✅ Start MCP server: `python mcp_server_container.py`
5. ✅ Use AI assistant in your IDE with the new tools

Your containerized ChromaDB setup is now ready for production use with the MCP server! 🚀

## 📝 Next Steps

1. **Load Your Real API Documentation**:
   ```bash
   python mcp_server_container.py --load-url https://your-api-docs.com
   ```

2. **Configure for Your Team**: Share the Docker Compose file and configurations

3. **Scale Up**: Consider using ChromaDB Cloud or clustering for production use

4. **Monitor Usage**: Set up logging and monitoring for the ChromaDB container