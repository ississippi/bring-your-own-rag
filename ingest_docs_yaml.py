#!/usr/bin/env python3
"""
Enhanced script to ingest API documentation into containerized ChromaDB
Supports YAML files (OpenAPI specs, custom docs) in addition to web scraping
"""

import asyncio
import sys
import yaml
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
import argparse
import logging

from mcp_server_container import ChromaContainerVectorStore
from mcp_server import DocumentLoader, DocumentChunk

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class YAMLDocumentChunk:
    """Extended DocumentChunk for YAML-specific metadata."""
    content: str
    source_file: str
    section_path: str  # e.g., "paths./users.get.responses.200"
    chunk_type: str    # e.g., "endpoint", "schema", "description"
    chunk_id: str
    metadata: Dict[str, Any]


class YAMLDocumentProcessor:
    """Processes YAML files and converts them to searchable document chunks."""
    
    def __init__(self):
        self.chunk_strategies = {
            'openapi': self._process_openapi_spec,
            'swagger': self._process_openapi_spec,
            'generic': self._process_generic_yaml,
            'custom_api_docs': self._process_custom_api_docs
        }
    
    def detect_yaml_type(self, yaml_content: Dict[str, Any]) -> str:
        """Detect the type of YAML file."""
        if 'openapi' in yaml_content or 'swagger' in yaml_content:
            return 'openapi'
        elif 'api_documentation' in yaml_content or 'endpoints' in yaml_content:
            return 'custom_api_docs'
        else:
            return 'generic'
    
    def process_yaml_file(self, file_path: str) -> List[DocumentChunk]:
        """Process a YAML file and return document chunks."""
        logger.info(f"Processing YAML file: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Handle multi-document YAML files
                documents = list(yaml.safe_load_all(f))
            
            all_chunks = []
            
            for doc_index, yaml_content in enumerate(documents):
                if yaml_content is None:
                    continue
                
                yaml_type = self.detect_yaml_type(yaml_content)
                logger.info(f"  Detected YAML type: {yaml_type}")
                
                processor = self.chunk_strategies.get(yaml_type, self._process_generic_yaml)
                chunks = processor(yaml_content, file_path, doc_index)
                all_chunks.extend(chunks)
            
            logger.info(f"  Generated {len(all_chunks)} chunks from {file_path}")
            return all_chunks
            
        except Exception as e:
            logger.error(f"Error processing YAML file {file_path}: {e}")
            return []
    
    def _process_openapi_spec(self, spec: Dict[str, Any], file_path: str, doc_index: int = 0) -> List[DocumentChunk]:
        """Process OpenAPI/Swagger specification."""
        chunks = []
        
        # Basic info chunk
        info = spec.get('info', {})
        if info:
            content = self._format_api_info(info)
            chunk = self._create_chunk(
                content=content,
                file_path=file_path,
                section_path="info",
                chunk_type="api_info",
                metadata={
                    "api_title": info.get('title', 'Unknown API'),
                    "api_version": info.get('version', 'unknown'),
                    "doc_index": doc_index
                }
            )
            chunks.append(chunk)
        
        # Server information
        servers = spec.get('servers', [])
        if servers:
            content = self._format_servers(servers)
            chunk = self._create_chunk(
                content=content,
                file_path=file_path,
                section_path="servers",
                chunk_type="server_info",
                metadata={"doc_index": doc_index}
            )
            chunks.append(chunk)
        
        # Process paths (endpoints)
        paths = spec.get('paths', {})
        for path, path_item in paths.items():
            chunks.extend(self._process_openapi_path(path, path_item, file_path, doc_index))
        
        # Process components/schemas
        components = spec.get('components', {})
        if components:
            chunks.extend(self._process_openapi_components(components, file_path, doc_index))
        
        return chunks
    
    def _process_openapi_path(self, path: str, path_item: Dict[str, Any], file_path: str, doc_index: int) -> List[DocumentChunk]:
        """Process a single OpenAPI path."""
        chunks = []
        
        # Common path parameters
        parameters = path_item.get('parameters', [])
        
        # Process each HTTP method
        for method in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head', 'trace']:
            if method in path_item:
                operation = path_item[method]
                content = self._format_openapi_operation(path, method.upper(), operation, parameters)
                
                chunk = self._create_chunk(
                    content=content,
                    file_path=file_path,
                    section_path=f"paths.{path}.{method}",
                    chunk_type="endpoint",
                    metadata={
                        "endpoint_path": path,
                        "http_method": method.upper(),
                        "operation_id": operation.get('operationId'),
                        "tags": operation.get('tags', []),
                        "doc_index": doc_index
                    }
                )
                chunks.append(chunk)
        
        return chunks
    
    def _process_openapi_components(self, components: Dict[str, Any], file_path: str, doc_index: int) -> List[DocumentChunk]:
        """Process OpenAPI components (schemas, responses, etc.)."""
        chunks = []
        
        # Process schemas
        schemas = components.get('schemas', {})
        for schema_name, schema_def in schemas.items():
            content = self._format_schema(schema_name, schema_def)
            
            chunk = self._create_chunk(
                content=content,
                file_path=file_path,
                section_path=f"components.schemas.{schema_name}",
                chunk_type="schema",
                metadata={
                    "schema_name": schema_name,
                    "schema_type": schema_def.get('type'),
                    "doc_index": doc_index
                }
            )
            chunks.append(chunk)
        
        # Process security schemes
        security_schemes = components.get('securitySchemes', {})
        for scheme_name, scheme_def in security_schemes.items():
            content = self._format_security_scheme(scheme_name, scheme_def)
            
            chunk = self._create_chunk(
                content=content,
                file_path=file_path,
                section_path=f"components.securitySchemes.{scheme_name}",
                chunk_type="security",
                metadata={
                    "security_scheme": scheme_name,
                    "security_type": scheme_def.get('type'),
                    "doc_index": doc_index
                }
            )
            chunks.append(chunk)
        
        return chunks
    
    def _process_custom_api_docs(self, content: Dict[str, Any], file_path: str, doc_index: int = 0) -> List[DocumentChunk]:
        """Process custom API documentation YAML format."""
        chunks = []
        
        # Process API documentation sections
        api_docs = content.get('api_documentation', content)
        
        # Overview/Description
        if 'overview' in api_docs:
            chunk = self._create_chunk(
                content=f"API Overview:\n{api_docs['overview']}",
                file_path=file_path,
                section_path="overview",
                chunk_type="overview",
                metadata={"doc_index": doc_index}
            )
            chunks.append(chunk)
        
        # Authentication
        if 'authentication' in api_docs:
            auth_content = self._format_authentication(api_docs['authentication'])
            chunk = self._create_chunk(
                content=auth_content,
                file_path=file_path,
                section_path="authentication",
                chunk_type="authentication",
                metadata={"doc_index": doc_index}
            )
            chunks.append(chunk)
        
        # Endpoints
        endpoints = api_docs.get('endpoints', [])
        for i, endpoint in enumerate(endpoints):
            content = self._format_custom_endpoint(endpoint)
            chunk = self._create_chunk(
                content=content,
                file_path=file_path,
                section_path=f"endpoints.{i}",
                chunk_type="endpoint",
                metadata={
                    "endpoint_name": endpoint.get('name'),
                    "endpoint_path": endpoint.get('path'),
                    "method": endpoint.get('method'),
                    "doc_index": doc_index
                }
            )
            chunks.append(chunk)
        
        # Examples
        if 'examples' in api_docs:
            examples_content = self._format_examples(api_docs['examples'])
            chunk = self._create_chunk(
                content=examples_content,
                file_path=file_path,
                section_path="examples",
                chunk_type="examples",
                metadata={"doc_index": doc_index}
            )
            chunks.append(chunk)
        
        return chunks
    
    def _process_generic_yaml(self, content: Dict[str, Any], file_path: str, doc_index: int = 0) -> List[DocumentChunk]:
        """Process generic YAML file by flattening structure."""
        chunks = []
        
        def flatten_yaml(obj: Any, path: str = "", level: int = 0) -> List[tuple]:
            """Recursively flatten YAML structure."""
            items = []
            
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{path}.{key}" if path else key
                    
                    if isinstance(value, (dict, list)) and level < 5:  # Limit recursion depth
                        items.extend(flatten_yaml(value, new_path, level + 1))
                    else:
                        # Create a chunk for this key-value pair
                        if isinstance(value, str) and len(value) > 20:  # Only meaningful text
                            items.append((new_path, key, str(value)))
                        elif not isinstance(value, str):
                            items.append((new_path, key, yaml.dump(value, default_flow_style=False)))
            
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    new_path = f"{path}[{i}]"
                    if isinstance(item, (dict, list)) and level < 5:
                        items.extend(flatten_yaml(item, new_path, level + 1))
                    else:
                        items.append((new_path, f"item_{i}", str(item)))
            
            return items
        
        flattened = flatten_yaml(content)
        
        for section_path, section_name, section_content in flattened:
            chunk = self._create_chunk(
                content=f"{section_name}:\n{section_content}",
                file_path=file_path,
                section_path=section_path,
                chunk_type="generic",
                metadata={
                    "section_name": section_name,
                    "doc_index": doc_index
                }
            )
            chunks.append(chunk)
        
        return chunks
    
    # Formatting methods
    
    def _format_api_info(self, info: Dict[str, Any]) -> str:
        """Format API info section."""
        content = f"# {info.get('title', 'API Documentation')}\n\n"
        
        if 'description' in info:
            content += f"**Description:** {info['description']}\n\n"
        
        if 'version' in info:
            content += f"**Version:** {info['version']}\n\n"
        
        if 'contact' in info:
            contact = info['contact']
            content += "**Contact Information:**\n"
            if 'name' in contact:
                content += f"- Name: {contact['name']}\n"
            if 'email' in contact:
                content += f"- Email: {contact['email']}\n"
            if 'url' in contact:
                content += f"- URL: {contact['url']}\n"
            content += "\n"
        
        if 'license' in info:
            license_info = info['license']
            content += f"**License:** {license_info.get('name', 'Unknown')}"
            if 'url' in license_info:
                content += f" ({license_info['url']})"
            content += "\n\n"
        
        return content
    
    def _format_servers(self, servers: List[Dict[str, Any]]) -> str:
        """Format server information."""
        content = "# API Servers\n\n"
        
        for i, server in enumerate(servers):
            content += f"## Server {i + 1}\n"
            content += f"**URL:** {server.get('url', 'Unknown')}\n"
            
            if 'description' in server:
                content += f"**Description:** {server['description']}\n"
            
            if 'variables' in server:
                content += "**Variables:**\n"
                for var_name, var_info in server['variables'].items():
                    content += f"- {var_name}: {var_info.get('description', 'No description')}\n"
                    if 'default' in var_info:
                        content += f"  - Default: {var_info['default']}\n"
            
            content += "\n"
        
        return content
    
    def _format_openapi_operation(self, path: str, method: str, operation: Dict[str, Any], path_params: List = None) -> str:
        """Format an OpenAPI operation."""
        content = f"# {method} {path}\n\n"
        
        if 'summary' in operation:
            content += f"**Summary:** {operation['summary']}\n\n"
        
        if 'description' in operation:
            content += f"**Description:** {operation['description']}\n\n"
        
        if 'operationId' in operation:
            content += f"**Operation ID:** {operation['operationId']}\n\n"
        
        if 'tags' in operation:
            content += f"**Tags:** {', '.join(operation['tags'])}\n\n"
        
        # Parameters
        all_params = list(path_params or []) + operation.get('parameters', [])
        if all_params:
            content += "## Parameters\n\n"
            for param in all_params:
                content += f"- **{param.get('name')}** ({param.get('in', 'unknown')}): {param.get('description', 'No description')}\n"
                if param.get('required'):
                    content += "  - Required: Yes\n"
                if 'schema' in param:
                    content += f"  - Type: {param['schema'].get('type', 'unknown')}\n"
            content += "\n"
        
        # Request body
        if 'requestBody' in operation:
            req_body = operation['requestBody']
            content += "## Request Body\n\n"
            if 'description' in req_body:
                content += f"{req_body['description']}\n\n"
            
            if 'content' in req_body:
                for media_type in req_body['content'].keys():
                    content += f"**Content-Type:** {media_type}\n"
            content += "\n"
        
        # Responses
        if 'responses' in operation:
            content += "## Responses\n\n"
            for status_code, response in operation['responses'].items():
                content += f"### {status_code}\n"
                if 'description' in response:
                    content += f"{response['description']}\n"
                content += "\n"
        
        return content
    
    def _format_schema(self, schema_name: str, schema_def: Dict[str, Any]) -> str:
        """Format a schema definition."""
        content = f"# Schema: {schema_name}\n\n"
        
        if 'description' in schema_def:
            content += f"**Description:** {schema_def['description']}\n\n"
        
        if 'type' in schema_def:
            content += f"**Type:** {schema_def['type']}\n\n"
        
        # Properties
        if 'properties' in schema_def:
            content += "## Properties\n\n"
            for prop_name, prop_def in schema_def['properties'].items():
                content += f"- **{prop_name}**"
                if 'type' in prop_def:
                    content += f" ({prop_def['type']})"
                if 'description' in prop_def:
                    content += f": {prop_def['description']}"
                content += "\n"
            content += "\n"
        
        # Required fields
        if 'required' in schema_def:
            content += f"**Required fields:** {', '.join(schema_def['required'])}\n\n"
        
        return content
    
    def _format_security_scheme(self, scheme_name: str, scheme_def: Dict[str, Any]) -> str:
        """Format a security scheme."""
        content = f"# Security Scheme: {scheme_name}\n\n"
        
        if 'type' in scheme_def:
            content += f"**Type:** {scheme_def['type']}\n\n"
        
        if 'description' in scheme_def:
            content += f"**Description:** {scheme_def['description']}\n\n"
        
        # Type-specific details
        if scheme_def.get('type') == 'http':
            if 'scheme' in scheme_def:
                content += f"**HTTP Scheme:** {scheme_def['scheme']}\n"
        elif scheme_def.get('type') == 'apiKey':
            if 'in' in scheme_def:
                content += f"**Location:** {scheme_def['in']}\n"
            if 'name' in scheme_def:
                content += f"**Parameter Name:** {scheme_def['name']}\n"
        elif scheme_def.get('type') == 'oauth2':
            if 'flows' in scheme_def:
                content += "**OAuth2 Flows:**\n"
                for flow_type, flow_def in scheme_def['flows'].items():
                    content += f"- {flow_type}: {flow_def.get('authorizationUrl', 'N/A')}\n"
        
        return content
    
    def _format_authentication(self, auth_config: Dict[str, Any]) -> str:
        """Format authentication configuration."""
        content = "# Authentication\n\n"
        
        if 'type' in auth_config:
            content += f"**Type:** {auth_config['type']}\n\n"
        
        if 'description' in auth_config:
            content += f"{auth_config['description']}\n\n"
        
        if 'examples' in auth_config:
            content += "## Examples\n\n"
            for example in auth_config['examples']:
                if isinstance(example, str):
                    content += f"```\n{example}\n```\n\n"
                else:
                    content += f"```yaml\n{yaml.dump(example)}\n```\n\n"
        
        return content
    
    def _format_custom_endpoint(self, endpoint: Dict[str, Any]) -> str:
        """Format a custom endpoint definition."""
        content = f"# {endpoint.get('method', 'GET')} {endpoint.get('path', '/unknown')}\n\n"
        
        if 'name' in endpoint:
            content += f"**Name:** {endpoint['name']}\n\n"
        
        if 'description' in endpoint:
            content += f"**Description:** {endpoint['description']}\n\n"
        
        if 'parameters' in endpoint:
            content += "## Parameters\n\n"
            for param in endpoint['parameters']:
                content += f"- **{param.get('name')}**: {param.get('description', 'No description')}\n"
            content += "\n"
        
        if 'example_request' in endpoint:
            content += "## Example Request\n\n"
            content += f"```\n{endpoint['example_request']}\n```\n\n"
        
        if 'example_response' in endpoint:
            content += "## Example Response\n\n"
            content += f"```\n{endpoint['example_response']}\n```\n\n"
        
        return content
    
    def _format_examples(self, examples: Dict[str, Any]) -> str:
        """Format examples section."""
        content = "# API Examples\n\n"
        
        for example_name, example_content in examples.items():
            content += f"## {example_name}\n\n"
            if isinstance(example_content, str):
                content += f"{example_content}\n\n"
            else:
                content += f"```yaml\n{yaml.dump(example_content)}\n```\n\n"
        
        return content
    
    def _create_chunk(self, content: str, file_path: str, section_path: str, chunk_type: str, metadata: Dict[str, Any]) -> DocumentChunk:
        """Create a DocumentChunk with proper ID and metadata."""
        # Create unique ID
        chunk_id = hashlib.md5(f"{file_path}#{section_path}#{content[:100]}".encode()).hexdigest()
        
        # Enhance metadata
        enhanced_metadata = {
            "source_type": "yaml",
            "section_path": section_path,
            "chunk_type": chunk_type,
            "file_path": file_path,
            **metadata
        }
        
        return DocumentChunk(
            content=content,
            url=f"file://{file_path}",
            title=Path(file_path).stem,
            section=section_path,
            chunk_id=chunk_id,
            metadata=enhanced_metadata
        )


async def ingest_yaml_documentation():
    """Enhanced documentation ingestion supporting YAML files."""
    parser = argparse.ArgumentParser(description="Ingest API documentation from YAML files and URLs")
    parser.add_argument("--yaml-files", nargs="+", help="YAML files to process")
    parser.add_argument("--yaml-dir", help="Directory containing YAML files")
    parser.add_argument("--urls", nargs="+", help="URLs to scrape")
    parser.add_argument("--collection-name", default="api-docs", help="ChromaDB collection name")
    parser.add_argument("--chroma-host", default="localhost", help="ChromaDB host")
    parser.add_argument("--chroma-port", type=int, default=8000, help="ChromaDB port")
    parser.add_argument("--clear-collection", action="store_true", help="Clear existing collection")
    
    args = parser.parse_args()
    
    if not any([args.yaml_files, args.yaml_dir, args.urls]):
        print("Error: Please specify --yaml-files, --yaml-dir, or --urls")
        sys.exit(1)
    
    # Initialize vector store
    vector_store = ChromaContainerVectorStore(
        collection_name=args.collection_name,
        chroma_host=args.chroma_host,
        chroma_port=args.chroma_port
    )
    
    # Clear collection if requested
    if args.clear_collection:
        try:
            vector_store.client.delete_collection(args.collection_name)
            logger.info(f"Cleared collection: {args.collection_name}")
            # Recreate collection
            vector_store = ChromaContainerVectorStore(
                collection_name=args.collection_name,
                chroma_host=args.chroma_host,
                chroma_port=args.chroma_port
            )
        except Exception as e:
            logger.warning(f"Could not clear collection: {e}")
    
    # Initialize processors
    yaml_processor = YAMLDocumentProcessor()
    document_loader = DocumentLoader()
    
    total_chunks = 0
    
    # Process YAML files
    yaml_files = []
    
    if args.yaml_files:
        yaml_files.extend(args.yaml_files)
    
    if args.yaml_dir:
        yaml_dir = Path(args.yaml_dir)
        if yaml_dir.exists():
            yaml_files.extend([
                str(f) for f in yaml_dir.glob("*.yml")
            ] + [
                str(f) for f in yaml_dir.glob("*.yaml")
            ])
        else:
            logger.warning(f"YAML directory not found: {args.yaml_dir}")
    
    for yaml_file in yaml_files:
        print(f"\n📄 Processing YAML file: {yaml_file}")
        
        try:
            chunks = yaml_processor.process_yaml_file(yaml_file)
            if chunks:
                await vector_store.add_documents(chunks)
                print(f"   ✅ Added {len(chunks)} chunks from {yaml_file}")
                total_chunks += len(chunks)
            else:
                print(f"   ⚠️  No chunks generated from {yaml_file}")
        
        except Exception as e:
            print(f"   ❌ Error processing {yaml_file}: {e}")
    
    # Process URLs (existing functionality)
    if args.urls:
        for url in args.urls:
            print(f"\n🌐 Processing URL: {url}")
            
            try:
                chunks = document_loader.load_from_url(url, max_depth=2)
                if chunks:
                    await vector_store.add_documents(chunks)
                    print(f"   ✅ Added {len(chunks)} chunks from {url}")
                    total_chunks += len(chunks)
                else:
                    print(f"   ⚠️  No content extracted from {url}")
            
            except Exception as e:
                print(f"   ❌ Error processing {url}: {e}")
    
    # Summary
    print(f"\n📊 Ingestion Summary:")
    print(f"   Total chunks loaded: {total_chunks}")
    
    # Get collection info
    info = await vector_store.get_collection_info()
    print(f"   Collection: {info['collection_name']}")
    print(f"   Total documents in DB: {info['document_count']}")
    
    # Test search
    if total_chunks > 0:
        print(f"\n🔍 Testing search functionality...")
        test_queries = ["authentication", "API endpoints", "schema", "examples"]
        
        for query in test_queries:
            results = await vector_store.search(query, limit=2)
            print(f"   '{query}': {len(results)} results")
            if results:
                first_result = results[0]
                metadata = first_result.get('metadata', {})
                source_info = metadata.get('source_type', 'unknown')
                if source_info == 'yaml':
                    print(f"      Top result from: {metadata.get('file_path', 'unknown')} ({metadata.get('chunk_type', 'unknown')})")
                else:
                    print(f"      Top result from: {metadata.get('url', 'unknown')}")


if __name__ == "__main__":
    asyncio.run(ingest_yaml_documentation())