"""Go-live readiness check (FDE practice): run before handing a deployment to a customer.

From memoryguard/:  python -m deploy.preflight      (start the API first for the live checks)
Exit code 0 = ready, 1 = at least one blocking failure.
"""
import socket
import subprocess
import sys

import httpx

import config
import db

RESULTS: list[tuple[str, str, str]] = []  # (status, check, detail)


def record(ok: bool | None, name: str, detail: str = "") -> None:
    RESULTS.append(("PASS" if ok else "WARN" if ok is None else "FAIL", name, detail))


def _lan_ip() -> str | None:
    """This machine's LAN address (UDP 'connect' sends no packets)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET address, never routed
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") or ip == "0.0.0.0" else ip
    except OSError:
        return None


def main() -> int:
    p = config.POLICY
    record(True, "Policy file valid", f"{config.POLICY_FILE.name}: customer={p.get('customer')}, "
                                      f"enforcement={p['enforcement']}, actions={p['allowed_actions']}")
    record(config.LLM_PROVIDER in p["llm_providers_allowed"], "LLM provider allowed by policy", config.LLM_PROVIDER)
    record(p.get("pseudonymize_llm_inputs", False), "Sensitive values pseudonymized before the LLM")
    record(p.get("require_human_review", False), "Human review required for drafted actions")
    record(True if p.get("ingest_sender_allowlist") or p.get("ingest_domain_allowlist") else None,
           "Ingest restricted to trusted senders/domains",
           f"senders={p.get('ingest_sender_allowlist') or 'any'}, domains={p.get('ingest_domain_allowlist') or 'any'}"
           + ("" if p.get("ingest_sender_allowlist") or p.get("ingest_domain_allowlist")
              else " (open for the live demo; set allowlists for production)"))
    record(True, "Vault retention enforced", f"{p['vault_retention_days']} days (purged at startup and on Approve)")

    try:
        tracked = subprocess.run(["git", "ls-files", ".env", "../.env"], capture_output=True, text=True,
                                 cwd=config.PKG_DIR).stdout.strip()
        record(not tracked, ".env not tracked by git", tracked or "untracked")
    except FileNotFoundError:
        record(None, ".env not tracked by git", "git not installed")

    v = db.verify_audit()
    record(v["ok"], "Audit log hash chain intact", f"{v['entries']} entries")

    api = "http://127.0.0.1:8000"
    try:
        raw = httpx.get(f"{api}/metrics", timeout=5)
        record(raw.status_code == 401, "API refuses requests without the token", f"HTTP {raw.status_code}")
        evil = httpx.get(f"{api}/health", headers={"host": "attacker.example"}, timeout=5)
        record(evil.status_code == 400, "API refuses foreign Host headers (DNS rebinding)", f"HTTP {evil.status_code}")
        authed = httpx.get(f"{api}/metrics", headers={"x-memoryguard-token": config.API_TOKEN}, timeout=5)
        record(authed.status_code == 200, "API answers with the token", f"enforcement={authed.json().get('enforcement')}")
        ssrf = httpx.post(f"{api}/ingest", json={"url": "http://169.254.169.254/latest/meta-data/"},
                          headers={"x-memoryguard-token": config.API_TOKEN}, timeout=10)
        record(ssrf.status_code == 400, "Ingest blocks cloud-metadata SSRF", ssrf.json().get("detail", "")[:60])
        # CORS must be off: no Access-Control-Allow-Origin for a foreign origin, even on a preflight request.
        opt = httpx.request("OPTIONS", f"{api}/metrics", timeout=5, headers={
            "origin": "https://evil.example", "access-control-request-method": "GET"})
        get = httpx.get(f"{api}/health", headers={"origin": "https://evil.example"}, timeout=5)
        acao = opt.headers.get("access-control-allow-origin") or get.headers.get("access-control-allow-origin")
        record(not acao, "CORS is off (no Access-Control-Allow-Origin)", f"header: {acao or 'absent'}")
    except httpx.HTTPError:
        record(False, "API reachable on 127.0.0.1:8000", "start it with npm run dev, then re-run")

    # The API must not be reachable from the network: connecting via this machine's LAN address must fail.
    lan_ip = _lan_ip()
    if lan_ip:
        try:
            with socket.create_connection((lan_ip, 8000), timeout=2):
                record(False, "API listens only on localhost", f"reachable on {lan_ip}:8000 from the network")
        except OSError:
            record(True, "API listens only on localhost", f"not reachable on LAN address {lan_ip}:8000")
    else:
        record(None, "API listens only on localhost", "no LAN address found to test (advisory)")

    try:
        out = subprocess.run(["manage-bde", "-status", "C:"], capture_output=True, text=True, timeout=10).stdout
        on = "Protection On" in out
        record(True if on else None, "Disk encryption (BitLocker) on C:", "on" if on else "off or unknown (advisory)")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        record(None, "Disk encryption (BitLocker) on C:", "could not check (advisory)")

    if "--full" in sys.argv:  # F5: the customer acceptance suite is part of the hand-off gate
        print("Running the acceptance suite (demo loop + security tests)...")
        run = subprocess.run([sys.executable, "-m", "demo.smoke_test", "1"], capture_output=True, text=True,
                             cwd=config.PKG_DIR, timeout=900)
        passed = run.stdout.count("  PASS ")
        failed_line = next((ln.strip() for ln in run.stdout.splitlines() if "FAIL" in ln), "")
        record(run.returncode == 0, "Acceptance suite (npm run smoke)",
               f"{passed} checks passed" if run.returncode == 0 else (failed_line or run.stderr[-200:])[:90])
    else:
        record(None, "Acceptance suite", "skipped - run with --full to include it")

    width = max(len(n) for _, n, _ in RESULTS)
    print("\nMemoryGuard go-live readiness\n")
    for status, name, detail in RESULTS:
        print(f"  [{status}] {name.ljust(width)}  {detail}")
    failed = sum(s == "FAIL" for s, _, _ in RESULTS)
    print(f"\n  {'READY' if not failed else 'NOT READY'}: {failed} blocking failure(s), "
          f"{sum(s == 'WARN' for s, _, _ in RESULTS)} warning(s)\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
