"""Fetch the sources, filter them, and write the README."""

import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from a2sv_roles.filter import select
from a2sv_roles.model import Role
from a2sv_roles.parse import parse_simplify, parse_speedyapply
from a2sv_roles.render import render

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources.yml"
README = ROOT / "README.md"
DATA = ROOT / "data" / "roles.json"


def main() -> None:
    config = yaml.safe_load(SOURCES.read_text())
    previous = _load_previous()
    source_defaults = {item["id"]: item.get("default_country") for item in config["sources"]}
    roles: list[Role] = []
    results: list[dict] = []

    for source in config["sources"]:
        print(f"Fetching {source['name']}...", flush=True)
        try:
            body = _fetch(source["url"])
            parsed = _parse(body, source)
            results.append({
                "id": source["id"],
                "name": source["name"],
                "page": source["page"],
                "ok": True,
                "rows": len(parsed),
                "error": "",
                "used_previous": False,
            })
            roles.extend(parsed)
        except Exception as error:
            fallback = [role for role in previous if role.source_id == source["id"]]
            results.append({
                "id": source["id"],
                "name": source["name"],
                "page": source["page"],
                "ok": False,
                "rows": len(fallback),
                "error": _short_error(error),
                "used_previous": bool(fallback),
            })
            roles.extend(fallback)

    kept, stats = select(roles, config, source_defaults)
    when = datetime.now(UTC)
    _write(kept, results, stats, when)
    README.write_text(render(kept, config, results, stats, when))
    print(f"Wrote {len(kept)} roles to {README}")
    for key in ("kept", "other company", "outside the countries we keep", "title is not new grad or intern software"):
        print(f"  {key}: {stats.get(key, 0)}")


def _parse(body: str, source: dict) -> list[Role]:
    if source["format"] == "simplify-json":
        return parse_simplify(json.loads(body), source)
    if source["format"] == "speedyapply-md":
        return parse_speedyapply(body, source)
    raise ValueError(f"Unknown format {source['format']}")


def _fetch(url: str) -> str:
    # The Simplify JSON feeds are large and slow to download from here.
    # One long attempt beats a short timeout that restarts the transfer.
    result = subprocess.run(
        ["curl", "-fL", "--retry", "1", "--retry-all-errors", "--retry-delay", "2", "-m", "600", "-A", "a2sv-top-tech-roles", url],
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        reason = detail[-1] if detail else f"curl exited {result.returncode}"
        raise RuntimeError(reason)
    return result.stdout.decode("utf-8")


def _load_previous() -> list[Role]:
    if not DATA.exists():
        return []
    raw = json.loads(DATA.read_text())
    return [Role.from_json(item) for item in raw.get("roles") or []]


def _write(roles: list[Role], results: list[dict], stats: Counter, when: datetime) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": when.isoformat(),
        "sources": results,
        "stats": dict(stats),
        "roles": [role.to_json() for role in sorted(roles, key=lambda role: (role.track, role.company, role.country_rank, role.title))],
    }
    DATA.write_text(json.dumps(payload, indent=2) + "\n")


def _short_error(error: Exception) -> str:
    text = str(error).strip() or type(error).__name__
    text = " ".join(text.split())
    if len(text) > 140:
        text = text[:137] + "..."
    return text
