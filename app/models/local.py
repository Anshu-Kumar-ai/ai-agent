from openai import OpenAI

from app.models.base import BaseModel


class LocalModel(BaseModel):
    name = "qwen3:8b"
    provider = "ollama"

    OLLAMA_URL = "http://127.0.0.1:11434"
    STARTUP_TIMEOUT = 30

    def __init__(self):
        self.client = OpenAI(
            base_url=f"{self.OLLAMA_URL}/v1",
            api_key="ollama",
        )

    def _ollama_running(self) -> bool:
        try:
            from urllib.request import urlopen

            with urlopen(
                f"{self.OLLAMA_URL}/api/tags",
                timeout=1,
            ):
                return True

        except Exception:
            return False

    def _start_ollama_if_needed(self) -> None:
        if self._ollama_running():
            return

        print("[Local] Waiting for Ollama...")

        import time

        # Give the Windows Ollama application time to start.
        deadline = time.monotonic() + 8

        while time.monotonic() < deadline:
            if self._ollama_running():
                print("[Local] Ollama is available.")
                return

            time.sleep(0.5)

        if self._ollama_running():
            return

        print("[Local] Ollama still unavailable. Starting server...")

        import shutil
        import subprocess

        ollama_path = shutil.which("ollama")

        if not ollama_path:
            raise RuntimeError(
                "Ollama executable was not found in PATH."
            )

        subprocess.Popen(
            [ollama_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            ),
        )

        deadline = time.monotonic() + self.STARTUP_TIMEOUT

        while time.monotonic() < deadline:
            if self._ollama_running():
                print("[Local] Ollama server started.")
                return

            time.sleep(0.5)

        raise RuntimeError(
            "Ollama did not become available."
        )

    def chat(self, message: str) -> str:
        self._start_ollama_if_needed()

        response = self.client.chat.completions.create(
            model=self.name,
            messages=[
                {
                    "role": "user",
                    "content": message,
                }
            ],
        )

        return response.choices[0].message.content
