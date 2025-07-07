import asyncio
import argparse
import logging
from pathlib import Path
import chromadb
from chromadb.config import Settings

# Import our existing classes
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
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
                allow_reset=True,
                is_persistent=False
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
            self.print_collection_sample(self.collection)
        except Exception as e:
            # Collection doesn't exist, create it
            logger.info(f"Collection {collection_name} not found, creating new collection...")
            self.collection = self.client.create_collection(
                name=collection_name,
                embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            )
            logger.info(f"Created new collection: {collection_name}")
            self.print_collection_sample(self.collection)
    
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
    
    async def print_collection_sample(collection, n=5):
    # Query the first n documents (you can adjust the query as needed)
        results = collection.query(
            query_texts=[""],  # Empty string to get "closest" to nothing, i.e., just return docs
            n_results=n,
            include=["documents", "metadatas", "ids"]
        )
        for i in range(len(results["documents"][0])):
            print(f"ID: {results['ids'][0][i]}")
            print(f"Content: {results['documents'][0][i]}")
            print(f"Metadata: {results['metadatas'][0][i]}")
            print("-" * 40)


async def main():
    """Main entry point for containerized ChromaDB version."""
    parser = argparse.ArgumentParser(description="API Documentation RAG MCP Server (Container Version)")
    parser.add_argument("--collection-name", default="api-docs", help="Name of the vector store collection")
    parser.add_argument("--chroma-host", default="localhost", help="ChromaDB container host")
    parser.add_argument("--chroma-port", type=int, default=8000, help="ChromaDB container port")
    parser.add_argument("--load-url", help="Optional: URL to load documentation from on startup")
    
    args = parser.parse_args()
    print(f"Starting MCP server with collection: {args.collection_name} at {args.chroma_host}:{args.chroma_port}")
    print(f"Load URL: {args.load_url}")
    print("Press Ctrl+C to stop the server.")
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
