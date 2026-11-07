"""Read-only installation checks; never capture the screen or send messages."""

from pathlib import Path
import subprocess

import requests


def check_installation(config):
    results = []
    executable = config["tesseract"]
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError("Tesseract exited with an error.")
        results.append("Tesseract: " + (result.stdout or result.stderr).splitlines()[0])
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        results.append("Tesseract unavailable: " + str(error))
    try:
        url = config["ollama_url"].rsplit("/api/", 1)[0] + "/api/tags"
        response = requests.get(url, timeout=(3, 5))
        response.raise_for_status()
        names = {item["name"] for item in response.json().get("models", [])}
        model = config["model"]
        installed = model in names or model + ":latest" in names
        results.append(f"Ollama reachable. Selected model {'installed' if installed else 'NOT installed'}: {model}")
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        results.append("Ollama unavailable: " + str(error))
    return "\n".join(results)
