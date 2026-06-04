#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# ///

"""Display ChatGPT conversations from exported JSON files."""

import json
import os
import re
import sys
import shutil
import unicodedata
from datetime import datetime


def display_width(text: str) -> int:
    """Measure display width accounting for double-width characters and emoji."""
    w = 0
    for ch in text:
        ea = unicodedata.east_asian_width(ch)
        if ea in ('F', 'W'):
            w += 2
        else:
            w += 1
    # Also handle emoji sequences (ZWJ, variation selectors, skin tones, flags)
    # These are already counted above; subtract overcount for zero-width joiners
    for ch in text:
        if unicodedata.category(ch) in ('Mn', 'Cf') and ord(ch) not in (0x200D,):
            # Combining marks and format chars (except ZWJ) add nothing to width
            w -= 1
    return max(w, 0)


def load_conversation(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def walk_thread(mapping: dict) -> list[dict]:
    """Walk the conversation tree from root to leaf."""
    root = None
    for node in mapping.values():
        if node.get("parent") is None:
            root = node
            break
    if not root:
        return []

    thread = [root]
    current = root
    while current.get("children") and len(current["children"]) > 0:
        next_id = current["children"][0]
        next_node = mapping.get(next_id)
        if not next_node:
            break
        thread.append(next_node)
        current = next_node
    return thread


def is_hidden(msg: dict | None) -> bool:
    if not msg:
        return True
    meta = msg.get("metadata", {})
    if meta.get("is_visually_hidden_from_conversation"):
        return True
    if msg.get("weight") == 0:
        return True
    content = msg.get("content", {})
    parts = content.get("parts", [])
    if not parts or all(p == "" for p in parts):
        return True
    if content.get("content_type") == "model_editable_context":
        return True
    return False


import re
import json as _json

# genui widgets: \ue200 genui \ue202 {JSON} \ue201
_GENUI_OPEN  = '\ue200'
_GENUI_MID   = '\ue202'
_GENUI_CLOSE = '\ue201'
_GENUI_MARKER = _GENUI_OPEN + 'genui' + _GENUI_MID


def _extract_genui_json(text: str, start: int) -> tuple[str, int] | None:
    """Extract balanced JSON object starting at `start`. Returns (json_str, end_pos)."""
    if start >= len(text) or text[start] != '{':
        return None
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1], i+1
        i += 1
    return None


def _parse_genui_jobs(text: str) -> list[str]:
    """Extract and render jobs_widget blocks from genui markup."""
    cards = []
    pos = 0
    while True:
        idx = text.find(_GENUI_MARKER, pos)
        if idx == -1:
            break
        json_start = idx + len(_GENUI_MARKER)
        result = _extract_genui_json(text, json_start)
        if not result:
            pos = json_start
            continue
        json_str, end = result
        # skip closing U+E201 if present
        if end < len(text) and text[end] == _GENUI_CLOSE:
            end += 1
        pos = end
        try:
            blob = _json.loads(json_str)
            widget = blob.get("jobs_widget")
            if widget:
                title = widget.get("title", "???")
                company = widget.get("company", "")
                location = widget.get("location", "")
                salary = widget.get("salary", "")
                apply_url = widget.get("apply_url", "")
                role = widget.get("role_summary", "")
                lines = [f"🏢  {title}"]
                if company:
                    lines.append(f"    {company}  ·  {location}")
                if salary and salary not in ("15 hours ago", "18 hours ago", "22 hours ago"):
                    lines.append(f"    💰 {salary}")
                if role:
                    lines.append(f"    {role}")
                if apply_url:
                    lines.append(f"    🔗 {apply_url}")
                cards.append("\n".join(lines))
        except (_json.JSONDecodeError, KeyError):
            pass
    return cards


