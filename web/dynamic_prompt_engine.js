import { app } from "../../scripts/app.js";

const OUTPUT_WIDTH = 160;
const OUTPUT_HEIGHT = 80;
const PREVIEW_PLACEHOLDER = "Joined prompt preview (empty until run)…";
const CLIP_REPORT_PREVIEW = "report_preview";
const CLIP_REPORT_PLACEHOLDER = "Token report preview (empty until run)…";

function graphOf(node) {
  return node.graph ?? app.graph;
}

function connectedNodeTitle(node, input) {
  if (input?.link == null) {
    return null;
  }
  const graph = graphOf(node);
  const link = graph?.links?.[input.link];
  if (!link) {
    return null;
  }
  const origin = graph.getNodeById?.(link.origin_id);
  if (!origin) {
    return null;
  }
  const title = typeof origin.title === "string" ? origin.title.trim() : origin.title;
  return title || null;
}

function createDynamicSocketHelpers(prefix, maxCount = Number.POSITIVE_INFINITY) {
  function slotNumber(name) {
    const suffix = typeof name === "string" ? name.slice(prefix.length) : "";
    if (!/^\d+$/.test(suffix)) {
      return Number.NaN;
    }
    return Number.parseInt(suffix, 10);
  }

  function isDynamicInput(input) {
    return input?.name?.startsWith(prefix);
  }

  function inputName(index) {
    return `${prefix}${index}`;
  }

  function removeInputSlot(node, input) {
    const index = node.inputs?.indexOf(input) ?? -1;
    if (index < 0) {
      return;
    }
    node.removeInput(index);
  }

  function refreshInputLabels(node) {
    let changed = false;
    for (const input of node.inputs ?? []) {
      if (!isDynamicInput(input)) {
        continue;
      }
      const title = connectedNodeTitle(node, input);
      const nextLabel = title || undefined;
      if (input.label !== nextLabel) {
        input.label = nextLabel;
        changed = true;
      }
    }
    if (changed) {
      graphOf(node)?.setDirtyCanvas?.(true, false);
    }
  }

  function visibleCount(node) {
    const slots = (node.inputs ?? []).filter(isDynamicInput);
    const highestConnected = slots.reduce((highest, input) => {
      if (input.link == null) {
        return highest;
      }
      const index = slotNumber(input.name);
      return Number.isInteger(index) ? Math.max(highest, index) : highest;
    }, -1);
    // Connected slot + one spare; none connected → a single empty socket.
    return Math.min(maxCount, Math.max(1, highestConnected + 2));
  }

  function setVisibleInputs(node, count) {
    const byIndex = new Map();
    for (const input of node.inputs ?? []) {
      if (!isDynamicInput(input)) {
        continue;
      }
      const index = slotNumber(input.name);
      if (Number.isInteger(index)) {
        byIndex.set(index, input);
      }
    }

    for (const [index, input] of [...byIndex.entries()]) {
      if (index < maxCount) {
        continue;
      }
      if (input?.link != null) {
        graphOf(node)?.removeLink?.(input.link);
      }
      removeInputSlot(node, input);
      byIndex.delete(index);
    }

    for (const [index, input] of [...byIndex.entries()]) {
      if (index >= count && input.link == null) {
        removeInputSlot(node, input);
        byIndex.delete(index);
      }
    }

    for (let index = 0; index < count; index++) {
      if (!byIndex.has(index)) {
        node.addInput(inputName(index), "STRING");
      }
    }
    refreshInputLabels(node);
  }

  return {
    isDynamicInput,
    refreshInputLabels,
    visibleCount,
    setVisibleInputs,
  };
}

const MAX_BRANCHES = 15;
const tagSockets = createDynamicSocketHelpers("tag_");
const branchSockets = createDynamicSocketHelpers("branch_", MAX_BRANCHES);
const inputSockets = createDynamicSocketHelpers("input_", MAX_BRANCHES);
const routingSockets = createDynamicSocketHelpers("input_");
const CHANCE_OPTIONS = ["Default", "Off", "1.5x", "2x"];

const PREVIEW_DOM_INSET = 24;
const PREVIEW_CHROME_PAD = 24;

function slotHeight() {
  return globalThis.LiteGraph?.NODE_SLOT_HEIGHT ?? 20;
}

