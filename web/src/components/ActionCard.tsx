import { Ban, CheckCircle2, Eye, KeyRound, Mail, PauseCircle, TriangleAlert, UserCog } from "lucide-react";
import type { AgentAction, Email, GateDecision, Payment } from "../api";

const NOUN: Record<string, string> = {
  draft_payment: "Payment", draft_email: "Email", grant_access: "Access change", reset_password: "Password reset",
};

/** One drafted action (payment, email, access change, password reset) and what the gate decided. */
export function ActionCard({ payment, email, action, gate, status, actionId, unprotected }: {
  payment: Payment | null; email: Email | null; action?: AgentAction | null; gate: GateDecision | null;
  status?: string | null; actionId?: string | null; unprotected?: boolean;
}) {
  const kind = payment ? "draft_payment" : email ? "draft_email" : action?.kind;
  if (!kind) return null;
  const what = NOUN[kind];
  const monitor = !!gate?.monitor;
  const blocked = !monitor && (gate?.decision === "block" || status === "blocked");
  const held = gate?.decision === "hold";
  const noGuard = unprotected || !gate;
  const tone = blocked ? "border-bad/40 bg-bad/10"
    : held || noGuard || monitor ? "border-flag/40 bg-flag/10" : "border-clean/30 bg-clean/5";
  const blockedTitle = kind === "draft_email" ? "Data leak blocked"
    : kind === "grant_access" ? "Privilege escalation blocked"
    : kind === "reset_password" ? "Account takeover blocked" : "Action blocked";
  const title = blocked ? blockedTitle
    : monitor ? `${what} allowed - monitor mode would block`
    : held ? "Held for verification"
    : noGuard ? `${what} carried out (unprotected)`
    : `${what} drafted · awaiting your review`;
  const KindIcon = kind === "draft_email" ? Mail : kind === "grant_access" ? UserCog : kind === "reset_password" ? KeyRound : CheckCircle2;
  const Icon = blocked ? Ban : monitor ? Eye : held ? PauseCircle : noGuard ? TriangleAlert : KindIcon;
  const iconTone = blocked ? "text-bad" : held || noGuard || monitor ? "text-flag" : "text-clean";
  const d = action?.data ?? {};
  return (
    <div className={`mt-2 rounded-xl border px-3 py-2.5 ${tone}`}>
      <div className="flex items-center gap-1.5 text-[13px] font-semibold text-white">
        <Icon className={`h-4 w-4 ${iconTone}`} />
        {title}
        {actionId && <span className="ml-auto text-[11px] font-normal text-gray-400">{actionId}</span>}
      </div>
      {payment && (
        <>
          <div className="tnum mt-1 text-xs text-gray-300">
            {payment.invoice} · INR {Number(payment.amount_inr ?? 0).toLocaleString("en-IN")}
          </div>
          {payment.recipients.map((r) => (
            <div key={r.account + r.name} className="tnum text-xs text-gray-400">→ {r.name} · {r.account}</div>
          ))}
        </>
      )}
      {email && (
        <div className="mt-1 space-y-0.5 text-xs">
          <div className="text-gray-300">To: <span className="tnum text-white">{email.to}</span></div>
          <div className="text-gray-400">Subject: {email.subject}</div>
          <div className="line-clamp-2 text-gray-500">{email.body}</div>
        </div>
      )}
      {kind === "grant_access" && (
        <div className="mt-1 text-xs text-gray-300">
          <span className="text-white">{d.user}</span> → <span className="text-white">{d.role || "access"}</span>
          {d.system && <span className="text-gray-400"> on {d.system}</span>}
        </div>
      )}
      {kind === "reset_password" && (
        <div className="mt-1 text-xs text-gray-300">
          Reset for <span className="text-white">{d.user}</span>, link sent to <span className="tnum text-white">{d.send_to || "?"}</span>
        </div>
      )}
      {gate?.reasons?.map((r) => <div key={r} className="mt-1.5 text-xs leading-relaxed text-gray-300">{r}</div>)}
    </div>
  );
}
