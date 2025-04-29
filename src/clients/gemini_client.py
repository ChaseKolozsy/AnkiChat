import asyncio
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types

# Get API key from environment
api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("Error: Neither GOOGLE_API_KEY nor GEMINI_API_KEY environment variable is set.")
    exit(1)


class GeminiMCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        # Specify the Gemini model to use
        self.model_name = "gemini-2.5-flash-preview-04-17"
        self.client = genai.Client(api_key=api_key)
        self.chat_session = None
        self.conversation_history = []

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server"""
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None # Or copy environment: os.environ.copy()
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def _get_mcp_tools_for_gemini(self) -> List[types.Tool]:
        """Fetch tools from MCP and format them for Gemini."""
        response = await self.session.list_tools()
        function_declarations = []
        
        for tool in response.tools:
            # Basic conversion, might need refinement based on actual schema complexity
            parameters_schema = tool.inputSchema or {"type": "object", "properties": {}}
            
            # Clean up schema to match Gemini's expectations
            cleaned_schema = {
                "type": "object",
                "properties": {},
                "required": []
            }
            
            # Copy and clean properties
            if 'properties' in parameters_schema:
                for prop_name, prop_schema in parameters_schema['properties'].items():
                    # Create a clean copy of the property schema
                    cleaned_prop = {}
                    
                    # Copy allowed fields
                    for field in ['type', 'description', 'items', 'enum']:
                        if field in prop_schema:
                            cleaned_prop[field] = prop_schema[field]
                    
                    # Handle nested objects
                    if prop_schema.get('type') == 'object' and 'properties' in prop_schema:
                        cleaned_prop['properties'] = {}
                        for sub_prop_name, sub_prop_schema in prop_schema['properties'].items():
                            cleaned_prop['properties'][sub_prop_name] = {
                                k: v for k, v in sub_prop_schema.items()
                                if k in ['type', 'description', 'items', 'enum']
                            }
                    
                    cleaned_schema['properties'][prop_name] = cleaned_prop

            # Handle required fields
            if 'required' in parameters_schema:
                if isinstance(parameters_schema['required'], list):
                    cleaned_schema['required'] = parameters_schema['required']
                elif isinstance(parameters_schema['required'], str):
                    cleaned_schema['required'] = [item.strip() for item in parameters_schema['required'].split(',')]
                else:
                    cleaned_schema['required'] = []

            # Ensure description is a string
            description = tool.description if isinstance(tool.description, str) else str(tool.description or "")

            # Create function declaration in the format expected by Gemini
            function_declaration = {
                "name": tool.name,
                "description": description,
                "parameters": cleaned_schema
            }
            
            function_declarations.append(function_declaration)
            
        return [types.Tool(function_declarations=function_declarations)]

    async def process_query(self, query: str) -> str:
        """Process a query using Gemini and available MCP tools"""
        if not self.session:
            raise ConnectionError("Not connected to MCP server.")

        # Get MCP tools for Gemini
        mcp_tools_for_gemini = await self._get_mcp_tools_for_gemini()
        
        # Add user message to conversation history
        message_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=query)]
        )
        
        # Create configuration for the request
        config = types.GenerateContentConfig(
            temperature=0.2,
            candidate_count=1,
            stop_sequences=None,
            max_output_tokens=2048,
            top_p=0.8,
            top_k=40,
            tools=mcp_tools_for_gemini,
            safety_settings=[
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        )
        
        final_response_text = []

        while True:
            try:
                # Send message to Gemini with tools via config
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=message_content,
                    config=config
                )
                
                # Extract response
                if hasattr(response, 'candidates') and response.candidates:
                    response_content = response.candidates[0].content
                else:
                    # Handle case where response format might be different
                    response_content = response
                
                # Check for function calls
                function_call = None
                if hasattr(response_content, 'parts') and response_content.parts:
                    for part in response_content.parts:
                        if hasattr(part, 'function_call'):
                            function_call = part.function_call
                            break
                
                # Add model response to conversation history
                if not function_call:
                    # Regular text response
                    final_response_text.append(response.text)
                    break
                else:
                    # Function call response
                    tool_name = function_call.name
                    tool_args = function_call.args
                    
                    final_response_text.append(f"[Calling MCP tool: {tool_name} with args: {tool_args}]")
                    
                    # Execute the MCP tool call
                    try:
                        tool_result = await self.session.call_tool(tool_name, dict(tool_args))
                        # Combine text parts of the result
                        result_content = " ".join([tc.text for tc in tool_result.content])
                        
                        # Add tool response to conversation history
                        tool_response = types.Content(
                            role="function",
                            parts=[types.Part.from_function_response(
                                name=tool_name,
                                response={"result": result_content}
                            )]
                        )
                        message_content = types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=result_content)]
                        )
                        
                    except Exception as e:
                        print(f"Error calling MCP tool {tool_name}: {e}")
                        error_msg = f"Failed to execute tool: {str(e)}"
                        final_response_text.append(f"[Error calling tool {tool_name}: {str(e)}]")
                        message_content = types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=error_msg)]
                        )
                    
                    # Continue the loop to let Gemini process the tool result
                    continue
                    
            except Exception as e:
                print(f"Error in Gemini request: {e}")
                final_response_text.append(f"[Error: {str(e)}]")
                break

        return "\n".join(final_response_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nGemini MCP Client Started!")
        print("Using model:", self.model_name)
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                # Prompt on a new line
                print("\nQuery: ", end="") 
                query = input().strip()

                if query.lower() == 'quit':
                    # Reset history for next potential session if desired
                    self.conversation_history = []
                    break

                response_text = await self.process_query(query)
                print("\n" + response_text) # Print response preceded by a newline

            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"\nError: {str(e)}") # Print error preceded by a newline
                # Optionally reset history on error or attempt recovery
                # self.conversation_history = [] # Reset if errors should clear context

    async def cleanup(self):
        """Clean up resources"""
        print("Cleaning up MCP client resources...")
        await self.exit_stack.aclose()
        print("Cleanup complete.")


async def main():
    """Main function to run the Gemini MCP client"""
    client = GeminiMCPClient()
    from pathlib import Path
    server_script = Path(__file__).parent.parent/ "servers" / "anki_mcp_server.py"
    try:
        print(f"Attempting to connect to MCP server: {str(server_script)}")
        await client.connect_to_server(str(server_script))
        await client.chat_loop()
    except FileNotFoundError:
        print(f"\nError: Server script not found at {str(server_script)}") # Precede with newline
    except ConnectionRefusedError:
        print("\nError: Connection to MCP server refused. Is the server running?") # Precede with newline
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}") # Precede with newline
        import traceback
        traceback.print_exc()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    # Consider adding argument parsing for server script path if needed
    # import argparse
    # parser = argparse.ArgumentParser()
    # parser.add_argument("--server-script", default="src/mcp_servers/anki-mcp/anki_mcp_server.py")
    # args = parser.parse_args()
    # asyncio.run(main(server_script=args.server_script))
    asyncio.run(main()) 