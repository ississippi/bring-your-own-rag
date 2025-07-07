import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from chromadb.config import Settings
import uuid

def add_sample_documents(collection_name, chroma_host="localhost", chroma_port=8000):
    """Add some sample documents to the collection for testing."""
    client = chromadb.HttpClient(
        host=chroma_host,
        port=chroma_port,
        settings=Settings(anonymized_telemetry=False)
    )
    
    try:
        collection = client.get_collection(name=collection_name)
        
        # Sample documents
        sample_docs = [
            {
                "content": "The Model Context Protocol (MCP) is a standard for AI applications to communicate with external data sources and tools.",
                "metadata": {"title": "MCP Overview", "category": "protocol", "source": "sample"}
            },
            {
                "content": "ChromaDB is a vector database that allows you to store and query embeddings for similarity search.",
                "metadata": {"title": "ChromaDB Introduction", "category": "database", "source": "sample"}
            },
            {
                "content": "Vector embeddings are numerical representations of text that capture semantic meaning for machine learning applications.",
                "metadata": {"title": "Vector Embeddings", "category": "ml", "source": "sample"}
            },
            {
                "content": "RAG (Retrieval-Augmented Generation) combines document retrieval with language models to provide more accurate responses.",
                "metadata": {"title": "RAG Systems", "category": "ai", "source": "sample"}
            },
            {
                "content": "API documentation helps developers understand how to use software libraries and services effectively.",
                "metadata": {"title": "API Documentation", "category": "development", "source": "sample"}
            }
        ]
        
        # Prepare data for ChromaDB
        documents = [doc["content"] for doc in sample_docs]
        metadatas = [doc["metadata"] for doc in sample_docs]
        ids = [str(uuid.uuid4()) for _ in sample_docs]
        
        # Add to collection
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        print(f"Added {len(sample_docs)} sample documents to collection '{collection_name}'")
        
    except Exception as e:
        print(f"Error adding sample documents: {e}")

def print_collection_sample(collection_name, chroma_host="localhost", chroma_port=8000, n=5):
    """Print a sample of documents from the collection."""
    client = chromadb.HttpClient(
        host=chroma_host,
        port=chroma_port,
        settings=Settings(anonymized_telemetry=False)
    )
    
    try:
        collection = client.get_collection(name=collection_name)
        
        # Get collection count
        count = collection.count()
        print(f"Collection '{collection_name}' has {count} documents")
        
        if count == 0:
            print("Collection is empty!")
            return
        
        # Query a sample of documents
        results = collection.query(
            query_texts=[""],  # Empty string to get documents
            n_results=min(n, count),
            include=["documents", "metadatas", "distances"]
        )
        
        print(f"\nSample of {len(results['documents'][0])} documents:")
        print("=" * 60)
        
        for i in range(len(results["documents"][0])):
            print(f"Document {i+1}:")
            print(f"Content: {results['documents'][0][i]}")
            print(f"Metadata: {results['metadatas'][0][i]}")
            print(f"Distance: {results['distances'][0][i]}")
            print("-" * 40)
            
    except Exception as e:
        print(f"Error: {e}")

def search_collection(collection_name, query, chroma_host="localhost", chroma_port=8000, n=3):
    """Search the collection for documents similar to the query."""
    client = chromadb.HttpClient(
        host=chroma_host,
        port=chroma_port,
        settings=Settings(anonymized_telemetry=False)
    )
    
    try:
        collection = client.get_collection(name=collection_name)
        
        results = collection.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"]
        )
        
        print(f"Search results for: '{query}'")
        print("=" * 60)
        
        for i in range(len(results["documents"][0])):
            print(f"Result {i+1} (similarity: {1 - results['distances'][0][i]:.3f}):")
            print(f"Content: {results['documents'][0][i]}")
            print(f"Metadata: {results['metadatas'][0][i]}")
            print("-" * 40)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ChromaDB Collection Manager")
    parser.add_argument("--action", choices=["view", "add-sample", "search"], default="view", 
                       help="Action to perform")
    parser.add_argument("--collection", default="test-collection", help="Collection name")
    parser.add_argument("--query", help="Search query (for search action)")
    parser.add_argument("--host", default="localhost", help="ChromaDB host")
    parser.add_argument("--port", type=int, default=8000, help="ChromaDB port")
    
    args = parser.parse_args()
    
    if args.action == "view":
        print_collection_sample(args.collection, args.host, args.port)
    elif args.action == "add-sample":
        add_sample_documents(args.collection, args.host, args.port)
    elif args.action == "search":
        if not args.query:
            print("Please provide a search query with --query")
        else:
            search_collection(args.collection, args.query, args.host, args.port) 