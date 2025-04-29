# AnkiChat

A powerful integration for using Anki with AI assistance.

## Installation

### Clone the Repository

To clone this repository with all its submodules, run:

```bash
git clone --recursive https://github.com/yourusername/AnkiChat.git
cd AnkiChat
```

If you've already cloned the repository without the `--recursive` flag, you can fetch the submodules with:

```bash
git submodule update --init --recursive
```

### Installation Steps

1. Install dependencies:

for linux:
```bash
./scripts/install_linux.sh
```

for mac:
```bash
./scripts/install_mac.sh
```

2. Configure the mcp server:

You can use the example config file as a template to configure the mcp server.

After initializing the uv project using install_mac.sh or install_linux.sh, you can configure the mcp server by adding the path to the virtual environment by typing the following command into the terminal:

```bash
which python
```
it will return something like this:

```bash
/Users/your_username/<path_to_venv>/.venv/bin/python
```

```bash
which uv
```
it will return something like this:

```bash
/Users/your_username/.local/bin/uv
```
or whatever path you have for uv

you will copy these paths and put it into the config replacing the `<path_to_venv>` with the path to the virtual environment and `<path_to_uv_binary>` with the path to the uv binary:

```json
{
    "mcpServers": {
      "Anki Operations": {
        "command": "<path_to_uv_binary>/uv>",
        "args": [
          "run",
          "--with",
          "mcp[cli]",
          "mcp",
          "run",
          "<path_to_venv>/anki_mcp_server.py"
        ],
        "env": {
          "VIRTUAL_ENV": "<path_to_venv>/.venv",
          "PATH": "<path_to_venv>/.venv/bin:${PATH}"
        }
      }
    }
  }
```

If you want to use  anki_mcp_server.py with Claude Desktop or Cursor even, or any other service that supports mcp and allows a config like this, you can simply copy the Anki Operations section and paste it into the mcp config file of the other service underneath the other tool names (make sure to add a comma after the last tool name in the previous service's mcpServers section before adding this new one as there has to be a comma between each server entry/member in the mcpServers section).

```json
{
    "mcpServers": {
      "Other Server": {
        "command": "other_command",
        "args": [
          "other_args"
        ],
        "env": {           // THIS IS AN OPTIONAL FIELD
          "other_env_vars" 
        }
      }, # add this comma after the last server entry/member in the mcpServers section
      "Anki Operations": {
        "command": "<path_to_uv_binary>/uv>",
        "args": [
          "run",
          "--with",
          "mcp[cli]",
          "mcp",
          "run",
          "<path_to_venv>/anki_mcp_server.py"
        ],
        "env": {
          "VIRTUAL_ENV": "<path_to_venv>/.venv",
          "PATH": "<path_to_venv>/.venv/bin:${PATH}"
        }
      }
    }
  }
```

## Features

- Seamless Anki integration
- AI-assisted flashcard creation
- Smart study planning
- Card quality assessment
