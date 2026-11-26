// kittymux — OpenCode 2 tells kittymux what it is doing, from its own events (no screen reading). OpenCode 1.x uses kittymux-agent-state.v1.js.
// Installed by `kittymux hooks --opencode --install` into ~/.config/opencode/plugins/; removed by `--remove`.
// GENERATED from kittymux's integrations/opencode/kittymux-agent-state.js — edit that file, then reinstall.
//
// It reports through bin/mux-status (the same path as Claude Code's hooks): working while a turn runs, waiting with the
// request when OpenCode asks for a permission or asks you a question, done when the turn succeeds, idle when it is
// interrupted or fails (an interrupted turn is never "finished"). Only inside a kitty pane; a failure is ignored, so it can
// never block OpenCode. The event names and payloads are the ones a live OpenCode 2.3.0 sent (captured 2026-11-13).
import { spawn } from "node:child_process";

const MUX_STATUS = "@KITTYMUX_HOME@/bin/mux-status";

function report(state, msg) {
  try {
    const args = msg ? ["--msg", String(msg).replace(/\s+/g, " ").trim().slice(0, 200), state] : [state];
    const child = spawn(MUX_STATUS, args, { stdio: "ignore" });
    child.on("error", () => {});
  } catch {
    // never let reporting break OpenCode
  }
}

const text = (v) => (typeof v === "string" && v.trim() ? v.trim() : "");

function permissionText(p) {
  // phrased as a request ("Allow …?"), which is what kittymux reads as needing you rather than an idle notice
  const action = text(p?.action);
  const what = Array.isArray(p?.resources) ? text(p.resources[0]) : "";
  if (action && what) return `Allow ${action}: ${what}?`;
  return action || what ? `Allow ${action || what}?` : "Allow this?";
}

function formText(form) {
  const field = Array.isArray(form?.fields) ? form.fields[0] : undefined;
  return text(field?.description) || text(field?.title) || text(form?.title) || "OpenCode needs your answer";
}

function handle(event, children) {
  const type = event?.type;
  const p = event?.properties ?? event?.data ?? {};
  const sessionID = text(p.sessionID) || text(p.form?.sessionID);
  const parent = text(p.parentID) || text(p.parentSessionID);
  const child = Boolean(sessionID && children.has(sessionID));
  switch (type) {
    case "session.created":
      if (sessionID && parent) children.add(sessionID); // a subagent: only its questions reach the pane
      break;
    case "session.deleted":
      if (sessionID) children.delete(sessionID);
      break;
    case "session.execution.started":
      if (!child) report("working");
      break;
    case "permission.asked":
      report("waiting", permissionText(p)); // a subagent's request needs you too
      break;
    case "form.created":
      report("waiting", formText(p.form));
      break;
    case "permission.replied":
    case "form.replied":
    case "form.cancelled":
      report("working");
      break;
    case "session.execution.succeeded":
      if (!child) report("done");
      break;
    case "session.execution.interrupted":
    case "session.execution.failed":
      if (!child) report("idle");
      break;
    default:
      break;
  }
}

export default {
  id: "kittymux-agent-state",
  setup(ctx) {
    if (!process.env.KITTY_WINDOW_ID || typeof ctx?.event?.subscribe !== "function") return;
    const controller = new AbortController();
    const children = new Set();
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) handle(event, children);
      } catch {
        // the stream ended (OpenCode is shutting down) or failed: reporting stops, OpenCode carries on
      }
    })();
    return () => controller.abort();
  },
};
