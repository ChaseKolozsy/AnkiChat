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

If you want to use  anki_mcp_server.py with Claude Desktop or Cursor even, or any other service that supports mcp and allows a config like this, you can simply copy the Anki Operations section and paste it into the mcp config file of the other service underneath the other tool names (make sure to add a comma after the last tool name in the previous service's mcpServers section before adding this new one as there has to be a comma between each server entry/member in the mcpServers section). For a desktop app that isn't claude or cursor, maybe try: [https://github.com/daodao97/chatmcp]

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
- Integration with chatmcp desktop app for enhanced AI chat functionality
- AnkiAPI utilizes the core Anki engine under the hood for reliable flashcard management

**Container Setup (No Proxy + Desktop Profile Mount)**
- Stop existing container: `docker rm -f anki-api`
- Run with restart policy, proxy vars cleared, and Desktop profile mounted:
  - `docker run -d --name anki-api --restart unless-stopped -p 5001:5001 -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= -e NO_PROXY=sync.ankiweb.net,localhost,127.0.0.1 -v $HOME/.local/share/Anki2:/home/anki/.local/share/Anki2 anki-api`
- Optional debug port: add `-p 5678:5678` if the port is free.
- After launch, configure `.env` in `AnkiClient` with `ANKI_USERNAME` and `ANKI_PASSWORD`; leave `ANKI_ENDPOINT` blank (or set to `https://sync.ankiweb.net/`).
- Why: clearing proxy vars avoids header-stripping; mounting your Desktop profile bypasses destructive full sync and uses your existing collection.

MacOS and Windows examples
- macOS (note the space in the path; keep the quotes):
  - `docker run -d --name anki-api --restart unless-stopped -p 5001:5001 -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= -e NO_PROXY=sync.ankiweb.net,localhost,127.0.0.1 -v "$HOME/Library/Application Support/Anki2":/home/anki/.local/share/Anki2 anki-api`
- Windows (PowerShell):
  - `docker run -d --name anki-api --restart unless-stopped -p 5001:5001 -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= -e NO_PROXY=sync.ankiweb.net,localhost,127.0.0.1 -v "$env:APPDATA\Anki2:/home/anki/.local/share/Anki2" anki-api`
- Windows (cmd.exe):
  - `docker run -d --name anki-api --restart unless-stopped -p 5001:5001 -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= -e NO_PROXY=sync.ankiweb.net,localhost,127.0.0.1 -v "%APPDATA%\Anki2:/home/anki/.local/share/Anki2" anki-api`
- Docker Desktop may require enabling file sharing for the mounted folder/drive in Settings.
