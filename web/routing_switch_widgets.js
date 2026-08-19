/** Pure helpers for Routing Switch chance/seed restore (no ComfyUI imports). */

export const CHANCE_OPTIONS = ["Default", "Off", "1.5x", "2x"];

function chanceIndexFromName(name) {
  if (typeof name !== "string" || !name.startsWith("chance_")) {
    return Number.NaN;
  }
  const suffix = name.slice("chance_".length);
  return /^\d+$/.test(suffix) ? Number.parseInt(suffix, 10) : Number.NaN;
}

export function routingInputIndex(name) {
  if (typeof name !== "string" || !name.startsWith("input_")) {
    return Number.NaN;
  }
  const suffix = name.slice("input_".length);
  return /^\d+$/.test(suffix) ? Number.parseInt(suffix, 10) : Number.NaN;
}

export function connectedRoutingIndicesFromInputs(inputs) {
  const indices = [];
  for (const input of inputs ?? []) {
    const index = routingInputIndex(input?.name);
    if (Number.isInteger(index) && input.link != null) {
      indices.push(index);
    }
  }
  return [...new Set(indices)].sort((a, b) => a - b);
}

function readSeedValue(value) {
  if (typeof value === "number") {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === "number") {
    return value[0];
  }
  return null;
}

function parseChancesByWidgetNames(widgetsValues, widgetNames) {
  const chances = {};
  let seed = null;
  for (let i = 0; i < widgetNames.length; i++) {
    const name = widgetNames[i];
    const value = widgetsValues[i];
    if (name === "seed") {
      const parsedSeed = readSeedValue(value);
      if (parsedSeed != null) {
        seed = parsedSeed;
      }
      continue;
    }
    if (Number.isInteger(chanceIndexFromName(name)) && CHANCE_OPTIONS.includes(value)) {
      chances[name] = value;
    }
  }
  return { seed, chances };
}

function parseChancesByConnectedIndices(widgetsValues, connectedIndices) {
  const chances = {};
  const chanceValues = widgetsValues.filter((value) =>
    CHANCE_OPTIONS.includes(value),
  );
  for (let i = 0; i < connectedIndices.length && i < chanceValues.length; i++) {
    chances[`chance_${connectedIndices[i]}`] = chanceValues[i];
  }
  return chances;
}

function parseSeedFromValues(widgetsValues) {
  for (const value of widgetsValues) {
    const seed = readSeedValue(value);
    if (seed != null) {
      return seed;
    }
  }
  return 0;
}

/**
 * Map positional widgets_values onto chance_N names.
 *
 * Save order is chance combos (connected slots, sorted) then seed + control.
 * Zip chance option strings with saved connected input indices so a hole
 * (input_0 + input_2) does not donate 2x to chance_1.
 */
export function parseRoutingSwitchWidgetValues(widgetsValues, options = {}) {
  if (!Array.isArray(widgetsValues) || widgetsValues.length === 0) {
    return { seed: 0, chances: {} };
  }

  const connectedIndices = Array.isArray(options.connectedIndices)
    ? options.connectedIndices
    : [];
  const widgetNames = Array.isArray(options.widgetNames)
    ? options.widgetNames
    : [];

  if (widgetNames.length === widgetsValues.length && widgetNames.length > 0) {
    const named = parseChancesByWidgetNames(widgetsValues, widgetNames);
    const namedChanceCount = Object.keys(named.chances).length;
    if (namedChanceCount > 0) {
      return {
        seed: named.seed != null ? named.seed : parseSeedFromValues(widgetsValues),
        chances: named.chances,
      };
    }
  }

  return {
    seed: parseSeedFromValues(widgetsValues),
    chances: parseChancesByConnectedIndices(widgetsValues, connectedIndices),
  };
}

export function applyParsedRoutingSwitchWidgets(node, parsed) {
  if (!parsed) {
    return;
  }
  node.__dpeChanceSaved = {
    ...(node.__dpeChanceSaved || {}),
    ...parsed.chances,
  };
  for (const widget of node.widgets ?? []) {
    if (widget.name === "seed" && typeof parsed.seed === "number") {
      widget.value = parsed.seed;
    } else if (parsed.chances[widget.name]) {
      widget.value = parsed.chances[widget.name];
    }
  }
}