function titleHeight() {
  return globalThis.LiteGraph?.NODE_TITLE_HEIGHT ?? 30;
}

function widgetRowHeight() {
  return globalThis.LiteGraph?.NODE_WIDGET_HEIGHT ?? 20;
}

/** Expand to ComfyUI/LiteGraph computed size; never force custom mins or shrink. */
function applyDefaultComputedSize(node) {
  if (typeof node.computeSize !== "function") {
    return;
  }
  const computed = node.computeSize();
  if (!computed) {
    return;
  }
  node.setSize([
    Math.max(computed[0] ?? 0, node.size?.[0] ?? 0),
    Math.max(computed[1] ?? 0, node.size?.[1] ?? 0),
  ]);
}

/** Preview widget by name — Tag Join uses "text"; CLIP Token Report uses "report_preview". */
function previewWidget(node, name = "text") {
  return (node.widgets ?? []).find((widget) => widget?.name === name) ?? null;
}

function ensurePreviewComputeSize(widget) {
  if (widget.__dpePreviewSized) {
    return;
  }
  widget.__dpePreviewSized = true;
  if (widget.__dpePreviewHeight == null) {
    widget.__dpePreviewHeight = OUTPUT_HEIGHT;
  }
  widget.computeSize = function (width) {
    const w =
      typeof width === "number" && width > 0
        ? width
        : Math.max(OUTPUT_WIDTH, widget.__dpePreviewWidth ?? OUTPUT_WIDTH);
    return [w, Math.max(OUTPUT_HEIGHT, widget.__dpePreviewHeight ?? OUTPUT_HEIGHT)];
  };
}

function otherWidgetsHeight(node, preview) {
  let height = 0;
  const nodeWidth = node.size?.[0] ?? OUTPUT_WIDTH;
  for (const widget of node.widgets ?? []) {
    if (!widget || widget === preview) {
      continue;
    }
    const size = widget.computeSize?.(nodeWidth);
    height += size?.[1] ?? widgetRowHeight();
  }
  return height;
}

function isWidgetBoundInput(input) {
  return input?.widget != null || input?.name === "text";
}

function freeSocketRowCount(node) {
  const freeIn = (node.inputs ?? []).filter((i) => !isWidgetBoundInput(i)).length;
  const freeOut = (node.outputs ?? []).length;
  return Math.max(freeIn, freeOut);
}

function availablePreviewHeight(node, preview) {
  const chrome =
    titleHeight() +
    freeSocketRowCount(node) * slotHeight() +
    otherWidgetsHeight(node, preview) +
    PREVIEW_CHROME_PAD;
  const nodeH = node.size?.[1] ?? OUTPUT_HEIGHT;
  return Math.max(OUTPUT_HEIGHT, nodeH - chrome);
}

function measureContentHeight(inputEl) {
  const previous = inputEl.style.height;
  inputEl.style.height = "0px";
  const measured = inputEl.scrollHeight;
  inputEl.style.height = previous;
  return Math.max(OUTPUT_HEIGHT, measured);
}

function previewDomWidth(node) {
  return Math.max(
    OUTPUT_WIDTH,
    (node.size?.[0] ?? OUTPUT_WIDTH) - PREVIEW_DOM_INSET,
  );
}

function syncPreviewDom(node, widget) {
  const width = previewDomWidth(node);
  const height = Math.max(OUTPUT_HEIGHT, widget.__dpePreviewHeight ?? OUTPUT_HEIGHT);
  widget.__dpePreviewWidth = width;
  widget.computedHeight = height;
  widget.inputEl.style.width = `${width}px`;
  widget.inputEl.style.height = `${height}px`;
}

function stylePreviewWidget(node, name = "text", placeholder = PREVIEW_PLACEHOLDER) {
  const widget = previewWidget(node, name);
  if (!widget?.inputEl) {
    return;
  }
  widget.inputEl.readOnly = true;
  widget.inputEl.style.opacity = "0.85";
  widget.inputEl.style.minWidth = `${OUTPUT_WIDTH}px`;
  widget.inputEl.style.minHeight = `${OUTPUT_HEIGHT}px`;
  widget.inputEl.style.maxWidth = "none";
  widget.inputEl.style.maxHeight = "none";
  widget.inputEl.style.resize = "none";
  if (!widget.inputEl.placeholder) {
    widget.inputEl.placeholder = placeholder;
  }
  ensurePreviewComputeSize(widget);
}

