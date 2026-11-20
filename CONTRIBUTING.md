# Contributing

The README is generated. Do not edit it by hand.

Change [`sources.yml`](sources.yml) when a company alias, a city, a title rule, or a source URL is wrong. Then:

```bash
pip install -r requirements.txt
python3 -m unittest discover tests
python3 -m a2sv_roles
```

Open a pull request that says, in a sentence or two, what was wrong and what the new rule keeps or drops.

Pull requests that add referrals, people's names, or hand-written rows in the README will not be merged. The list is apply links and the rules that chose them.
