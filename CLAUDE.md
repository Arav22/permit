# permit

Claude Code plugin that explains every permission prompt in plain English, estimates real costs, auto-snapshots files, and coaches users on Claude Code best practices.

## Architecture

```
core/           Pure Python modules, no external deps
  analyzer.py      Classifies tools, parses bash, detects risk (safe/caution/danger)
  coach.py         15 anti-pattern detections + learning trajectory
  cost.py          Token estimation, smart model tips, pricing
  real_cost.py     Real cost from ~/.claude/stats-cache.json delta tracking
  discovery.py     10 contextual hints + 4 obsolescence patterns from catalog
  hints_catalog.json  JSON hints catalog (updateable without code changes)
  formatter.py     80-char ASCII box with ANSI colors, word-wrap
  patterns.py      Workflow recognition (explore, test-fix, deploy, etc.)
  tracker.py       Per-session history in /tmp/permit-session-*.json
  project_tracker.py  Cross-session .permit/project.json
  project_report.py   ASCII + HTML project reports
  report.py        Per-session report
  rollback.py      File snapshot + fuzzy restore
  config.py        Config loader (default: smart verbosity, auto model)

hooks/
  pretooluse.py    Main entry — analyze, cost, snapshot, coach, hints → box
  posttooluse.py   Record event to session + project tracker

skills/
  permit/          /permit slash command
  permit-rollback/ /permit-rollback interactive restore
  permit-screenshot/ /permit-screenshot capture screen
  permit-update/   /permit update — fetch latest hints catalog
```

## Common commands

```bash
python3 demo.py                   # See all features in action
python3 generate_screenshot.py    # Build docs/demo.html
pytest                            # Run 323 tests
pytest tests/test_coach.py -v    # Run specific module
bash install.sh                   # Install/update hooks in Claude Code
bash uninstall.sh                 # Remove hooks
```

## Key design decisions

- **stdlib only** — no pip install, works anywhere Python 3.10+ exists
- **smart verbosity default** — safe ops = compact 1 line, danger = full box
- **model auto-detect** — reads `CLAUDE_CODE_3P_SEEDED_SONNET_DEFAULT` and `ANTHROPIC_DEFAULT_SONNET_MODEL` for Bedrock
- **real cost from stats-cache** — reads `~/.claude/stats-cache.json` delta, not just estimates
- **JSON hints catalog** — `core/hints_catalog.json` updateable without code push
- **learning persists** — `~/.claude/permit-learning.json` tracks pattern frequency across sessions

## Config

Create `.claude/permit.config.json` in your project or home dir:

```json
{
  "verbosity": "smart",
  "cost": { "budget": 5.00 },
  "coach": { "enabled": true, "maxTipsPerBox": 2 }
}
```

## Tests

Add tests in `tests/test_X.py`. Each test file imports from `core/` directly.
Run `pytest tests/test_new.py -v` to test a single module.
