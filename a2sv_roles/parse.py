"""Turn a source file into role rows. No filtering here."""

import re
from datetime import UTC, datetime

from a2sv_roles.model import Role

APPLY_HREF = re.compile(
    r'href="(https?://[^"]+)"[^>]*>\s*<img[^>]*alt="Apply"',
    re.IGNORECASE,
)
COMPANY_NAME = re.compile(r"<strong>([^<]+)</strong>", re.IGNORECASE)
AGE = re.compile(r"^(\d+)d$")
SALARY = re.compile(r"\$|/\s*hr|/\s*yr", re.IGNORECASE)


def parse_simplify(payload, source: dict) -> list[Role]:
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                payload = value
                break
    if not isinstance(payload, list):
        raise ValueError(f"{source['id']} did not return a list of roles")

    roles: list[Role] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        if row.get("active") is False or row.get("is_visible") is False:
            continue
        url = (row.get("url") or "").strip()
        title = (row.get("title") or "").strip()
        company = (row.get("company_name") or "").strip()
        if not url or not title or not company:
            continue
        posted = _posted(row.get("date_posted"))
        locations = row.get("locations") or []
        if isinstance(locations, str):
            locations = [locations]
        roles.append(
            Role(
                company=company,
                title=title,
                locations=[str(item).strip() for item in locations if str(item).strip()],
                url=url,
                track=source["track"],
                source_id=source["id"],
                source_name=source["name"],
                source_page=source["page"],
                posted_at=posted,
                age_days=_age_from(posted),
                sponsorship=_clean(row.get("sponsorship")),
                category=_clean(row.get("category")),
                terms=[str(item) for item in (row.get("terms") or [])],
            )
        )
    return roles


def parse_speedyapply(text: str, source: dict) -> list[Role]:
    roles: list[Role] = []
    for line in text.splitlines():
        if 'alt="Apply"' not in line or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        company_match = COMPANY_NAME.search(cells[0])
        apply_match = APPLY_HREF.search(line)
        if not company_match or not apply_match:
            continue
        apply_at = next(
            (index for index, cell in enumerate(cells) if 'alt="Apply"' in cell),
            None,
        )
        if apply_at is None or apply_at < 2:
            continue
        location_at = apply_at - 1
        if SALARY.search(cells[location_at]):
            location_at -= 1
        if location_at < 2:
            continue
        age_days = None
        last = cells[-1].strip()
        age_match = AGE.match(last)
        if age_match:
            age_days = int(age_match.group(1))
        roles.append(
            Role(
                company=company_match.group(1).strip(),
                title=cells[1],
                locations=[cells[location_at]],
                url=apply_match.group(1).strip(),
                track=source["track"],
                source_id=source["id"],
                source_name=source["name"],
                source_page=source["page"],
                age_days=age_days,
                sponsorship=None,
                category=None,
            )
        )
    return roles


def _posted(value) -> datetime | None:
    if not isinstance(value, (int, float)):
        return None
    seconds = float(value)
    if seconds > 10**12:
        seconds = seconds / 1000
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _age_from(posted: datetime | None) -> int | None:
    if posted is None:
        return None
    delta = datetime.now(UTC) - posted
    return max(0, delta.days)


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
