// kittymux — OpenCode 1.x tells kittymux what it is doing, from its own events (no screen reading). OpenCode 2 uses kittymux-agent-state.js.
// Installed by `kittymux hooks --opencode --install` (when `opencode --version` is 1.x) into ~/.config/opencode/plugins/kittymux-agent-state.js.
// GENERATED from kittymux's integrations/opencode/kittymux-agent-state.js — edit that file, then reinstall.
//
// It reports through bin/mux-status (the same path as Claude Code's hooks): working while a turn runs, waiting with the
// question when OpenCode asks for a permission or asks you a question, done when the turn ends. Only inside a kitty pane;
// a failure is ignored, so it can never block OpenCode.
import { spawn } from "node:child_process";

const MUX_STATUS = "@KITTYMUX_HOME@/bin/mux-status";
const childSessions = new Map(); // a subagent's session → its parent: only its questions reach the pane

function report(state, msg) {
  if (!process.env.KITTY_WINDOW_ID) return;
  try {
    const args = msg ? ["--msg", String(msg).slice(0, 200), state] : [state];
    const child = spawn(MUX_STATUS, args, { stdio: "ignore" });
    child.on("error", () => {});
  } catch {
    // never let reporting break OpenCode
  }
}

function permissionText(properties) {
  // phrased as a request ("Allow …?"), which is what kittymux reads as needing you rather than an idle notice
  const what = properties?.title ?? properties?.pattern ?? properties?.type;
  return typeof what === "string" && what.trim() ? `Allow ${what.trim()}?` : "Allow this?";
}

function askedText(properties) {
  const q = properties?.questions?.[0]?.question ?? properties?.question ?? properties?.title ?? properties?.message;
  return typeof q === "string" && q.trim() ? q.trim() : "OpenCode needs your answer";
}

export const KittymuxAgentStatePlugin = async () => {
  if (!process.env.KITTY_WINDOW_ID) return {};
  return {
    "chat.message": async ({ sessionID }) => {
      if (sessionID && childSessions.has(sessionID)) return;
      report("working");
    },
    event: async ({ event }) => {
      const type = event?.type;
      const properties = event?.properties ?? {};
      const info = properties.info;
      if (info?.id && info.parentID) childSessions.set(info.id, info.parentID);
      const sessionID = typeof properties.sessionID === "string" ? properties.sessionID : undefined;
      const child = sessionID && childSessions.has(sessionID);
      switch (type) {
        case "permission.asked":
          report("waiting", permissionText(properties)); // a subagent's request needs you too
          break;
        case "question.asked":
          report("waiting", askedText(properties));
          break;
        case "permission.replied":
        case "question.replied":
        case "question.rejected":
          report("working");
          break;
        case "tool.execute.before":
        case "tool.execute.after":
          if (!child) report("working");
          break;
        case "session.idle":
          if (!child) report("done");
          break;
        case "session.deleted":
          if (sessionID) childSessions.delete(sessionID);
          break;
        default:
          break;
      }
    },
  };
};