/**
 * @param {"content"|"resize"} mode
 *   content — height from textarea scrollHeight (grow with joined text)
 *   resize  — height from remaining node space (manual drag)
 */
function fitPreviewWidget(node, mode = "content", name = "text") {
  const widget = previewWidget(node, name);
  if (!widget?.inputEl) {
    return;
  }
  const placeholder = name === CLIP_REPORT_PREVIEW ? CLIP_REPORT_PLACEHOLDER : PREVIEW_PLACEHOLDER;
  stylePreviewWidget(node, name, placeholder);
  // Width first so scrollHeight reflects the correct wrap width.
  const width = previewDomWidth(node);
  widget.inputEl.style.width = `${width}px`;
  widget.__dpePreviewWidth = width;
  if (mode === "resize") {
    widget.__dpePreviewHeight = availablePreviewHeight(node, widget);
  } else {
    widget.__dpePreviewHeight = measureContentHeight(widget.inputEl);
  }
  syncPreviewDom(node, widget);
}

function setPreviewValue(node, text, name = "text") {
  const widget = previewWidget(node, name);
  if (!widget) {
    return;
  }
  const placeholder = name === CLIP_REPORT_PREVIEW ? CLIP_REPORT_PLACEHOLDER : PREVIEW_PLACEHOLDER;
  const value = Array.isArray(text) ? (text[0] ?? "") : (text ?? "");
  widget.value = value;
  if (widget.inputEl) {
    widget.inputEl.value = value;
  }
  stylePreviewWidget(node, name, placeholder);
  fitPreviewWidget(node, "content", name);
  applyDefaultComputedSize(node);
  graphOf(node)?.setDirtyCanvas?.(true, false);
}

function registerDynamicStringNode(nodeType, sockets, options = {}) {
  const { withOutputPreview = false, afterLayout = null } = options;

  function runLayout(node) {
    sockets.setVisibleInputs(node, sockets.visibleCount(node));
    sockets.refreshInputLabels(node);
    afterLayout?.(node);
    if (withOutputPreview) {
      stylePreviewWidget(node);
      fitPreviewWidget(node, "content");
    }
    applyDefaultComputedSize(node);
  }

  const originalCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const result = originalCreated?.apply(this, arguments);
    queueMicrotask(() => {
      runLayout(this);
    });
    return result;
  };

  if (withOutputPreview) {
    const originalOnResize = nodeType.prototype.onResize;
    nodeType.prototype.onResize = function () {
      const result = originalOnResize?.apply(this, arguments);
      fitPreviewWidget(this, "resize");
      return result;
    };

    const originalOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      originalOnConfigure?.apply(this, arguments);
      requestAnimationFrame(() => {
        runLayout(this);
      });
    };

    const originalExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      const result = originalExecuted?.apply(this, arguments);
      setPreviewValue(this, message?.text);
      return result;
    };
  } else {
    const originalOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      originalOnConfigure?.apply(this, arguments);
      requestAnimationFrame(() => {
        runLayout(this);
      });
    };
  }

  const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
  nodeType.prototype.onConnectionsChange = function () {
    const result = originalConnectionsChange?.apply(this, arguments);
    queueMicrotask(() => {
      runLayout(this);
    });
    return result;
  };
}

function chanceWidgetName(index) {
  return `chance_${index}`;
}

function spacerWidgetName(index) {
  return `__spacer_${index}`;
}

function isChanceWidget(widget) {
  return typeof widget?.name === "string" && /^chance_\d+$/.test(widget.name);
}

function isSpacerWidget(widget) {
  return typeof widget?.name === "string" && /^__spacer_\d+$/.test(widget.name);
}

function routingInputIndex(name) {
  if (typeof name !== "string" || !name.startsWith("input_")) {
    return Number.NaN;
  }
  const suffix = name.slice("input_".length);
  return /^\d+$/.test(suffix) ? Number.parseInt(suffix, 10) : Number.NaN;
}

function removeNodeWidget(node, widget) {
  if (!widget) {
    return;
  }
  if (typeof node.removeWidget === "function") {
    node.removeWidget(widget);
    return;
  }
  const index = node.widgets?.indexOf(widget) ?? -1;
  if (index >= 0) {
    node.widgets.splice(index, 1);
  }
}

