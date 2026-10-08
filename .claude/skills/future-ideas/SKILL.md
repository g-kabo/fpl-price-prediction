---
name: future-ideas
description: Review the FPL Price Prediction site and maintain its feature backlog, docs/future-ideas.md. Use it to come up with new features, pages, model or pipeline improvements, or fixes, and to add them as scored, grouped, placed ideas. Every idea gets Effort, Usefulness and Impact scores, a report-or-app verdict, a branch-or-main call and links. Use this whenever the user asks for ideas, improvements, suggestions or "what should we build next", wants the app reviewed for gaps, asks to update, tidy or re-score the ideas doc, wants follow-ons or combinations of existing ideas, or reports something they've built that should change an idea's status, even if they never name the file.
---

# Future ideas

`docs/future-ideas.md` is the project's living backlog. It is read by the user
and by later sessions, and its numbers are referred to in conversation, commit
messages and code ("ideas #32 and #42"), so it has to stay accurate,
consistently scored and navigable. This skill covers reviewing the project for
new ideas and keeping that file in shape.

A session usually does one or more of:

1. **Reconcile**: bring statuses and wording up to date with what has shipped.
2. **Review and generate**: look at the site and the code, and come up with new
   ideas, fixes, follow-ons and combinations.
3. **Write**: add them to the doc, scored and placed.
4. **Check and report**: run the checks, then tell the user what changed.

Do whichever parts the request calls for; a "tidy the ideas doc" needs only
1, 3 and 4. Don't commit unless asked. When asked, the ideas doc is docs only,
so it goes straight to `main` after a `git pull`.

## 1. Reconcile first

The doc goes stale in two ways: ideas get built without their status changing,
and the architecture moves underneath the wording (the project went from a Dash
app on Render to a static GitHub Pages site in `web/`, which left rows talking
about `dcc.Store` and Render). Before adding anything:

- Read `CLAUDE.md`, all of `docs/future-ideas.md`, and the "Things the user has
  decided" list. Anything there, or in the doc's "Out of scope" section, is not
  to be re-proposed unless the user reopens it.
- Run `git log --oneline -30` and `git branch -a`. Commit messages often name
  ideas ("ideas #32 and #42"). For each idea touched since the last review, set
  its Status: `done`, `done (report: <path>)` for a report, `in progress
  (branch <name>)`, or `dropped (<reason>)`. Status values are `idea`, `planned`,
  `in progress`, `done` and `dropped`.
- Check `git stash list`. A stashed copy of the doc has happened before: 30
  ideas were stranded in a stash for days. If one exists, merge it before
  editing, never over it.
- Fix wording that names retired tech, files that no longer exist, or
  conditions that have since been met ("once #9 is merged" when #9 is live).

## 2. Review and generate

Ground every idea in what exists, because the doc's value is that its rows are
true. Check the claims behind a row (column names, file paths, numbers) by
reading the code or data, not from memory. If an idea depends on data, confirm
it's there: the snapshot is `data/live/players.csv`, the daily history is
`data/history/<season>/*.csv` (one row per player per day, with projections
and predictions), and `models/` holds the saved seasons and price history.

**Look at the site.** It's a static build of `web/` (Price Watch `index.html`,
What if `lab.html`, How it works `how-it-works.html`). Build and serve it as
CLAUDE.md describes, and walk the pages with a browser tool if one is
available. Note what a manager can't do, what is confusing, and what is
broken. Something broken is a **fix**: tell the user straight away, and add it
as an idea titled `**Fix: …**` in Quick wins unless they want it fixed now.

**Lenses that have produced good ideas here:**

- *The manager's questions.* Who will rise or fall, who's good value, is this
  form real, what about my players, what happened overnight?
- *Data already collected but unused.* E.g. `news`, `price_change_proj*`, xG,
  `n_clamped`.
- *Honesty about uncertainty.* Small samples, clamped inputs, in-sample
  comparisons, narrow intervals.
- *Follow-ons.* For each built or planned idea, what it makes cheap or possible
  next. Record these with a **From** column.
- *Inverses and complements.* "Plays every game" is the inverse of "misses N
  gameweeks".
- *Report instead of app.* Questions answered once a season, or only useful to
  the model's builder.
- *Model health.* Drift, bias, interval coverage, and the fact that the true
  answer only arrives once a year when FPL publishes prices.
