"""Simulated security checks for ASHR routing messages."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from .utils import stable_json


MIN_VALID_ADVERTISED_COST = 0.01
MAX_TTL = 64


@dataclass
class ASHRMessage:
    message_type: str
    sender_router_id: str
    area_id: int
    sequence_number: int
    ttl: int
    body: dict[str, Any]
    auth_tag: str = ""

    def payload_for_auth(self) -> dict[str, Any]:
        return {
            "message_type": self.message_type,
            "sender_router_id": self.sender_router_id,
            "area_id": self.area_id,
            "sequence_number": self.sequence_number,
            "ttl": self.ttl,
            "body": self.body,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload_for_auth()
        payload["auth_tag"] = self.auth_tag
        return payload


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str


class SecurityManager:
    """Security validation model used by ASHR.

    This is intentionally simulation-level security: it models the checks a
    secure link-state protocol would perform without implementing a real key
    exchange or router daemon.
    """

    def __init__(self, trusted_neighbors: dict[str, set[str]] | None = None, shared_keys: dict[str, bytes] | None = None):
        self.trusted_neighbors: dict[str, set[str]] = trusted_neighbors or {}
        self.shared_keys: dict[str, bytes] = shared_keys or {}
        self.highest_sequence: dict[tuple[str, str], int] = {}

    @classmethod
    def from_topology(cls, routers: list[str], adjacency: dict[str, set[str]]) -> "SecurityManager":
        shared_keys = {router: f"ashr-demo-key::{router}".encode("utf-8") for router in routers}
        return cls(trusted_neighbors={router: set(adjacency.get(router, set())) for router in routers}, shared_keys=shared_keys)

    def add_trusted_neighbor(self, router_id: str, neighbor_id: str) -> None:
        self.trusted_neighbors.setdefault(router_id, set()).add(neighbor_id)

    def set_key(self, router_id: str, key: bytes) -> None:
        self.shared_keys[router_id] = key

    def sign_message(self, message: ASHRMessage) -> ASHRMessage:
        key = self.shared_keys.get(message.sender_router_id)
        if key is None:
            message.auth_tag = ""
            return message
        message.auth_tag = hmac.new(
            key,
            stable_json(message.payload_for_auth()).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return message

    def expected_auth_tag(self, message: ASHRMessage) -> str:
        key = self.shared_keys.get(message.sender_router_id)
        if key is None:
            return ""
        return hmac.new(
            key,
            stable_json(message.payload_for_auth()).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def validate_message(self, receiver_router_id: str, message: ASHRMessage) -> ValidationResult:
        if message.ttl <= 0 or message.ttl > MAX_TTL:
            return ValidationResult(False, "invalid TTL")

        trusted = self.trusted_neighbors.get(receiver_router_id, set())
        if message.sender_router_id not in trusted:
            return ValidationResult(False, "sender is not a trusted neighbor")

        expected_tag = self.expected_auth_tag(message)
        if not expected_tag or not hmac.compare_digest(expected_tag, message.auth_tag):
            return ValidationResult(False, "invalid HMAC authentication tag")

        sequence_key = (receiver_router_id, message.sender_router_id)
        previous_sequence = self.highest_sequence.get(sequence_key, -1)
        if message.sequence_number <= previous_sequence:
            return ValidationResult(False, "replayed or stale sequence number")

        if self._contains_fake_low_cost(message.body):
            return ValidationResult(False, "fake low-cost route rejected")

        self.highest_sequence[sequence_key] = message.sequence_number
        return ValidationResult(True, "accepted")

    def _contains_fake_low_cost(self, body: dict[str, Any]) -> bool:
        advertised = []
        if "advertised_cost" in body:
            advertised.append(body["advertised_cost"])
        for link in body.get("links", []):
            if isinstance(link, dict):
                if "advertised_cost" in link:
                    advertised.append(link["advertised_cost"])
                if "cost" in link:
                    advertised.append(link["cost"])
        for value in advertised:
            try:
                if float(value) < MIN_VALID_ADVERTISED_COST:
                    return True
            except (TypeError, ValueError):
                return True
        return False


def tamper_auth_tag(message: ASHRMessage) -> ASHRMessage:
    message.auth_tag = "0" * 64
    return message
