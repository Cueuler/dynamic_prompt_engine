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
const pickSockets = createDynamicSocketHelpers("pick_");
const inputSockets = createDynamicSocketHelpers("input_");

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

function previewWidget(node) {
  return (node.widgets ?? []).find((widget) => widget?.name === "text") ?? node.widgets?.[0];
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
  if (!widget.__dpePreviewSized) {
    widget.__dpePreviewSized = true;
    const previous = widget.computeSize?.bind(widget);
    widget.computeSize = function (width) {
      const size = previous?.(width) ?? [OUTPUT_WIDTH, OUTPUT_HEIGHT];
      const w =
        typeof width === "number" && width > 0
          ? width
          : Math.max(OUTPUT_WIDTH, size[0] ?? OUTPUT_WIDTH);
      return [w, Math.max(OUTPUT_HEIGHT, size[1] ?? OUTPUT_HEIGHT)];
    };
  }
}

function fitPreviewWidget(node) {
  const widget = previewWidget(node);
  if (!widget?.inputEl) {
    return;
  }
  stylePreviewWidget(node);
  const width = Math.max(OUTPUT_WIDTH, (node.size?.[0] ?? OUTPUT_WIDTH) - 24);
  const height = Math.max(OUTPUT_HEIGHT, widget.computedHeight ?? OUTPUT_HEIGHT);
  widget.inputEl.style.width = `${width}px`;
  widget.inputEl.style.height = `${height}px`;
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
  fitPreviewWidget(node);
  applyDefaultComputedSize(node);
  graphOf(node)?.setDirtyCanvas?.(true, false);
}

function registerDynamicStringNode(nodeType, sockets, options = {}) {
  const { withOutputPreview = false } = options;

  const originalCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const result = originalCreated?.apply(this, arguments);
    queueMicrotask(() => {
      sockets.setVisibleInputs(this, 1);
      if (withOutputPreview) {
        stylePreviewWidget(this);
        fitPreviewWidget(this);
      }
      applyDefaultComputedSize(this);
    });
    return result;
  };

  if (withOutputPreview) {
    const originalOnResize = nodeType.prototype.onResize;
    nodeType.prototype.onResize = function () {
      const result = originalOnResize?.apply(this, arguments);
      fitPreviewWidget(this);
      return result;
    };

    const originalOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      originalOnConfigure?.apply(this, arguments);
      requestAnimationFrame(() => {
        sockets.setVisibleInputs(this, sockets.visibleCount(this));
        sockets.refreshInputLabels(this);
        stylePreviewWidget(this);
        fitPreviewWidget(this);
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
        fitPreviewWidget(this);
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

app.registerExtension({
  name: "dynamic-prompt-engine.dynamic-sockets",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === "TagJoin") {
      registerDynamicStringNode(nodeType, tagSockets, {
        withOutputPreview: true,
      });
      return;
    }

    if (nodeData.name === "SeededInputPick") {
      registerDynamicStringNode(nodeType, pickSockets);
      return;
    }

    if (nodeData.name === "TextPoolRouter") {
      registerDynamicStringNode(nodeType, inputSockets);
    }
  },
});
