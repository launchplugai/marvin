"""Data models for Protocol Engine — ProtocolSignal, DNA Artifacts, and PDC types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Tier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    ELITE = "ELITE"
    INTERNAL = "INTERNAL"


class Category(str, Enum):
    PHYSICAL_STATE = "physical_state"
    TACTICAL_MATCHUP = "tactical_matchup"
    VOLATILITY = "volatility"
    PSYCHOLOGY = "psychology"
    MARKET_BEHAVIOR = "market_behavior"
    OFFICIATING = "officiating"
    DATA_QUALITY = "data_quality"


class ImpactType(str, Enum):
    STABILITY_MODIFIER = "stability_modifier"
    FRAGILITY_DELTA = "fragility_delta"
    CONSTRAINT_FLAG = "constraint_flag"
    CONFIDENCE_ADJUSTMENT = "confidence_adjustment"


class ImpactMode(str, Enum):
    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"


class CapabilityStatus(str, Enum):
    WORKING = "WORKING"
    BROKEN = "BROKEN"
    MISSING = "MISSING"
    WRONG = "WRONG"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# ProtocolSignal — the standard output of every evaluator
# ---------------------------------------------------------------------------

@dataclass
class ProtocolSignal:
    """Standard output returned by every protocol evaluator."""

    protocol_id: str
    triggered: bool
    confidence: float  # 0.0–1.0
    impact: Impact
    evidence_data: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0.0–1.0, got {self.confidence}")


@dataclass
class Impact:
    """The quantified effect of a triggered protocol."""

    impact_type: ImpactType
    value: float
    clamped: bool = False  # True if value was clamped to bounds

    @staticmethod
    def clamp_value(value: float, clamp_min: float, clamp_max: float) -> tuple[float, bool]:
        clamped = value
        was_clamped = False
        if value < clamp_min:
            clamped = clamp_min
            was_clamped = True
        elif value > clamp_max:
            clamped = clamp_max
            was_clamped = True
        return clamped, was_clamped


# ---------------------------------------------------------------------------
# DNA Artifacts — the output format for the DNA contract
# ---------------------------------------------------------------------------

@dataclass
class EvidenceArtifact:
    """A piece of evidence produced by a protocol."""

    protocol_id: str
    summary: str
    fields: Dict[str, Any]


@dataclass
class WeightArtifact:
    """A weight modification produced by a protocol."""

    protocol_id: str
    target: str  # e.g. "stabilityModifier", "fragilityDelta"
    delta: float


@dataclass
class AuditNoteArtifact:
    """An audit trail entry for a protocol evaluation."""

    protocol_id: str
    note: str


@dataclass
class ConstraintArtifact:
    """A constraint flag (e.g. 'avoid', 'downgrade confidence')."""

    protocol_id: str
    constraint_type: str
    reason: str


@dataclass
class ProtocolArtifacts:
    """All DNA artifacts emitted by a single protocol evaluation."""

    evidence: Optional[EvidenceArtifact] = None
    weight: Optional[WeightArtifact] = None
    audit_note: Optional[AuditNoteArtifact] = None
    constraint: Optional[ConstraintArtifact] = None


# ---------------------------------------------------------------------------
# PDC types — parsed protocol definitions
# ---------------------------------------------------------------------------

@dataclass
class ProtocolDefinition:
    """A single protocol definition parsed from PDC."""

    protocol_id: str
    name: str
    sport: List[str]
    category: Category
    enabled: bool
    tier: Tier
    inputs: Dict[str, List[str]]
    evaluator: Dict[str, str]
    thresholds: Dict[str, Any]
    weights: Dict[str, Any]
    impact_model: Dict[str, Any]
    artifact_mapping: Dict[str, Any]
    explain_templates: Dict[str, Any]
    tags: List[str] = field(default_factory=list)


@dataclass
class PDCatalog:
    """The full Protocol Definition Catalog."""

    catalog_version: str
    dna_contract_version: str
    generated_at: str
    defaults: Dict[str, Any]
    protocols: List[ProtocolDefinition]

    def get_protocol(self, protocol_id: str) -> Optional[ProtocolDefinition]:
        for p in self.protocols:
            if p.protocol_id == protocol_id:
                return p
        return None

    def get_protocols_for_sport(self, sport: str) -> List[ProtocolDefinition]:
        return [p for p in self.protocols if sport in p.sport]

    def get_enabled_protocols(self, sport: str, user_tier: Tier) -> List[ProtocolDefinition]:
        tier_rank = {Tier.FREE: 0, Tier.PRO: 1, Tier.ELITE: 2, Tier.INTERNAL: 3}
        user_rank = tier_rank.get(user_tier, 0)
        return [
            p for p in self.protocols
            if p.enabled
            and sport in p.sport
            and tier_rank.get(p.tier, 3) <= user_rank
        ]
