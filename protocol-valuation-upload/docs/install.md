# Install

The skill is the folder [`skills/protocol-valuation`](../skills/protocol-valuation). Each [release](https://github.com/hoeeem/protocol-valuation/releases/latest) also ships it as `protocol-valuation.zip`, with a SHA-256 checksum. It needs an agent that can read `SKILL.md` and run standard-library Python 3.8 or later. It has no dependencies and needs no API keys.

## Claude (claude.ai, desktop and mobile apps)

1. Download `protocol-valuation.zip` from the latest release.
2. Go to **Customize → Skills**, click **+**, choose **Create skill**, then **Upload a skill**, and select the zip.
3. Switch the skill on.
4. Make sure code execution is enabled:
   - Free, Pro and Max: **Settings → Capabilities**.
   - Team and Enterprise: an owner enables it under **Organization settings → Plugins & skills**.

Then ask: *"Value HYPE."* ([Claude help: use skills](https://support.claude.com/en/articles/12512180-use-skills-in-claude))

## Claude Code

As a plugin from this repository:

```text
/plugin marketplace add hoeeem/protocol-valuation
/plugin install protocol-valuation@protocol-valuation
```

Or copy the folder as a personal skill:

```bash
git clone https://github.com/hoeeem/protocol-valuation
cp -r protocol-valuation/skills/protocol-valuation ~/.claude/skills/
```

## Grok Build (xAI's CLI)

```bash
git clone https://github.com/hoeeem/protocol-valuation
mkdir -p ~/.grok/skills && cp -r protocol-valuation/skills/protocol-valuation ~/.grok/skills/
```

It then appears as `/protocol-valuation`. Grok Build also reads skills installed for Claude Code. ([xAI docs: skills, plugins and marketplaces](https://docs.x.ai/build/features/skills-plugins-marketplaces))

## Grok Bot

See [grok-bot.md](grok-bot.md).

## Any other agent

Give the agent the folder (or the zip) and tell it to follow `SKILL.md`. Its first step is the self-test:

```bash
python3 protocol-valuation/scripts/selftest.py    # must print ALL CHECKS PASSED
```

## Check the download

```bash
sha256sum -c protocol-valuation.zip.sha256
```
