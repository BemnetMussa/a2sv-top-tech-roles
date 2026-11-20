"""Shared types. Kept small so the filter can be tested without the network."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Role:
    company: str
    title: str
    locations: list[str]
    url: str
    track: str
    source_id: str
    source_name: str
    source_page: str
    posted_at: datetime | None = None
    age_days: int | None = None
    sponsorship: str | None = None
    category: str | None = None
    terms: list[str] = field(default_factory=list)
    # Filled by the country filter. Parallel to the locations we keep.
    kept_locations: list[str] = field(default_factory=list)
    country: str | None = None
    country_rank: int = 99

    def to_json(self) -> dict:
        return {
            "company": self.company,
            "title": self.title,
            "locations": self.kept_locations or self.locations,
            "url": self.url,
            "track": self.track,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_page": self.source_page,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "age_days": self.age_days,
            "sponsorship": self.sponsorship,
            "category": self.category,
            "terms": self.terms,
            "country": self.country,
            "country_rank": self.country_rank,
        }

    @classmethod
    def from_json(cls, raw: dict) -> "Role":
        posted = raw.get("posted_at")
        return cls(
            company=raw["company"],
            title=raw["title"],
            locations=list(raw.get("locations") or []),
            url=raw["url"],
            track=raw["track"],
            source_id=raw["source_id"],
            source_name=raw["source_name"],
            source_page=raw.get("source_page") or "",
            posted_at=datetime.fromisoformat(posted) if posted else None,
            age_days=raw.get("age_days"),
            sponsorship=raw.get("sponsorship"),
            category=raw.get("category"),
            terms=list(raw.get("terms") or []),
            kept_locations=list(raw.get("locations") or []),
            country=raw.get("country"),
            country_rank=raw.get("country_rank") or 99,
        )
