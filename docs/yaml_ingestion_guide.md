# YAML File Ingestion Usage Guide

This guide shows how to use the enhanced `ingest_docs_yaml.py` script to load API documentation from YAML files into ChromaDB for use with the MCP server.

## 🔧 Setup

### Install Additional Dependencies

Add to your `requirements.txt`:
```text
# Existing dependencies...
mcp>=1.0.0
chromadb>=0.4.18
sentence-transformers>=2.2.2
requests>=2.31.0
beautifulsoup4>=4.12.2
lxml>=4.9.3
pydantic>=2.4.0

# New dependency for YAML support
PyYAML>=6.0
```

Install the new dependency:
```bash
pip install PyYAML>=6.0
```

## 📁 Supported YAML Formats

The script automatically detects and processes different YAML formats:

### 1. **OpenAPI/Swagger Specifications**
- Detects `openapi` or `swagger` fields
- Extracts endpoints, schemas, security schemes
- Creates searchable chunks for each API operation

### 2. **Custom API Documentation**
- Looks for `api_documentation` or `endpoints` fields
- Supports custom documentation structures
- Extracts authentication, examples, and endpoint details

### 3. **Generic YAML Files**
- Flattens any YAML structure into searchable chunks
- Good for configuration files with documentation
- Preserves hierarchical structure in metadata

## 🚀 Usage Examples

### Basic YAML File Ingestion

```bash
# Ingest a single OpenAPI specification
python ingest_docs_yaml.py --yaml-files openapi_spec.yaml

# Ingest multiple YAML files
python ingest_docs_yaml.py --yaml-files api1.yaml api2.yaml config.yaml

# Ingest all YAML files from a directory
python ingest_docs_yaml.py --yaml-dir ./docs/apis/

# Combine YAML files and web scraping
python ingest_docs_yaml.py \
  --yaml-files openapi.yaml \
  --urls https://docs.external-api.com
```

### Advanced Options

```bash
# Specify ChromaDB connection
python ingest_docs_yaml.py \
  --yaml-files payment_api.yaml \
  --collection-name payment-docs \
  --chroma-host localhost \
  --chroma-port 8000

# Clear existing collection and reload
python ingest_docs_yaml.py \
  --yaml-files updated_api.yaml \
  --collection-name my-api-docs \
  --clear-collection

# Process directory with custom collection
python ingest_docs_yaml.py \
  --yaml-dir ./internal-apis/ \
  --collection-name internal-api-docs \
  --clear-collection
```

## 📊 What Gets Extracted

### From OpenAPI Specifications:

#### **API Information**
- Title, description, version
- Contact information and licensing
- Server URLs and environments

#### **Endpoints**
- HTTP method and path
- Operation summary and description
- Parameters (path, query, header, body)
- Request/response schemas
- Status codes and error responses

#### **Schemas**
- Data models and their properties
- Required fields and validation rules
- Nested object structures

#### **Security**
- Authentication schemes (OAuth, API Key, etc.)
- Security requirements per endpoint

### From Custom API Documentation:

#### **Overview**
- API description and purpose
- General usage guidelines

#### **Authentication**
- Authentication methods
- Code examples for auth

#### **Endpoints**
- Custom endpoint definitions
- Request/response examples
- Parameter descriptions

#### **Examples**
- Code samples
- Error handling patterns
- Best practices

### From Generic YAML:

#### **Hierarchical Data**
- Configuration settings
- Service definitions
- Any structured YAML content

## 🔍 Search Examples

After ingestion, you can search for various types of information:

### **Authentication Queries**
```
"How do I authenticate with the API?"
"Bearer token authentication"
"OAuth 2.0 flow setup"
```

### **Endpoint Queries**
```
"Create payment endpoint"
"GET user profile API"
"Update user information"
```

### **Schema Queries**
```
"Payment request schema"
"User model properties"
"Card details validation"
```

### **Error Handling**
```
"Error response format"
"HTTP status codes"
"Rate limiting"
```

## 📝 Example Workflow

### 1. Prepare Your YAML Files

