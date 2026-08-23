from app.application.inference import InferenceHealth


class StubInference:
    def complete(self, prompt: str) -> str:
        return f"[stub] You said: {prompt}"

    def health(self) -> InferenceHealth:
        return "ready"
