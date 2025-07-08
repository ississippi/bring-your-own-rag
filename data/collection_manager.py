import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from chromadb.config import Settings
import uuid
import json
from typing import Dict, List, Optional, Any

def get_collection_stats(collection_name: str, chroma_host: str = "localhost", chroma_port: int = 8000) -> Dict[str, Any]:
    """Get comprehensive statistics about a collection."""
    client = chromadb.HttpClient(
        host=chroma_host,
        port=chroma_port,
        settings=Settings(anonymized_telemetry=False)
    )
    
    try:
        collection = client.get_collection(name=collection_name)
        
        # Get basic stats
        count = collection.count()
        
        # Get a sample to analyze metadata
        if count > 0:
            sample_results = collection.query(
                query_texts=[""],
                n_results=min(100, count),
                include=["metadatas"]
            )
            
            # Analyze metadata
            metadata_keys = set()
            metadata_values = {}
            
            for metadata in sample_results['metadatas'][0]:
                if metadata:
                    for key, value in metadata.items():
                        metadata_keys.add(key)
                        if key not in metadata_values:
                            metadata_values[key] = set()
                        if isinstance(value, (str, int, float, bool)):
                            metadata_values[key].add(str(value))
            
            # Get unique values (limit to first 10 for display)
            metadata_summary = {}
            for key, values in metadata_values.items():
                metadata_summary[key] = list(values)[:10]
                if len(values) > 10:
                    metadata_summary[key].append(f"... and {len(values) - 10} more")
        
        else:
            metadata_keys = set()
            metadata_summary = {}
        
        return {
            "collection_name": collection_name,
            "document_count": count,
            "metadata_keys": list(metadata_keys),
            "metadata_summary": metadata_summary,
            "status": "active"
        }
        
    except Exception as e:
        return {
            "collection_name": collection_name,
            "error": str(e),
            "status": "error"
        }

def add_sample_documents(collection_name: str, chroma_host: str = "localhost", chroma_port: int = 8000, 
                        sample_type: str = "default") -> None:
    """Add sample documents to the collection for testing."""
    client = chromadb.HttpClient(
        host=chroma_host,
        port=chroma_port,
        settings=Settings(anonymized_telemetry=False)
    )
    
    try:
        collection = client.get_collection(name=collection_name)
        
        # Different sample document sets
        sample_sets = {
            "default": [
                {
                    "content": "The Model Context Protocol (MCP) is a standard for AI applications to communicate with external data sources and tools.",
                    "metadata": {"title": "MCP Overview", "category": "protocol", "source": "sample", "type": "concept"}
                },
                {
                    "content": "ChromaDB is a vector database that allows you to store and query embeddings for similarity search.",
                    "metadata": {"title": "ChromaDB Introduction", "category": "database", "source": "sample", "type": "tool"}
                },
                {
                    "content": "Vector embeddings are numerical representations of text that capture semantic meaning for machine learning applications.",
                    "metadata": {"title": "Vector Embeddings", "category": "ml", "source": "sample", "type": "concept"}
                },
                {
                    "content": "RAG (Retrieval-Augmented Generation) combines document retrieval with language models to provide more accurate responses.",
                    "metadata": {"title": "RAG Systems", "category": "ai", "source": "sample", "type": "concept"}
                },
                {
                    "content": "API documentation helps developers understand how to use software libraries and services effectively.",
                    "metadata": {"title": "API Documentation", "category": "development", "source": "sample", "type": "concept"}
                }
            ],
            "api": [
                {
                    "content": "Authentication endpoints require a valid API key in the Authorization header.",
                    "metadata": {"title": "Authentication", "category": "auth", "source": "sample", "type": "endpoint"}
                },
                {
                    "content": "GET /users returns a list of all users with optional pagination parameters.",
                    "metadata": {"title": "Get Users", "category": "users", "source": "sample", "type": "endpoint"}
                },
                {
                    "content": "POST /users creates a new user account with email and password validation.",
                    "metadata": {"title": "Create User", "category": "users", "source": "sample", "type": "endpoint"}
                },
                {
                    "content": "Error responses include a status code, error message, and optional details field.",
                    "metadata": {"title": "Error Handling", "category": "errors", "source": "sample", "type": "concept"}
                }
            ],
            "minimal": [
                {
                    "content": "This is a minimal sample document for testing purposes.",
                    "metadata": {"title": "Test Document", "source": "sample"}
                }
            ]
        }
        
        sample_docs = sample_sets.get(sample_type, sample_sets["default"])
        
        # Prepare data for ChromaDB
        documents = [doc["content"] for doc in sample_docs]
        metadatas = [doc["metadata"] for doc in sample_docs]
        ids = [f"sample_{sample_type}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(sample_docs))]
        
        # Add to collection
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        print(f"✅ Added {len(sample_docs)} {sample_type} sample documents to collection '{collection_name}'")
        
    except Exception as e:
        print(f"❌ Error adding sample documents: {e}")

def print_collection_sample(collection_name: str, chroma_host: str = "localhost", chroma_port: int = 8000, 
                          n: int = 5, show_full_content: bool = False) -> None:
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
        print(f"📊 Collection '{collection_name}' has {count} documents")
        
        if count == 0:
            print("📭 Collection is empty!")
            return
        
        # Query a sample of documents
        results = collection.query(
            query_texts=[""],  # Empty string to get documents
            n_results=min(n, count),
            include=["documents", "metadatas", "distances", "ids"]
        )
        
        print(f"\n📄 Sample of {len(results['documents'][0])} documents:")
        print("=" * 80)
        
        for i in range(len(results["documents"][0])):
            content = results['documents'][0][i]
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i]
            doc_id = results['ids'][0][i]
            
            print(f"📝 Document {i+1} (ID: {doc_id})")
            
            # Show content (truncated or full)
            if show_full_content:
                print(f"Content: {content}")
            else:
                preview = content[:200] + "..." if len(content) > 200 else content
                print(f"Content: {preview}")
            
            # Show metadata in a nice format
            if metadata:
                print("Metadata:")
                for key, value in metadata.items():
                    print(f"  {key}: {value}")
            
            print(f"Distance: {distance:.4f}")
            print("-" * 80)
            
    except Exception as e:
        print(f"❌ Error: {e}")

