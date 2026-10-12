"""Optional synthesis settings.

Template parameters preserve numeral sorts regardless of these options.
"""
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class SynthesisOptions:
    preserve_discrete_predicates: bool = False
    prioritize_seed_differences: bool = False
    fixpoint_simplifier: str = "recursive"
    compact_qe: bool = False
    export_winning_region: bool = False
    strict_template_checks: bool = False

    def __post_init__(self):
        if self.fixpoint_simplifier not in ("recursive", "z3-context"):
            raise ValueError("fixpoint_simplifier must be 'recursive' or 'z3-context'")
        for field in fields(self):
            if field.name != "fixpoint_simplifier" and type(getattr(self, field.name)) is not bool:
                raise ValueError(f"{field.name} must be a boolean")

    @classmethod
    def from_mapping(cls, values=None):
        if values is None:
            return cls()
        if not isinstance(values, dict):
            raise ValueError("synthesis_options must be an object")
        unknown = set(values) - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError("Unknown synthesis options: " + ", ".join(sorted(unknown)))
        return cls(**values)
