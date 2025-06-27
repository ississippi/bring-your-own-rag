# API Documentation RAG MCP Server

A **Model Context Protocol (MCP) server** that enables AI coding assistants to access proprietary API documentation through semantic search. This project implements "Bring Your Own RAG" for coding assistants, allowing developers to get contextual help from their own API documentation while coding.

## 🎯 Features

- **Semantic Search**: Natural language queries over API documentation
- **Multi-IDE Support**: Works with Cursor, VS Code, and any MCP-compatible client
- **Vector Store Integration**: Currently supports Chroma (extensible to others)
- **Web Documentation Loading**: Automatically crawls and indexes documentation from URLs
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
                       │ (Web Scraper)   │
                       └─────────────────┘
```

## 🚀 Quick Start

### 1. Installation

```bash
# Clone or download the project files
git clone <your-repo> api-docs-rag
cd api-docs-rag

# Run the setup script
python setup.py
```

The setup script will:
- Install all dependencies
- Create IDE configuration files
- Test the server
- Optionally load test documentation

### 2. Manual Setup (Alternative)

```bash
# Install dependencies
pip install -r requirements.txt

# Test the server
python mcp_server.py --help
```

### 3. Configure Your IDE

#### For Cursor

Create `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "api-docs-rag": {
      "command": "python",
      "args": [
        "/path/to/your/mcp_server.py",
        "--collection-name", "my-api-docs",
        "--chroma-path", "./chroma_db"
      ]
    }
  }
}
```

#### For VS Code

Create `.vscode/mcp.json` in your project:

```json
{
  "mcpServers": {
    "api-docs-rag": {
      "command": "python",
      "args": [
        "/path/to/your/mcp_server.py",
        "--collection-name", "my-api-docs",
        "--chroma-path", "./chroma_db"
      ]
    }
  }
}
```

### 4. Load Documentation

You can load documentation in several ways:

#### Option A: Command Line
```bash
python mcp_server.py --load-url https://api.example.com/docs --collection-name my-api
```

#### Option B: Through the AI Assistant
Once configured, ask your AI assistant:
```
"Load documentation from https://api.example.com/docs"
```

## 🔧 Usage

### Available Tools

The MCP server provides three main tools:

1. **`search_api_docs`** - Search through documentation
2. **`load_documentation`** - Load new documentation from URLs
3. **`get_collection_info`** - Get information about your documentation collection

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

```bash
# Start server with specific collection
python mcp_server.py --collection-name stripe-api --chroma-path ./stripe_docs

# Load documentation on startup
python mcp_server.py --load-url https://stripe.com/docs/api --collection-name stripe-api

# Use custom Chroma path
python mcp_server.py --chroma-path /custom/path/to/vector/db
```

## 🛠️ Configuration Options

### Command Line Arguments

- `--collection-name`: Name of the vector store collection (default: "api-docs")
- `--chroma-path`: Path to Chroma database directory (default: "./chroma_db")
- `--load-url`: URL to load documentation from on startup

### Environment Variables

You can also configure via environment variables:

```bash
export CHROMA_PATH="/path/to/chroma/db"
export COLLECTION_NAME="my-api-docs"
```

## 📁 Project Structure

```
api-docs-rag/
├── mcp_server.py          # Main MCP server implementation
├── requirements.txt       # Python dependencies
├── setup.py              # Setup and configuration script
├── README.md             # This file
├── .cursor/              # Cursor configuration
│   └── mcp.json
├── .vscode/              # VS Code configuration
│   └── mcp.json
└── chroma_db/            # Vector database (created automatically)
    └── ...
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
# Test with Python documentation
python mcp_server.py --load-url https://docs.python.org/3/library/requests.html

# Test with a REST API documentation
python mcp_server.py --load-url https://jsonplaceholder.typicode.com/guide/
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

2. **MCP server not appearing in IDE**
   - Restart your IDE after configuration
   - Check that paths in mcp.json are absolute
   - Verify Python path is correct

3. **No search results**
   - Ensure documentation is loaded: use `get_collection_info` tool
   - Try broader search terms
   - Check that the URL content was successfully scraped

4. **Server startup issues**
   ```bash
   # Test server directly
   python mcp_server.py --help
   
   # Check logs
   python mcp_server.py --collection-name test 2>&1 | tee server.log
   ```

### Debug Mode

Enable verbose logging:

```python
# Add to mcp_server.py
logging.basicConfig(level=logging.DEBUG)
```

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- Support for more vector stores
- Better document chunking strategies
- Support for different documentation formats (OpenAPI, etc.)
- Performance optimizations
- Better error handling

## 📝 License

This project is open source. See LICENSE file for details.

## 🙏 Acknowledgments

- Built using [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- Vector embeddings powered by [sentence-transformers](https://www.sbert.net/)
- Vector storage via [ChromaDB](https://www.trychroma.com/)
- Web scraping with [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)

---

**Happy coding with AI-powered documentation assistance! 🚀**