function ensureSpacerWidget(node, index) {
  const name = spacerWidgetName(index);
  const existing = (node.widgets ?? []).find((widget) => widget.name === name);
  if (existing) {
    return existing;
  }
  const spacer = {
    name,
    type: "spacer",
    value: "",
    serialize: false,
    computeSize(width) {
      return [typeof width === "number" && width > 0 ? width : 200, slotHeight()];
    },
    draw() {},
  };
  if (!Array.isArray(node.widgets)) {
    node.widgets = [];
  }
  node.widgets.push(spacer);
  return spacer;
}

function ensureChanceWidget(node, index, savedValue) {
  const name = chanceWidgetName(index);
  const existing = (node.widgets ?? []).find((widget) => widget.name === name);
  if (existing) {
    return existing;
  }
  const value =
    typeof savedValue === "string" && CHANCE_OPTIONS.includes(savedValue)
      ? savedValue
      : "Default";
  return node.addWidget("combo", name, value, () => {}, {
    values: CHANCE_OPTIONS,
  });
}

function orderRoutingSwitchWidgets(node) {
  const widgets = node.widgets ?? [];
  const seed = widgets.filter((widget) => widget.name === "seed");
  const rest = widgets.filter(
    (widget) =>
      widget.name !== "seed" &&
      !isChanceWidget(widget) &&
      !isSpacerWidget(widget),
  );
  const indices = new Set();
  for (const widget of widgets) {
    if (isChanceWidget(widget)) {
      indices.add(Number.parseInt(widget.name.slice("chance_".length), 10));
    }
    if (isSpacerWidget(widget)) {
      indices.add(Number.parseInt(widget.name.slice("__spacer_".length), 10));
    }
  }
  const ordered = [];
  for (const index of [...indices].sort((a, b) => a - b)) {
    const spacer = widgets.find((widget) => widget.name === spacerWidgetName(index));
    const chance = widgets.find((widget) => widget.name === chanceWidgetName(index));
    if (spacer) {
      ordered.push(spacer);
    }
    if (chance) {
      ordered.push(chance);
    }
  }
  node.widgets = [...seed, ...ordered, ...rest];
}

function layoutRoutingSwitchSlots(node) {
  const title = titleHeight();
  let y = title;
  const seed = (node.widgets ?? []).find((widget) => widget.name === "seed");
  if (seed) {
    const size = seed.computeSize?.(node.size?.[0] ?? 240);
    y += size?.[1] ?? widgetRowHeight();
  }
  for (const input of node.inputs ?? []) {
    const index = routingInputIndex(input.name);
    if (!Number.isInteger(index)) {
      continue;
    }
    const row = slotHeight();
    input.pos = [0, y + row * 0.5];
    y += row;
    if (input.link != null) {
      y += widgetRowHeight();
    }
  }
  const right = node.size?.[0] ?? 240;
  if (node.outputs?.[0]) {
    node.outputs[0].pos = [right, title + widgetRowHeight() * 0.5];
  }
  if (node.outputs?.[1]) {
    node.outputs[1].pos = [
      right,
      title + widgetRowHeight() + slotHeight() * 0.5,
    ];
  }
}

function computeRoutingSwitchSize(node) {
  const minWidth = 240;
  let height = titleHeight() + 8;
  const width = node.size?.[0] ?? minWidth;
  for (const widget of node.widgets ?? []) {
    if (widget.hidden) {
      continue;
    }
    const size = widget.computeSize?.(width);
    height += size?.[1] ?? widgetRowHeight();
  }
  return [Math.max(minWidth, width), height];
}

function applyRoutingSwitchWidgetValues(node, widgetsValues) {
  if (!Array.isArray(widgetsValues) || widgetsValues.length === 0) {
    return;
  }
  const seed = (node.widgets ?? []).find((widget) => widget.name === "seed");
  if (seed) {
    const first = widgetsValues[0];
    if (typeof first === "number") {
      seed.value = first;
    } else if (Array.isArray(first) && typeof first[0] === "number") {
      seed.value = first[0];
    }
  }
  const chanceValues = widgetsValues.filter((value) =>
    CHANCE_OPTIONS.includes(value),
  );
  const chances = (node.widgets ?? [])
    .filter(isChanceWidget)
    .sort(
      (a, b) =>
        Number.parseInt(a.name.slice("chance_".length), 10) -
        Number.parseInt(b.name.slice("chance_".length), 10),
    );
  for (let i = 0; i < chances.length && i < chanceValues.length; i++) {
    chances[i].value = chanceValues[i];
  }
}

