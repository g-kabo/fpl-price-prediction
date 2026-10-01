# Future ideas

A running list of possible features for the app. First drafted 2026-10-01 from
a walkthrough of the live app at GW5 of 2026-27. Update the **Status** column as
ideas are picked up, finished or dropped, and add new ones at the bottom of the
right section.

**Effort** is how much work it takes. **Usefulness** is how much a visitor gains.
**Impact** is what it does for the project as a whole (credibility, return
visits, sharing). Each is Low / Medium / High.

**Status** values: `idea` · `planned` · `in progress` · `done` · `dropped`.

## Quick wins

| # | Idea | Effort | Usefulness | Impact | Status |
|---|---|---|---|---|---|
| 1 | **Early-season confidence warning.** At GW5, Groß projected to 344 points, which is exactly the training maximum. Show a "based on N GWs" badge or add a minimum-minutes filter so small-sample flukes don't fill the Model's XI. Keeps the current-form-only projection; it only shows the uncertainty. | Low | High | High | idea |
| 2 | **Injury/availability flag** in the transfer list and drawer, from `news` and `chance_of_playing_next_round` (already in the snapshot). | Low | Medium | Medium | idea |
| 3 | **Price-tier and minutes filters** on the transfer list, using `config.PRICE_TIERS`. | Low | Medium | Medium | idea |
| 4 | **Download the transfer list as CSV.** | Low | Medium | Low | idea |
| 5 | **Copy-link button in the player drawer.** Deep links already work (`board-deeplink`). | Low | Medium | Medium | idea |
| 6 | **Highlight the searched player on the market map**, and label the biggest outliers. | Low | Medium | Low | idea |
| 7 | **Keep-warm ping for Render**, a cron job (e.g. a GitHub Action) to remove the 30–60s cold start. | Low | Medium | High | idea |

## Medium projects

| # | Idea | Effort | Usefulness | Impact | Status |
|---|---|---|---|---|---|
| 8 | **Prediction trend per player.** Sparkline in the drawer built from `data/history/` ("predicted £7.9m → £8.6m over 3 weeks"). | Medium | High | High | idea |
| 9 | **"Movers this week" section.** Biggest changes in predicted price since the last snapshot(s). Same history data as #8. | Medium | High | High | idea |
| 10 | **Send a current player to What if.** A "tweak this projection" button in the Price Watch drawer; What if currently only loads 2025-26 seasons. | Medium | High | Medium | idea |
| 11 | **Compare two players side by side** (prediction, interval, top drivers). | Medium | Medium | Medium | idea |
| 12 | **My team import** by FPL team ID, showing the squad's predicted next-season value. Most engaging, but the appeal is curiosity and pre-season planning more than weekly decisions. | Medium | Medium | High | idea |
| 13 | **Club summary**: average predicted change by club. | Low–Med | Low | Low | idea |

## Bigger or longer-term

| # | Idea | Effort | Usefulness | Impact | Status |
|---|---|---|---|---|---|
| 14 | **Wider intervals for projected seasons.** The 95% range only covers model error, not the uncertainty of scaling a few games up to 38. Widen it when fewer games have been played. Backtest coverage is already slightly narrow (90.8%). | Med–High | Medium | High | idea |
| 15 | **Track-record page** once FPL sets the 2027-28 prices, scoring how the daily forecasts converged. Conflicts with the "no accuracy content in the app" decision, so it needs an explicit go-ahead. | Medium | Medium | High | idea |
| 16 | **Shareable player cards**: an Open Graph image per player link. | Med–High | Low | Medium | idea |

## Suggested order

1. #1 and #7: cheap fixes for the two weakest first impressions.
2. #8 and #9: the daily history is already being collected, and these give people a reason to come back.
3. #10: links the two pages together.

## Out of scope (already decided)

Not to be re-proposed unless the user reopens them: ELO or team-strength
features, blending projections toward last season, accuracy tables on
`/how-it-works`, and season min/max price bars (need a new data source first).
