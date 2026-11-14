"""Read-only HTML view of a conversation tree (US-086, review surface only).

Writes one self-contained page: branches, PackSpec versions, fork and collapse events, and
the disposition of every span per branch. Stored text is untrusted and is always escaped.
There are no actions on the page: locking, promoting, amending and reopening stay in the API.

    python -m tools.conversation_tree.view /absolute/conversation.sqlite > tree.html
"""
from __future__ import annotations

from html import escape
import os
import sys

from .tree import ConversationTree

_CSS = """
:root{--bg:#fbfaf7;--fg:#1d1f23;--muted:#667085;--line:#d9d6ce;--card:#fff;
--rep:#d7f0df;--res:#f3ecd2;--exc:#e6e6ea;--unk:#f8d7d3;--accent:#2d5d7b}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e7e5e0;--muted:#98a2b3;--line:#33373d;
--card:#1c1f23;--rep:#1f4a30;--res:#4a4222;--exc:#34363c;--unk:#5a2a26;--accent:#8fc1de}}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:980px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.note{color:var(--muted);font-size:13px;margin:0 0 16px}
.legend span,.chip{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;margin-right:6px}
.REPRESENTED{background:var(--rep)}.RESIDUAL{background:var(--res)}
.EXCLUDED_BY_RULE{background:var(--exc);color:var(--muted)}.UNKNOWN{background:var(--unk)}
details{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:8px 0;padding:8px 12px}
summary{cursor:pointer;font-weight:600}summary small{font-weight:400;color:var(--muted);margin-left:8px}
.off summary{color:var(--muted);text-decoration:line-through}
.turn{margin:10px 0;padding-left:10px;border-left:3px solid var(--line)}
.who{font-size:12px;color:var(--muted);letter-spacing:.04em}
.span{padding:1px 2px;border-radius:3px;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;padding:4px 8px;
border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:500}
ul.tree{list-style:none;padding-left:18px;margin:4px 0}ul.tree li{margin:2px 0}
code{font-size:12px;color:var(--accent)}
"""


def _tree(state, parent=None):
    kids = [n for n, b in state["branches"].items() if b["parent"] == parent]
    if not kids:
        return ""
    items = []
    for name in kids:
        node = state["branches"][name]
        spec = node["packspecs"][-1]
        status = "" if node["active"] else " (closed)"
        items.append('<li><a href="#b-%s">%s</a> <span class="chip EXCLUDED_BY_RULE">%s</span> '
                     'PackSpec v%d %s%s%s</li>' % (
                         escape(name, True), escape(name), node["kind"], spec["version"],
                         spec["status"], status, _tree(state, name)))
    return '<ul class="tree">%s</ul>' % "".join(items)


def render(tree):
    state = tree.replay()
    texts = {t["turn_id"]: t for t in tree.turns()}
    out = ['<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           '<title>Conversation tree</title><style>%s</style></head><body><main>' % _CSS,
           '<h1>Conversation tree</h1>',
           '<p class="note">Declared structure, not validated meaning. Obligations are lexical candidates; '
           'only USER statements carry authority. %d turns, %d branches, snapshot <code>%s</code>.</p>' % (
               len(texts), len(state["branches"]), escape(str(state["head"])[:16])),
           '<p class="legend">' + "".join('<span class="%s">%s</span>' % (d, d.replace("_", " ").lower())
                                          for d in ("REPRESENTED", "RESIDUAL", "EXCLUDED_BY_RULE", "UNKNOWN"))
           + '</p>', '<h2>Branches</h2>', _tree(state) or '<p class="note">No root yet.</p>']
    if state["standing"]:
        out.append('<h2>Standing rules</h2><table><tr><th>Level</th><th>Turn</th><th>Text</th></tr>')
        for rule in state["standing"]:
            body = texts[rule["turn_id"]]["content"].decode("utf-8", "replace")
            out.append('<tr><td>%s</td><td><code>%s</code></td><td>%s</td></tr>' % (
                rule["level"], escape(rule["turn_id"]), escape(body)))
        out.append('</table>')
    events = [("Classified", c["event_id"], "%s as %s" % (c["turn_id"], c["verdict"]))
              for c in state["classifications"]]
    events += [("Differential", d["event_id"], "fork %s: %s" % (d["fork_id"], d["verdict"]))
               for d in state["differentials"]]
    for name, node in state["branches"].items():
        if node["kind"] != "ROOT":
            events.append(("Branch opened", node["created_by"], "%s (%s) from %s" % (name, node["kind"], node["parent"])))
        if node.get("pruned_by"):
            events.append(("Branch closed", node["pruned_by"], name))
        if node.get("reopened_context"):
            events.append(("Branch reopened", node["reopened_context"]["reopen_event"], name))
    if events:
        out.append('<h2>Fork and collapse events</h2><table><tr><th>Event</th><th>ID</th><th>Detail</th></tr>')
        for kind, event_id, detail in sorted(events, key=lambda e: e[1]):
            out.append('<tr><td>%s</td><td><code>%s</code></td><td>%s</td></tr>' % (
                kind, escape(event_id), escape(detail)))
        out.append('</table>')
    out.append('<h2>Ledger per branch</h2>')
    for name, node in state["branches"].items():
        ledger = tree.ledger(name)
        counts = " · ".join("%s %d" % (k.replace("_", " ").lower(), v) for k, v in ledger["counts"].items())
        out.append('<details id="b-%s"%s><summary>%s<small>%s</small></summary>' % (
            escape(name, True), "" if node["active"] else ' class="off"', escape(name), counts))
        out.append('<table><tr><th>PackSpec</th><th>Status</th><th>Candidates</th><th>Inventory</th></tr>')
        for spec in node["packspecs"]:
            out.append('<tr><td>v%d</td><td>%s</td><td>%d</td><td>%s</td></tr>' % (
                spec["version"], spec["status"], len(spec["obligations"]),
                "unknown" if spec["unknown"] else "lexical candidates"))
        out.append('</table>')
        last = None
        for span in ledger["spans"]:
            turn = texts[span["turn_id"]]
            if span["turn_id"] != last:
                if last is not None:
                    out.append('</div>')
                out.append('<div class="turn"><div class="who">%s · <code>%s</code></div>' % (
                    turn["actor"], escape(span["turn_id"])))
                last = span["turn_id"]
            if span["rule"] == "NOT_UTF8_TEXT":
                body = "[%d bytes, not text]" % (span["end"] - span["start"])
            else:
                body = turn["content"].decode("utf-8")[span["start"]:span["end"]]
            title = span["disposition"] + (" / " + span["rule"] if span["rule"] else "")
            out.append('<span class="span %s" title="%s">%s</span>' % (
                span["disposition"], escape(title, True), escape(body)))
        if last is not None:
            out.append('</div>')
        out.append('</details>')
    out.append('</main></body></html>')
    return "".join(out)


def main(argv):
    if len(argv) != 2:
        print("usage: view /absolute/conversation.sqlite", file=sys.stderr)
        return 2
    if not os.path.isfile(argv[1]):
        print("No such conversation database", file=sys.stderr)
        return 2
    tree = ConversationTree(argv[1])
    try:
        sys.stdout.write(render(tree))
    finally:
        tree.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
