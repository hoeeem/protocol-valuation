#!/usr/bin/env python3
"""Shared input handling for every protocol-valuation script: JSON loading, number validation, daily-series
normalisation and a CLI wrapper that turns any input error into one clean line (exit code 2).
Set PV_DEBUG=1 to see full tracebacks."""
import json, math, os, sys
from datetime import date, datetime, timezone

UNPUBLISHED_MAX = 2   # up to 2 trailing complete days with no row = not yet published by the source (DefiLlama posts with a lag)

class InputError(ValueError):
    """Bad input: reported as one line, never a traceback."""

def iso_day(d):
    """Unix day number -> YYYY-MM-DD (UTC)."""
    return datetime.fromtimestamp(d * 86400, timezone.utc).date().isoformat()

def published_end(by_day, last):
    """Last day to measure a daily series to. `last` is the last complete UTC day by the clock.
    If the source has no row for the last 1-2 complete days, they are not published yet (DefiLlama posts a day late): end
    on the source's last row instead of counting them as zero. If the data stops earlier than that, the file is most likely
    out of date: the windows still end on its last row (zeros would understate earnings), with a flag to get a fresh copy.
    Returns (end_day, gap_days, flag or None)."""
    days = [d for d in by_day if d <= last]
    if not days: return None, None, None
    top = max(days); gap = last - top
    if 0 < gap <= UNPUBLISHED_MAX:
        return top, gap, (f"LATEST DAY NOT PUBLISHED: no data yet for the last {gap} complete day(s); windows end on "
                          f"{iso_day(top)}, the source's last day")
    if gap > UNPUBLISHED_MAX:
        return top, gap, (f"DATA OUT OF DATE: the data ends on {iso_day(top)}, {gap} days before the valuation date, so the "
                          "windows end there. Download or save a fresh copy before relying on them (if the source really has "
                          "nothing since then, revenue may have stopped)")
    return last, 0, None

def load_json(path):
    if not path or str(path).startswith("--"): raise InputError("missing file argument")
    if not os.path.exists(path): raise InputError(f"file not found: {path}")
    with open(path, encoding="utf-8") as fh:
        txt = fh.read()
    if not txt.strip(): raise InputError(f"{path} is empty")
    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        raise InputError(f"{path} is not valid JSON ({e.msg} at line {e.lineno}, column {e.colno})")

def write_text(path, text):
    with open(path, "w", encoding="utf-8") as fh: fh.write(text)

def write_json(path, obj, **kw):
    with open(path, "w", encoding="utf-8") as fh: json.dump(obj, fh, ensure_ascii=False, **kw)

def arg(argv, flag, required=False):
    """Value after a --flag; clean error if the flag is given without a value."""
    if flag not in argv:
        if required: raise InputError(f"{flag} is required")
        return None
    i = argv.index(flag)
    if i + 1 >= len(argv) or argv[i + 1].startswith("--"): raise InputError(f"{flag} needs a value")
    return argv[i + 1]

def num(v, name, lo=None, hi=None, lo_open=False, allow_none=False):
    """A finite real number (not a bool or a string), optionally bounded."""
    if v is None and allow_none: return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise InputError(f"{name} must be a number, got {v!r}")
    if not math.isfinite(v): raise InputError(f"{name} must be finite, got {v!r}")
    if lo is not None and (v <= lo if lo_open else v < lo): raise InputError(f"{name} must be {'>' if lo_open else '>='} {lo}, got {v!r}")
    if hi is not None and v > hi: raise InputError(f"{name} must be <= {hi}, got {v!r}")
    return float(v)

def iso_date(v, name):
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        raise InputError(f"{name} must be a date YYYY-MM-DD, got {v!r}")

def iso_ts(v, name):
    try:
        datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise InputError(f"{name} must be an ISO 8601 timestamp (e.g. 2026-10-14T09:46:49Z), got {v!r}")
    return v

def series(chart, name="series"):
    """Normalise a daily series [[ts, value], ...]: seconds or milliseconds timestamps (ms detected), numeric strings
    accepted, null values skipped, exact duplicate timestamps counted once (last wins). Returns (sorted pairs, notes)."""
    if not isinstance(chart, list):
        raise InputError(f"{name}: expected a list of [unix_ts, usd] pairs (or a dict with totalDataChart)")
    notes, by_ts, dupes, nulls = [], {}, 0, 0
    for i, p in enumerate(chart):
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise InputError(f"{name}: row {i} is not a [unix_ts, usd] pair: {p!r}")
        t, v = p
        if v is None: nulls += 1; continue
        try:
            t = float(t); v = float(v)
        except (TypeError, ValueError):
            raise InputError(f"{name}: row {i} has a non-numeric value: {p!r}")
        if not (math.isfinite(t) and math.isfinite(v)): raise InputError(f"{name}: row {i} is not finite: {p!r}")
        if t in by_ts: dupes += 1
        by_ts[t] = v
    if by_ts and sorted(by_ts)[len(by_ts) // 2] > 1e11:
        by_ts = {t / 1000.0: v for t, v in by_ts.items()}; notes.append("timestamps were in milliseconds; converted to seconds")
    if dupes: notes.append(f"{dupes} exact duplicate timestamp(s) counted once")
    if nulls: notes.append(f"{nulls} null value(s) skipped")
    return sorted((int(t), v) for t, v in by_ts.items()), notes

def cli(main, argv):
    """Run a CLI main(); any input error prints one line and exits 2. STOP findings keep their STOP: prefix."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception: pass
        return main(argv)
    except Exception as e:  # noqa: BLE001 - deliberate: no raw tracebacks for users
        if os.environ.get("PV_DEBUG"): raise
        msg = str(e).strip("'\"") or type(e).__name__
        if msg.startswith("STOP"): print(msg, file=sys.stderr)
        elif isinstance(e, InputError): print(f"ERROR: {msg}", file=sys.stderr)
        elif isinstance(e, KeyError): print(f"ERROR: missing field {msg!r} (see reference/FACTS.md)", file=sys.stderr)
        else: print(f"ERROR: {type(e).__name__}: {msg} (set PV_DEBUG=1 for details)", file=sys.stderr)
        sys.exit(2)