def extract_text(parts: list) -> str:
    """Extract plain text from message parts, replacing genui widgets with clean cards."""
    pieces = []
    for p in parts:
        if not isinstance(p, str):
            continue
        # Parse job cards first (before we strip markers)
        cards = _parse_genui_jobs(p)
        # Strip all genui markup using balanced-brace extraction
        cleaned = p
        # Remove \ue200 genui \ue202 {balanced_json} \ue201 blocks
        pos = 0
        result_parts = []
        while True:
            idx = cleaned.find(_GENUI_MARKER, pos)
            if idx == -1:
                result_parts.append(cleaned[pos:])
                break
            result_parts.append(cleaned[pos:idx])
            json_start = idx + len(_GENUI_MARKER)
            extracted = _extract_genui_json(cleaned, json_start)
            if extracted:
                _, end = extracted
                if end < len(cleaned) and cleaned[end] == _GENUI_CLOSE:
                    end += 1
                pos = end
            else:
                # Couldn't parse — skip past this marker
                pos = json_start
        cleaned = ''.join(result_parts)
        # Strip genui_run lines
        cleaned = re.sub(r'genui_run result of .*?\n\n?', '', cleaned)
        # Strip any leftover private-use chars
        cleaned = cleaned.replace(_GENUI_OPEN, '').replace(_GENUI_MID, '').replace(_GENUI_CLOSE, '')
        # Remove leftover "genui" word
        cleaned = re.sub(r'\bgenui\b', '', cleaned)
        # Collapse multiple blank lines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            pieces.append(cleaned)
        for card in cards:
            pieces.append(card)
    return "\n\n".join(pieces).strip()


# ── display helpers ──────────────────────────────────────────────

TERM = shutil.get_terminal_size()
WIDTH = min(TERM.columns, 90)

ROLE_STYLE = {
    "user":      ("🧑 You",         "left"),
    "assistant": ("🤖 ChatGPT",     "left"),
    "tool":      ("🔧 Tool",        "left"),
    "system":    ("⚙️  System",     "center"),
}

BOX_TOP    = "╭" + "─" * (WIDTH - 2) + "╮"
BOX_MID    = "├" + "─" * (WIDTH - 2) + "┤"
BOX_BOT    = "╰" + "─" * (WIDTH - 2) + "╯"


def box_line(text: str = "", align: str = "left") -> str:
    """Return text padded inside box borders."""
    inner_width = WIDTH - 4  # one space + border on each side
    visible = display_width(text)
    if align == "right":
        pad = inner_width - visible
        return "│ " + (" " * max(pad, 0)) + text + " │"
    elif align == "center":
        pad_left = (inner_width - visible) // 2
        pad_right = inner_width - visible - pad_left
        return "│ " + (" " * max(pad_left, 0)) + text + (" " * max(pad_right, 0)) + " │"
    else:
        # left
        return "│ " + text + (" " * max(inner_width - visible, 0)) + " │"


def wrap_text(text: str, width: int) -> list[str]:
    """Word-wrap text to a given display width."""
    if not text:
        return [""]
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            cur_w = display_width(current)
            word_w = display_width(word)
            if cur_w + word_w + (1 if current else 0) > width:
                lines.append(current.rstrip())
                current = word
            else:
                current += " " + word if current else word
        lines.append(current)
    return lines


def format_time(ts: float | None) -> str:
    if ts is None:
        return ""
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def show_conversation(conv: dict) -> None:
    title = conv.get("title", "Untitled")
    create_time = conv.get("create_time")
    mapping = conv.get("mapping", {})
    thread = walk_thread(mapping)

    # ── header ──
    print()
    print(BOX_TOP)
    print(box_line(f"📁  {title}", align="center"))
    if create_time:
        print(box_line(format_time(create_time), align="center"))
    print(box_line(align="center"))
    print(box_line(f"{len([n for n in thread if n.get('message')])} total messages", align="center"))
    print(BOX_BOT)

    msg_count = 0
    inner_width = WIDTH - 4  # usable text width inside box

    for node in thread:
        msg = node.get("message")
        if is_hidden(msg):
            continue

        msg_count += 1
        role = msg["author"]["role"]
        label, _ = ROLE_STYLE.get(role, (f"❓ {role}", "left"))
        ts = msg.get("create_time")
        parts = msg.get("content", {}).get("parts", [])
        text = extract_text(parts)

        if not text:
            continue

        # Build header with speaker + timestamp
        # Format: "│  [timestamp]                    Speaker │"
        ts_str = format_time(ts) if ts else ""
        header = f"{ts_str}    {label}"

        print()
        print(BOX_TOP)
        print(box_line(header, align="right"))
        print(BOX_MID)

        # Word-wrap the body
        body_lines = wrap_text(text, inner_width)
        for line in body_lines:
            print(box_line(line))

        print(BOX_BOT)

    # ── footer ──
    print()
    print(BOX_TOP)
    print(box_line(f"✨ {msg_count} visible messages", align="center"))
    print(BOX_BOT)
    print()


def find_most_recent(directory: str) -> str | None:
    """Find the most recently modified *.json file, excluding index and cache files."""
    import glob
    json_files = [
        f for f in glob.glob(os.path.join(directory, "*.json"))
        if not os.path.basename(f).startswith(("index", "listing"))
    ]
    if not json_files:
        return None
    return max(json_files, key=os.path.getmtime)


