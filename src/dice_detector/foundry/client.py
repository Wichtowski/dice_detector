import httpx

from dice_detector.models import FoundryConfig, RollResult


class FoundryClient:
    def __init__(self, config: FoundryConfig) -> None:
        self.config = config
        self._connected = False

    def connect(self) -> bool:
        try:
            response = httpx.get(f"{self.config.http_url}/", timeout=2.0)
            self._connected = response.status_code < 500
            return self._connected
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False

    def send_roll(self, result: RollResult) -> bool:
        if not self._connected:
            return False
        try:
            response = httpx.post(
                f"{self.config.http_url}/api/dice-detector/roll",
                json={
                    "message": result.to_markdown(),
                    "result": result.model_dump(mode="json"),
                },
                timeout=5.0,
            )
            return response.status_code < 400
        except Exception:
            return False