function syncRoutingSwitchChances(node) {
  node.__dpeChanceSaved = node.__dpeChanceSaved || {};
  for (const widget of node.widgets ?? []) {
    if (isChanceWidget(widget)) {
      node.__dpeChanceSaved[widget.name] = widget.value;
    }
  }

  const wanted = new Set();
  const connected = new Set();
  for (const input of node.inputs ?? []) {
    const index = routingInputIndex(input.name);
    if (!Number.isInteger(index)) {
      continue;
    }
    wanted.add(index);
    if (input.link != null) {
      connected.add(index);
    }
  }

  for (const widget of [...(node.widgets ?? [])]) {
    if (isChanceWidget(widget)) {
      const index = Number.parseInt(widget.name.slice("chance_".length), 10);
      if (!connected.has(index)) {
        removeNodeWidget(node, widget);
      }
    } else if (isSpacerWidget(widget)) {
      const index = Number.parseInt(widget.name.slice("__spacer_".length), 10);
      if (!wanted.has(index)) {
        removeNodeWidget(node, widget);
      }
    }
  }

  for (const index of [...wanted].sort((a, b) => a - b)) {
    ensureSpacerWidget(node, index);
    if (connected.has(index)) {
      ensureChanceWidget(
        node,
        index,
        node.__dpeChanceSaved[chanceWidgetName(index)],
      );
    }
  }

  orderRoutingSwitchWidgets(node);
  node.widgets_start_y = titleHeight();
  layoutRoutingSwitchSlots(node);
}

function registerRoutingSwitch(nodeType) {
  registerDynamicStringNode(nodeType, routingSockets, {
    afterLayout: (node) => {
      const pending = node.__dpeRoutingWidgets;
      syncRoutingSwitchChances(node);
      if (pending) {
        applyRoutingSwitchWidgetValues(node, pending);
        delete node.__dpeRoutingWidgets;
      }
      const size = computeRoutingSwitchSize(node);
      node.setSize([
        Math.max(size[0], node.size?.[0] ?? 0),
        Math.max(size[1], node.size?.[1] ?? 0),
      ]);
    },
  });

  nodeType.prototype.computeSize = function () {
    return computeRoutingSwitchSize(this);
  };

  const originalConfigure = nodeType.prototype.onConfigure;
  nodeType.prototype.onConfigure = function (info) {
    if (Array.isArray(info?.widgets_values)) {
      this.__dpeRoutingWidgets = [...info.widgets_values];
    }
    originalConfigure?.apply(this, arguments);
  };
}

function registerCLIPTokenReport(nodeType) {
  function ensureReportPreviewWidget(node) {
    let widget = previewWidget(node, CLIP_REPORT_PREVIEW);
    if (widget) {
      return widget;
    }
    widget = node.addWidget("text", CLIP_REPORT_PREVIEW, "", () => {}, {
      multiline: true,
    });
    widget.serialize = false;
    return widget;
  }

  function runLayout(node) {
    ensureReportPreviewWidget(node);
    stylePreviewWidget(node, CLIP_REPORT_PREVIEW, CLIP_REPORT_PLACEHOLDER);
    fitPreviewWidget(node, "content", CLIP_REPORT_PREVIEW);
    applyDefaultComputedSize(node);
  }

  const originalCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const result = originalCreated?.apply(this, arguments);
    queueMicrotask(() => {
      runLayout(this);
    });
    return result;
  };

  const originalOnResize = nodeType.prototype.onResize;
  nodeType.prototype.onResize = function () {
    const result = originalOnResize?.apply(this, arguments);
    fitPreviewWidget(this, "resize", CLIP_REPORT_PREVIEW);
    return result;
  };

  const originalOnConfigure = nodeType.prototype.onConfigure;
  nodeType.prototype.onConfigure = function () {
    originalOnConfigure?.apply(this, arguments);
    requestAnimationFrame(() => {
      runLayout(this);
    });
  };

  const originalExecuted = nodeType.prototype.onExecuted;
  nodeType.prototype.onExecuted = function (message) {
    const result = originalExecuted?.apply(this, arguments);
    setPreviewValue(this, message?.text, CLIP_REPORT_PREVIEW);
    return result;
  };
}

