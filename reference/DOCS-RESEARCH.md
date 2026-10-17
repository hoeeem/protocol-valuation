# Docs and whitepaper research

Market data gives price and earnings. Almost everything else the method needs comes from the protocol's own documentation: the supply schedule, fee routing, buybacks and burns, governance, regulatory posture and exploit history. This file is the procedure for finding it, reading it and recording it. The output is an **evidence log** and a **supply schedule**, both feeding `facts.json`.

## 1. Find the official sources (and only those)

Phishing clones of docs sites are common, so establish the official domains before reading anything.

1. **CoinGecko** coin data `links`: `homepage`, `whitepaper` (often the docs site), `official_forum_url`, `repos_url`, `twitter_screen_name`, `blockchain_site` (explorers).
2. **DefiLlama** `api.llama.fi/protocol/<slug>`: `url`, `twitter`, `github`, `audit_links`.
3. A domain is official if it appears in either list, or is linked from a domain that does. A docs site found only through a search engine is not official until linked from one of these.
4. Links the user sent (SKILL.md step 0) are the place to start, under the same rule: check each against the two lists, and say so before using one that isn't on an official domain.

Record the official domains at the top of the evidence log.

## 2. Map the docs before reading

Docs sites are often JavaScript-rendered and come back empty from a plain fetch. Try in order:
- **`<docs-root>/llms.txt`** (GitBook, Mintlify, Docusaurus plugins): an index of every page with URLs. `llms-full.txt` is the whole site as text.
- **Markdown variants**: GitBook pages also serve at `<page-url>.md`.
- **`<site>/sitemap.xml`**.
- Search restricted to the domain: `site:<docs-domain> tokenomics`, `site:<docs-domain> fees`.
- Whitepaper PDFs: download and read the relevant sections (tokenomics, fee model, governance).
- If everything is JS-only and none of the above works, use a browser tool if one is available; otherwise record the gap.

From the index, list the pages that match section 3 before fetching any.

## 3. What to read, and which facts it feeds

| Look for (page titles / keywords) | Extract | facts.json field |
|---|---|---|
| Tokenomics, token, allocation, genesis, TGE, vesting, unlocks, distribution | Max supply; every allocation bucket with % / tokens, TGE unlock, cliff, vesting length, start date; emission pool and how much is already distributed | `supply_schedule.py` input → `supply.S0`, `vest`, `unissued` |
| Fees, fee distribution, revenue, protocol fee, fee switch | Where each fee goes (holders, buyback fund, LPs/vault, deployers/builders), percentages, whether automatic | `risk.routing`, `payout`; E0 cleaning (exclude deployer/builder/LP shares) |
| Buyback, burn, assistance fund, treasury, revenue share, staking rewards | Buyback mechanism (automatic vs discretionary), whether bought tokens are burned or held, any stated count or rate, commitment length | `supply.buyback` (`mode`, `tokens_per_yr`, `years`, `continue_after`), `burned`/`retired` buckets |
| Staking, rewards, emissions, inflation | Reward rate and source (new emissions vs fees), amount emitted to date | emission bucket `distributed`; `supply.self_sustaining` |
| Governance, DAO, proposals, upgrades, multisig, admin, timelock, validators | Who can change rules or upgrade contracts, timelock length, validator/signer count, legal entity or foundation | `risk.concentrated_control`, `team_can_change_rules`, `no_legal_wrapper`, `alignment_offset` |
| Terms, legal, restricted jurisdictions, KYC, compliance | KYC requirement, US access policy, licences, enforcement actions | `risk.reg_class`, `formal_action` |
| Audits, security, bug bounty, incidents, post-mortem | Audit coverage, exploits and losses (≥ $10m counts), dates | `risk.major_exploit`, rubric `major_exploit` |
| Collateral, deposits, treasury, stablecoin, yield | Whether yield on user deposits or treasury reaches holders, and how much | `earnings.other` (E0_other) |
| Architecture, chain, bonds, locks, slashing | Own chain or unique tech; bonded/locked participation | rubric `own_chain_or_unique_tech`, `bond_lock`, `supplier_dependency` |
| Launch, mainnet, history | First revenue / launch date | `risk.launch_date` |

## 3a. Map where the money goes, then find protocol revenue

Before any number, write the money map (it goes into the report):

| Question | Answer, with a source |
|---|---|
| What do users pay for? | e.g. trading fees, borrow interest, launch fees |
| Who receives each part? | liquidity providers / lenders, builders and front-ends, the treasury, token holders |
| What comes out before holders? | operating costs, incentives paid from revenue |
| What share reaches holders, and how? | `benefit_form`: buyback and burn, buyback and hold, distribution, staking distribution |
| Is it automatic, discretionary or only proposed? | the routing class (METHOD.md §3) |
| Must holders stake or lock to receive it? | `access`: all holders, stakers only, lockers only |

Record the last three in `facts.rights` and `risk.routing`. A token whose holders receive none of the money, with no stated mechanism that would change that, can't be valued from cash flows with this method: say so.

