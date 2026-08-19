import assert from "node:assert/strict";
import test from "node:test";

import {
  applyParsedRoutingSwitchWidgets,
  connectedRoutingIndicesFromInputs,
  parseRoutingSwitchWidgetValues,
} from "./routing_switch_widgets.js";

test("connectedRoutingIndicesFromInputs collects wired input indices", () => {
  const parsed = parseRoutingSwitchWidgetValues(["Default", "2x", 42], {
    connectedIndices: connectedRoutingIndicesFromInputs([
      { name: "input_0", link: 1 },
      { name: "input_2", link: 2 },
      { name: "seed", link: 99 },
    ]),
  });
  assert.deepEqual(parsed.chances, {
    chance_0: "Default",
    chance_2: "2x",
  });
});

test("parseRoutingSwitchWidgetValues keeps chance-first layouts mapped by saved slots", () => {
  const parsed = parseRoutingSwitchWidgetValues(["Default", "Off", 99], {
    connectedIndices: [0, 1],
  });
  assert.deepEqual(parsed.chances, {
    chance_0: "Default",
    chance_1: "Off",
  });
});

test("parseRoutingSwitchWidgetValues maps named chance widgets", () => {
  const parsed = parseRoutingSwitchWidgetValues(
    ["Default", "Off"],
    {
      widgetNames: ["chance_0", "chance_2"],
    },
  );
  assert.deepEqual(parsed.chances, {
    chance_0: "Default",
    chance_2: "Off",
  });
});

test("applyParsedRoutingSwitchWidgets restores chance widgets only", () => {
  const chance0 = { name: "chance_0", value: "Default" };
  const chance1 = { name: "chance_1", value: "Off" };
  const node = { widgets: [chance0, chance1] };
  applyParsedRoutingSwitchWidgets(node, {
    chances: { chance_0: "2x", chance_1: "1.5x" },
  });
  assert.equal(chance0.value, "2x");
  assert.equal(chance1.value, "1.5x");
});
