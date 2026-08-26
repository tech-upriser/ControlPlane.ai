import os
import yaml
from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class PolicyProfile(BaseModel):
    name: str
    description: str = ""

    # Responsibility controls
    pii_action: Literal["redact", "block", "flag", "allow"] = "redact"
    pii_sensitivity: Literal["high", "medium", "low"] = "high"
    content_safety_action: Literal["block", "flag", "allow"] = "block"
    injection_action: Literal["block", "flag", "allow"] = "block"

    # Performance controls
    hallucination_strictness: float = Field(default=0.7, ge=0.0, le=1.0)
    context_health_threshold: float = Field(default=50.0, ge=0.0, le=100.0)

    # Cost controls
    loop_detection_window: int = Field(default=5, ge=2, le=20)
    loop_similarity_threshold: float = Field(default=0.85, ge=0.5, le=1.0)
    max_latency_budget_ms: int = Field(default=100, ge=10, le=5000)

    # Tool safety controls
    tool_call_action: Literal["allow", "require_approval", "block"] = "allow"
    restricted_tools: List[str] = Field(default_factory=list)

    # Escalation
    escalation_enabled: bool = False
    escalation_webhook: Optional[str] = None


class PolicyEngine:
    def __init__(self):
        self._profiles: dict[str, PolicyProfile] = {}

    def load_profiles(self, config_dir: str) -> None:
        """Reads all YAML files from config_dir, parses into PolicyProfile objects."""
        if not os.path.isdir(config_dir):
            raise FileNotFoundError(f"Config directory not found: {config_dir}")

        for filename in os.listdir(config_dir):
            if filename.endswith(('.yaml', '.yml')):
                filepath = os.path.join(config_dir, filename)
                with open(filepath, 'r') as f:
                    data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    profile = PolicyProfile(**data)
                    self._profiles[profile.name] = profile

    def get_profile(self, name: str) -> PolicyProfile:
        """Returns profile by name. Raises KeyError if not found."""
        if name not in self._profiles:
            raise KeyError(f"Policy profile not found: {name}")
        return self._profiles[name]

    def resolve_profile(self, headers: dict) -> PolicyProfile:
        """Reads 'x-controlplane-profile' header (case-insensitive).
        Falls back to 'default' profile if header missing or profile unknown."""
        # Normalize headers to lowercase keys
        normalized = {k.lower(): v for k, v in headers.items()}
        profile_name = normalized.get('x-controlplane-profile', 'default')

        try:
            return self.get_profile(profile_name)
        except KeyError:
            return self.get_profile('default')

    def list_profiles(self) -> List[str]:
        """Returns all loaded profile names."""
        return sorted(self._profiles.keys())
