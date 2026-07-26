from __future__ import annotations

import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .runtime import sanitize_payload


class ProviderConnectionSummary(BaseModel):
    id: str
    workspace_id: str
    provider: str
    purpose: str
    display_name: str
    state: Literal["active", "invalid", "revoked"]
    scopes: list[str]
    secret_fingerprint: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class ProtectedProviderConnectionRequest(BaseModel):
    id: str | None = None
    provider: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    purpose: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    display_name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=list, max_length=32)
    encrypted_secret: str = Field(min_length=16, max_length=131072)
    kms_key_version: str = Field(min_length=8, max_length=512)
    secret_fingerprint: str = Field(pattern=r"^[a-f0-9]{16,64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[a-zA-Z0-9:._/-]{1,120}", scope) for scope in value):
            raise ValueError("invalid provider scope")
        return sorted(set(value))


class ProviderConnectionService:
    def __init__(self, store: Any):
        self.store = store

    def list(self, workspace_id: str) -> list[ProviderConnectionSummary]:
        return [ProviderConnectionSummary.model_validate(row) for row in self.store.list_provider_connections(workspace_id)]

    def put(self, workspace_id: str, request: ProtectedProviderConnectionRequest) -> ProviderConnectionSummary:
        row = self.store.put_provider_connection(
            connection_id=request.id or f"connection_{uuid4().hex}", workspace_id=workspace_id,
            provider=request.provider, purpose=request.purpose, display_name=request.display_name,
            state="active", scopes=request.scopes, encrypted_secret=request.encrypted_secret,
            kms_key_version=request.kms_key_version, secret_fingerprint=request.secret_fingerprint,
            metadata=sanitize_payload(request.metadata),
        )
        return ProviderConnectionSummary.model_validate(row)

    def protected(self, workspace_id: str, connection_id: str) -> dict[str, Any]:
        return self.store.get_provider_connection_secret(workspace_id, connection_id)

    def revoke(self, workspace_id: str, connection_id: str) -> ProviderConnectionSummary:
        return ProviderConnectionSummary.model_validate(
            self.store.revoke_provider_connection(workspace_id, connection_id)
        )
