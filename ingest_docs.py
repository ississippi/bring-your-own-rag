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