Create API documentation in YAML format (see example files):
- `openapi_payment.yaml` - OpenAPI specification
- `internal_apis.yaml` - Custom API documentation
- `config_docs.yaml` - Configuration with documentation

### 2. Start ChromaDB

```bash
# Start ChromaDB container
docker-compose -f docker-compose.local.yml up -d
```

### 3. Ingest Documentation

```bash
# Ingest all API documentation
python ingest_docs_yaml.py \
  --yaml-dir ./api-docs/ \
  --collection-name company-apis \
  --clear-collection
```

Expected output:
```
📄 Processing YAML file: ./api-docs/openapi_payment.yaml
  Detected YAML type: openapi
   ✅ Added 15 chunks from ./api-docs/openapi_payment.yaml

📄 Processing YAML file: ./api-docs/internal_apis.yaml
  Detected YAML type: custom_api_docs
   ✅ Added 8 chunks from ./api-docs/internal_apis.yaml

📊 Ingestion Summary:
   Total chunks loaded: 23
   Collection: company-apis
   Total documents in DB: 23

🔍 Testing search functionality...
   'authentication': 3 results
      Top result from: ./api-docs/openapi_payment.yaml (security)
   'API endpoints': 5 results
      Top result from: ./api-docs/internal_apis.yaml (endpoint)
```

### 4. Configure MCP Server

Update your `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "company-apis": {
      "command": "python",
      "args": [
        "/path/to/mcp_server_container.py",
        "--collection-name", "company-apis",
        "--chroma-host", "localhost",
        "--chroma-port", "8000"
      ]
    }
  }
}
```

### 5. Start Coding with AI Assistance

Open Cursor/VS Code and start coding:

**Developer**: "How do I create a payment in the Payment API?"

**AI Assistant**: *Searches YAML documentation and responds with:*
> Found payment creation documentation in your Payment API specification:
> 
> **POST /payments**
> - Creates a new payment transaction
> - Requires authentication with Bearer token
> - Request body must include: amount, currency, payment_method
> - Returns 201 with payment ID on success
> 
> Example request:
> ```json
> {
>   "amount": 29.99,
>   "currency": "USD", 
>   "payment_method": {
>     "type": "card",
>     "card": { ... }
>   }
> }
> ```

## 🛠️ Troubleshooting

### Common Issues

#### **YAML Parsing Errors**
```bash
# Check YAML syntax
python -c "import yaml; print(yaml.safe_load(open('your-file.yaml')))"
```

#### **No Chunks Generated**
- Check if YAML file has meaningful content
- Ensure proper structure for auto-detection
- Use `--verbose` flag for detailed logging

#### **ChromaDB Connection Issues**
```bash
# Test ChromaDB connectivity
curl http://localhost:8000/api/v1/heartbeat

# Check if collection exists
curl http://localhost:8000/api/v1/collections
```

#### **Empty Search Results**
```bash
# Check collection contents
python -c "
import chromadb
client = chromadb.HttpClient(host='localhost', port=8000)
collection = client.get_collection('your-collection-name')
print('Document count:', collection.count())
"
```

## 🎯 Best Practices

### **YAML File Organization**
```
project/
├── docs/
│   ├── apis/
│   │   ├── payment_api.yaml      # OpenAPI specs
│   │   ├── user_api.yaml
│   │   └── notification_api.yaml
│   ├── internal/
│   │   ├── auth_service.yaml     # Custom docs
│   │   └── config_docs.yaml
│   └── examples/
│       └── integration_examples.yaml
```

### **Collection Naming**
- Use descriptive collection names: `payment-api-v2`, `internal-services`
- Separate different API versions or services
- Use consistent naming conventions

### **Content Organization**
- Put related APIs in the same collection
- Use clear, descriptive section names
- Include examples and error handling
- Document authentication thoroughly

### **Incremental Updates**
```bash
# Update specific API documentation
python ingest_docs_yaml.py \
  --yaml-files updated_payment_api.yaml \
  --collection-name payment-api-v2 \
  --clear-collection  # Only if you want to replace all content
```

This YAML ingestion capability makes it easy to keep your AI assistant up-to-date with the latest API documentation, whether it's OpenAPI specifications, custom documentation, or internal configuration files.
