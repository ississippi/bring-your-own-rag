# Bring Your Own RAG - API Documentation MCP Server

A **Model Context Protocol (MCP) server** that enables AI coding assistants to access proprietary API documentation through semantic search. This project implements "Bring Your Own RAG" for coding assistants, allowing developers to get contextual help from their own API documentation while coding.

## 🎯 Features

- **Semantic Search**: Natural language queries over API documentation
- **Multi-IDE Support**: Works with Cursor, VS Code, and any MCP-compatible client
- **Vector Store Integration**: Currently supports Chroma (extensible to others)
- **Web Documentation Loading**: Automatically crawls and indexes documentation from URLs
- **YAML Documentation Support**: Load OpenAPI specs and custom API documentation from YAML files
- **Containerized Deployment**: Docker support for production deployments
- **Real-time Integration**: Live access to documentation while coding
- **Extensible Architecture**: Easy to add support for other vector stores

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Cursor/VSCode │    │   MCP Server    │    │  Vector Store   │
│                 │◄──►│                 │◄──►│    (Chroma)     │
│  AI Assistant   │    │  API Docs RAG   │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Documentation   │
                       │   Loader        │
                       │ (Web + YAML)    │
                       └─────────────────┘
```

## 🚀 Quick Start

### Option 1: Containerized Setup (Recommended)

```bash
# Clone the repository
git clone <your-repo> bring-your-own-rag
cd bring-your-own-rag

# Ensure you have Python 3.10+ installed
python --version  # Should be 3.10 or higher

# Start ChromaDB container
cd data
docker-compose up -d

# Install Python dependencies
cd ..
pip install -r requirements.txt

# Load sample documentation
cd data
python ingest_docs_yaml.py --yaml-files example_files.yaml exocoin_openapi_spec.yaml --collection-name test-collection --chroma-host localhost --chroma-port 8000 --clear-collection

# Start the MCP server
python mcp_server_container.py --collection-name test-collection --chroma-host localhost --chroma-port 8000
```

### Option 2: Local Setup

```bash
# Clone the repository
git clone <your-repo> bring-your-own-rag
cd bring-your-own-rag

# Ensure you have Python 3.10+ installed
python --version  # Should be 3.10 or higher

# Install dependencies
pip install -r requirements.txt

# Start with local ChromaDB
python mcp_server.py --collection-name my-api-docs --chroma-path ./chroma_db
```

### Option 3: Using the Setup Script

```bash
# Clone the repository
git clone <your-repo> bring-your-own-rag
cd bring-your-own-rag

# Run the setup script
python setup.py
```

## 🔧 Usage

### Available Tools

The MCP server provides three main tools:

1. **`search_api_docs`** - Search through documentation
2. **`load_documentation`** - Load new documentation from URLs
3. **`get_collection_info`** - Get information about your documentation collection

### Loading Documentation

#### From YAML Files (Recommended)

```bash
# Load specific YAML files
cd data
python ingest_docs_yaml.py --yaml-files your_api_spec.yaml --collection-name my-api-docs --chroma-host localhost --chroma-port 8000

# Load all YAML files in a directory
python ingest_docs_yaml.py --yaml-dir . --collection-name my-api-docs --chroma-host localhost --chroma-port 8000

# Clear existing collection and load fresh data
python ingest_docs_yaml.py --yaml-files your_files.yaml --collection-name my-api-docs --chroma-host localhost --chroma-port 8000 --clear-collection
```

#### From URLs

```bash
# Load documentation from a URL
python mcp_server.py --load-url https://api.example.com/docs --collection-name my-api-docs
```

### Managing Collections

```bash
# View collection contents
cd data
python collection_manager.py --action view

# View collection statistics
python collection_manager.py --action stats

# List all collections
python collection_manager.py --action list

# Add sample data for testing
python collection_manager.py --action add-sample --sample-type default

# Add API-specific sample data
python collection_manager.py --action add-sample --sample-type api

# Search the collection
python collection_manager.py --action search --query "authentication"

# Export collection to file
python collection_manager.py --action export --output my_collection.json --format json

# View with full content
python collection_manager.py --action view --full-content --n 3
```

### Example Interactions

#### In Cursor/VS Code Chat:

**Developer**: "I need to authenticate with the PaymentAPI"

**AI Assistant**: *Uses `search_api_docs` tool automatically*
> Found relevant documentation for authentication...
> 
> **API Authentication**
> The PaymentAPI uses OAuth 2.0 with client credentials flow...
> 
> ```javascript
> const auth = await PaymentAPI.authenticate({
>   clientId: process.env.PAYMENT_CLIENT_ID,
>   clientSecret: process.env.PAYMENT_SECRET
> });
> ```

**Developer**: "Show me error handling examples"

**AI Assistant**: *Searches and provides contextual error handling patterns from your documentation*

### Command Line Usage

#### Containerized Mode
```bash
# Start server with containerized ChromaDB
python data/mcp_server_container.py --collection-name my-api-docs --chroma-host localhost --chroma-port 8000

# Load documentation on startup
python data/mcp_server_container.py --collection-name my-api-docs --chroma-host localhost --chroma-port 8000 --load-url https://api.example.com/docs
```

#### Local Mode
```bash
# Start server with local ChromaDB
python mcp_server.py --collection-name my-api-docs --chroma-path ./chroma_db

