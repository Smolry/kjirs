import json, time
from pathlib import Path
from typing import Any

class DataCache:
    def __init__(self, mode: str, cache_dir: str, ttl_seconds: int):
        self.mode = mode.lower()
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.memory: dict[str, tuple[float, Any]] = {}
        if self.mode == "file":
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Any | None:
        now = time.time()
        if key in self.memory:
            created, value = self.memory[key]
            if now - created < self.ttl_seconds:
                return value
            self.memory.pop(key, None)
        if self.mode == "file":
            path = self.cache_dir / f"{key}.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if now - payload["created_at"] < self.ttl_seconds:
                    self.memory[key] = (payload["created_at"], payload["value"])
                    return payload["value"]
                path.unlink(missing_ok=True)
            except (OSError, ValueError, KeyError, TypeError):
                return None
        return None

    def set(self, key: str, value: Any) -> None:
        now = time.time()
        self.memory[key] = (now, value)
        if self.mode == "file":
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self.cache_dir / f"{key}.json"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"created_at": now, "value": value}), encoding="utf-8")
            tmp.replace(path)

    def clear(self) -> None:
        self.memory.clear()
        if self.mode == "file" and self.cache_dir.exists():
            for path in self.cache_dir.glob("*.json"):
                path.unlink(missing_ok=True)
