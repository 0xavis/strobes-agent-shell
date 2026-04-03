"""Command execution and file I/O for the shell bridge agent."""

import asyncio
import base64
import glob
import os
import platform
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional


async def execute_shell_command(
    command: str,
    timeout: int = 60,
    cwd: Optional[str] = None,
) -> dict:
    """Execute a shell command via subprocess."""
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
            }
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            duration_ms = int((time.monotonic() - start) * 1000)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
                "duration_ms": duration_ms,
                "error": "timeout",
            }
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "duration_ms": duration_ms,
            "error": str(e),
        }


async def execute_code(
    language: str,
    code: str,
    timeout: int = 60,
    cwd: Optional[str] = None,
) -> dict:
    """Execute code by writing to a temp file and running with the appropriate interpreter."""
    lang = language.lower()

    if lang in ("python", "python3"):
        suffix = ".py"
        interpreter = "python3"
    elif lang in ("node", "javascript", "js"):
        suffix = ".js"
        interpreter = "node"
    elif lang in ("typescript", "ts"):
        suffix = ".ts"
        interpreter = "npx ts-node"
    elif lang in ("bash", "sh", "shell"):
        # Execute directly as shell command
        return await execute_shell_command(code, timeout=timeout, cwd=cwd)
    else:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Unsupported language: {language}",
            "exit_code": -1,
            "duration_ms": 0,
        }

    # Write to temp file and execute
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, dir=cwd
    ) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = await execute_shell_command(
            f"{interpreter} {temp_path}",
            timeout=timeout,
            cwd=cwd,
        )
        return result
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def read_file(path: str) -> dict:
    """Read a file and return its content."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not p.is_file():
            return {"success": False, "error": f"Not a file: {path}"}

        size = p.stat().st_size
        # Limit to 1MB text read
        if size > 1_048_576:
            content = p.read_bytes()[:1_048_576].decode(errors="replace")
            return {
                "success": True,
                "content": content,
                "truncated": True,
                "size": size,
            }

        return {
            "success": True,
            "content": p.read_text(errors="replace"),
            "size": size,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str, mode: str = "overwrite") -> dict:
    """Write content to a file."""
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with open(p, "a") as f:
                f.write(content)
        else:
            p.write_text(content)

        return {"success": True, "path": str(p), "size": p.stat().st_size}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_files(directory: str = ".", pattern: Optional[str] = None, recursive: bool = False) -> dict:
    """List files in a directory."""
    try:
        p = Path(directory).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}
        if not p.is_dir():
            return {"success": False, "error": f"Not a directory: {directory}"}

        if pattern:
            if recursive:
                matches = list(p.rglob(pattern))
            else:
                matches = list(p.glob(pattern))
            files = [
                {
                    "name": str(m.relative_to(p)),
                    "type": "dir" if m.is_dir() else "file",
                    "size": m.stat().st_size if m.is_file() else 0,
                }
                for m in sorted(matches)[:500]
            ]
        else:
            files = [
                {
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                }
                for item in sorted(p.iterdir())[:500]
            ]

        return {"success": True, "directory": str(p), "files": files}
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_file(path: str, content_b64: str) -> dict:
    """Upload a file (base64-encoded content)."""
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(content_b64)
        p.write_bytes(data)
        return {"success": True, "path": str(p), "size": len(data)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def download_file(path: str) -> dict:
    """Download a file (returns base64-encoded content)."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not p.is_file():
            return {"success": False, "error": f"Not a file: {path}"}

        size = p.stat().st_size
        if size > 10_485_760:  # 10MB limit
            return {"success": False, "error": f"File too large: {size} bytes (max 10MB)"}

        content = base64.b64encode(p.read_bytes()).decode()
        return {"success": True, "content_b64": content, "size": size}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_env_info() -> dict:
    """Get environment information about the machine."""
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "arch": platform.machine(),
        "hostname": platform.node(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
        "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
    }

    # Check for common tools
    tools = {}
    for tool in ["python3", "node", "npm", "git", "docker", "nmap", "curl", "wget",
                 "nuclei", "httpx", "subfinder", "ffuf", "gobuster"]:
        tools[tool] = shutil.which(tool) is not None
    info["tools"] = tools

    return {"success": True, **info}
