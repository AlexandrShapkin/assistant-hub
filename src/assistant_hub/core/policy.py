"""Deterministic permission mechanism, independent of any language model."""
from .contracts import ActionIntent, ApprovalRule, Decision, Manifest


def decide(intent: ActionIntent, manifest: Manifest | None,
           rules: tuple[ApprovalRule, ...] = ()) -> Decision:
    if manifest is None or manifest.service_id != intent.service_id:
        return Decision("deny", "unknown service")
    capability = next((c for c in manifest.capabilities if c.name == intent.operation), None)
    if capability is None:
        return Decision("deny", "unknown capability")
    if capability.risk == "high":
        return Decision("review", "high risk requires human review")
    if not capability.mutating:
        return Decision("allowed", "declared read capability")
    for rule in rules:
        if (rule.service_id, rule.account_id, rule.operation, rule.target, rule.payload) == (
            intent.service_id, intent.account_id, intent.operation, intent.target, intent.payload
        ):
            return Decision("preapproved", "exact explicit user-approved rule")
    return Decision("review", "mutation requires human review")
