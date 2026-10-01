# Future ideas

A running list of possible features for the app. First drafted 2026-10-01 from
a walkthrough of the live app at GW5 of 2026-27. Update the **Status** column as
ideas are picked up, finished or dropped, and add new ones at the bottom of the
right section. Ideas 17–29 were added later the same day.

**Effort** is how much work it takes. **Usefulness** is how much a visitor gains.
**Impact** is what it does for the project as a whole (credibility, return
visits, sharing). Each is Low / Medium / High.

**Status** values: `idea` · `planned` · `in progress` · `done` · `dropped`.
While an idea is being built on a branch, name the branch in its Status, e.g.
`in progress` (branch `price-history`), and set it to `done` when it reaches `main`.

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
| 18 | **Overnight price changes.** Who actually rose or fell last night, from `price_change_event` or the day-to-day diff in `data/history/`. The question managers check every morning, and a different one from forecast movers (#9). | Low | High | High | idea |
| 23 | **Rank context in the card**: "#3 predicted riser among midfielders", "top 10% of forecast moves". | Low | Medium | Low | idea |
| 27 | **Download the predictions**: a `/predictions.csv` route for today's forecasts, plus a link to the history in the repo. | Low | Medium | Medium | idea |

## Medium projects

| # | Idea | Effort | Usefulness | Impact | Status |
|---|---|---|---|---|---|
| 8 | **Prediction trend per player.** Sparkline in the drawer built from `data/history/` ("predicted £7.9m → £8.6m over 3 weeks"). | Medium | High | High | done |
| 9 | **"Movers this week" section.** Biggest changes in predicted price since the last snapshot(s). Same history data as #8. | Medium | High | High | done |
| 10 | **Send a current player to What if.** A "tweak this projection" button in the Price Watch drawer; What if currently only loads 2025-26 seasons. | Medium | High | Medium | idea |
| 11 | **Compare two players side by side** (prediction, interval, top drivers). | Medium | Medium | Medium | idea |
| 12 | **My team import** by FPL team ID, showing the squad's predicted next-season value. Most engaging, but the appeal is curiosity and pre-season planning more than weekly decisions. | Medium | Medium | High | idea |
| 13 | **Club summary**: average predicted change by club. | Low–Med | Low | Low | idea |
| 17 | **Phone layout for the transfer list.** The 7-column grid has no breakpoint below 1100px, so it can't fit on a phone. Collapse to player + forecast + move under ~640px. Most FPL browsing is on phones. | Low–Med | High | High | idea |
| 19 | **Watchlist.** Star players, kept in the visitor's browser (`dcc.Store` with local storage), with a "My watchlist" filter on the transfer list and movers. No login. | Low–Med | High | High | idea |
| 20 | **Luck check in the card.** Compare goals and assists with `expected_goals` and `expected_assists`: "his forecast leans on 6 goals from 2.1 xG, so expect it to fall if he cools off". Flags fragile forecasts without changing the model. | Medium | High | High | idea |
| 21 | **"What it would take."** The model is linear, so each extra goal adds a fixed amount: "each goal from here adds about £0.12m; 3 more puts him in the next price tier". Uses `config.PRICE_TIERS`. | Low–Med | High | Medium | idea |
| 22 | **Price-tier moves.** Players forecast to move up or down one of the user's tiers next season (e.g. "£5.5m → premium mid"). | Low–Med | Medium | Medium | idea |
| 24 | **FPL's own price-change pressure.** The snapshot saves `price_change_proj*` likelihoods that are never shown; a "likely to rise soon" badge. Caveat: one snapshot a day, taken after the night's changes, so it is a day old by evening. | Medium | High | Medium | idea |
| 25 | **Filters in the URL.** Search, position, club and sort in the address, so a view can be bookmarked or shared. Builds on the existing `?player=` deep link. | Low–Med | Medium | Medium | idea |
| 26 | **Earlier seasons in What if.** Data goes back to 2017-18 but What if only loads 2025-26. Picking an old season and seeing the model against what FPL actually charged builds credibility, per player rather than as accuracy tables. | Medium | Medium | Medium | idea |
| 28 | **Player search in the nav bar**, opening any player's card from any page. | Low–Med | Medium | Low | idea |
| 29 | **RSS feed of forecast movers** ("after GW6: biggest forecast moves"). Only worth it once #9 is merged. | Low–Med | Low | Low | idea |

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
4. #18, #17 and #20: overnight changes is cheap with data already recorded; the
   phone layout is the biggest real-world gap; the luck check is the most
   distinctive idea and leaves the model alone.

## Out of scope (already decided)

Not to be re-proposed unless the user reopens them: ELO or team-strength
features, blending projections toward last season, accuracy tables on
`/how-it-works`, and season min/max price bars (need a new data source first).