def search_collection(collection_name: str, query: str, chroma_host: str = "localhost", 
                    chroma_port: int = 8000, n: int = 3, show_metadata: bool = True) -> None:
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
            include=["documents", "metadatas", "distances", "ids"]
        )
        
        print(f"🔍 Search results for: '{query}'")
        print("=" * 80)
        
        if not results["documents"][0]:
            print("❌ No results found")
            return
        
        for i in range(len(results["documents"][0])):
            content = results['documents'][0][i]
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i]
            doc_id = results['ids'][0][i]
            similarity = 1 - distance
            
            print(f"🎯 Result {i+1} (similarity: {similarity:.3f}, ID: {doc_id})")
            print(f"Content: {content}")
            
            if show_metadata and metadata:
                print("Metadata:")
                for key, value in metadata.items():
                    print(f"  {key}: {value}")
            
            print("-" * 80)
            
    except Exception as e:
        print(f"❌ Error: {e}")

def list_collections(chroma_host: str = "localhost", chroma_port: int = 8000) -> None:
    """List all available collections."""
    client = chromadb.HttpClient(
        host=chroma_host,
        port=chroma_port,
        settings=Settings(anonymized_telemetry=False)
    )
    
    try:
        collections = client.list_collections()
        
        if not collections:
            print("📭 No collections found")
            return
        
        print(f"📚 Found {len(collections)} collection(s):")
        print("=" * 50)
        
        for collection in collections:
            try:
                stats = get_collection_stats(collection.name, chroma_host, chroma_port)
                if stats["status"] == "active":
                    print(f"📁 {collection.name} ({stats['document_count']} documents)")
                    if stats["metadata_keys"]:
                        print(f"   Metadata keys: {', '.join(stats['metadata_keys'])}")
                else:
                    print(f"📁 {collection.name} (error: {stats.get('error', 'unknown')})")
            except Exception as e:
                print(f"📁 {collection.name} (error accessing: {e})")
            print()
            
    except Exception as e:
        print(f"❌ Error listing collections: {e}")