const ENGINE_NODE_NAMES = new Set([
  "SeededTextPool",
  "RoutingSwitch",
  "BranchRandomSwitcher",
  "TagJoin",
  "BranchSelector",
]);

function expectedOutputCount(nodeData) {
  if (Array.isArray(nodeData?.output)) {
    return nodeData.output.length;
  }
  if (Array.isArray(nodeData?.output_name)) {
    return nodeData.output_name.length;
  }
  return null;
}

/**
 * Saved workflows may still carry phantom outputs (e.g. TagJoin "seed") from older
 * UI experiments. Those slots are not in RETURN_TYPES, so links to them crash
 * validation with "tuple index out of range".
 */
function syncNodeOutputsToSchema(node, nodeData) {
  const expected = expectedOutputCount(nodeData);
  if (expected == null || !Array.isArray(node.outputs)) {
    return;
  }
  while (node.outputs.length > expected) {
    const index = node.outputs.length - 1;
    const output = node.outputs[index];
    if (output?.links?.length) {
      for (const linkId of [...output.links]) {
        graphOf(node)?.removeLink?.(linkId);
      }
    }
    node.removeOutput(index);
  }
}

function looksLikeSeparator(value) {
  return typeof value === "string" && /^[\s,]*$/.test(value);
}

/** Drop widgets removed from the Python schema (e.g. TagJoin separator). */
function stripUnknownWidgets(node, nodeData) {
  if (nodeData?.name !== "TagJoin" || !Array.isArray(node.widgets)) {
    return;
  }
  const text = previewWidget(node);
  for (let i = node.widgets.length - 1; i >= 0; i--) {
    const widget = node.widgets[i];
    if (widget?.name !== "separator") {
      continue;
    }
    if (
      text &&
      looksLikeSeparator(text.value) &&
      typeof widget.value === "string" &&
      !looksLikeSeparator(widget.value)
    ) {
      text.value = widget.value;
      if (text.inputEl && typeof text.inputEl.value === "string") {
        text.inputEl.value = String(widget.value);
      }
    }
    if (typeof node.removeWidget === "function") {
      node.removeWidget(widget);
    } else {
      node.widgets.splice(i, 1);
    }
  }
}

/**
 * Normalize TagJoin widget values saved by older workflow versions that had a
 * separator widget. Returns `[prompt]` or null when already in the current format.
 */
function migrateTagJoinWidgets(info) {
  const wv = info?.widgets_values;
  if (!Array.isArray(wv) || wv.length !== 2) {
    return null;
  }
  if (typeof wv[0] !== "string" || typeof wv[1] !== "string") {
    return null;
  }
  const firstSep = looksLikeSeparator(wv[0]);
  const secondSep = looksLikeSeparator(wv[1]);
  if (firstSep && !secondSep) {
    return [wv[1]];
  }
  if (secondSep && !firstSep) {
    return [wv[0]];
  }
  return null;
}

/**
 * Normalize SeededTextPool widget values saved by older workflow versions.
 * Returns the converted [pool_text, bypass_chance, seed] array, or null when
 * the values are already in the current format.
 *
 * Known legacy layouts:
 *
 *   2-element:     [stream_key, pool_text]
 *   4-element A:   [stream_key, pool_text, bypass_chance (bool), seed (int)]
 *   4-element B:   [stream_key, pool_text, seed (int), seed_mode (str)]
 *   5-element C:   [stream_key, pool_text, bypass_chance (bool), seed, seed_mode]
 *   5-element D:   [stream_key, pool_text, seed (int), seed_mode (str), extra (str)]
 */
