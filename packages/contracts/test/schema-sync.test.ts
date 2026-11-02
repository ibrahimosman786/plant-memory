import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { FINDING_TYPES, RUN_EVENT_TYPES, SEVERITIES } from "../src/index.ts";

const here = dirname(fileURLToPath(import.meta.url));
const schema = (name: string) =>
  JSON.parse(readFileSync(join(here, "..", "schemas", name), "utf8")) as Record<string, any>;

test("finding enums match the JSON schema", () => {
  const s = schema("finding.schema.json");
  assert.deepEqual([...FINDING_TYPES], s.properties.type.enum);
  assert.deepEqual([...SEVERITIES], s.properties.severity.enum);
});

test("run event types match the JSON schema", () => {
  const s = schema("run-event.schema.json");
  assert.deepEqual([...RUN_EVENT_TYPES], s.properties.type.enum);
});

test("tool result envelope has the required fields from section 9", () => {
  const s = schema("tool-result.schema.json");
  assert.deepEqual(s.required, [
    "status",
    "snapshot_id",
    "data",
    "evidence_ids",
    "warnings",
    "unresolved",
    "tool_version",
  ]);
  assert.deepEqual(s.properties.status.enum, ["complete", "partial", "blocked", "failed"]);
});
