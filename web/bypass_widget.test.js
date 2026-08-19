import assert from "node:assert/strict";
import test from "node:test";

import {
  coerceBypassChance,
  migrateUniqueLinePickerWidgets,
  parseUniqueLinePickerWidgetValues,
  parseSeededTextPoolWidgetValues,
} from "./bypass_widget.js";

test("coerceBypassChance treats only explicit on-states as 50%", () => {
  assert.equal(coerceBypassChance(true), true);
  assert.equal(coerceBypassChance(1), true);
  assert.equal(coerceBypassChance("50%"), true);

  assert.equal(coerceBypassChance(false), false);
  assert.equal(coerceBypassChance(0), false);
  assert.equal(coerceBypassChance("Off"), false);
  assert.equal(coerceBypassChance(null), false);
  assert.equal(coerceBypassChance("randomize"), false);
  assert.equal(coerceBypassChance("fixed"), false);
  assert.equal(coerceBypassChance("increment"), false);
  assert.equal(coerceBypassChance("decrement"), false);
  assert.equal(coerceBypassChance(42), false);
});

test("migrateUniqueLinePickerWidgets keeps boolean-as-int with seed", () => {
  assert.deepEqual(
    migrateUniqueLinePickerWidgets({ widgets_values: [0, 42] }),
    [false, 42],
  );
  assert.deepEqual(
    migrateUniqueLinePickerWidgets({ widgets_values: [1, 42] }),
    [true, 42],
  );
});

test("migrateUniqueLinePickerWidgets leaves current boolean format unchanged", () => {
  assert.equal(
    migrateUniqueLinePickerWidgets({ widgets_values: [false, 42] }),
    null,
  );
  assert.equal(
    migrateUniqueLinePickerWidgets({ widgets_values: [true, 42] }),
    null,
  );
});

test("migrateUniqueLinePickerWidgets handles legacy seed and smeared control mode", () => {
  assert.deepEqual(
    migrateUniqueLinePickerWidgets({ widgets_values: [42] }),
    [false, 42],
  );
  assert.deepEqual(
    migrateUniqueLinePickerWidgets({ widgets_values: [42, "randomize"] }),
    [false, 42],
  );
});

test("parseUniqueLinePickerWidgetValues reads migrated and current layouts", () => {
  assert.deepEqual(parseUniqueLinePickerWidgetValues([false, 42]), {
    bypass_chance: false,
    seed: 42,
  });
  assert.deepEqual(parseUniqueLinePickerWidgetValues([true, 42]), {
    bypass_chance: true,
    seed: 42,
  });
  assert.deepEqual(parseUniqueLinePickerWidgetValues([0, 42]), {
    bypass_chance: false,
    seed: 42,
  });
  assert.deepEqual(parseUniqueLinePickerWidgetValues([1, 42]), {
    bypass_chance: true,
    seed: 42,
  });
  assert.deepEqual(parseUniqueLinePickerWidgetValues([42, "randomize"]), {
    bypass_chance: false,
    seed: 42,
  });
});

test("parseSeededTextPoolWidgetValues coerces smeared bypass slot", () => {
  assert.deepEqual(
    parseSeededTextPoolWidgetValues(["alice\nbob", "randomize", 7]),
    {
      pool_text: "alice\nbob",
      bypass_chance: false,
      seed: 7,
    },
  );
  assert.deepEqual(
    parseSeededTextPoolWidgetValues(["pool", true, 99]),
    {
      pool_text: "pool",
      bypass_chance: true,
      seed: 99,
    },
  );
});
