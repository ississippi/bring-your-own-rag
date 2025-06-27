#!/usr/bin/env python3
"""
API Documentation RAG MCP Server

A Model Context Protocol server that provides semantic search over proprietary API documentation
using vector embeddings. Supports multiple vector stores (currently Chroma) and can load
documentation from URLs.

Usage:
    python mcp_server.py --collection-name my-api-docs --chroma-path ./chroma_db
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urljoin, urlparse
import hashlib

import requests
from bs4 import BeautifulSoup
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """Represents a chunk of documentation with metadata."""
    content: str
    url: str
    title: str
    section: str
    chunk_id: str
    metadata: Dict[str, Any]


class VectorStore(ABC):
    """Abstract base class for vector store implementations."""
    
    @abstractmethod
    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        """Add document chunks to the vector store."""
        pass
    
    @abstractmethod
    async def search(self, query: str, limit: int = 5, filters: Optional[Dict] = None) -> List[Dict]:
        """Search for similar documents."""
        pass
    
    @abstractmethod
    async def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection."""
        pass


class ChromaVectorStore(VectorStore):
    """Chroma vector store implementation."""
    
    def __init__(self, collection_name: str, persist_directory: str = "./chroma_db"):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Initialize Chroma client
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(
                name=collection_name,
                embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            )
        except ValueError:
            self.collection = self.client.create_collection(
                name=collection_name,
                embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            )
    
    async def add_documents(self, chunks: List[DocumentChunk]) -> None:
        """Add document chunks to Chroma collection."""
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
        """Search for similar documents in Chroma."""
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
        """Get information about the Chroma collection."""
        count = self.collection.count()
        return {
            "collection_name": self.collection_name,
            "document_count": count,
            "vector_store_type": "chroma",
            "persist_directory": self.persist_directory
        }


