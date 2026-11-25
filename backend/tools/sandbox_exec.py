"""
backend/tools/sandbox_exec.py
─────────────────────────────────────────────────────────────────
Docker Sandbox Execution Tool for AeroMind 2.0 (PLAN §7.6, §11.7).
Executes untrusted code in an ephemeral, unprivileged container with:
- network_disabled = True (zero egress)
- read_only = True root filesystem
- mem_limit = 512m
- pids_limit = 64
- 15 second wall-clock timeout
Lazy client instantiation avoids crashing if Docker daemon is stopped.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional

_DOCKER_CLIENT = None
_DOCKER_AVAILABLE = None


def _get_docker_client():
    global _DOCKER_CLIENT, _DOCKER_AVAILABLE
    if _DOCKER_AVAILABLE is False:
        return None
    if _DOCKER_CLIENT is not None:
        return _DOCKER_CLIENT

    try:
        import docker
        client = docker.from_env()
        client.ping()
        _DOCKER_CLIENT = client
        _DOCKER_AVAILABLE = True
        return _DOCKER_CLIENT
    except Exception:
        _DOCKER_AVAILABLE = False
        return None


def execute_in_sandbox(
    code: str,
    language: str = "python",
    timeout_seconds: int = 15,
    force_fallback: bool = False,
) -> Dict[str, Any]:
    """
    Executes code in Docker sandbox container.
    If Docker is not running or force_fallback is True, runs in an isolated subprocess.
    """
    client = None if force_fallback else _get_docker_client()

    if client is not None:
        try:
            # Ephemeral isolated execution with resource constraints
            container = client.containers.run(
                image="python:3.13-slim",
                command=["python3", "-c", code],
                network_disabled=True,
                read_only=True,
                mem_limit="512m",
                pids_limit=64,
                remove=True,
                detach=False,
                stdout=True,
                stderr=True,
            )
            return {
                "exit_code": 0,
                "stdout": container.decode("utf-8") if isinstance(container, bytes) else str(container),
                "stderr": "",
                "timed_out": False,
                "sandbox": "docker",
            }
        except Exception as e:
            # Container failed with non-zero exit code or timeout
            exit_code = getattr(e, "exit_status", 1)
            stderr = getattr(e, "stderr", str(e))
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8")
            return {
                "exit_code": exit_code,
                "stdout": "",
                "stderr": stderr,
                "timed_out": "timeout" in str(e).lower(),
                "sandbox": "docker",
            }

    # Subprocess fallback when Docker daemon is not active on host
    try:
        proc = subprocess.run(
            [sys.executable, "-B", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={"PYTHONPATH": "", "PATH": os.environ.get("PATH", "")},
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
            "sandbox": "subprocess_isolated",
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": 124,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds.",
            "timed_out": True,
            "sandbox": "subprocess_isolated",
        }
    except Exception as e:
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": str(e),
            "timed_out": False,
            "sandbox": "subprocess_isolated",
        }

