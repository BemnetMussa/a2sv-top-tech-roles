"""Render the page people actually open."""

from collections import Counter
from datetime import UTC, datetime, timedelta

from a2sv_roles.filter import sponsorship_label
from a2sv_roles.model import Role

TRACKS = (
    ("new_grad", "New grad"),
    ("intern", "Internships"),
)


def render(roles: list[Role], config: dict, source_results: list[dict], stats: Counter, when: datetime) -> str:
    local = when.astimezone(UTC) + timedelta(hours=3)
    stamp = local.strftime("%-d %b %Y, %H:%M EAT")
    by_track = {track: [role for role in roles if role.track == track] for track, _ in TRACKS}
    companies_with_roles = {role.company for role in roles}
    quiet = [company for company in config["companies"] if company["name"] not in companies_with_roles]

    lines: list[str] = [
        "# A2SV top tech roles",
        "",
        "Software engineering internships and new-grad jobs at the six companies where A2SV students have received the most offers. The page is rebuilt every day from public lists. Every rule below is the rule in [`sources.yml`](sources.yml).",
        "",
        f"**Last update:** {stamp}",
        "",
        "| | Open links |",
        "|---|---:|",
        f"| New grad | {len(by_track['new_grad'])} |",
        f"| Internships | {len(by_track['intern'])} |",
        f"| Companies with no open link | {len(quiet)} |",
        "",
        "## Start here",
        "",
        "1. Open **New grad** or **Internships**.",
        "2. Use the apply link. It goes to the employer.",
        "3. If a company is under **No public posting this week**, the sources had no role that passed the filter. Use that company's own careers page.",
        "",
    ]
    for track, heading in TRACKS:
        lines.extend(_track_section(heading, by_track[track], config))
    lines.extend(_quiet_section(quiet))
    lines.extend(_method(config, source_results, stats))
    lines.append("")
    return "\n".join(lines)


def _track_section(heading: str, roles: list[Role], config: dict) -> list[str]:
    lines = [f"## {heading}", ""]
    if not roles:
        lines.append("No open link passed the filter today.")
        lines.append("")
        return lines
    rank = {company["name"]: company["rank"] for company in config["companies"]}
    grouped: dict[str, list[Role]] = {}
    for role in roles:
        grouped.setdefault(role.company, []).append(role)
    for company in sorted(grouped, key=lambda name: rank.get(name, 99)):
        show_sponsorship = any(sponsorship_label(role.sponsorship) != "—" for role in grouped[company])
        lines.append(f"### {company}")
        lines.append("")
        header = ["Role", "Location"]
        if show_sponsorship:
            header.append("Sponsorship")
        header.extend(["Posted", "Apply", "Source"])
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        ordered = sorted(grouped[company], key=lambda role: (role.country_rank, role.age_days if role.age_days is not None else 10**6, role.title))
        for role in ordered:
            cells = [_cell(role.title), _cell(_locations(role.kept_locations))]
            if show_sponsorship:
                cells.append(sponsorship_label(role.sponsorship))
            cells.extend([_age(role.age_days), f"[Apply]({role.url})", _source(role)])
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return lines


def _quiet_section(companies: list[dict]) -> list[str]:
    lines = [
        "## No public posting this week",
        "",
        "These companies stay on the page because A2SV students have joined them. None of today's sources had an open role that passed the filter. Bloomberg in particular is often missing from the public lists.",
        "",
        "| Company | Official page |",
        "|---|---|",
    ]
    if not companies:
        lines.append("| — | Every target company has at least one open link above. |")
    for company in companies:
        lines.append(f"| {company['name']} | [Careers]({company['careers']}) |")
    lines.append("")
    return lines


def _method(config: dict, source_results: list[dict], stats: Counter) -> list[str]:
    countries = ", ".join(country["name"] for country in config["countries"])
    companies = ", ".join(company["name"] for company in config["companies"])
    lines = [
        "## How this list is made",
        "",
        "Company choice comes from the [A2SV impact report](https://a2sv.org/impact-report): Google, Bloomberg, Amazon, Goldman Sachs, Databricks, and Palantir. The countries are the ones in that same report.",
        "",
        "### Sources",
        "",
        "| Source | Fetched | Rows read | Result |",
        "|---|---|---:|---|",
    ]
    for result in source_results:
        fetched = "yes" if result["ok"] else "no"
        detail = result["error"] if not result["ok"] else "ok"
        if result.get("used_previous"):
            detail = "fetch failed, previous rows kept"
        lines.append(
            f"| [{result['name']}]({result['page']}) | {fetched} | {result['rows']} | {detail} |"
        )
    lines.extend([
        "",
        "### What a row must pass",
        "",
        f"- **Company.** {companies}. A lookalike such as Bloomberg Industry Group is excluded.",
        f"- **Country.** {countries}. A US state code counts as the United States. Canada, India, and the other places listed in `sources.yml` do not.",
        "- **Title.** Software internship, or software new grad / early career / university / the class years 2026 and 2027. Senior titles, SDE II without an early-career label, apprenticeships, support, QA, sales, consulting, and PhD-only roles are removed.",
        f"- **Age.** Posted within the last {config['max_age_days']} days. Simplify rows marked inactive are removed.",
        "- **One opening.** The same job is kept once, even when two sources link to it differently. The more specific title is kept, and a direct apply link is preferred.",
        "",
        "Sponsorship is shown only when a source states it. `—` means the source did not say. This list does not guess, and it does not filter people out for needing a visa.",
        "",
        "### This run",
        "",
        "| | Rows |",
        "|---|---:|",
    ])
    labels = [
        ("kept", "Kept"),
        ("other company", "Other company"),
        ("outside the countries we keep", "Outside the countries"),
        ("title is not new grad or intern software", "Title filtered out"),
        ("older than the age limit", "Older than the age limit"),
        ("not a software role", "Not software"),
        ("internship season already passed", "Past internship season"),
        ("duplicate link", "Duplicate link"),
    ]
    for key, label in labels:
        lines.append(f"| {label} | {stats.get(key, 0)} |")
    lines.extend([
        "",
        "### What this page does not do",
        "",
        "It does not apply for you. It does not store referrals or names. When a source fails, yesterday's rows from that source stay up and the table above says so, so the page does not go blank.",
        "",
        "This is an independent list made for A2SV students. It is not published by A2SV.",
        "",
        "The machine-readable copy of these rows is [`data/roles.json`](data/roles.json).",
    ])
    return lines


def _source(role: Role) -> str:
    name = _cell(role.source_name)
    if " · " in role.source_name:
        return name
    return f"[{name}]({role.source_page})"


def _locations(locations: list[str]) -> str:
    if len(locations) <= 3:
        return "; ".join(locations)
    extra = len(locations) - 3
    return "; ".join(locations[:3]) + f"; +{extra} more"


def _age(days: int | None) -> str:
    if days is None:
        return "—"
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day"
    return f"{days} days"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
