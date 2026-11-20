"""Decide which rows an A2SVian should see."""

import re
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urlsplit

from a2sv_roles.model import Role

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "IA", "ID",
    "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT",
    "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY", "DC",
}
STATE_RE = re.compile(r",\s*(" + "|".join(sorted(US_STATES)) + r")\b")

SPONSORSHIP_LABELS = {
    "offers sponsorship": "Yes",
    "does not offer sponsorship": "No",
    "u.s. citizenship is required": "US citizenship",
    "other": "—",
}


def select(roles: list[Role], config: dict, source_defaults: dict[str, str | None]) -> tuple[list[Role], Counter]:
    """Return roles that pass every rule, plus a count of why rows were dropped."""
    stats: Counter = Counter()
    kept: list[Role] = []
    for role in roles:
        reason = _reject(role, config, source_defaults.get(role.source_id))
        if reason:
            stats[reason] += 1
            continue
        stats["kept"] += 1
        kept.append(role)
    return _dedupe(kept, stats), stats


def match_company(name: str, config: dict) -> dict | None:
    text = name.strip().lower()
    for company in config["companies"]:
        for excluded in company.get("exclude") or []:
            if text == excluded.lower() or text.startswith(excluded.lower() + " "):
                return None
        for alias in company["aliases"]:
            alias_text = alias.lower()
            if text == alias_text or text.startswith(alias_text + " "):
                return company
    return None


def title_ok(title: str, track: str, config: dict) -> bool:
    text = title.lower()
    rules = config["title"]
    if any(word in text for word in rules["drop_words"]):
        return False
    if any(re.search(pattern, text) for pattern in rules["drop_patterns"]):
        return False
    if not any(word in text for word in config["software_title_any"]):
        return False
    if any(re.search(pattern, text) for pattern in rules["level_ii_patterns"]):
        if not any(phrase in text for phrase in rules["level_ii_ok_if"]):
            return False
    if track == "intern":
        return _is_intern_title(text, rules)
    if _is_intern_title(text, rules):
        return False
    if any(word in text for word in rules["new_grad_any"]):
        return True
    return any(re.search(pattern, text) for pattern in rules["new_grad_patterns"])


def matching_locations(locations: list[str], config: dict, default_country: str | None) -> list[tuple[str, str, int]]:
    """Locations that sit in an allowed country. Each item is text, country, rank."""
    found: list[tuple[str, str, int]] = []
    for location in locations:
        match = _one_location(location, config)
        if match:
            found.append((location, match["name"], match["rank"]))
    if found:
        return found
    if default_country and _is_bare_remote(locations):
        country = next(item for item in config["countries"] if item["name"] == default_country)
        return [("Remote", country["name"], country["rank"])]
    return []


def _is_intern_title(text: str, rules: dict) -> bool:
    if re.search(r"\bintern(ship|ships)?\b", text):
        return True
    return any(word in text for word in rules["intern_any"] if word != "intern")


def sponsorship_label(value: str | None) -> str:
    if not value:
        return "—"
    return SPONSORSHIP_LABELS.get(value.strip().lower(), "—")


def _reject(role: Role, config: dict, default_country: str | None) -> str | None:
    company = match_company(role.company, config)
    if company is None:
        return "other company"
    if role.age_days is not None and role.age_days > config["max_age_days"]:
        return "older than the age limit"
    if role.category and role.category in config["drop_categories"]:
        return "not a software role"
    if not title_ok(role.title, role.track, config):
        return "title is not new grad or intern software"
    if _past_intern_only(role, config):
        return "internship season already passed"
    matches = matching_locations(role.locations, config, default_country)
    if not matches:
        return "outside the countries we keep"
    matches.sort(key=lambda item: item[2])
    role.company = company["name"]
    role.kept_locations = [item[0] for item in matches]
    role.country = matches[0][1]
    role.country_rank = matches[0][2]
    return None


def _past_intern_only(role: Role, config: dict) -> bool:
    if role.track != "intern" or not role.terms:
        return False
    terms = {term.strip() for term in role.terms if term and term.strip().upper() != "N/A"}
    if not terms:
        return False
    if any("2027" in term or "2028" in term for term in terms):
        return False
    past = set(config["past_intern_terms"])
    return terms <= past


def _one_location(location: str, config: dict) -> dict | None:
    text = location.lower()
    for skipped in config["skip_locations_containing"]:
        if skipped in text:
            return None
    united_states = next(item for item in config["countries"] if item["name"] == "United States")
    if united_states.get("states") and STATE_RE.search(location):
        return united_states
    for country in config["countries"]:
        if country["name"] == "United States":
            continue
        if _country_hit(text, country):
            return country
    if _country_hit(text, united_states):
        return united_states
    return None


def _country_hit(text: str, country: dict) -> bool:
    if any(token in text for token in country.get("any") or []):
        return True
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in country.get("words") or [])


def _is_bare_remote(locations: list[str]) -> bool:
    if not locations:
        return False
    return all(re.fullmatch(r"remote(?:\s*,\s*remote)?", item.strip(), re.IGNORECASE) for item in locations)


def _dedupe(roles: list[Role], stats: Counter) -> list[Role]:
    by_job: dict[str, Role] = {}
    for role in roles:
        key = _job_key(role.url)
        current = by_job.get(key)
        if current is None:
            by_job[key] = role
            continue
        stats["duplicate link"] += 1
        stats["kept"] -= 1
        by_job[key] = _merge(current, role)
    return list(by_job.values())


def _merge(current: Role, incoming: Role) -> Role:
    winner, other = (current, incoming) if _more_specific(current, incoming) else (incoming, current)
    names: list[str] = []
    for part in f"{winner.source_name} · {other.source_name}".split(" · "):
        if part and part not in names:
            names.append(part)
    winner.source_name = " · ".join(names)
    if "/apply" in other.url and "/apply" not in winner.url:
        winner.url = other.url
    if sponsorship_label(winner.sponsorship) == "—" and sponsorship_label(other.sponsorship) != "—":
        winner.sponsorship = other.sponsorship
    if len(other.kept_locations) > len(winner.kept_locations):
        winner.kept_locations = other.kept_locations
        winner.country = other.country
        winner.country_rank = other.country_rank
    return winner


def _more_specific(left: Role, right: Role) -> bool:
    if len(left.title) != len(right.title):
        return len(left.title) > len(right.title)
    return "/apply" in left.url


def _job_key(url: str) -> str:
    """One opening can be linked two ways. Treat those as the same row."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    amazon = re.search(r"/jobs/(\d+)", path)
    if host.endswith("amazon.jobs") and amazon:
        return f"amazon:{amazon.group(1)}"
    lever = re.search(r"/([^/]+)/([0-9a-f-]{36})", path)
    if host.endswith("lever.co") and lever:
        return f"lever:{lever.group(1)}:{lever.group(2)}"
    query = dict(parse_qsl(parts.query))
    greenhouse = query.get("gh_jid") or query.get("token")
    if greenhouse and ("greenhouse.io" in host or "gh_jid" in query or "token" in query):
        return f"greenhouse:{greenhouse}"
    google = re.search(r"/results/(\d+)", path)
    if host.endswith("google.com") and google:
        return f"google:{google.group(1)}"
    return _url_key(url)


def _url_key(url: str) -> str:
    """Same apply link, ignoring tracking parameters. Job ids in the query stay."""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"gh_src", "src"}
    ]
    query.sort()
    path = parts.path.rstrip("/") or "/"
    suffix = f"?{urlencode(query)}" if query else ""
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}{suffix}"