def export_collection(collection_name: str, output_file: str, chroma_host: str = "localhost", 
                    chroma_port: int = 8000, format: str = "json") -> None:
    """Export collection data to a file."""
    client = chromadb.HttpClient(
        host=chroma_host,
        port=chroma_port,
        settings=Settings(anonymized_telemetry=False)
    )
    
    try:
        collection = client.get_collection(name=collection_name)
        count = collection.count()
        
        if count == 0:
            print(f"📭 Collection '{collection_name}' is empty, nothing to export")
            return
        
        # Get all documents
        results = collection.query(
            query_texts=[""],
            n_results=count,
            include=["documents", "metadatas", "ids"]
        )
        
        # Prepare export data
        export_data = {
            "collection_name": collection_name,
            "document_count": count,
            "export_timestamp": str(Path().cwd()),
            "documents": []
        }
        
        for i in range(len(results["documents"][0])):
            doc_data = {
                "id": results['ids'][0][i],
                "content": results['documents'][0][i],
                "metadata": results['metadatas'][0][i] or {}
            }
            export_data["documents"].append(doc_data)
        
        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            if format.lower() == "json":
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            else:
                # Simple text format
                f.write(f"Collection: {collection_name}\n")
                f.write(f"Document Count: {count}\n")
                f.write("=" * 50 + "\n\n")
                
                for doc in export_data["documents"]:
                    f.write(f"ID: {doc['id']}\n")
                    f.write(f"Content: {doc['content']}\n")
                    if doc['metadata']:
                        f.write(f"Metadata: {doc['metadata']}\n")
                    f.write("-" * 30 + "\n\n")
        
        print(f"✅ Exported {count} documents from '{collection_name}' to '{output_file}'")
        
    except Exception as e:
        print(f"❌ Error exporting collection: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ChromaDB Collection Manager - Enhanced Tool")
    parser.add_argument("--action", choices=["view", "add-sample", "search", "stats", "list", "export"], 
                       default="view", help="Action to perform")
    parser.add_argument("--collection", default="test-collection", help="Collection name")
    parser.add_argument("--query", help="Search query (for search action)")
    parser.add_argument("--host", default="localhost", help="ChromaDB host")
    parser.add_argument("--port", type=int, default=8000, help="ChromaDB port")
    parser.add_argument("--n", type=int, default=5, help="Number of results to show")
    parser.add_argument("--sample-type", choices=["default", "api", "minimal"], default="default",
                       help="Type of sample data to add")
    parser.add_argument("--full-content", action="store_true", help="Show full document content")
    parser.add_argument("--output", help="Output file for export")
    parser.add_argument("--format", choices=["json", "text"], default="json", help="Export format")
    
    args = parser.parse_args()
    
    if args.action == "view":
        print_collection_sample(args.collection, args.host, args.port, args.n, args.full_content)
    elif args.action == "add-sample":
        add_sample_documents(args.collection, args.host, args.port, args.sample_type)
    elif args.action == "search":
        if not args.query:
            print("❌ Please provide a search query with --query")
        else:
            search_collection(args.collection, args.query, args.host, args.port, args.n)
    elif args.action == "stats":
        stats = get_collection_stats(args.collection, args.host, args.port)
        if stats["status"] == "active":
            print(f"📊 Collection Statistics for '{stats['collection_name']}':")
            print(f"   Documents: {stats['document_count']}")
            print(f"   Metadata Keys: {', '.join(stats['metadata_keys'])}")
            if stats['metadata_summary']:
                print("   Metadata Summary:")
                for key, values in stats['metadata_summary'].items():
                    print(f"     {key}: {', '.join(values)}")
        else:
            print(f"❌ Error: {stats.get('error', 'Unknown error')}")
    elif args.action == "list":
        list_collections(args.host, args.port)
    elif args.action == "export":
        if not args.output:
            args.output = f"{args.collection}_export.{args.format}"
        export_collection(args.collection, args.output, args.host, args.port, args.format) 