function migrateSeededTextPoolWidgets(info) {
  const wv = info?.widgets_values;
  if (!Array.isArray(wv)) {
    return null;
  }
  if (typeof wv[0] !== "string" || typeof wv[1] !== "string") {
    return null;
  }
  // Legacy 2-element: [stream_key, pool_text] -> [pool_text, false, 0]
  if (wv.length === 2) {
    return [wv[1], false, 0];
  }
  // Legacy 4-element
  if (wv.length === 4) {
    // Format A: [stream_key, pool_text, bypass_chance (bool), seed] -> [pool_text, bypass_chance, seed]
    if (typeof wv[2] === "boolean") {
      return [wv[1], wv[2], wv[3]];
    }
    // Format B: [stream_key, pool_text, seed, seed_mode (str)] -> [pool_text, false, seed]
    if (typeof wv[3] === "string") {
      return [wv[1], false, wv[2]];
    }
  }
  // Legacy 5-element: old ComfyUI seed widget stores [value, mode]
  if (wv.length === 5) {
    // Format C: [stream_key, pool_text, bypass_chance (bool), seed, seed_mode] -> [pool_text, bypass_chance, seed]
    if (typeof wv[2] === "boolean") {
      const seed = typeof wv[3] === "number" ? wv[3] : 0;
      return [wv[1], wv[2], seed];
    }
    // Format D: [stream_key, pool_text, seed, seed_mode (str), extra (str)] -> [pool_text, false, seed]
    if (typeof wv[2] === "number" && typeof wv[3] === "string") {
      return [wv[1], false, wv[2]];
    }
  }
  return null;
}

/** Push migrated values into the already-created widgets and their DOM elements. */
function applyMigratedWidgetValues(node, values) {
  if (!values) {
    return;
  }
  for (let index = 0; index < values.length; index++) {
    const widget = node.widgets?.[index];
    if (!widget) {
      continue;
    }
    widget.value = values[index];
    if (widget.inputEl && typeof widget.inputEl.value === "string") {
      widget.inputEl.value = String(values[index]);
    }
  }
  node.setDirtyCanvas?.(true, true);
}

function registerSchemaSync(nodeType, nodeData) {
  const originalCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const result = originalCreated?.apply(this, arguments);
    queueMicrotask(() => {
      syncNodeOutputsToSchema(this, nodeData);
      stripUnknownWidgets(this, nodeData);
    });
    return result;
  };

  const originalConfigure = nodeType.prototype.onConfigure;
  nodeType.prototype.onConfigure = function (info) {
    let migrated = null;
    if (nodeData.name === "SeededTextPool") {
      migrated = migrateSeededTextPoolWidgets(info);
      if (migrated) {
        // Keep the in-memory node data canonical for re-serialization.
        info.widgets_values = migrated;
      }
    } else if (nodeData.name === "TagJoin") {
      migrated = migrateTagJoinWidgets(info);
      if (migrated) {
        info.widgets_values = migrated;
      }
    }
    originalConfigure?.apply(this, arguments);
    // ComfyUI fills widget values before onConfigure runs, so mutating
    // info.widgets_values alone leaves the visible widgets stale. Push the
    // migrated values into the created widgets explicitly.
    applyMigratedWidgetValues(this, migrated);
    if (migrated && nodeData.name === "TagJoin") {
      const text = previewWidget(this);
      if (text) {
        text.value = migrated[0];
        if (text.inputEl && typeof text.inputEl.value === "string") {
          text.inputEl.value = String(migrated[0]);
        }
      }
    }
    stripUnknownWidgets(this, nodeData);
    requestAnimationFrame(() => {
      syncNodeOutputsToSchema(this, nodeData);
      stripUnknownWidgets(this, nodeData);
    });
  };
}

app.registerExtension({
  name: "dynamic-prompt-engine.dynamic-sockets",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === "CLIPTokenReport") {
      registerCLIPTokenReport(nodeType);
      registerSchemaSync(nodeType, nodeData);
      return;
    }

    if (!ENGINE_NODE_NAMES.has(nodeData.name)) {
      return;
    }

    if (nodeData.name === "TagJoin") {
      registerDynamicStringNode(nodeType, tagSockets, {
        withOutputPreview: true,
      });
    } else if (nodeData.name === "BranchRandomSwitcher") {
      registerDynamicStringNode(nodeType, branchSockets);
    } else if (nodeData.name === "BranchSelector") {
      registerDynamicStringNode(nodeType, inputSockets);
    } else if (nodeData.name === "RoutingSwitch") {
      registerRoutingSwitch(nodeType);
    }

    // After dynamic-socket wrappers so schema sync runs last on create/configure.
    registerSchemaSync(nodeType, nodeData);
  },
});
