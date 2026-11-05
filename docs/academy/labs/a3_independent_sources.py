"""A3 · Three sources agree, but they all copied the same original."""
from _common import AS_OF, ev, evaluate, show

pack = {"id": "recovery-corroboration", "version": "1.0",
        "requirements": [{"id": "recovery-procedure", "min_independent_sources": 2}]}
copies = [ev("ops-7.3", "recovery-procedure", "ops-handbook"),
          ev("ops-mirror-7.3", "recovery-procedure", "ops-handbook"),
          ev("fwd-email-7.3", "recovery-procedure", "ops-handbook")]
show("Three citations, one origin", evaluate(pack, copies, as_of=AS_OF))
show("Add one independent origin", evaluate(pack, copies + [ev("cab-minutes-0412", "recovery-procedure", "change-board")], as_of=AS_OF))
