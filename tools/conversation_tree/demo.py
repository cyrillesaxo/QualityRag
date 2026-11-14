"""Worked example: provisional governance, an ambiguous drift, and the read-back gate.

Run: python -m tools.conversation_tree.demo
"""
import json
import tempfile
from pathlib import Path

from .tree import ConversationTree

AT = "2026-11-14T12:00:00Z"


def main():
    with tempfile.TemporaryDirectory() as folder:
        tree = ConversationTree(str(Path(folder) / "conversation.sqlite"))
        say = lambda i, actor, text: tree.append_turn(turn_id=i, actor=actor, content=text, at=AT)
        say("u1", "USER", "Draft a refund policy for the store. Employees qualify after 90 days, "
                          "except temporary employees. The policy must not exceed one page.")
        tree.open_root(turn_id="u1", at=AT)
        say("a1", "ASSISTANT", "Here is a draft refund policy.")
        tree.attach(branch="root", turn_id="a1", at=AT)
        say("u2", "USER", "What is a good recipe for bread?")
        fork = tree.advance(branch="root", turn_id="u2", at=AT, fork_id="f1")
        state = fork["state"]
        gate = tree.gate("f1-mrg", loaded={"u2"})  # the assistant holds only the newest turn
        report = {
            "custody": tree.custody_report(),
            "classification": state["classifications"][-1],
            "fork": {name: {"kind": state["branches"][name]["kind"],
                            "visible_turns": tree._effective(state, name),
                            "obligations": len(state["branches"][name]["packspecs"][-1]["obligations"])}
                     for name in fork["branches"]},
            "merged_ledger_counts": tree.ledger("f1-mrg")["counts"],
            "isolated_ledger_counts": tree.ledger("f1-iso")["counts"],
            "gate_on_merged_branch": {k: gate[k] for k in ("verdict", "required_reads", "can_generate")},
            "read_back": [tree.read(r["turn_id"], r["start"], r["end"])["content"].decode()
                          for r in gate["required_reads"]],
        }
        tree.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