### Finding protocol revenue

DefiLlama gives three series for the parent slug: `dailyFees`, `dailyRevenue` and `dailyHoldersRevenue`. Fetch all three every time and run `scripts/revenue_stack.py` (SKILL.md step 3). Then confirm with the protocol's own sources:

| Check | Where | What it settles |
|---|---|---|
| Where each fee goes | Docs fee page; DefiLlama `methodology` text for each child protocol | Whether DefiLlama's revenue and holder revenue match the real routing; the documented holder share for `revenue_stack.py --holder-share` (e.g. "80% of protocol fees" buys back and burns) |
| The fee-switch proposal | Governance forum, Snapshot or Tally, or on-chain proposals | `take_rate`, which pools, chains or products, start date, any staking requirement |
| DAO operating costs | Forum budget threads, service-provider proposals, treasury reports | `--expenses` for the distributable base |
| Incentives paid out of revenue | Forum, treasury reports | `--incentives` (only cash or treasury-asset incentives; token emissions go in the supply schedule) |
| Treasury inflows | Treasury address on the explorer (from the docs) | A sanity check when DefiLlama doesn't track revenue |

Rules:
- If DefiLlama and the docs disagree by more than 20%, use the lower figure, bracket with the higher, and record both in the evidence log.
- If DefiLlama doesn't track revenue at all, build it from the docs' fee split × DefiLlama fees, and flag it.
- Never use past buyback amounts as the fee-switch base when the protocol's revenue is larger. Buybacks are a policy choice; revenue is what a switch could route.
- Compare the measured holder share (the stack's `holders_of_revenue`) with the documented share. If they differ by more than 20%, say which one the revenue check uses and why (a buyback that runs behind revenue raises the measured share in a falling market; revenue DefiLlama doesn't track lowers the documented one's fit).

## 4. When the docs are silent

Docs regularly omit tokenomics, team vesting and legal posture. Fall back down this list, and record which tier each fact came from:

1. Official docs and whitepaper
2. Official blog, governance forum, on-chain proposals, foundation site, posts from the protocol's official X account
3. On-chain data: explorers, token holder pages, contract state
4. Unlock trackers: tokenomist.ai, DefiLlama unlocks (`defillama.com/unlocks/<slug>`), tokenomics.com
5. Research reports and exchange academies
6. News

**User-supplied material** (screenshots, CSV downloads, saved API files, links) takes the tier of where it came from: a saved `api.llama.fi` response or a DefiLlama CSV counts as DefiLlama itself; a screenshot counts as its page, read by eye. Record it as `user-supplied (<what>, <date>)` and cross-check a screenshot's figures wherever another source is reachable.

**Conflicts.** Newer official beats older official; official beats third-party; on-chain beats docs for balances. If two credible sources disagree by more than 10% on a supply number, use the higher tier as primary, run the other as a bracket and flag it. Trackers' "circulating" often excludes vested-unclaimed, staked or foundation-held tokens: never use it as S0 when a schedule exists (D15).

**Unknowns.** A boolean you cannot evidence stays `false` and goes on the gaps list. Never infer a vesting schedule ("23.8% over 24 months") that no source states; if a source says a schedule is non-linear or undisclosed, model the closest stated terms, set `schedule_uncertain: true` and show a bracket.

## 5. Supply schedule

Write the allocation as `schedule.json` (format in `scripts/supply_schedule.py`) and run:
```
python3 scripts/supply_schedule.py schedule.json --md supply.md --json supply_out.json
```
Bucket types: `vesting` (TGE %, cliff, linear months, start date), `unlocked`, `emission` (unminted pool, with `distributed` to date), `discretionary` (foundation/treasury inventory without a schedule: goes to the unissued pool by default), `retired` (held by a buyback fund, not resaleable). Give `burned` or `total_supply` so burns are removed, and `tracker_circulating` to reconcile.

The script checks the buckets sum to max supply, flags uncertain schedules, unstated emission distributions and a >10% gap to the tracker. Copy `S0`, `vest` and `unissued` into `facts.json → supply` and set `fallback_circulating: false`.

## 6. Evidence log

Keep `evidence.md` alongside `facts.json`. One row per fact used:

| Field | Value | Quote (< 15 words) | URL | Accessed (ISO) | Tier |
|---|---|---|---|---|---|
| risk.routing | mechanical | "converts trading fees to HYPE in a fully automated manner" | docs …/trading/fees.md | 2026-10-14T14:10Z | 1 |

Every documented boolean in `facts.json` cites a row. The report includes the log (or its key rows) and the gaps list.

## 7. Red flags to report even if they don't change a number
- Admin keys or a multisig that can upgrade contracts or mint without a timelock.
- Fee routing that governance can switch off (alignment is then not `mechanical`).
- Team or investor vesting described as "not linear", "discretionary" or undisclosed.
- Large foundation/treasury inventory without a release policy.
- Docs pages last updated more than 12 months ago on fast-moving topics (fees, tokenomics).
