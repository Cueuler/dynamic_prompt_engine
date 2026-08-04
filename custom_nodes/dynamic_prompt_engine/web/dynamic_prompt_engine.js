import { app } from "../../../scripts/app.js";

const OUTPUT_WIDTH = 160;
const OUTPUT_HEIGHT = 80;
const PREVIEW_PLACEHOLDER = "Joined prompt preview (empty until run)…";

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

function createDynamicSocketHelpers(prefix) {
  function slotNumber(name) {
    return Number.parseInt(name.slice(prefix.length), 10);
  }

  function isDynamicInput(input) {
    return input?.name?.startsWith(prefix);
  }

  function inputName(index) {
    return `${prefix}${index}`;
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
    const highestConnected = slots.reduce(
      (highest, input) =>
        input.link != null ? Math.max(highest, slotNumber(input.name)) : highest,
      -1,
    );
    // Connected slot + one spare; none connected → a single empty socket.
    return Math.max(1, highestConnected + 2);
  }

  function setVisibleInputs(node, count) {
    const current = (node.inputs ?? []).filter(isDynamicInput);
    for (let index = current.length - 1; index >= count; index--) {
      const input = current[index];
      if (input.link == null) {
        node.removeInput(node.inputs.indexOf(input));
      }
    }

    let currentCount = (node.inputs ?? []).filter(isDynamicInput).length;
    while (currentCount < count) {
      node.addInput(inputName(currentCount), "STRING");
      currentCount++;
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

const tagSockets = createDynamicSocketHelpers("tag_");

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

/** Tag Join preview only — never fall back to another widget. */
function previewWidget(node) {
  return (node.widgets ?? []).find((widget) => widget?.name === "text") ?? null;
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

function stylePreviewWidget(node) {
  const widget = previewWidget(node);
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
    widget.inputEl.placeholder = PREVIEW_PLACEHOLDER;
  }
  ensurePreviewComputeSize(widget);
}

/**
 * @param {"content"|"resize"} mode
 *   content — height from textarea scrollHeight (grow with joined text)
 *   resize  — height from remaining node space (manual drag)
 */
function fitPreviewWidget(node, mode = "content") {
  const widget = previewWidget(node);
  if (!widget?.inputEl) {
    return;
  }
  stylePreviewWidget(node);
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

function setPreviewValue(node, text) {
  const widget = previewWidget(node);
  if (!widget) {
    return;
  }
  const value = Array.isArray(text) ? (text[0] ?? "") : (text ?? "");
  widget.value = value;
  if (widget.inputEl) {
    widget.inputEl.value = value;
  }
  stylePreviewWidget(node);
  fitPreviewWidget(node, "content");
  applyDefaultComputedSize(node);
  graphOf(node)?.setDirtyCanvas?.(true, false);
}

function registerDynamicStringNode(nodeType, sockets, options = {}) {
  const { withOutputPreview = false } = options;

  const originalCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const result = originalCreated?.apply(this, arguments);
    queueMicrotask(() => {
      sockets.setVisibleInputs(this, sockets.visibleCount(this));
      if (withOutputPreview) {
        stylePreviewWidget(this);
        fitPreviewWidget(this, "content");
      }
      applyDefaultComputedSize(this);
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
        sockets.setVisibleInputs(this, sockets.visibleCount(this));
        sockets.refreshInputLabels(this);
        stylePreviewWidget(this);
        fitPreviewWidget(this, "content");
        applyDefaultComputedSize(this);
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
        sockets.setVisibleInputs(this, sockets.visibleCount(this));
        sockets.refreshInputLabels(this);
        applyDefaultComputedSize(this);
      });
    };
  }

  const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
  nodeType.prototype.onConnectionsChange = function () {
    const result = originalConnectionsChange?.apply(this, arguments);
    queueMicrotask(() => {
      sockets.setVisibleInputs(this, sockets.visibleCount(this));
      sockets.refreshInputLabels(this);
      if (withOutputPreview) {
        stylePreviewWidget(this);
        fitPreviewWidget(this, "resize");
      }
      applyDefaultComputedSize(this);
    });
    return result;
  };

  const originalDrawForeground = nodeType.prototype.onDrawForeground;
  nodeType.prototype.onDrawForeground = function () {
    sockets.refreshInputLabels(this);
    return originalDrawForeground?.apply(this, arguments);
  };
}

const ENGINE_NODE_NAMES = new Set([
  "SeededTextPool",
  "BranchToggle",
  "TagJoin",
  "BranchSelect2",
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

/** Drop widgets removed from the Python schema (e.g. TagJoin separator). */
function stripUnknownWidgets(node, nodeData) {
  if (nodeData?.name !== "TagJoin" || !Array.isArray(node.widgets)) {
    return;
  }
  for (let i = node.widgets.length - 1; i >= 0; i--) {
    if (node.widgets[i]?.name === "separator") {
      node.widgets.splice(i, 1);
    }
  }
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
  nodeType.prototype.onConfigure = function () {
    originalConfigure?.apply(this, arguments);
    requestAnimationFrame(() => {
      syncNodeOutputsToSchema(this, nodeData);
      stripUnknownWidgets(this, nodeData);
    });
  };
}

app.registerExtension({
  name: "dynamic-prompt-engine.dynamic-sockets",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (!ENGINE_NODE_NAMES.has(nodeData.name)) {
      return;
    }

    if (nodeData.name === "TagJoin") {
      registerDynamicStringNode(nodeType, tagSockets, {
        withOutputPreview: true,
      });
    }

    // After dynamic-socket wrappers so schema sync runs last on create/configure.
    registerSchemaSync(nodeType, nodeData);
  },
});