- *Pipeline and season lifecycle.* The daily bot, the season rollover, the
  off-season, storage growth.
- *Phone, accessibility and sharing.*

Check new ideas against the existing ones, by meaning as well as title. If a
new thought extends an existing idea, add it to that row instead of creating a
near-duplicate.

## 3. Write

### Scores

Each score is `Low`, `Low–Med`, `Medium`, `Med–High` or `High` (with an en dash
`–`). A qualifier is allowed when the honest answer differs by audience, e.g.
`Low for visitors`.

- **Effort**: the work to build it, including checking it.
- **Usefulness**: what a visitor (an FPL manager) gains.
- **Impact**: what it does for the project as a whole: credibility, return
  visits, sharing, model or pipeline health.

Score honestly against the existing rows so the scale stays consistent. For
calibration from the doc:

| Idea | Effort | Usefulness | Impact |
|---|---|---|---|
| Download the transfer list as CSV | Low | Medium | Low |
| Early-season confidence warning | Low | High | High |
| Linked edits in What if | Low–Med | High | Medium |
| Player profile page | Medium | High | High |
| Model health report | Medium | Low for visitors | High |

### Placement

- **Number**: the next number after the highest in the doc. Never renumber:
  numbers are referenced elsewhere and are the link anchors.
- **Section**: by effort (Quick wins for `Low`; Medium projects for `Low–Med`
  and `Medium`; Bigger or longer-term above that), "Model health and pipeline"
  for model or operational ideas, or "Ideas sparked by others" (which has a
  **From** column) when the idea depends on or grows out of other ideas.
- **Row**: `| N | **Short title.** Concrete detail: what, where, from which
  data, the evidence (a number or an example player), and the caveat. | Effort
  | Usefulness | Impact | idea |`. A cell can't contain a `|` or a line break
  without breaking the table, so use "/" or "or" instead. Write references to
  other ideas as plain `#N`; the link script turns them into links.

### Report or app

Add the idea to the "Report or app?" table unless it's an app feature (the
default). Signs it belongs in a **report**: the answer changes once a season
or less, the audience is the model's builder, it's accuracy content (the user
keeps that off the app), or it's research that decides whether a feature is
worth building. **Report first, then decide** when the app version is only
safe if a check passes. **Hybrid** when a report computes something and the
app shows one sentence of it. **Tooling** for pipeline checks and plumbing.

### Branch or main

Every push to `main` rebuilds the live site, so add each new idea to exactly
one row of the "Branch or straight to main?" table. It needs a branch if any of
these hold:

1. It will take more than one sitting.
2. Its release time should be chosen (e.g. waiting for a gameweek).
3. It touches the model, the pipeline or the daily snapshot workflow.
4. It's an experiment that might be thrown away.

Otherwise it goes straight to `main`. Reports and scripts that don't change the
site go to `main`. Scheduled workflow changes go to `main` and are checked
with a manual run, because a schedule only runs from the default branch.

### Combinations

Look for ideas that are worth more built together: ones that share a screen, a
data source, a decision, or a dependency. Add or extend a row in the
"Combinations" table with what it becomes and why together, e.g. "Scenario
lab": several What if scenarios as one row of controls rather than four
features. Update existing combinations when a new idea joins one, and drop
ideas from a combination when they're dropped.

## 4. Check and report

Run, from the repo root, with the interpreter CLAUDE.md names:

```
"..\FPL Python Dashboard\.venv\Scripts\python.exe" docs/link_ideas.py
"..\FPL Python Dashboard\.venv\Scripts\python.exe" .claude/skills/future-ideas/scripts/check_ideas.py
```

`link_ideas.py` adds anchors and links and rebuilds the "Jump to" line, and is
safe to re-run. `check_ideas.py` reports duplicate numbers, invalid scores or
statuses, ideas missing from (or repeated in) the branch guide, combinations
and verdicts naming ideas that don't exist, broken links, and tables split by
a blank line. Fix anything it reports before finishing.

Then tell the user, briefly:

- **Statuses and wording changed** in reconciling, and why.
- **New ideas** as a table: number, title, Effort, Usefulness, Impact, and
  report/app where it isn't app.
- **Your top two or three picks** and the reason for each, plus any new or
  extended combinations.
- **Anything found broken**, first, if there was any.
- **That nothing is committed**, unless they asked.