if __name__ == "__main__":
    import glob
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_dirs = [
        os.path.join(script_dir, "export", "mwt", "conversations"),
        os.path.join(script_dir, "chatgpt-export", "conversations"),
    ]

    HELP = f"""\
Usage: {os.path.basename(__file__)} [OPTIONS] [CONVERSATION.json]

Display ChatGPT conversation exports with clean formatting.

Options:
  -l, --list-subjects [DIR]   List all conversation titles in DIR
                               (defaults to export/mwt/conversations)
  -h, --help                  Show this help message

Examples:
  {os.path.basename(__file__)}                          # show most recent
  {os.path.basename(__file__)} abc123.json              # show specific file
  {os.path.basename(__file__)} -l                       # list all subjects
  {os.path.basename(__file__)} -l some/other/dir        # list subjects in dir
"""

    if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help"):
        print(HELP)
        sys.exit(0)

    if len(sys.argv) >= 2 and sys.argv[1] in ("--list-subjects", "-l"):
        # --- list mode ---
        target_dir = sys.argv[2] if len(sys.argv) > 2 else None
        if target_dir and not os.path.isdir(target_dir):
            print(f"Not a directory: {target_dir}")
            sys.exit(1)

        search_dirs = [target_dir] if target_dir else [d for d in default_dirs if os.path.isdir(d)]
        # Fall back to current directory if default dirs don't exist
        if not search_dirs and not target_dir:
            cwd = os.getcwd()
            if any(f.endswith('.json') for f in os.listdir(cwd) if not os.path.basename(f).startswith(('index', 'listing'))):
                search_dirs = [cwd]
        if not search_dirs:
            print("No conversation directory found.")
            print(f"Searched default: {', '.join(default_dirs)}")
            print(f"Run '{os.path.basename(__file__)} -l <dir>' to specify a directory.")
            sys.exit(1)

        total = 0
        all_json_files: list[tuple[str, list[str]]] = []  # (dir, [files])
        for d in search_dirs:
            json_files = sorted(
                f for f in glob.glob(os.path.join(d, "*.json"))
                if not os.path.basename(f).startswith(("index", "listing"))
            )
            all_json_files.append((d, json_files))
            total += len(json_files)

        print(f"\n📁  {len(all_json_files)} director{'y' if len(all_json_files) == 1 else 'ies'}, {total} conversation{'s' if total != 1 else ''}\n")

        for d, json_files in all_json_files:
            if target_dir or len(all_json_files) > 1:
                print(f"  ── {os.path.basename(d)} ──")
            for f in json_files:
                try:
                    conv = load_conversation(f)
                    conv_id = os.path.splitext(os.path.basename(f))[0]
                    title = conv.get("title", "(untitled)")
                    ts = conv.get("create_time")
                    date_str = format_time(ts) if ts else ""
                    # Count visible messages
                    mapping = conv.get("mapping", {})
                    total_msgs = sum(1 for n in mapping.values() if n.get("message"))
                    visible_msgs = sum(1 for n in mapping.values() if not is_hidden(n.get("message")))
                    count_str = f"[{visible_msgs}/{total_msgs} msgs]"
                    print(f"  {conv_id}  {date_str:20s}  {count_str:>14s}  {title}")
                except Exception:
                    print(f"  {os.path.basename(f):40s}  [error reading]")
            if not target_dir and d != search_dirs[-1]:
                print()
        sys.exit(0)

    if len(sys.argv) < 2:
        # Search common export locations for the most recent conversation
        all_files = []
        for d in default_dirs:
            if os.path.isdir(d):
                all_files.extend(
                    f for f in glob.glob(os.path.join(d, "*.json"))
                    if not os.path.basename(f).startswith(("index", "listing"))
                )
        if not all_files:
            print("No conversation files found.")
            print(f"Searched: {', '.join(default_dirs)}")
            print(f"\nRun '{os.path.basename(__file__)} -h' for help.")
            sys.exit(1)
        target = max(all_files, key=os.path.getmtime)
        print(f"📂  {os.path.basename(target)}\n")
        show_conversation(load_conversation(target))
    else:
        if not os.path.isfile(sys.argv[1]):
            print(f"File not found: {sys.argv[1]}")
            print(f"Run '{os.path.basename(__file__)} -h' for help.")
            sys.exit(1)
        show_conversation(load_conversation(sys.argv[1]))
