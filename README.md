# Protocol Valuation

Estimate a crypto protocol token's value from earnings, growth, competitive strength, risk and token supply.

Based on Jean-Yves Devloo's [Blocmates valuation framework](https://www.blocmates.com/articles/hyperliquid-stop-borrowing-multiples-start-deriving-them). The skill derives an earnings multiple from the protocol's economics and uses a discounted cash-flow model to produce bear, base and bull scenarios.

## Get started

1. Download and extract this package.
2. Give the complete `protocol-valuation` folder to an AI assistant that can read files, research the web and run Python. If your assistant supports custom skill uploads, use the skill ZIP with its folder structure intact.
3. Ask: **Use this skill to value [protocol name]. Read SKILL.md and follow its workflow.**
4. Review the assumptions before the assistant calculates the valuation.

Uploading only `SKILL.md` is not enough. Keep the scripts, reference documents and example inputs together. An assistant without code execution cannot run the bundled calculator.

## What you receive

- Bear, base and bull valuations, plus a probability-weighted estimate.
- A comparison with the current token price.
- The earnings growth needed to justify that price.
- Sensitivity analysis, sources, assumptions and confidence flags.
- Conditional valuations where a documented future mechanism could direct earnings to holders.

## What to provide

Start with the protocol name and official website. If available, add its documentation, recent fee-routing or unlock announcements, and daily fee, revenue and holder-revenue data. The assistant researches missing information and identifies anything it cannot verify.

## Requirements

- Python 3.8 or later; the calculator uses the Python standard library.
- An AI assistant with file access, code execution and web research capabilities.
- Sufficient verifiable data about the protocol and token.

The calculator itself runs locally and does not fetch market data. The assistant gathers the inputs separately. Public data sources are used; the package does not require private API credentials.

## Calculator commands

Run these from the extracted `protocol-valuation` folder after preparing protocol-specific facts according to `reference/FACTS.md`:

```bash
python3 scripts/engine.py defaults facts.json --md judgement.md --json inputs.json
```

Review the judgement table. Record confirmation and any changes in `overrides.json`, then regenerate the inputs:

```bash
python3 scripts/engine.py defaults facts.json --overrides overrides.json --md judgement.md --json inputs.json
python3 scripts/engine.py inputs.json --md valuation.md --json valuation.json
```

An override file containing only confirmation is `{"confirmed": true}`. See `SKILL.md` for the full research and validation workflow.

## Package contents

| Item | Purpose |
|---|---|
| `SKILL.md` | Workflow for the AI assistant |
| `scripts/` | Calculator, data-processing tools and required integrity check |
| `reference/` | Methodology, input schema and research guidance |
| `examples/` | Input examples and the integrity check's reference inputs; not current market data |
| `LICENSE` | MIT licence |

## Scope and limitations

This framework is designed for tokens with identifiable holder earnings, or a credible specified route to future holder earnings. It does not establish a universal value for every cryptocurrency. Results depend on the data and assumptions; missing data, short histories and conditional payments are flagged.

The bundled calculator is version 6.6.0. This distribution keeps its calculation code unchanged and presents the files needed for use.

Model output under stated assumptions, not financial advice.
