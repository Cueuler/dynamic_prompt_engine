import assert from "node:assert/strict";
import test from "node:test";

import {
  applyParsedRoutingSwitchWidgets,
  connectedRoutingIndicesFromInputs,
  parseRoutingSwitchWidgetValues,
} from "./routing_switch_widgets.js";

test("connectedRoutingIndicesFromInputs uses saved input_N links, not live widgets", () => {
  assert.deepEqual(
    connectedRoutingIndicesFromInputs([
      { name: "input_2", link: 10 },
      { name: "input_0", link: 11 },
      { name: "input_1", link: null },
      { name: "seed", link: 99 },
    ]),
    [0, 2],
  );
});

test("parseRoutingSwitchWidgetValues zips chance strings onto saved slot names", () => {
  const parsed = parseRoutingSwitchWidgetValues(
    ["Off", "2x", 42, "randomize"],
    { connectedIndices: [0, 2] },
  );
  assert.equal(parsed.seed, 42);
  assert.deepEqual(parsed.chances, {
    chance_0: "Off",
    chance_2: "2x",
  });
  assert.equal(parsed.chances.chance_1, undefined);
});

test("parseRoutingSwitchWidgetValues keeps seed-first layouts mapped by saved slots", () => {
  const parsed = parseRoutingSwitchWidgetValues(
    [99, "fixed", "1.5x", "Off"],
    { connectedIndices: [0, 2] },
  );
  assert.equal(parsed.seed, 99);
  assert.deepEqual(parsed.chances, {
    chance_0: "1.5x",
    chance_2: "Off",
  });
});

test("parseRoutingSwitchWidgetValues prefers widget names when they align", () => {
  const parsed = parseRoutingSwitchWidgetValues(
    ["Off", "2x", 7, "randomize"],
    {
      connectedIndices: [0, 1],
      widgetNames: ["chance_0", "chance_2", "seed", "control_after_generate"],
    },
  );
  assert.equal(parsed.seed, 7);
  assert.deepEqual(parsed.chances, {
    chance_0: "Off",
    chance_2: "2x",
  });
});

test("parseRoutingSwitchWidgetValues does not assign 2x to chance_1 for holes", () => {
  const parsed = parseRoutingSwitchWidgetValues(["Default", "2x", 1], {
    connectedIndices: [0, 5],
  });
  assert.deepEqual(parsed.chances, {
    chance_0: "Default",
    chance_5: "2x",
  });
});

test("applyParsedRoutingSwitchWidgets writes by chance_N name", () => {
  const chance0 = { name: "chance_0", value: "Default" };
  const chance1 = { name: "chance_1", value: "Default" };
  const seed = { name: "seed", value: 0 };
  const node = { widgets: [chance0, chance1, seed] };
  applyParsedRoutingSwitchWidgets(node, {
    seed: 42,
    chances: { chance_0: "Off", chance_2: "2x" },
  });
  assert.equal(chance0.value, "Off");
  assert.equal(chance1.value, "Default");
  assert.equal(seed.value, 42);
  assert.equal(node.__dpeChanceSaved.chance_2, "2x");
});
