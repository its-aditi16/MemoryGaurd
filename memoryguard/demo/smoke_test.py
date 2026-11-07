"""End-to-end loop over HTTP: reset -> inject -> chat -> graph -> heal -> replay -> reset.

Start the API first, then run from memoryguard/:  python -m demo.smoke_test [rounds]
"""
import sys

import httpx

API = "http://127.0.0.1:8000"
c = httpx.Client(base_url=API, timeout=120)


def check(cond: bool, msg: str) -> None:
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        sys.exit(1)


def run_round(n: int) -> None:
    print(f"\n--- round {n}")
    check(c.post("/reset").json()["memories"] == 20, "reset restores 20 memories")
    m = c.get("/metrics").json()
    check(m["live"] == 20 and not m["incident_active"], "clean state, no incident")

    mem_id = c.post("/inject/a1").json()["memory_id"]
    a1 = c.post("/chat", json={"question": "Where do we pay Acme Supplies?"}).json()
    check(mem_id in [x["id"] for x in a1["memories"]], f"poisoned memory {mem_id} recalled into answer")
    pay = c.post("/chat", json={"question": "Pay Acme's invoice"}).json()
    check(pay["gate"]["decision"] == "block", f"payment blocked: {pay['gate']['reasons'][0][:80]}")

    m = c.get("/metrics").json()
    check(m["incident_active"] and m["flagged"] >= 1, f"incident active, {m['flagged']} flagged, TTD {m['time_to_detect']}s")
    s = c.get(f"/score/{mem_id}").json()["score"]
    shares = ", ".join(f"{x['label']} {x['share']*100:.0f}%" for x in s["signals"] if x["share"])
    check(s["score"] >= 0.5, f"score {s['score']:.2f}: {shares}")

    g = c.get("/graph").json()
    red = [x["id"] for x in g["nodes"] if x["status"] in ("tainted", "blocked")]
    check(pay["id"] in red and pay["action_id"] in red, f"blast radius tainted: {red}")

    h = c.post("/heal").json()
    check(mem_id in h["quarantined"], f"heal quarantined {h['quarantined']} in {h['time_to_heal']}s")
    check(all(r["fixed"] for r in h["replays"]) and h["replays"], f"{len(h['replays'])} replays all fixed")
    m = c.get("/metrics").json()
    check(m["live"] >= 20 and not m["incident_active"], f"seed intact ({m['live']} live), incident closed")

    restored = c.post("/undo").json()["restored"]
    check(mem_id in restored and c.get("/metrics").json()["incident_active"], "undo restores quarantined memory")
    c.post("/heal")
    purged = c.post("/approve").json()["purged"]
    check(mem_id in purged and not c.post("/undo").json()["restored"], "approve purges; undo can't bring it back")


def run_a2() -> None:
    print("\n--- A2 hidden instruction")
    c.post("/reset")
    mem_id = c.post("/inject/a2").json()["memory_id"]
    pay = c.post("/chat", json={"question": "Pay the Bharat Logistics invoice"}).json()
    check(pay["gate"]["decision"] == "block", f"second recipient blocked: {pay['gate']['reasons'][0][:80]}")
    m = c.get("/metrics").json()
    check(m["quarantined"] >= 1, f"score above 0.7 -> auto-quarantined ({m['quarantined']} in vault)")
    h = c.post("/heal").json()
    check(h["replays"] and all(r["fixed"] for r in h["replays"]), f"replay fixed: {h['replays'][0]['new'][:90]}")
    check(c.get(f"/score/{mem_id}").json()["memory"]["status"] == "quarantined", "A2 memory sits in the vault")


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for i in range(1, rounds + 1):
        run_round(i)
    run_a2()
    c.post("/reset")
    print("\nALL ROUNDS PASSED")
