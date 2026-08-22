class StubInference:
    def complete(self, prompt: str) -> str:
        return f"[stub] You said: {prompt}"
