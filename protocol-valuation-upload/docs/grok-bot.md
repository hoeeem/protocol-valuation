# Run protocol-valuation in Grok Bot

[Grok Bot](https://docs.x.ai/grok-bot/overview) is xAI's always-on agent. Each Bot has a name, a job and memory, and works on a persistent cloud computer with a browser, a terminal and a filesystem. That makes it a good home for this skill. The Bot can open DefiLlama's raw data pages itself, run the Python scripts, keep reports in its files and re-run valuations on a schedule.

> **Status (October 2026).** Grok Bot's docs describe saving skills by asking the Bot, not dropping a `SKILL.md` folder in. So the method below has two parts. The Bot copies this repository onto its computer, then saves a private skill that points to it. These steps follow xAI's published docs but haven't been run end to end on Grok Bot yet. If a step doesn't match what you see, [open an issue](https://github.com/hoeeem/protocol-valuation/issues).

## What you need

- **Grok Bot access.** It comes with paid individual Cursor plans and Cursor Teams. You can also link a SuperGrok, SuperGrok Plus or SuperGrok Heavy subscription, or use the X Subscription bundle. Usage resets weekly and is counted in agent steps and tokens, and a full valuation takes many steps.
- **The desktop app** (macOS, Windows or Linux). Slash commands for skills are typed in the desktop composer.

## 1. Create a Bot for the job

Start a new Bot and describe its job in plain words:

```text
Your name is Token Analyst. Your job is to value crypto and DeFi tokens from the cash that reaches their holders,
using the protocol-valuation skill I'm about to install. You never give buy or sell advice: every result is
"model output under stated assumptions, not financial advice". Ask me before sending, posting or publishing anything.
```

## 2. Install the skill

Paste this into the Bot's chat:

```text
Install the protocol-valuation skill from https://github.com/hoeeem/protocol-valuation:

1. In a terminal on your computer, clone it to /workspace/protocol-valuation
   (git clone https://github.com/hoeeem/protocol-valuation /workspace/protocol-valuation).
   If git isn't available, download the latest release zip from
   https://github.com/hoeeem/protocol-valuation/releases/latest and unzip it to
   /workspace/protocol-valuation/skills/ instead.
2. Run: python3 /workspace/protocol-valuation/skills/protocol-valuation/scripts/selftest.py
   It must end with ALL CHECKS PASSED. If python3 is missing, install it, then run the self-test again.
3. Read /workspace/protocol-valuation/skills/protocol-valuation/SKILL.md in full.
4. Save a private skill called "protocol-valuation" with this description:
   "Value a crypto/DeFi token from the cash flows that reach holders, with a derived multiple. Use when I ask
   to value a protocol or token, estimate fair value, or find the growth the market is pricing in."
   and these instructions:
   "Follow /workspace/protocol-valuation/skills/protocol-valuation/SKILL.md exactly, step by step, starting
   with step 0 (ask me which protocol and what data I can send). Run the scripts by full path from
   /workspace/protocol-valuation/skills/protocol-valuation/scripts/ and keep each valuation's files in
   /workspace/valuations/<token>-<date>/. Always run the self-test first. If the folder is missing (for
   example after a computer update), clone the repository again before starting. Show me the judgement
   table and wait for my confirmation before valuing. Never present a result as advice."
5. Tell me the self-test result and confirm the skill is saved.
```

Keep the scripts in `/workspace`. Files there survive computer updates, but installed apps and packages don't. That's why the skill re-runs the self-test first, and reinstalls Python if it has to.

## 3. Check the skill is available

In the desktop composer, type `/` and look for **protocol-valuation**. If it isn't there:
1. Open **Connect apps** in the sidebar.
2. Select the connected count next to the title.
3. Turn the skill on for this Bot under **Private skills**.

Private skills are shared by all your Bots.

## 4. Run a valuation

```text
/protocol-valuation value HYPE
```

The Bot asks which protocol you mean (if the name is ambiguous) and what data you can send. Everything you could send is optional, because the Bot has its own browser and can open DefiLlama's raw data pages itself. It then:
1. builds the facts file;
2. shows you the judgement table and waits;
3. runs the engine;
4. writes the report, which leads with the valuation basis and input confidence.

Read the flags. An **EXTREME RESULT** or **LOW** confidence means the number needs the re-check the report describes before you use it anywhere.

## 5. Optional: a weekly re-valuation

Grok Bot can run routines while your computer is off. Ask the Bot that owns the job:

```text
Every Monday at 08:00 London time, re-run protocol-valuation for HYPE, PUMP and PONS using the confirmed
judgement inputs from their last valuation, save each report in /workspace/valuations/, and message me a
table of fair value vs price, input confidence and any new flags. Don't post or send anything else.
If a data source is unreachable, say so instead of guessing.
```

To manage routines, open the Bot, choose **View conversation details**, then **Routines**. From there you can test-run, pause or edit one. Schedules must be at least five minutes apart, with up to 50 routines per Bot. Keep anything that sends, posts or publishes behind your approval.

## 6. Optional: X

The docs say you can tag **@bot** in a post or reply on X once your X account is connected (not available in every region). The docs don't say whether other people's tags trigger your Bot. Treat it as a way for you to summon your own Bot. It isn't a public reply bot. Keep the approval rule on posting: a valuation posted in public should carry its confidence rating and the not-financial-advice line.

## Updating

```text
Update protocol-valuation: run git -C /workspace/protocol-valuation pull, then run the self-test and tell me
the version (python3 /workspace/protocol-valuation/skills/protocol-valuation/scripts/engine.py --version).
```

## Notes

- **Shared computer.** All your Bots share one computer, files and logins. This skill needs no logins or API keys, because DefiLlama and CoinGecko's public endpoints are enough, so there's nothing secret to store.
- **Attachments.** You can attach DefiLlama screenshots or saved data pages to the chat: up to 6 files per message, 25 MB each.
- **Sources:**
  - [Grok Bot overview](https://docs.x.ai/grok-bot/overview)
  - [Skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations)
  - [Working with Grok Bot](https://cursor.com/docs/grok-bot/work)
