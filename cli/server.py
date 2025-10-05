"""
Server lifecycle management for AnkiChat CLI

Automatically starts and stops the web app API server in the background.
"""

import subprocess
import time
import sys
import atexit
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Global server process
_server_process: Optional[subprocess.Popen] = None


def ensure_server_running(host: str = 'localhost', port: int = 8888) -> str:
    """
    Start web app server if not running, return server URL

    Args:
        host: Server host (default: localhost)
        port: Server port (default: 8000)

    Returns:
        Server URL (e.g., "http://localhost:8000")

    Raises:
        RuntimeError: If server fails to start
    """
    global _server_process

    server_url = f"http://{host}:{port}"

    # Check if already running
    try:
        response = requests.get(f"{server_url}/api/health", timeout=2)
        if response.status_code == 200:
            logger.info(f"Server already running at {server_url}")
            return server_url
    except requests.exceptions.RequestException:
        pass  # Server not running, will start it

    # Start server in background
    logger.info(f"Starting API server at {server_url}...")

    try:
        _server_process = subprocess.Popen(
            [
                'anki-chat-web',
                '--host', host, '--port', str(port)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr with stdout
            text=True
        )
    except Exception as e:
        raise RuntimeError(f"Failed to start server process: {e}")

    # Wait for server to be ready
    max_attempts = 20
    for attempt in range(max_attempts):
        time.sleep(1)

        # Check if process died
        if _server_process.poll() is not None:
            # Process terminated, get output
            stdout, stderr = _server_process.communicate()
            error_msg = f"Server process died during startup.\n"
            if stderr:
                error_msg += f"STDERR: {stderr}\n"
            if stdout:
                error_msg += f"STDOUT: {stdout}"
            raise RuntimeError(error_msg)

        try:
            response = requests.get(f"{server_url}/api/health", timeout=1)
            if response.status_code == 200:
                logger.info(f"Server started successfully at {server_url}")
                # Register cleanup on exit
                atexit.register(cleanup_server)
                return server_url
        except requests.exceptions.RequestException:
            continue

    # Server failed to start - try to get output
    stdout, stderr = '', ''
    if _server_process.poll() is None:
        # Still running but not responding
        _server_process.terminate()
        try:
            stdout, stderr = _server_process.communicate(timeout=2)
        except:
            pass
    else:
        stdout, stderr = _server_process.communicate()

    error_msg = f"Failed to start API server after {max_attempts} seconds.\n"
    if stdout:
        error_msg += f"OUTPUT: {stdout[:1000]}"

    cleanup_server()
    raise RuntimeError(error_msg)


def cleanup_server():
    """Cleanup server process on exit"""
    global _server_process

    if _server_process is not None:
        logger.info("Shutting down API server...")
        try:
            _server_process.terminate()
            _server_process.wait(timeout=5)
            logger.info("Server shut down successfully")
        except subprocess.TimeoutExpired:
            logger.warning("Server did not terminate gracefully, killing process...")
            _server_process.kill()
            _server_process.wait()
        except Exception as e:
            logger.error(f"Error during server cleanup: {e}")
        finally:
            _server_process = None


def is_server_running(host: str = 'localhost', port: int = 8888) -> bool:
    """
    Check if server is running

    Args:
        host: Server host
        port: Server port

    Returns:
        True if server is running, False otherwise
    """
    server_url = f"http://{host}:{port}"
    try:
        response = requests.get(f"{server_url}/api/health", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False
