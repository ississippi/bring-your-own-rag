#!/usr/bin/env python3
"""
Example: Vendor Setup Script for API Documentation RAG

This script demonstrates how API vendors can package and distribute
the MCP server to their customers with pre-configured documentation.

Example for a fictional "PaymentAPI" vendor.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
import argparse

# Import the MCP server components
from mcp_server import ChromaVectorStore, DocumentLoader, APIDocumentationMCPServer


class VendorSetup:
    """Setup script for API vendors to distribute to customers."""
    
    def __init__(self, vendor_name: str, api_docs_urls: list, collection_name: str):
        self.vendor_name = vendor_name
        self.api_docs_urls = api_docs_urls
        self.collection_name = collection_name
    
    async def setup_customer_environment(self, customer_path: str):
        """Set up the MCP server environment for a customer."""
        print(f"🏢 Setting up {self.vendor_name} API Documentation Assistant")
        print("=" * 60)
        
        customer_dir = Path(customer_path)
        customer_dir.mkdir(exist_ok=True)
        
        # 1. Create vector store
        print("📊 Initializing documentation database...")
        vector_store = ChromaVectorStore(
            collection_name=self.collection_name,
            persist_directory=str(customer_dir / "api_docs_db")
        )
        
        # 2. Load documentation
        print("📄 Loading API documentation...")
        document_loader = DocumentLoader()
        
        total_chunks = 0
        for url in self.api_docs_urls:
            print(f"   Loading from: {url}")
            try:
                chunks = document_loader.load_from_url(url, max_depth=3)
                await vector_store.add_documents(chunks)
                total_chunks += len(chunks)
                print(f"   ✅ Loaded {len(chunks)} documentation sections")
            except Exception as e:
                print(f"   ⚠️  Warning: Could not load {url}: {e}")
        
        print(f"📚 Total documentation sections loaded: {total_chunks}")
        
        # 3. Create IDE configurations
        await self._create_ide_configs(customer_dir)
        
        # 4. Create launcher script
        await self._create_launcher_script(customer_dir)
        
        # 5. Create usage examples
        await self._create_usage_examples(customer_dir)
        
        print(f"\n✅ Setup complete! Files created in: {customer_dir}")
        return True
    
    async def _create_ide_configs(self, customer_dir: Path):
        """Create IDE configuration files."""
        print("⚙️  Creating IDE configurations...")
        
        server_script = customer_dir / f"{self.collection_name}_mcp_server.py"
        
        # Create custom server script
        server_content = f'''#!/usr/bin/env python3
"""
{self.vendor_name} API Documentation MCP Server
Auto-generated customer setup
"""

import sys
import asyncio
from pathlib import Path

# Add the parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp_server import ChromaVectorStore, APIDocumentationMCPServer

async def main():
    """Main entry point for {self.vendor_name} API docs server."""
    vector_store = ChromaVectorStore(
        collection_name="{self.collection_name}",
        persist_directory=str(Path(__file__).parent / "api_docs_db")
    )
    
    mcp_server = APIDocumentationMCPServer(vector_store)
    
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
'''
        
        server_script.write_text(server_content)
        server_script.chmod(0o755)
        
        # Cursor configuration
        cursor_dir = customer_dir / ".cursor"
        cursor_dir.mkdir(exist_ok=True)
        
        cursor_config = {
            "mcpServers": {
                f"{self.collection_name}": {
                    "command": "python",
                    "args": [str(server_script.absolute())],
                    "env": {
                        "PYTHONPATH": str(customer_dir.absolute())
                    }
                }
            }
        }
        
        (cursor_dir / "mcp.json").write_text(json.dumps(cursor_config, indent=2))
        
        # VS Code configuration
        vscode_dir = customer_dir / ".vscode"
        vscode_dir.mkdir(exist_ok=True)
        (vscode_dir / "mcp.json").write_text(json.dumps(cursor_config, indent=2))
        
        print("   ✅ Created Cursor and VS Code configurations")
    
    async def _create_launcher_script(self, customer_dir: Path):
        """Create a simple launcher script."""
        launcher_content = f'''#!/usr/bin/env python3
"""
{self.vendor_name} API Documentation Assistant Launcher
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Launch the MCP server for testing."""
    server_script = Path(__file__).parent / "{self.collection_name}_mcp_server.py"
    
    print("🚀 Starting {self.vendor_name} API Documentation Assistant")
    print("💡 This will start the MCP server for testing.")
    print("📖 For IDE integration, see the setup instructions in README.txt")
    print()
    
    try:
        subprocess.run([sys.executable, str(server_script)], check=True)
    except KeyboardInterrupt:
        print("\\n👋 Server stopped.")
    except Exception as e:
        print(f"❌ Error starting server: {{e}}")

if __name__ == "__main__":
    main()
'''
        
        launcher = customer_dir / f"start_{self.collection_name}_assistant.py"
        launcher.write_text(launcher_content)
        launcher.chmod(0o755)
        
        print("   ✅ Created launcher script")
    
    async def _create_usage_examples(self, customer_dir: Path):
        """Create usage examples and documentation."""
        readme_content = f'''# {self.vendor_name} API Documentation Assistant

Welcome to your AI-powered coding assistant for {self.vendor_name} APIs!

## 🚀 Quick Start

1. **Install Dependencies** (if not already done):
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Your IDE**:
   
   ### For Cursor:
   - Copy the `.cursor/mcp.json` file to your project
   - Restart Cursor
   
   ### For VS Code:
   - Copy the `.vscode/mcp.json` file to your project  
   - Restart VS Code

3. **Start Coding**:
   - Open a new file in your IDE
   - Start the AI chat/assistant
   - Ask questions about {self.vendor_name} APIs!

## 💬 Example Conversations

### Authentication Setup
**You**: "How do I authenticate with {self.vendor_name} API?"

**AI Assistant**: *Searches documentation and provides specific auth examples*

### Error Handling
**You**: "Show me error handling patterns for failed payments"

**AI Assistant**: *Finds relevant error codes and handling examples*

### Integration Examples
**You**: "I need to integrate payment webhooks"

**AI Assistant**: *Provides webhook setup code and examples*

## 🔧 Troubleshooting

### Server Not Starting
```bash
# Test the server directly
python {self.collection_name}_mcp_server.py --help

# Check if documentation is loaded
python start_{self.collection_name}_assistant.py
```

### No Search Results
- The documentation database contains {len(self.api_docs_urls)} documentation sources
- Try broader search terms
- Use the 'get_collection_info' tool to verify data is loaded

## 📞 Support

For technical support with this documentation assistant:
- Check the main README.md for detailed troubleshooting
- Contact your {self.vendor_name} developer support team

For {self.vendor_name} API questions:
- Visit: {self.api_docs_urls[0] if self.api_docs_urls else 'your developer portal'}
- Contact: {self.vendor_name} API support

---

**Happy coding with AI-powered {self.vendor_name} API assistance! 🎉**
'''
        
        (customer_dir / "README.txt").write_text(readme_content)
        
        # Create example queries file
        examples_content = f'''# Example Queries for {self.vendor_name} API Assistant

## Authentication & Setup
- "How do I get API credentials for {self.vendor_name}?"
- "Show me authentication examples"
- "What are the required headers for API calls?"

## Common Operations
- "How do I create a payment?"
- "Show me webhook handling code"
- "What are the available API endpoints?"

## Error Handling
- "What error codes should I handle?"
- "Show me retry logic examples"
- "How do I handle rate limiting?"

## Advanced Features
- "How do I implement recurring payments?"
- "Show me batch operation examples"
- "What are the webhook signature verification steps?"

## Debugging
- "How do I test API calls?"
- "What logging should I implement?"
- "Show me debugging best practices"

---

💡 **Tip**: The AI assistant can search through all {self.vendor_name} documentation automatically!
Just ask in natural language and it will find the most relevant information.
'''
        
        (customer_dir / "example_queries.txt").write_text(examples_content)
        print("   ✅ Created usage documentation and examples")


# Example configurations for different vendors

PAYMENT_API_VENDOR = VendorSetup(
    vendor_name="PaymentFlow",
    api_docs_urls=[
        "https://docs.paymentflow.example/api/",
        "https://docs.paymentflow.example/webhooks/",
        "https://docs.paymentflow.example/auth/"
    ],
    collection_name="paymentflow-api"
)

SOCIAL_API_VENDOR = VendorSetup(
    vendor_name="SocialConnect",
    api_docs_urls=[
        "https://developers.socialconnect.example/docs/",
        "https://developers.socialconnect.example/auth/",
    ],
    collection_name="socialconnect-api"
)


async def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(description="Vendor API Documentation Setup")
    parser.add_argument("--vendor", choices=["payment", "social"], default="payment",
                       help="Which vendor setup to use")
    parser.add_argument("--output-dir", default="./customer_setup",
                       help="Directory to create customer setup in")
    parser.add_argument("--customer-name", default="customer",
                       help="Customer name for personalization")
    
    args = parser.parse_args()
    
    # Select vendor configuration
    if args.vendor == "payment":
        vendor = PAYMENT_API_VENDOR
    elif args.vendor == "social":
        vendor = SOCIAL_API_VENDOR
    else:
        print("Unknown vendor type")
        sys.exit(1)
    
    # Create customer-specific directory
    customer_dir = Path(args.output_dir) / f"{args.customer_name}_{vendor.collection_name}"
    
    print(f"Creating setup for {args.customer_name} using {vendor.vendor_name} configuration...")
    
    # Run setup
    success = await vendor.setup_customer_environment(str(customer_dir))
    
    if success:
        print(f"\n📦 Customer setup package created!")
        print(f"📁 Location: {customer_dir}")
        print(f"\n📧 Send this folder to your customer with instructions:")
        print(f"   1. Extract the folder to their development environment")
        print(f"   2. Follow the README.txt instructions")
        print(f"   3. Start coding with AI assistance!")
    else:
        print("\n❌ Setup failed. Check the logs above.")


if __name__ == "__main__":
    # Example usage:
    # python vendor_setup_example.py --vendor payment --customer-name acme-corp
    # python vendor_setup_example.py --vendor social --customer-name startup-inc --output-dir ./customer_packages
    
    asyncio.run(main())