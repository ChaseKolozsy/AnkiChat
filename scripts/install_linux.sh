#!/bin/bash

# Make sure core dependencies are installed
sudo apt-get update && sudo apt-get install -y build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev curl libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

# Install Docker if not present
if ! command -v docker &>/dev/null; then
  echo "Docker not found. Installing..."
  sudo apt-get update
  sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce
else
  echo "Docker already installed."
fi

# Install uv if not present
echo "Checking for uv..."
if ! command -v uv &>/dev/null; then
  echo "uv not found. Installing..."
  pip install uv
else
  echo "uv already installed."
fi

# Install pyenv if not present
if ! command -v pyenv &>/dev/null; then
  curl https://pyenv.run | bash
  echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
  echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
  echo 'eval "$(pyenv init -)"' >> ~/.bashrc
  source ~/.bashrc
fi

# Run the build script
echo "Building Docker image..."
cd AnkiAPI/docker && ./build.sh 

uv venv
source .venv/bin/activate

# Install project dependencies
uv pip install .

which python
which uv