# Load documentation on startup
python mcp_server.py --load-url https://api.example.com/docs --collection-name my-api-docs
```

## 🛠️ Configuration Options

### Command Line Arguments

#### Containerized Mode (`mcp_server_container.py`)
- `--collection-name`: Name of the vector store collection (default: "api-docs")
- `--chroma-host`: ChromaDB container host (default: "localhost")
- `--chroma-port`: ChromaDB container port (default: 8000)
- `--load-url`: URL to load documentation from on startup

#### Local Mode (`mcp_server.py`)
- `--collection-name`: Name of the vector store collection (default: "api-docs")
- `--chroma-path`: Path to Chroma database directory (default: "./chroma_db")
- `--load-url`: URL to load documentation from on startup

### Environment Variables

You can also configure via environment variables:

```bash
export CHROMA_HOST="localhost"
export CHROMA_PORT="8000"
export COLLECTION_NAME="my-api-docs"
```

## 📁 Project Structure

```
bring-your-own-rag/
├── mcp_server.py              # Main MCP server (local mode)
├── requirements.txt           # Python dependencies
├── setup.py                  # Setup and configuration script
├── test_mcp_server.py        # Test suite
├── vendor_setup_example.py   # Vendor setup example
├── README.md                 # This file
├── .cursor/                  # Cursor configuration
│   └── mcp.json
├── .vscode/                  # VS Code configuration
│   └── mcp.json
├── docs/                     # Documentation
│   ├── chroma_setup_guide.md
│   ├── yaml_ingestion_guide.md
│   ├── mcp_communication_protocols.md
│   ├── deployment_models_guide.md
│   └── security_model_guide.md
└── data/                     # Data and containerized setup
    ├── mcp_server_container.py    # Containerized MCP server
    ├── ingest_docs_yaml.py        # YAML documentation loader
    ├── collection_manager.py      # Collection management tools
    ├── print_collection_sample.py # Simple collection viewer
    ├── docker-compose.yml         # ChromaDB container setup
    ├── example_files.yaml         # Sample API documentation
    ├── exocoin_openapi_spec.yaml  # Sample OpenAPI spec
    ├── chroma_venv/              # Virtual environment
    └── chroma_data/              # ChromaDB data directory
```

## 🔌 Extending to Other Vector Stores

The project is designed to be extensible. To add support for other vector stores:

1. **Implement the `VectorStore` interface**:

```python
class MyVectorStore(VectorStore):
    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        # Implementation here
        pass
    
    async def search(self, query: str, limit: int = 5, filters: Optional[Dict] = None) -> List[Dict]:
        # Implementation here
        pass
    
    async def get_collection_info(self) -> Dict[str, Any]:
        # Implementation here
        pass
```

2. **Update the main function** to use your vector store:

```python
# In main()
vector_store = MyVectorStore(config_params)
```

### Planned Vector Store Support

- ✅ Chroma (implemented)
- 🔄 Qdrant (coming soon)
- 🔄 Pinecone (coming soon)
- 🔄 Weaviate (coming soon)

## 🧪 Testing

### Test with Sample Documentation

```bash
# Test with provided YAML files
cd data
python ingest_docs_yaml.py --yaml-files example_files.yaml exocoin_openapi_spec.yaml --collection-name test-collection --chroma-host localhost --chroma-port 8000

# Test with web documentation
python mcp_server.py --load-url https://docs.python.org/3/library/requests.html
```

### Verify Setup

1. Start your IDE (Cursor or VS Code)
2. Open a project
3. Start a chat with the AI assistant
4. Ask: "What tools are available?"
5. You should see the API documentation tools listed

## 🚨 Troubleshooting

### Common Issues

1. **"Module not found" errors**
   ```bash
   pip install -r requirements.txt
   ```

2. **ChromaDB connection issues**
   ```bash
   # Check if ChromaDB container is running
   cd data
   docker-compose ps
   
   # Restart ChromaDB
   docker-compose restart
   ```

3. **MCP server not appearing in IDE**
   - Restart your IDE after configuration
   - Check that paths in mcp.json are absolute
   - Verify Python path is correct

4. **No search results**
   - Ensure documentation is loaded: use `get_collection_info` tool
   - Try broader search terms
   - Check that the YAML files were successfully processed

5. **Server startup issues**
   ```bash
   # Test server directly
   python mcp_server.py --help
   python data/mcp_server_container.py --help
   
   # Check logs
   python mcp_server.py --collection-name test 2>&1 | tee server.log
   ```

### Debug Mode

Enable verbose logging:

```python
# Add to mcp_server.py or mcp_server_container.py
logging.basicConfig(level=logging.DEBUG)
```

## 📚 Documentation

- [Chroma Setup Guide](docs/chroma_setup_guide.md) - Detailed ChromaDB setup instructions
- [YAML Ingestion Guide](docs/yaml_ingestion_guide.md) - How to load YAML documentation
- [MCP Communication Protocols](docs/mcp_communication_protocols.md) - Protocol details
- [Deployment Models Guide](docs/deployment_models_guide.md) - Deployment options
- [Security Model Guide](docs/security_model_guide.md) - Security considerations

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- Support for more vector stores
- Better document chunking strategies
- Support for different documentation formats (OpenAPI, etc.)
- Performance optimizations
- Better error handling
- Additional documentation loaders

## 📝 License

This project is open source. See LICENSE file for details.

## 🙏 Acknowledgments

- Built using [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- Vector embeddings powered by [sentence-transformers](https://www.sbert.net/)
- Vector storage via [ChromaDB](https://www.trychroma.com/)
- Web scraping with [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)
- Container orchestration with [Docker Compose](https://docs.docker.com/compose/)

---

**Happy coding with AI-powered documentation assistance! 🚀**