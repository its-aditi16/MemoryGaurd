"""Audit log CLI: verify the hash chain or export it for a customer's security team.

From memoryguard/:  python -m deploy.audit verify
                    python -m deploy.audit export <file.jsonl>
"""
import json
import shutil
import sys

import config
import db


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    v = db.verify_audit()
    if cmd == "verify":
        status = "INTACT" if v["ok"] else f"BROKEN at entry {v['broken_at']}"
        print(json.dumps({"status": status, **v}, indent=2))
        return 0 if v["ok"] else 1
    if cmd == "export":
        if len(sys.argv) < 3:
            print("usage: python -m deploy.audit export <file.jsonl>")
            return 2
        shutil.copyfile(config.AUDIT_LOG, sys.argv[2])
        print(f"exported {v['entries']} entries to {sys.argv[2]} (chain {'intact' if v['ok'] else 'BROKEN'}, "
              f"head {v['head'][:16]}...)")
        return 0 if v["ok"] else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