class DocumentLoader:
    """Loads and processes API documentation from URLs."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; API-Docs-Loader/1.0)'
        })
    
    def load_from_url(self, url: str, max_depth: int = 2) -> List[DocumentChunk]:
        """Load documentation from a URL and extract chunks."""
        chunks = []
        visited_urls = set()
        
        def extract_chunks_from_page(page_url: str, depth: int = 0) -> None:
            if depth > max_depth or page_url in visited_urls:
                return
            
            visited_urls.add(page_url)
            logger.info(f"Processing: {page_url} (depth: {depth})")
            
            try:
                response = self.session.get(page_url, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract title
                title_elem = soup.find('title')
                title = title_elem.get_text().strip() if title_elem else "Unknown"
                
                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                # Extract main content areas
                main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup
                
                # Extract sections
                sections = main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                
                if not sections:
                    # If no sections found, treat entire content as one chunk
                    content = main_content.get_text().strip()
                    if content and len(content) > 50:  # Minimum content threshold
                        chunk = self._create_chunk(content, page_url, title, "main", {})
                        chunks.append(chunk)
                else:
                    # Process each section
                    for i, section in enumerate(sections):
                        section_title = section.get_text().strip()
                        section_content = self._extract_section_content(section)
                        
                        if section_content and len(section_content) > 50:
                            chunk = self._create_chunk(
                                section_content, 
                                page_url, 
                                title, 
                                section_title,
                                {"section_index": i}
                            )
                            chunks.append(chunk)
                
                # Find and follow links (for limited depth crawling)
                if depth < max_depth:
                    base_domain = urlparse(page_url).netloc
                    links = soup.find_all('a', href=True)
                    
                    for link in links:
                        href = link.get('href')
                        if href:
                            full_url = urljoin(page_url, href)
                            link_domain = urlparse(full_url).netloc
                            
                            # Only follow links within the same domain
                            if (link_domain == base_domain and 
                                full_url not in visited_urls and
                                not any(skip in full_url.lower() for skip in ['#', 'javascript:', 'mailto:', '.pdf', '.zip'])):
                                extract_chunks_from_page(full_url, depth + 1)
            
            except Exception as e:
                logger.warning(f"Error processing {page_url}: {str(e)}")
        
        extract_chunks_from_page(url)
        logger.info(f"Extracted {len(chunks)} chunks from {len(visited_urls)} pages")
        return chunks
    
    def _extract_section_content(self, section_elem) -> str:
        """Extract content following a section header."""
        content_parts = [section_elem.get_text().strip()]
        
        # Get all siblings until next header of same or higher level
        current_level = int(section_elem.name[1])  # h1 -> 1, h2 -> 2, etc.
        
        for sibling in section_elem.find_next_siblings():
            if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                sibling_level = int(sibling.name[1])
                if sibling_level <= current_level:
                    break
            
            if sibling.name in ['p', 'div', 'pre', 'code', 'ul', 'ol', 'table']:
                text = sibling.get_text().strip()
                if text:
                    content_parts.append(text)
        
        return '\n\n'.join(content_parts)
    
    def _create_chunk(self, content: str, url: str, title: str, section: str, metadata: Dict) -> DocumentChunk:
        """Create a DocumentChunk with a unique ID."""
        # Create unique ID based on content hash
        content_hash = hashlib.md5(f"{url}#{section}#{content[:100]}".encode()).hexdigest()
        
        return DocumentChunk(
            content=content,
            url=url,
            title=title,
            section=section,
            chunk_id=f"{content_hash}",
            metadata=metadata
        )


class APIDocumentationMCPServer:
    """MCP Server for API Documentation RAG."""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.document_loader = DocumentLoader()
        self.server = Server("api-docs-rag")
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup MCP server handlers."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List available tools."""
            return [
                types.Tool(
                    name="search_api_docs",
                    description="Search through API documentation using semantic similarity. Use this when you need to find relevant documentation, code examples, or API usage patterns.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query in natural language (e.g., 'authentication methods', 'REST API endpoints', 'error handling')"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 5)",
                                "default": 5
                            },
                            "filters": {
                                "type": "object",
                                "description": "Optional filters for search (e.g., {'section': 'authentication'})",
                                "additionalProperties": True
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="load_documentation",
                    description="Load API documentation from a URL into the vector store. Use this to ingest new documentation.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to load documentation from"
                            },
                            "max_depth": {
                                "type": "integer",
                                "description": "Maximum crawling depth for linked pages (default: 2)",
                                "default": 2
                            }
                        },
                        "required": ["url"]
                    }
                ),
                types.Tool(
                    name="get_collection_info",
                    description="Get information about the current documentation collection.",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls."""
            try:
                if name == "search_api_docs":
                    return await self._search_docs(arguments)
                elif name == "load_documentation":
                    return await self._load_docs(arguments)
                elif name == "get_collection_info":
                    return await self._get_info(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
            except Exception as e:
                logger.error(f"Error in tool {name}: {str(e)}")
                return [types.TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]
    
    async def _search_docs(self, arguments: dict) -> list[types.TextContent]:
        """Handle search_api_docs tool call."""
        query = arguments.get("query", "")
        limit = arguments.get("limit", 5)
        filters = arguments.get("filters")
        
        if not query:
            return [types.TextContent(
                type="text",
                text="Error: Query parameter is required"
            )]
        
        results = await self.vector_store.search(query, limit, filters)
        
        if not results:
            return [types.TextContent(
                type="text",
                text=f"No relevant documentation found for query: '{query}'"
            )]
        
        # Format results
        response_parts = [f"Found {len(results)} relevant documentation sections for: '{query}'\n"]
        
        for i, result in enumerate(results, 1):
            metadata = result.get("metadata", {})
            score = result.get("similarity_score", 0.0)
            
            response_parts.append(f"## Result {i} (Score: {score:.3f})")
            response_parts.append(f"**Title:** {metadata.get('title', 'Unknown')}")
            response_parts.append(f"**Section:** {metadata.get('section', 'main')}")
            response_parts.append(f"**URL:** {metadata.get('url', 'Unknown')}")
            response_parts.append(f"**Content:**\n{result['content']}\n")
        
        return [types.TextContent(
            type="text",
            text="\n".join(response_parts)
        )]
    
    async def _load_docs(self, arguments: dict) -> list[types.TextContent]:
        """Handle load_documentation tool call."""
        url = arguments.get("url", "")
        max_depth = arguments.get("max_depth", 2)
        
        if not url:
            return [types.TextContent(
                type="text",
                text="Error: URL parameter is required"
            )]
        
        try:
            # Load documents
            chunks = self.document_loader.load_from_url(url, max_depth)
            
            if not chunks:
                return [types.TextContent(
                    type="text",
                    text=f"No content could be extracted from: {url}"
                )]
            
            # Add to vector store
            await self.vector_store.add_documents(chunks)
            
            return [types.TextContent(
                type="text",
                text=f"Successfully loaded {len(chunks)} documentation chunks from {url}"
            )]
            
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error loading documentation from {url}: {str(e)}"
            )]
    
    async def _get_info(self, arguments: dict) -> list[types.TextContent]:
        """Handle get_collection_info tool call."""
        info = await self.vector_store.get_collection_info()
        
        info_text = "## Documentation Collection Information\n"
        for key, value in info.items():
            info_text += f"**{key.replace('_', ' ').title()}:** {value}\n"
        
        return [types.TextContent(
            type="text",
            text=info_text
        )]
    
    async def run(self, transport):
        """Run the MCP server."""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                NotificationOptions()
            )


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="API Documentation RAG MCP Server")
    parser.add_argument(
        "--collection-name",
        default="api-docs",
        help="Name of the vector store collection"
    )
    parser.add_argument(
        "--chroma-path",
        default="./chroma_db",
        help="Path to Chroma database directory"
    )
    parser.add_argument(
        "--load-url",
        help="Optional: URL to load documentation from on startup"
    )
    
    args = parser.parse_args()
    
    # Initialize vector store
    vector_store = ChromaVectorStore(
        collection_name=args.collection_name,
        persist_directory=args.chroma_path
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
    await mcp_server.run(mcp.server.stdio.stdio_server())


if __name__ == "__main__":
    asyncio.run(main())