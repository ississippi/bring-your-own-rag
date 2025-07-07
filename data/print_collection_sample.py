import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from chromadb.config import Settings

def print_collection_sample(collection_name, chroma_host="localhost", chroma_port=8000, n=5):
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
            print(f"Content: {results['documents'][0][i][:200]}...")  # First 200 chars
            print(f"Metadata: {results['metadatas'][0][i]}")
            print(f"Distance: {results['distances'][0][i]}")
            print("-" * 40)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print_collection_sample("test-collection")