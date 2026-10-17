import test from "node:test";
import assert from "node:assert/strict";
import {
  applySyncResults,
  friendlyError,
  money,
  syncEnvelope,
  validServer,
} from "../src/domain.ts";

const action = {
  action_id: "a1",
  type: "score_event",
  queued_at: "2026-10-17T07:00:00Z",
  base_version: 3,
  payload: {
    event_id: "evt-1",
    match_id: "m1",
    type: "score",
    payload: { team_id: "t1", event_type: "raid_point" },
  },
  scope: "server|tenant|user",
  state: "pending",
};
test("sync matches PDF 5.14 and excludes local-only metadata and completed items", () => {
  assert.deepEqual(
    syncEnvelope("dev-1", [
      action,
      { ...action, action_id: "a2", state: "applied" },
    ]),
    {
      device_id: "dev-1",
      actions: [
        {
          action_id: "a1",
          type: "score_event",
          queued_at: "2026-10-17T07:00:00Z",
          base_version: 3,
          payload: action.payload,
        },
      ],
    },
  );
});
test("sync batches at most 100 actions without changing their idempotency keys", () => {
  const input = Array.from({ length: 105 }, (_, i) => ({
    ...action,
    action_id: `a${i}`,
  }));
  const body = syncEnvelope("dev", input);
  assert.equal(body.actions.length, 100);
  assert.equal(body.actions[99].action_id, "a99");
  assert.equal(input.length, 105);
});
test("rejected actions retain their explanation and unacknowledged actions stay pending", () => {
  const output = applySyncResults(
    [action, { ...action, action_id: "a2" }],
    [
      {
        action_id: "a1",
        status: "rejected",
        resolution: "server_wins",
        error_code: "MATCH_NOT_IN_PROGRESS",
        server_version: 4,
        processed_order: 1,
        signature: null,
      },
    ],
  );
  assert.equal(output[0].state, "rejected");
  assert.equal(output[0].reason, "MATCH_NOT_IN_PROGRESS");
  assert.equal(output[1].state, "pending");
  assert.equal(action.state, "pending");
});
test("duplicate acknowledgements finish the action without generating a fresh action id", () => {
  const [output] = applySyncResults(
    [action],
    [
      {
        action_id: "a1",
        status: "duplicate",
        resolution: "skipped_duplicate",
        error_code: null,
        server_version: 4,
        processed_order: 1,
        signature: null,
      },
    ],
  );
  assert.equal(output.state, "duplicate");
  assert.equal(output.action_id, "a1");
});
test("server settings reject credentials and non-HTTP schemes", () => {
  assert.equal(
    validServer(" http://192.168.43.10:8080/ "),
    "http://192.168.43.10:8080",
  );
  for (const bad of [
    "file:///tmp",
    "http://user:password@host:8080",
    "https://host?token=secret",
  ])
    assert.throws(() => validServer(bad));
});
test("money uses integer paisa and errors have user-facing explanations", () => {
  assert.equal(money(450000), "PKR 4500.00");
  assert.match(friendlyError("SQUAD_FULL"), /full/);
  assert.doesNotMatch(friendlyError("SQUAD_FULL"), /SQUAD_FULL/);
});
