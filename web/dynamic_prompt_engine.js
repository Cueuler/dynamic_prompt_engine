import { app } from "../../scripts/app.js";
import {
  CHANCE_OPTIONS,
  applyParsedRoutingSwitchWidgets,
  connectedRoutingIndicesFromInputs,
  parseRoutingSwitchWidgetValues,
  routingInputIndex,
} from "./routing_switch_widgets.js";

const OUTPUT_WIDTH = 160;
const OUTPUT_HEIGHT = 80;
const PREVIEW_PLACEHOLDER = "Joined prompt preview (empty until run)…";
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
  return input?.widget != null || input?.name === "text" || input?.name === "report";
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
  const placeholder = name === "report" ? CLIP_REPORT_PLACEHOLDER : PREVIEW_PLACEHOLDER;
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
  const placeholder = name === "report" ? CLIP_REPORT_PLACEHOLDER : PREVIEW_PLACEHOLDER;
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

function isChanceWidget(widget) {
  return typeof widget?.name === "string" && /^chance_\d+$/.test(widget.name);
}

function isLegacyRoutingLayoutWidget(widget) {
  const name = widget?.name;
  return (
    name === "__chance_gap" ||
    (typeof name === "string" && /^__spacer_\d+$/.test(name))
  );
}

function isSeedControlWidget(widget) {
  const name = widget?.name;
  return (
    name === "control_after_generate" ||
    name === "controlAfterGenerate" ||
    (typeof name === "string" && name.includes("control_after_generate"))
  );
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

function routingInputDisplayName(node, index) {
  const input = (node.inputs ?? []).find(
    (slot) => routingInputIndex(slot.name) === index,
  );
  const label = typeof input?.label === "string" ? input.label.trim() : "";
  return label || input?.name || `input_${index}`;
}

function labelChanceWidgets(node) {
  for (const widget of node.widgets ?? []) {
    if (!isChanceWidget(widget)) {
      continue;
    }
    const index = Number.parseInt(widget.name.slice("chance_".length), 10);
    widget.label = routingInputDisplayName(node, index);
  }
}

function ensureChanceWidget(node, index, savedValue) {
  const name = chanceWidgetName(index);
  const value =
    typeof savedValue === "string" && CHANCE_OPTIONS.includes(savedValue)
      ? savedValue
      : "Default";
  const existing = (node.widgets ?? []).find((widget) => widget.name === name);
  if (existing) {
    if (CHANCE_OPTIONS.includes(savedValue)) {
      existing.value = savedValue;
    }
    return existing;
  }
  const widget = node.addWidget("combo", name, value, () => {}, {
    values: CHANCE_OPTIONS,
  });
  widget.label = routingInputDisplayName(node, index);
  return widget;
}

function orderRoutingSwitchWidgets(node) {
  const widgets = node.widgets ?? [];
  const rest = widgets.filter(
    (widget) =>
      !isChanceWidget(widget) &&
      !isLegacyRoutingLayoutWidget(widget),
  );
  const chances = widgets
    .filter(isChanceWidget)
    .sort(
      (a, b) =>
        Number.parseInt(a.name.slice("chance_".length), 10) -
        Number.parseInt(b.name.slice("chance_".length), 10),
    );
  node.widgets = [...chances, ...rest];
}

function clearRoutingSwitchSlotPositions(node) {
  delete node.widgets_start_y;
  for (const input of node.inputs ?? []) {
    if (Number.isInteger(routingInputIndex(input.name))) {
      delete input.pos;
    }
  }
  for (const output of node.outputs ?? []) {
    delete output.pos;
  }
}

function syncRoutingSwitchChances(node) {
  node.__dpeChanceSaved = node.__dpeChanceSaved || {};
  for (const widget of node.widgets ?? []) {
    if (isChanceWidget(widget) && CHANCE_OPTIONS.includes(widget.value)) {
      node.__dpeChanceSaved[widget.name] = widget.value;
    }
  }

  const connected = new Set();
  for (const input of node.inputs ?? []) {
    const index = routingInputIndex(input.name);
    if (Number.isInteger(index) && input.link != null) {
      connected.add(index);
    }
  }

  for (const widget of [...(node.widgets ?? [])]) {
    if (isChanceWidget(widget)) {
      const index = Number.parseInt(widget.name.slice("chance_".length), 10);
      if (!connected.has(index)) {
        removeNodeWidget(node, widget);
      }
    } else if (isLegacyRoutingLayoutWidget(widget)) {
      removeNodeWidget(node, widget);
    }
  }

  for (const index of [...connected].sort((a, b) => a - b)) {
    ensureChanceWidget(
      node,
      index,
      node.__dpeChanceSaved[chanceWidgetName(index)],
    );
  }

  orderRoutingSwitchWidgets(node);
  clearRoutingSwitchSlotPositions(node);
  for (const widget of [...(node.widgets ?? []).filter(isChanceWidget)]) {
    delete widget.width;
  }
  labelChanceWidgets(node);
}

function registerRoutingSwitch(nodeType) {
  // Default LiteGraph slot stack at the top. Chance combos (named like their
  // inputs) sit below as normal widgets; master seed comes from DPE Global Seed.
  registerDynamicStringNode(nodeType, routingSockets, {
    afterLayout: (node) => {
      const pending = node.__dpeRoutingWidgets;
      const connectedIndices =
        node.__dpeRoutingConnected?.length > 0
          ? node.__dpeRoutingConnected
          : connectedRoutingIndicesFromInputs(node.inputs);
      if (pending) {
        applyParsedRoutingSwitchWidgets(
          node,
          parseRoutingSwitchWidgetValues(pending, { connectedIndices }),
        );
      }
      syncRoutingSwitchChances(node);
      if (pending) {
        applyParsedRoutingSwitchWidgets(
          node,
          parseRoutingSwitchWidgetValues(pending, { connectedIndices }),
        );
        delete node.__dpeRoutingWidgets;
        delete node.__dpeRoutingConnected;
      }
    },
  });

  const originalArrange = nodeType.prototype.arrange;
  nodeType.prototype.arrange = function () {
    clearRoutingSwitchSlotPositions(this);
    const result = originalArrange?.apply(this, arguments);
    labelChanceWidgets(this);
    return result;
  };

  const originalConfigure = nodeType.prototype.onConfigure;
  nodeType.prototype.onConfigure = function (info) {
    if (Array.isArray(info?.widgets_values)) {
      this.__dpeRoutingWidgets = [...info.widgets_values];
    }
    this.__dpeRoutingConnected = connectedRoutingIndicesFromInputs(info?.inputs);
    originalConfigure?.apply(this, arguments);
  };
}

function registerOutputPreviewNode(nodeType, previewName, placeholder) {
  function runLayout(node) {
    stylePreviewWidget(node, previewName, placeholder);
    fitPreviewWidget(node, "content", previewName);
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
    fitPreviewWidget(this, "resize", previewName);
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
    setPreviewValue(this, message?.[previewName], previewName);
    return result;
  };
}

function disableGlobalSeedControlAfterGenerate(node) {
  const seedWidget = (node.widgets ?? []).find((widget) => widget.name === "seed");
  if (!seedWidget) {
    return;
  }
  seedWidget.options = seedWidget.options ?? {};
  seedWidget.options.control_after_generate = false;
  for (const widget of [...(node.widgets ?? [])]) {
    if (isSeedControlWidget(widget)) {
      removeNodeWidget(node, widget);
    }
  }
}

function registerGlobalSeedChrome(nodeType) {
  const originalCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const result = originalCreated?.apply(this, arguments);
    queueMicrotask(() => disableGlobalSeedControlAfterGenerate(this));
    return result;
  };

  const originalConfigure = nodeType.prototype.onConfigure;
  nodeType.prototype.onConfigure = function () {
    originalConfigure?.apply(this, arguments);
    disableGlobalSeedControlAfterGenerate(this);
    requestAnimationFrame(() => disableGlobalSeedControlAfterGenerate(this));
  };
}

app.registerExtension({
  name: "dynamic-prompt-engine.dynamic-sockets",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === "DPEGlobalSeed") {
      registerGlobalSeedChrome(nodeType);
      return;
    }

    if (nodeData.name === "CLIPTokenReport") {
      registerOutputPreviewNode(nodeType, "report", CLIP_REPORT_PLACEHOLDER);
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
  },
});
