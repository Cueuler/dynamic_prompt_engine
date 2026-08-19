/** Pure helpers for bypass_chance widget restore (no ComfyUI imports). */

export const SEED_CONTROL_MODES = new Set([
  "fixed",
  "increment",
  "decrement",
  "randomize",
  "increment-wrap",
]);

/** Only explicit on-states count as 50%; smeared seed/control strings stay Off. */
export function coerceBypassChance(value) {
  if (value === true || value === 1 || value === "50%") {
    return true;
  }
  return false;
}

export function isSeedControlMode(value) {
  return typeof value === "string" && SEED_CONTROL_MODES.has(value);
}

/**
 * UniqueLinePicker used to expose only a seed widget. Inserting bypass_chance
 * before seed would otherwise steal the saved seed value.
 *
 * Legacy: [seed] or [seed, controlMode] -> [false, seed]
 * Boolean-as-int: [0|1, seed, ...] -> [false|true, seed, ...]
 */
export function migrateUniqueLinePickerWidgets(info) {
  const wv = info?.widgets_values;
  if (!Array.isArray(wv) || wv.length === 0) {
    return null;
  }

  if (typeof wv[0] === "boolean") {
    return null;
  }

  if ((wv[0] === 0 || wv[0] === 1) && typeof wv[1] === "number") {
    const migrated = [coerceBypassChance(wv[0]), wv[1]];
    if (wv.length > 2 && isSeedControlMode(wv[2])) {
      migrated.push(wv[2]);
    }
    return migrated;
  }

  if (typeof wv[0] === "number") {
    if (wv.length === 1) {
      return [false, wv[0]];
    }
    if (isSeedControlMode(wv[1])) {
      return [false, wv[0]];
    }
    if (wv[0] > 1) {
      return [false, wv[0]];
    }
  }

  return null;
}

export function parseUniqueLinePickerWidgetValues(widgetsValues) {
  if (!Array.isArray(widgetsValues) || widgetsValues.length === 0) {
    return { bypass_chance: false, seed: 0 };
  }

  const migrated = migrateUniqueLinePickerWidgets({ widgets_values: widgetsValues });
  const normalized = migrated ?? widgetsValues;

  if (
    typeof normalized[0] === "boolean" ||
    normalized[0] === 0 ||
    normalized[0] === 1
  ) {
    return {
      bypass_chance: coerceBypassChance(normalized[0]),
      seed: typeof normalized[1] === "number" ? normalized[1] : 0,
    };
  }

  if (typeof normalized[0] === "number") {
    return {
      bypass_chance: false,
      seed: normalized[0],
    };
  }

  return { bypass_chance: false, seed: 0 };
}

export function parseSeededTextPoolWidgetValues(widgetsValues) {
  if (!Array.isArray(widgetsValues) || widgetsValues.length === 0) {
    return { pool_text: "", bypass_chance: false, seed: 0 };
  }

  if (typeof widgetsValues[0] === "string") {
    return {
      pool_text: widgetsValues[0],
      bypass_chance: coerceBypassChance(widgetsValues[1]),
      seed: typeof widgetsValues[2] === "number" ? widgetsValues[2] : 0,
    };
  }

  return { pool_text: "", bypass_chance: false, seed: 0 };
}

function setWidgetValue(widget, value) {
  if (!widget) {
    return;
  }
  widget.value = value;
  if (widget.inputEl && typeof widget.inputEl.value === "string") {
    widget.inputEl.value = String(value);
  }
}

export function pinUniqueLinePickerWidgets(node, widgetsValues) {
  const parsed = parseUniqueLinePickerWidgetValues(widgetsValues);
  for (const widget of node.widgets ?? []) {
    if (widget.name === "bypass_chance") {
      setWidgetValue(widget, parsed.bypass_chance);
    } else if (widget.name === "seed") {
      setWidgetValue(widget, parsed.seed);
    }
  }
  node.setDirtyCanvas?.(true, true);
}

export function pinSeededTextPoolWidgets(node, widgetsValues) {
  const parsed = parseSeededTextPoolWidgetValues(widgetsValues);
  for (const widget of node.widgets ?? []) {
    if (widget.name === "pool_text") {
      setWidgetValue(widget, parsed.pool_text);
    } else if (widget.name === "bypass_chance") {
      setWidgetValue(widget, parsed.bypass_chance);
    } else if (widget.name === "seed") {
      setWidgetValue(widget, parsed.seed);
    }
  }
  node.setDirtyCanvas?.(true, true);
}

/** Fix a smeared toggle without re-reading stale positional storage. */
export function coerceLiveBypassWidget(node) {
  const bypass = (node.widgets ?? []).find((w) => w.name === "bypass_chance");
  if (bypass) {
    setWidgetValue(bypass, coerceBypassChance(bypass.value));
  }
}

export function collectUniqueLinePickerWidgetValues(node) {
  const widgets = node.widgets ?? [];
  const bypass = widgets.find((w) => w.name === "bypass_chance");
  const seed = widgets.find((w) => w.name === "seed");
  return [
    coerceBypassChance(bypass?.value),
    typeof seed?.value === "number" ? seed.value : 0,
  ];
}

export function collectSeededTextPoolWidgetValues(node) {
  const widgets = node.widgets ?? [];
  const pool = widgets.find((w) => w.name === "pool_text");
  const bypass = widgets.find((w) => w.name === "bypass_chance");
  const seed = widgets.find((w) => w.name === "seed");
  return [
    pool?.value ?? "",
    coerceBypassChance(bypass?.value),
    typeof seed?.value === "number" ? seed.value : 0,
  ];
}
