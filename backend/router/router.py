"""
backend/router/router.py
─────────────────────────────────────────────────────────────────
Model Router for AeroMind 2.0 (PLAN §7.1, §7.2, ADR-0005, ADR-0007).
All model resolution is performed by capability tag, device-aware
hardware tier, and zero-egress validation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse
import yaml

from router.hardware_probe import get_current_tier

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml"

# Role name to canonical capability tag mapping (PLAN §7.1)
ROLE_TO_CAPABILITY: Dict[str, str] = {
    "orchestrator": "planning",
    "synthesis": "drafting",
    "vision_table": "vision",
    "math": "math",
    "reasoning": "general_reasoning",
    "verification": "evaluation",
    "code": "code_gen",
    "coding": "code_gen",
}

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class NoModelForCapability(Exception):
    """Raised when no model exists for the requested capability tag in the current tier."""
    pass


class ModelFailureError(NoModelForCapability):
    """Raised when all candidates for a capability fail health checks or circuit breaker."""
    pass


class ModelRouter:
    """
    Router that resolves capability tags to model configuration entries.
    Loads models.yaml, selects the hardware tier, and enforces zero-egress invariants.
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        environment: Optional[str] = None,
        hardware_tier: Optional[str] = None,
    ) -> None:
        self.config_path = Path(config_path) if config_path else CONFIG_PATH
        if not self.config_path.exists():
            raise FileNotFoundError(f"Model registry configuration not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._raw_config: Dict[str, Any] = yaml.safe_load(f) or {}

        # Profile / Environment selection
        env_from_os = os.environ.get("AEROMIND_ENV") or os.environ.get("WORKBENCH_ENV") or "local"
        self.environment = environment or env_from_os

        valid_environments = [k for k in self._raw_config.keys() if k != "version"]
        if self.environment not in self._raw_config:
            raise ValueError(
                f"Unknown environment '{self.environment}'. Valid environments in {self.config_path.name}: {valid_environments}"
            )

        # Hardware tier selection (ADR-0007)
        self.hardware_tier = (
            hardware_tier
            or os.environ.get("AEROMIND_HW_TIER")
            or get_current_tier()
        )

        # Load-time validation
        self._validate_registry()
        self.enforce_zero_egress_startup_guard()

    def enforce_zero_egress_startup_guard(self) -> None:
        """Enforces offline environment flags and verifies no cloud models are referenced."""
        is_zero_egress = os.environ.get("ZERO_EGRESS_MODE", "true").lower() == "true"
        if is_zero_egress:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["ENABLE_COLPALI_DOWNLOAD"] = "false"

            # Check if active tier models contain any cloud references
            tier_models = self.get_tier_models()
            for m in tier_models:
                tag = str(m.get("model_tag", ""))
                if ":cloud" in tag or "-cloud" in tag or m.get("remote_model"):
                    raise RuntimeError(
                        f"Zero-egress startup violation: model '{m.get('name')}' references cloud tag '{tag}'."
                    )

    def _validate_registry(self) -> None:
        """Enforces schema, zero-egress, and parity invariants at load time."""
        env_block = self._raw_config.get(self.environment, {})

        # 1. Local environment must enforce loopback and no cloud models
        if self.environment == "local":
            for tier_name, entries in env_block.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    endpoint = entry.get("endpoint", "")
                    parsed = urlparse(endpoint)
                    host = parsed.hostname or ""
                    if host not in LOOPBACK_HOSTS and not host.startswith("192.168.") and not host.startswith("10."):
                        raise ValueError(
                            f"Zero-egress violation: non-loopback endpoint '{endpoint}' found in tier '{tier_name}' for model '{entry.get('name')}'."
                        )

                    model_tag = str(entry.get("model_tag", ""))
                    if model_tag.endswith(":cloud") or model_tag.endswith("-cloud") or ":cloud" in model_tag:
                        raise ValueError(
                            f"Zero-egress violation: cloud model tag '{model_tag}' prohibited in local profile for model '{entry.get('name')}'."
                        )

                    if not entry.get("version"):
                        raise ValueError(
                            f"Schema violation: required 'version' field missing in tier '{tier_name}' for model '{entry.get('name')}'."
                        )

        # 2. Invariant: If 'hf' exists, every capability present in 'hf' MUST be present in 'local'
        if "hf" in self._raw_config and "local" in self._raw_config:
            hf_capabilities: Set[str] = set()
            for entry in self._raw_config["hf"]:
                hf_capabilities.update(entry.get("capabilities", []))

            local_capabilities: Set[str] = set()
            for tier_entries in self._raw_config["local"].values():
                if isinstance(tier_entries, list):
                    for entry in tier_entries:
                        local_capabilities.update(entry.get("capabilities", []))

            missing_in_local = hf_capabilities - local_capabilities
            if missing_in_local:
                raise ValueError(
                    f"Invariant violation (§7.1): capabilities present in 'hf' but missing from 'local': {sorted(missing_in_local)}"
                )

    def get_tier_models(self, tier: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all model entries for the specified or current hardware tier."""
        target_tier = tier or self.hardware_tier
        env_block = self._raw_config.get(self.environment, {})
        if target_tier in env_block:
            return env_block[target_tier]
        # If flat list under environment (e.g. hf)
        if isinstance(env_block, list):
            return env_block
        return []

    def get_tier_capabilities(self, tier: Optional[str] = None) -> Set[str]:
        """Returns the set of all capability tags supported in the specified or current tier."""
        models = self.get_tier_models(tier)
        caps: Set[str] = set()
        for m in models:
            caps.update(m.get("capabilities", []))
        return caps

    def get(self, capability: str, check_health: bool = True) -> Dict[str, Any]:
        """
        Resolves a capability tag with health check and automatic ranked failover (Task 2.6).
        Serves the next-ranked model on the same tag if the primary candidate fails health check,
        emitting a MODEL_FAILOVER audit event. Fails loudly with ModelFailureError (MODEL_FAILURE)
        if all candidates are unavailable.
        """
        canonical_tag = ROLE_TO_CAPABILITY.get(capability.lower(), capability.lower())
        models = self.get_tier_models()

        matching = [m for m in models if canonical_tag in [c.lower() for c in m.get("capabilities", [])]]

        if not matching:
            valid_caps = sorted(self.get_tier_capabilities())
            raise NoModelForCapability(
                f"No model found for capability '{capability}' (canonical: '{canonical_tag}') "
                f"in tier '{self.hardware_tier}'. Valid capabilities in this tier: {valid_caps}"
            )

        # Sort: default: true first, then lowest rank
        sorted_matches = sorted(
            matching,
            key=lambda m: (
                0 if m.get("default", False) else 1,
                m.get("rank", 999),
            ),
        )

        if not check_health:
            return sorted_matches[0]

        from router.health import health_checker
        from observability.audit import AuditEvent, audit_logger

        primary_model = sorted_matches[0]
        selected_candidate = None

        for idx, candidate in enumerate(sorted_matches):
            endpoint = candidate.get("endpoint", "")
            tag = candidate.get("model_tag", candidate.get("name", ""))
            if health_checker.is_available(endpoint, tag):
                selected_candidate = candidate
                if idx > 0:
                    # Emits MODEL_FAILOVER event
                    try:
                        audit_logger.emit(
                            AuditEvent(
                                workspace_id="system",
                                user_id="system",
                                conversation_id="conv_failover",
                                task_id=f"failover_{canonical_tag}",
                                event_type="MODEL_FAILOVER",
                                agent_name="model_router",
                                permission_check=True,
                                details={
                                    "capability": canonical_tag,
                                    "primary_model": primary_model.get("name"),
                                    "failover_model": candidate.get("name"),
                                    "rank": candidate.get("rank"),
                                },
                                succeeded=True,
                            )
                        )
                    except Exception:
                        pass
                break

        if selected_candidate is not None:
            return selected_candidate

        # All candidates failed health check or tripped circuit breaker
        try:
            audit_logger.emit(
                AuditEvent(
                    workspace_id="system",
                    user_id="system",
                    conversation_id="conv_failover",
                    task_id=f"failure_{canonical_tag}",
                    event_type="MODEL_FAILURE",
                    agent_name="model_router",
                    permission_check=True,
                    details={
                        "capability": canonical_tag,
                        "candidates_tried": [m.get("name") for m in sorted_matches],
                        "reason": "All candidates down or circuit breaker tripped",
                    },
                    succeeded=False,
                )
            )
        except Exception:
            pass

        raise ModelFailureError(
            f"MODEL_FAILURE: All candidate models for capability '{capability}' in tier '{self.hardware_tier}' are down or unresponsive."
        )

    def resolve(self, capability: str) -> Dict[str, Any]:
        """Static resolution without active health probe (backward compatible)."""
        return self.get(capability, check_health=False)

    def get_model_tag(self, capability: str) -> str:
        """Returns the Ollama/provider model tag for the resolved capability."""
        entry = self.get(capability, check_health=True)
        return entry.get("model_tag", entry.get("name", ""))


# Global singleton router instance
router = ModelRouter()

