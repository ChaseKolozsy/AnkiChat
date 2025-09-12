#!/usr/bin/env python3
"""CLI entry point for AnkiChat MCP server."""

import sys
import os
from pathlib import Path

def main():
    """Main entry point for the AnkiChat MCP server."""
    # Add the project root to the path
    project_root = Path(__file__).parents[1]
    sys.path.insert(0, str(project_root))
    
    # Import the MCP server module
    from src.servers import anki_mcp_server
    
    # Run the MCP server
    anki_mcp_server.mcp.run()

if __name__ == "__main__":
    main()