from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import os


@dataclass
class AdminConfig:
    # Agent strategy
    system_prompt: str = ""
    engine_type: str = "llm"  # "llm" | "rule_based"
    llm_max_iterations: int = 10
    turn_timeout_seconds: int = 60
    inter_turn_delay: int = 2

    # Research priorities
    research_priority_techs: list = field(default_factory=lambda: [
        "Alphabet", "Code of Laws", "Republic", "Writing",
        "Mathematics", "Construction", "Trade", "Banking"
    ])

    # Agent tool rules
    min_city_distance: int = 4
    default_science_rate: int = 60
    default_tax_rate: int = 30
    default_luxury_rate: int = 10

    # Game mechanism settings (written to serv script)
    game_timeout: int = 60
    aifill: int = 10
    max_connections_per_host: int = 256


_config: AdminConfig | None = None


def get_config() -> AdminConfig:
    global _config
    if _config is None:
        _config = AdminConfig()
    return _config


def update_config(partial: dict) -> dict:
    """Validate and update config fields. Returns {changed: {}, errors: []}"""
    cfg = get_config()
    changed = {}
    errors = []

    validators = {
        'min_city_distance': lambda v: 2 <= int(v) <= 15,
        'default_science_rate': lambda v: 0 <= int(v) <= 100,
        'llm_max_iterations': lambda v: 1 <= int(v) <= 30,
        'turn_timeout_seconds': lambda v: 10 <= int(v) <= 600,
        'inter_turn_delay': lambda v: 0 <= int(v) <= 120,
        'aifill': lambda v: 0 <= int(v) <= 30,
    }

    for key, value in partial.items():
        if not hasattr(cfg, key):
            errors.append(f"Unknown field: {key}")
            continue
        if key in validators:
            try:
                if not validators[key](value):
                    errors.append(f"Invalid value for {key}: {value}")
                    continue
            except (ValueError, TypeError):
                errors.append(f"Invalid type for {key}: {value}")
                continue
        old = getattr(cfg, key)
        setattr(cfg, key, type(old)(value) if not isinstance(old, list) else value)
        changed[key] = value

    return {"changed": changed, "errors": errors}


def config_to_dict() -> dict:
    return asdict(get_config())


def save_config(path: Path):
    path.write_text(json.dumps(config_to_dict(), indent=2))


def load_config(path: Path):
    global _config
    data = json.loads(path.read_text())
    _config = AdminConfig(**{k: v for k, v in data.items() if hasattr(AdminConfig, k)})
