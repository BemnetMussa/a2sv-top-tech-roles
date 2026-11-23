import unittest
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from a2sv_roles.filter import match_company, matching_locations, select, title_ok
from a2sv_roles.model import Role
from a2sv_roles.parse import parse_speedyapply
from a2sv_roles.render import render

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "sources.yml").read_text())


def role(**kwargs) -> Role:
    base = dict(
        company="Amazon",
        title="Software Development Engineer - 2027",
        locations=["London, United Kingdom"],
        url="https://example.com/jobs/1",
        track="new_grad",
        source_id="speedyapply-intl-newgrad",
        source_name="speedyapply",
        source_page="https://example.com",
        age_days=3,
    )
    base.update(kwargs)
    return Role(**base)


class FilterTest(unittest.TestCase):
    def test_london_new_grad_stays(self):
        kept, stats = select([role()], CONFIG, {})
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].country, "United Kingdom")
        self.assertEqual(stats["kept"], 1)

    def test_sde_ii_without_early_career_drops(self):
        kept, _ = select([role(title="Software Dev Engineer II - AMZ10587293")], CONFIG, {})
        self.assertEqual(kept, [])

    def test_google_early_career_ii_stays(self):
        kept, _ = select([
            role(company="Google", title="Software Engineer II - Early Career", locations=["Dublin, Ireland"])
        ], CONFIG, {})
        self.assertEqual(len(kept), 1)

    def test_bloomberg_industry_group_is_not_bloomberg(self):
        self.assertIsNone(match_company("Bloomberg Industry Group", CONFIG))
        self.assertEqual(match_company("Bloomberg", CONFIG)["name"], "Bloomberg")

    def test_hyderabad_drops_and_london_in_a_split_row_stays(self):
        kept, _ = select([
            role(locations=["Hyderabad, India"]),
            role(url="https://example.com/jobs/2", locations=["London, United Kingdom", "Hyderabad, India"]),
        ], CONFIG, {})
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].kept_locations, ["London, United Kingdom"])

    def test_cambridge_massachusetts_is_the_united_states(self):
        found = matching_locations(["Cambridge, MA"], CONFIG, None)
        self.assertEqual(found[0][1], "United States")

    def test_support_intern_drops(self):
        self.assertFalse(title_ok("Cloud Support Associate Internship", "intern", CONFIG))

    def test_internal_tools_is_not_an_internship(self):
        self.assertTrue(title_ok("Software Engineer, Internal Tools - 2027", "new_grad", CONFIG))

    def test_same_amazon_job_from_two_links_is_one_row(self):
        short = role(
            title="Software Development Engineer – Early Career",
            url="https://amazon.jobs/en/jobs/10597803/software-development-engineer-amazon-leo",
            source_name="Simplify new grad",
        )
        full = role(
            title="Software Development Engineer - Amazon Leo - Early Career - 2027 - US",
            url="https://www.amazon.jobs/jobs/10597803/apply",
            source_name="speedyapply US new grad",
        )
        kept, stats = select([short, full], CONFIG, {})
        self.assertEqual(len(kept), 1)
        self.assertIn("Amazon Leo", kept[0].title)
        self.assertTrue(kept[0].url.endswith("/apply"))
        self.assertIn("Simplify new grad", kept[0].source_name)
        self.assertIn("speedyapply US new grad", kept[0].source_name)
        self.assertEqual(stats["duplicate link"], 1)

    def test_different_job_ids_on_the_same_board_both_stay(self):
        intern = role(
            track="intern",
            title="Software Engineering Intern - 2027",
            url="https://databricks.com/company/careers/open-positions/job?gh_jid=111",
        )
        new_grad = role(
            title="Software Engineer - New Grad - 2027",
            url="https://databricks.com/company/careers/open-positions/job?gh_jid=222",
        )
        kept, _ = select([intern, new_grad], CONFIG, {})
        self.assertEqual(len(kept), 2)

    def test_duplicate_url_is_kept_once_and_prefers_sponsorship(self):
        first = role(url="https://example.com/jobs/9?utm_source=x")
        second = role(url="https://example.com/jobs/9/", sponsorship="Offers Sponsorship", source_id="simplify-newgrad")
        kept, stats = select([first, second], CONFIG, {})
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].sponsorship, "Offers Sponsorship")
        self.assertEqual(stats["duplicate link"], 1)

    def test_old_role_drops(self):
        kept, _ = select([role(age_days=120)], CONFIG, {})
        self.assertEqual(kept, [])

    def test_past_summer_intern_drops_and_2027_stays(self):
        old = role(track="intern", title="Software Engineer Intern", terms=["Summer 2026"], url="https://example.com/a")
        current = role(track="intern", title="Software Engineer Intern", terms=["Summer 2027"], url="https://example.com/b")
        kept, _ = select([old, current], CONFIG, {})
        self.assertEqual([item.url for item in kept], ["https://example.com/b"])


class ParseTest(unittest.TestCase):
    def test_speedyapply_rows_with_and_without_salary(self):
        text = "\n".join([
            '| <a href="https://www.amazon.com"><strong>Amazon</strong></a> | Software Dev Engineer I | Santa Clara, CA | $186k/yr | <a href="https://www.amazon.jobs/jobs/1/apply"><img src="https://i.imgur.com/a.png" alt="Apply" width="70"/></a> | 2d |',
            '| <a href="https://databricks.com"><strong>Databricks</strong></a> | Software Engineer - New Grad - 2027 | London, United Kingdom | <a href="https://databricks.com/job/2"><img src="https://i.imgur.com/a.png" alt="Apply" width="70"/></a> | 17d |',
        ])
        source = {"id": "x", "name": "speedyapply", "page": "https://example.com", "track": "new_grad"}
        rows = parse_speedyapply(text, source)
        self.assertEqual(rows[0].locations, ["Santa Clara, CA"])
        self.assertEqual(rows[0].url, "https://www.amazon.jobs/jobs/1/apply")
        self.assertEqual(rows[0].age_days, 2)
        self.assertEqual(rows[1].locations, ["London, United Kingdom"])
        self.assertEqual(rows[1].title, "Software Engineer - New Grad - 2027")


class RenderTest(unittest.TestCase):
    def test_europe_comes_first_and_the_role_title_is_the_link(self):
        london = role(country="United Kingdom", country_rank=1, kept_locations=["London, United Kingdom"])
        seattle = role(
            title="Software Engineer I",
            url="https://example.com/jobs/2",
            locations=["Seattle, WA"],
            kept_locations=["Seattle, WA"],
            country="United States",
            country_rank=6,
        )
        page = render([london, seattle], CONFIG, [], Counter(), datetime(2026, 11, 22, 10, 31, tzinfo=UTC))
        self.assertLess(page.index("## Open outside the US"), page.index("## New grad"))
        self.assertIn("[Software Development Engineer - 2027](https://example.com/jobs/1)", page)
        self.assertIn("London, UK", page)


if __name__ == "__main__":
    unittest.main()
