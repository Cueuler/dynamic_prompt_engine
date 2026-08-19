/** Pure helpers for Routing Switch chance restore (no ComfyUI imports). */

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

function parseChancesByWidgetNames(widgetsValues, widgetNames) {
  const chances = {};
  for (let i = 0; i < widgetNames.length; i++) {
    const name = widgetNames[i];
    const value = widgetsValues[i];
    if (Number.isInteger(chanceIndexFromName(name)) && CHANCE_OPTIONS.includes(value)) {
      chances[name] = value;
    }
  }
  return chances;
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

/**
 * Map positional widgets_values onto chance_N names.
 *
 * Save order is chance combos (connected slots, sorted).
 */
export function parseRoutingSwitchWidgetValues(widgetsValues, options = {}) {
  if (!Array.isArray(widgetsValues) || widgetsValues.length === 0) {
    return { chances: {} };
  }

  const connectedIndices = Array.isArray(options.connectedIndices)
    ? options.connectedIndices
    : [];
  const widgetNames = Array.isArray(options.widgetNames)
    ? options.widgetNames
    : [];

  if (widgetNames.length === widgetsValues.length && widgetNames.length > 0) {
    const namedChances = parseChancesByWidgetNames(widgetsValues, widgetNames);
    if (Object.keys(namedChances).length > 0) {
      return { chances: namedChances };
    }
  }

  return {
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
    if (parsed.chances[widget.name]) {
      widget.value = parsed.chances[widget.name];
    }
  }
}
