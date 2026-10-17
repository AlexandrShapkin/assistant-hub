"""Explicit account/capability activation of trusted in-process adapters."""
from dataclasses import dataclass
from .contracts import Adapter, Manifest, nonempty


@dataclass(frozen=True)
class Binding:
    account_id: str
    capabilities: tuple[str, ...] = ("read",)

    def __post_init__(self) -> None:
        if (not nonempty(self.account_id) or not isinstance(self.capabilities, tuple)
                or not self.capabilities or any(not nonempty(c) for c in self.capabilities)
                or len(set(self.capabilities)) != len(self.capabilities)):
            raise ValueError("invalid account binding")


class Registry:
    def __init__(self) -> None:
        self._adapters: dict[str, Adapter] = {}
        self._manifests: dict[str, Manifest] = {}
        self._accounts: dict[str, tuple[str, ...]] = {}
        self._bindings: dict[tuple[str, str], Binding] = {}

    def enable(self, adapter: Adapter, bindings: tuple[Binding, ...] = ()) -> None:
        manifest = getattr(adapter, "manifest", None)
        if not isinstance(manifest, Manifest) or not callable(getattr(adapter, "poll", None)):
            raise ValueError("adapter requires a valid manifest and poll method")
        manifest.__post_init__()
        accounts = getattr(adapter, "accounts", None)
        if (not isinstance(accounts, tuple) or not accounts
                or any(not nonempty(a) for a in accounts) or len(set(accounts)) != len(accounts)):
            raise ValueError("adapter requires distinct stable account IDs")
        service = manifest.service_id
        if service in self._adapters:
            raise ValueError("service already enabled")
        if not isinstance(bindings, tuple):
            raise ValueError("bindings must be a tuple")
        enabled = {}
        declared = {c.name for c in manifest.capabilities}
        for binding in bindings:
            if not isinstance(binding, Binding):
                raise ValueError("invalid binding")
            binding.__post_init__()
            if (binding.account_id not in accounts or not set(binding.capabilities) <= declared
                    or binding.account_id in enabled):
                raise ValueError("unsupported or duplicate account/capability binding")
            enabled[binding.account_id] = binding
        self._adapters[service] = adapter
        self._manifests[service] = manifest
        self._accounts[service] = accounts
        self._bindings.update({(service, a): b for a, b in enabled.items()})

    def get(self, service_id: str) -> Adapter:
        return self._adapters[service_id]

    def require(self, service_id: str, account_id: str, capability: str) -> Adapter:
        adapter = self.get(service_id)
        binding = self._bindings.get((service_id, account_id))
        if binding is None or capability not in binding.capabilities:
            raise ValueError("account capability is not enabled")
        if adapter.manifest != self._manifests[service_id] or adapter.accounts != self._accounts[service_id]:
            raise ValueError("adapter identity changed after registration")
        return adapter

    def manifests(self) -> tuple[Manifest, ...]:
        return tuple(self._manifests.values())
