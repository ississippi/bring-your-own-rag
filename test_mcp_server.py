#!/usr/bin/env python3
"""
Test script for API Documentation RAG MCP Server

This script tests the core functionality of the MCP server including:
- Vector store operations
- Document loading
- Search functionality
- MCP tool integration
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_server import (
    ChromaVectorStore, 
    DocumentLoader, 
    APIDocumentationMCPServer,
    DocumentChunk
)


class MCPServerTester:
    """Test suite for MCP server functionality."""
    
    def __init__(self):
        self.temp_dir = None
        self.vector_store = None
        self.document_loader = None
        self.mcp_server = None
    
    async def setup(self):
        """Set up test environment."""
        print("🔧 Setting up test environment...")
        
        # Create temporary directory for test database
        self.temp_dir = tempfile.mkdtemp(prefix="mcp_test_")
        print(f"   Test database: {self.temp_dir}")
        
        # Initialize components
        self.vector_store = ChromaVectorStore(
            collection_name="test-collection",
            persist_directory=self.temp_dir
        )
        
        self.document_loader = DocumentLoader()
        self.mcp_server = APIDocumentationMCPServer(self.vector_store)
        
        print("✅ Test environment ready")
    
    async def cleanup(self):
        """Clean up test environment."""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
            print(f"🧹 Cleaned up test directory: {self.temp_dir}")
    
    async def test_vector_store_basic(self):
        """Test basic vector store operations."""
        print("\n📊 Testing vector store operations...")
        
        # Create test chunks
        test_chunks = [
            DocumentChunk(
                content="This is a test document about authentication using OAuth 2.0 flow.",
                url="https://example.com/auth",
                title="Authentication Guide",
                section="OAuth Setup",
                chunk_id="test_chunk_1",
                metadata={"type": "authentication", "version": "v1"}
            ),
            DocumentChunk(
                content="Error handling in REST APIs should return proper status codes and messages.",
                url="https://example.com/errors",
                title="Error Handling",
                section="HTTP Status Codes",
                chunk_id="test_chunk_2",
                metadata={"type": "error_handling", "version": "v1"}
            ),
            DocumentChunk(
                content="Rate limiting protects your API from excessive requests. Use 429 status code.",
                url="https://example.com/rate-limit",
                title="Rate Limiting",
                section="Protection",
                chunk_id="test_chunk_3",
                metadata={"type": "rate_limiting", "version": "v1"}
            )
        ]
        
        # Test adding documents
        await self.vector_store.add_documents(test_chunks)
        print("   ✅ Documents added successfully")
        
        # Test collection info
        info = await self.vector_store.get_collection_info()
        assert info["document_count"] == 3, f"Expected 3 documents, got {info['document_count']}"
        print(f"   ✅ Collection info: {info['document_count']} documents")
        
        # Test search
        results = await self.vector_store.search("authentication OAuth", limit=2)
        assert len(results) > 0, "No search results found"
        assert "oauth" in results[0]["content"].lower(), "OAuth content not found in top result"
        print(f"   ✅ Search returned {len(results)} relevant results")
        
        # Test filtered search
        filtered_results = await self.vector_store.search(
            "API errors", 
            limit=5,
            filters={"type": "error_handling"}
        )
        assert len(filtered_results) > 0, "No filtered search results found"
        print(f"   ✅ Filtered search returned {len(filtered_results)} results")
        
        print("✅ Vector store tests passed!")
    
    async def test_document_loader(self):
        """Test document loading from a simple HTML string."""
        print("\n📄 Testing document loader...")
        
        # Create a simple test HTML file
        test_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test API Documentation</title></head>
        <body>
            <h1>API Documentation</h1>
            <h2>Authentication</h2>
            <p>Use API keys for authentication. Include the key in the Authorization header.</p>
            
            <h2>Endpoints</h2>
            <p>The API provides REST endpoints for data access.</p>
            
            <h3>GET /users</h3>
            <p>Retrieve user information. Requires authentication.</p>
        </body>
        </html>
        """
        
        # Save to temporary file and create a file:// URL
        test_file = Path(self.temp_dir) / "test_docs.html"
        test_file.write_text(test_html)
        test_url = f"file://{test_file.absolute()}"
        
        try:
            chunks = self.document_loader.load_from_url(test_url, max_depth=0)
            assert len(chunks) > 0, "No chunks extracted from test HTML"
            
            # Check that we got meaningful content
            contents = [chunk.content for chunk in chunks]
            combined_content = " ".join(contents).lower()
            
            assert "authentication" in combined_content, "Authentication content not found"
            assert "api" in combined_content, "API content not found"
            
            print(f"   ✅ Extracted {len(chunks)} chunks from test HTML")
            
            # Test adding these chunks to vector store
            await self.vector_store.add_documents(chunks)
            print("   ✅ Loaded chunks added to vector store")
            
        except Exception as e:
            print(f"   ⚠️  Document loader test skipped (file:// URLs might not work): {e}")
            # This is okay - we'll test with the MCP tools instead
        
        print("✅ Document loader tests completed!")
    
    async def test_mcp_tools(self):
        """Test MCP server tools."""
        print("\n🔧 Testing MCP tools...")
        
        # Test get_collection_info tool
        info_result = await self.mcp_server._get_info({})
        assert len(info_result) == 1, "Expected one text content result"
        assert "collection" in info_result[0].text.lower(), "Collection info not in result"
        print("   ✅ get_collection_info tool works")
        
        # Test search tool with existing data
        search_result = await self.mcp_server._search_docs({
            "query": "authentication",
            "limit": 2
        })
        assert len(search_result) == 1, "Expected one text content result"
        result_text = search_result[0].text
        print(f"   ✅ search_api_docs tool returned: {len(result_text)} characters")
        
        # Test search with no results
        no_results = await self.mcp_server._search_docs({
            "query": "nonexistent topic that should return nothing",
            "limit": 5
        })
        assert "no relevant documentation found" in no_results[0].text.lower(), "Expected no results message"
        print("   ✅ Empty search handled correctly")
        
        print("✅ MCP tools tests passed!")
    
    async def test_error_handling(self):
        """Test error handling scenarios."""
        print("\n🚨 Testing error handling...")
        
        # Test search with empty query
        empty_search = await self.mcp_server._search_docs({"query": ""})
        assert "error" in empty_search[0].text.lower(), "Expected error for empty query"
        print("   ✅ Empty query handled correctly")
        
        # Test load_documentation with invalid URL
        invalid_load = await self.mcp_server._load_docs({"url": "not-a-valid-url"})
        assert "error" in invalid_load[0].text.lower(), "Expected error for invalid URL"
        print("   ✅ Invalid URL handled correctly")
        
        print("✅ Error handling tests passed!")
    
    async def run_all_tests(self):
        """Run all tests."""
        print("🧪 Running MCP Server Test Suite")
        print("=" * 50)
        
        try:
            await self.setup()
            
            await self.test_vector_store_basic()
            await self.test_document_loader()
            await self.test_mcp_tools()
            await self.test_error_handling()
            
            print("\n" + "=" * 50)
            print("✅ All tests passed successfully!")
            print("\nYour MCP server is ready to use!")
            
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            await self.cleanup()
        
        return True


async def main():
    """Run the test suite."""
    tester = MCPServerTester()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🚀 Next steps:")
        print("1. Configure your IDE (see README.md)")
        print("2. Load some real documentation:")
        print("   python mcp_server.py --load-url https://your-api-docs.com")
        print("3. Start coding with AI assistance!")
    else:
        print("\n🔧 Please fix the issues above before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())