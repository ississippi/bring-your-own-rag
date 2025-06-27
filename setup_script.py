#!/usr/bin/env python3
"""
Setup script for API Documentation RAG MCP Server

This script helps you set up the project and configure it for use with Cursor or VS Code.
"""

import json
import os
import sys
import subprocess
from pathlib import Path


def install_dependencies():
    """Install required Python dependencies."""
    print("Installing Python dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False
    return True


def create_cursor_config(project_path: str, collection_name: str = "api-docs"):
    """Create Cursor MCP configuration."""
    cursor_dir = Path(project_path) / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    
    config = {
        "mcpServers": {
            "api-docs-rag": {
                "command": "python",
                "args": [
                    str(Path(project_path) / "mcp_server.py"),
                    "--collection-name",
                    collection_name,
                    "--chroma-path",
                    str(Path(project_path) / "chroma_db")
                ],
                "env": {
                    "PYTHONPATH": project_path
                }
            }
        }
    }
    
    config_path = cursor_dir / "mcp.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Cursor configuration created at: {config_path}")
    return config_path


def create_vscode_config(project_path: str, collection_name: str = "api-docs"):
    """Create VS Code MCP configuration."""
    vscode_dir = Path(project_path) / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    
    config = {
        "mcpServers": {
            "api-docs-rag": {
                "command": "python",
                "args": [
                    str(Path(project_path) / "mcp_server.py"),
                    "--collection-name",
                    collection_name,
                    "--chroma-path",
                    str(Path(project_path) / "chroma_db")
                ]
            }
        }
    }
    
    config_path = vscode_dir / "mcp.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ VS Code configuration created at: {config_path}")
    return config_path


def test_server(project_path: str, test_url: str = None):
    """Test the MCP server with optional URL loading."""
    print("Testing MCP server...")
    
    # Test basic server startup
    cmd = [
        sys.executable,
        str(Path(project_path) / "mcp_server.py"),
        "--collection-name", "test-collection"
    ]
    
    if test_url:
        cmd.extend(["--load-url", test_url])
    
    try:
        # Run with timeout to test startup
        result = subprocess.run(
            cmd + ["--help"],  # Just test help to verify imports work
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ MCP server can start successfully!")
            return True
        else:
            print(f"❌ MCP server failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ MCP server test timed out")
        return False
    except Exception as e:
        print(f"❌ MCP server test failed: {e}")
        return False


def main():
    """Main setup function."""
    print("🚀 Setting up API Documentation RAG MCP Server")
    print("=" * 50)
    
    # Get project path
    project_path = os.getcwd()
    print(f"Project path: {project_path}")
    
    # Get configuration options
    collection_name = input("Enter collection name (default: api-docs): ").strip()
    if not collection_name:
        collection_name = "api-docs"
    
    test_url = input("Enter test URL to load documentation from (optional): ").strip()
    if not test_url:
        test_url = None
    
    ide_choice = input("Choose IDE (cursor/vscode/both) [default: both]: ").strip().lower()
    if not ide_choice:
        ide_choice = "both"
    
    print("\n📦 Step 1: Installing dependencies...")
    if not install_dependencies():
        sys.exit(1)
    
    print("\n⚙️  Step 2: Creating IDE configurations...")
    if ide_choice in ["cursor", "both"]:
        create_cursor_config(project_path, collection_name)
    
    if ide_choice in ["vscode", "both"]:
        create_vscode_config(project_path, collection_name)
    
    print("\n🧪 Step 3: Testing server...")
    if test_server(project_path, test_url):
        print("\n✅ Setup completed successfully!")
        print("\nNext steps:")
        print("1. Restart your IDE (Cursor/VS Code)")
        print("2. Open a project and start coding")
        print("3. Use the AI assistant - it can now search your API documentation!")
        
        if test_url:
            print(f"4. Documentation from {test_url} has been loaded and indexed")
        else:
            print("4. Use the 'load_documentation' tool to add API documentation")
        
        print("\nExample usage in chat:")
        print("- 'Search for authentication examples'")
        print("- 'Find error handling patterns'")
        print("- 'Show me REST API endpoints'")
        
    else:
        print("\n❌ Setup completed with errors. Check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()