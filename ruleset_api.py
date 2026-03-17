import re
from pathlib import Path
import os


# Auto-detect ruleset directory
def _find_ruleset_dir() -> Path | None:
    _ruleset_env = os.environ.get("RULESET_PATH", "").strip()
    candidates = [
        Path(_ruleset_env) if _ruleset_env else None,
        Path(__file__).resolve().parent.parent / "xbworld-server/freeciv/freeciv/data",
        Path.home() / "freeciv/share/freeciv/",
        Path("/usr/share/freeciv/"),
    ]
    for p in candidates:
        if p and p.exists():
            return p
    return None


def parse_ruleset_sections(text: str) -> dict:
    """Parse INI-like ruleset text into {section_name: {key: value}}"""
    sections = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(';') or line.startswith('#'):
            continue
        m = re.match(r'^\[([^\]]+)\]$', line)
        if m:
            current = m.group(1)
            sections[current] = {}
            continue
        if current and '=' in line:
            key, _, val = line.partition('=')
            sections[current][key.strip()] = val.strip().strip('"')
    return sections


def patch_ruleset_text(text: str, section: str, key: str, value: str) -> str:
    """Replace a key=value in a specific section. Returns modified text."""
    in_section = False
    lines = text.splitlines(keepends=True)
    result = []
    patched = False
    for line in lines:
        stripped = line.strip()
        if re.match(rf'^\[{re.escape(section)}\]$', stripped):
            in_section = True
            result.append(line)
            continue
        if stripped.startswith('[') and in_section:
            in_section = False
        if in_section and not patched:
            m = re.match(rf'^({re.escape(key)})\s*=\s*(.+)$', stripped)
            if m:
                # preserve indentation
                indent = len(line) - len(line.lstrip())
                result.append(' ' * indent + f'{key} = {value}\n')
                patched = True
                continue
        result.append(line)
    return ''.join(result)


def list_units(ruleset_dir: Path | None = None) -> list[dict]:
    """Return list of unit stats from units.ruleset"""
    d = ruleset_dir or _find_ruleset_dir()
    if not d:
        return []
    # Try common paths
    for candidate in [
        d / "classic/units.ruleset",
        d / "civ2civ3/units.ruleset",
        d / "multiplayer/units.ruleset",
        d / "units.ruleset",
    ]:
        if candidate.exists():
            sections = parse_ruleset_sections(candidate.read_text())
            units = []
            for name, props in sections.items():
                if name.startswith('unit_'):
                    units.append({
                        "name": props.get("name", name),
                        "section": name,
                        "build_cost": _int(props.get("build_cost", "0")),
                        "attack": _int(props.get("attack", "0")),
                        "defense": _int(props.get("defense", "0")),
                        "move_rate": _int(props.get("move_rate", "0")),
                    })
            return units
    return []


def list_buildings(ruleset_dir: Path | None = None) -> list[dict]:
    d = ruleset_dir or _find_ruleset_dir()
    if not d:
        return []
    for candidate in [
        d / "classic/buildings.ruleset",
        d / "civ2civ3/buildings.ruleset",
        d / "multiplayer/buildings.ruleset",
        d / "buildings.ruleset",
    ]:
        if candidate.exists():
            sections = parse_ruleset_sections(candidate.read_text())
            buildings = []
            for name, props in sections.items():
                if name.startswith('building_'):
                    buildings.append({
                        "name": props.get("name", name),
                        "section": name,
                        "build_cost": _int(props.get("build_cost", "0")),
                        "upkeep": _int(props.get("upkeep", "0")),
                    })
            return buildings
    return []


def patch_unit_stat(unit_name: str, stat: str, value: int, ruleset_dir: Path | None = None) -> dict:
    d = ruleset_dir or _find_ruleset_dir()
    if not d:
        return {"ok": False, "error": "Ruleset directory not found"}
    for candidate in [
        d / "classic/units.ruleset",
        d / "civ2civ3/units.ruleset",
        d / "multiplayer/units.ruleset",
    ]:
        if candidate.exists():
            text = candidate.read_text()
            sections = parse_ruleset_sections(text)
            section = next((k for k, v in sections.items() if v.get("name") == unit_name), None)
            if not section:
                return {"ok": False, "error": f"Unit '{unit_name}' not found"}
            new_text = patch_ruleset_text(text, section, stat, str(value))
            candidate.write_text(new_text)
            return {"ok": True, "note": "Restart game server for changes to take effect"}
    return {"ok": False, "error": "units.ruleset not found"}


def patch_building_stat(building_name: str, stat: str, value: int, ruleset_dir: Path | None = None) -> dict:
    d = ruleset_dir or _find_ruleset_dir()
    if not d:
        return {"ok": False, "error": "Ruleset directory not found"}
    for candidate in [
        d / "classic/buildings.ruleset",
        d / "civ2civ3/buildings.ruleset",
        d / "multiplayer/buildings.ruleset",
    ]:
        if candidate.exists():
            text = candidate.read_text()
            sections = parse_ruleset_sections(text)
            section = next((k for k, v in sections.items() if v.get("name") == building_name), None)
            if not section:
                return {"ok": False, "error": f"Building '{building_name}' not found"}
            new_text = patch_ruleset_text(text, section, stat, str(value))
            candidate.write_text(new_text)
            return {"ok": True, "note": "Restart game server for changes to take effect"}
    return {"ok": False, "error": "buildings.ruleset not found"}


def _int(s: str) -> int:
    try:
        return int(s)
    except Exception:
        return 0
