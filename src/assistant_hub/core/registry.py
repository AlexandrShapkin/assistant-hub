"""Explicit in-process registration, without discovery, imports, or execution by name."""
from .contracts import Adapter, Manifest


class Registry:
    def __init__(self) -> None:
        self._adapters: dict[str, Adapter] = {}

    def enable(self, adapter: Adapter) -> None:
        if not isinstance(adapter.manifest, Manifest):
            raise ValueError("adapter requires a valid manifest")
        service = adapter.manifest.service_id
        if service in self._adapters:
            raise ValueError("service already enabled")
        self._adapters[service] = adapter

    def get(self, service_id: str) -> Adapter:
        return self._adapters[service_id]

    def manifests(self) -> tuple[Manifest, ...]:
        return tuple(a.manifest for a in self._adapters.values())
