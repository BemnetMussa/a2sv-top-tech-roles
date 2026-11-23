"""Render the page people actually open."""

from collections import Counter
from datetime import UTC, datetime, timedelta

from a2sv_roles.filter import sponsorship_label
from a2sv_roles.model import Role

TRACKS = (
    ("new_grad", "New grad"),
    ("intern", "Internships"),
)
PLACE_NAMES = (
    ("United Kingdom", "UK"),
    ("United States", "US"),
    ("The Netherlands", "Netherlands"),
)


def render(roles: list[Role], config: dict, source_results: list[dict], stats: Counter, when: datetime) -> str:
    local = when.astimezone(UTC) + timedelta(hours=3)
    stamp = local.strftime("%-d %b %Y, %H:%M EAT")
    by_track = {track: [role for role in roles if role.track == track] for track, _ in TRACKS}
    companies_with_roles = {role.company for role in roles}
    quiet = [company for company in config["companies"] if company["name"] not in companies_with_roles]
    europe = [role for role in roles if role.country and role.country != "United States"]

    lines = [
        "# A2SV top tech roles",
        "",
        "Software internships and new-grad jobs at the six companies where A2SV students have received the most offers. The page is rebuilt every day.",
        "",
        f"**{stamp}**",
        "",
        f"**{len(by_track['new_grad'])}** new grad · **{len(by_track['intern'])}** internships · **{len(europe)}** outside the US",
        "",
        "[Outside the US](#open-outside-the-us) · [New grad](#new-grad) · [Internships](#internships) · [No listing](#no-listing-this-week) · [How this list is made](#how-this-list-is-made)",
        "",
        "> [!TIP]",
        "> Most A2SV offers were in the UK, Germany, Ireland, Poland, and the Netherlands. Those links are first. Read the work-authorization line on the posting before you submit. This page does not know who sponsors.",
        "",
    ]
    lines.extend(_europe_section(europe, config))
    for track, heading in TRACKS:
        lines.extend(_track_section(heading, by_track[track], config))
    lines.extend(_quiet_section(quiet))
    lines.extend(_method(config, source_results, stats))
    lines.append("")
    return "\n".join(lines)


def _europe_section(roles: list[Role], config: dict) -> list[str]:
    lines = ["## Open outside the US", ""]
    if not roles:
        lines.append("No open link outside the United States passed the filter today.")
        lines.append("")
        return lines
    lines.append("The shorter list. Same jobs also appear under New grad or Internships.")
    lines.append("")
    lines.extend(_table(roles, config, show_track=True))
    return lines


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
        rows = grouped[company]
        lines.append(f"### {company} · {len(rows)}")
        lines.append("")
        lines.extend(_table(rows, config, show_track=False, show_company=False))
    return lines


def _table(roles: list[Role], config: dict, show_track: bool, show_company: bool = True) -> list[str]:
    rank = {company["name"]: company["rank"] for company in config["companies"]}
    ordered = sorted(
        roles,
        key=lambda role: (
            role.country_rank,
            rank.get(role.company, 99),
            0 if role.track == "new_grad" else 1,
            role.age_days if role.age_days is not None else 10**6,
            role.title,
        ),
    )
    show_sponsorship = any(sponsorship_label(role.sponsorship) != "—" for role in ordered)
    header = []
    if show_track:
        header.append("Track")
    if show_company:
        header.append("Company")
    header.extend(["Role", "Where", "Posted"])
    if show_sponsorship:
        header.append("Sponsorship")
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    for role in ordered:
        cells = []
        if show_track:
            cells.append("New grad" if role.track == "new_grad" else "Intern")
        if show_company:
            cells.append(role.company)
        cells.extend([
            f"[{_cell(role.title)}]({role.url})",
            _cell(_where(role)),
            _age(role.age_days),
        ])
        if show_sponsorship:
            cells.append(sponsorship_label(role.sponsorship))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _quiet_section(companies: list[dict]) -> list[str]:
    lines = ["## No listing this week", ""]
    if not companies:
        lines.append("Every target company has at least one open link above.")
        lines.append("")
        return lines
    names = _name_list(company["name"] for company in companies)
    lines.extend([
        f"{names} stay on this page because A2SV students have joined them. No public posting passed the filter today.",
        "",
    ])
    for company in companies:
        lines.append(f"- [{company['name']} careers]({company['careers']})")
    lines.append("")
    return lines


def _method(config: dict, source_results: list[dict], stats: Counter) -> list[str]:
    countries = ", ".join(country["name"] for country in config["countries"])
    companies = ", ".join(company["name"] for company in config["companies"])
    failed = [result for result in source_results if not result["ok"]]
    lines = [
        "## How this list is made",
        "",
        "<details>",
        "<summary>Sources, rules, and this run's counts</summary>",
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
        detail = "ok"
        if not result["ok"]:
            detail = "fetch failed, previous rows kept" if result.get("used_previous") else (result["error"] or "failed")
        lines.append(
            f"| [{result['name']}]({result['page']}) | {fetched} | {result['rows']} | {_cell(detail)} |"
        )
    if failed:
        lines.extend(["", "A failed source keeps yesterday's rows, so the page does not go blank."])
    lines.extend([
        "",
        "### What a row must pass",
        "",
        f"- **Company.** {companies}. A lookalike such as Bloomberg Industry Group is excluded.",
        f"- **Country.** {countries}. A US state code counts as the United States. Canada, India, and the other places listed in [`sources.yml`](sources.yml) do not.",
        "- **Title.** Software internship, or software new grad / early career / university / the class years 2026 and 2027. Senior titles, SDE II without an early-career label, apprenticeships, support, QA, sales, consulting, and PhD-only roles are removed.",
        f"- **Age.** Posted within the last {config['max_age_days']} days. Simplify rows marked inactive are removed.",
        "- **One opening.** The same job is kept once, even when two sources link to it differently. The more specific title is kept, and a direct apply link is preferred.",
        "",
        "Sponsorship is shown only when a source states it. This list does not guess, and it does not filter people out for needing a visa.",
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
        "The list does not apply for you, and it does not store referrals or names.",
        "",
        "This is an independent list made for A2SV students. It is not published by A2SV. The machine-readable copy is [`data/roles.json`](data/roles.json).",
        "",
        "</details>",
        "",
    ])
    return lines


def _where(role: Role) -> str:
    places = [_short_place(place) for place in (role.kept_locations or role.locations)]
    if not places:
        return role.country or "—"
    if len(places) == 1:
        return places[0]
    extra = len(places) - 1
    return f"{places[0]} · +{extra}"


def _short_place(place: str) -> str:
    for long_name, short_name in PLACE_NAMES:
        place = place.replace(long_name, short_name)
    return place


def _age(days: int | None) -> str:
    if days is None:
        return "—"
    if days <= 0:
        return "today"
    return f"{days}d"


def _name_list(names) -> str:
    items = list(names)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
