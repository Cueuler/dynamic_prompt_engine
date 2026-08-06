#!/usr/bin/env python3
"""Convert legacy Dynamic Prompt Engine workflows to the current node format.

Two migrations run on every workflow document:

1. SeededTextPool widgets::

       [stream_key, pool_text]                                  # 2-widget
       [stream_key, pool_text, bypass_chance, seed]             # 4-widget
       [stream_key, pool_text, seed, seed_mode]                 # 4-widget B
       [stream_key, pool_text, bypass_chance, seed, seed_mode]  # 5-widget C
       [stream_key, pool_text, seed, seed_mode, extra]          # 5-widget D

   become the current::

       [pool_text, bypass_chance, seed]                         # 3-widget

2. Context removal: the old PROMPT_CONTEXT channel (``PromptContext`` nodes,
   ``PROMPT_CONTEXT`` inputs/outputs and links) is dropped. Seed-based control
   is the only mechanism now, so every context artifact is removed: top-level
   nodes/links, subgraph nodes/links, subgraph interface entries, and subgraph
   input/output node slots. Links left dangling by the removed nodes are
   dropped too.

Only SeededTextPool nodes get their widgets rewritten; all other nodes pass
through with context removed.

Usage::

    python convert_legacy_workflow.py old_workflow.json new_workflow.json
    python convert_legacy_workflow.py old_workflow.json   # prints to stdout
    python convert_legacy_workflow.py < old_workflow.json > new_workflow.json
"""

import argparse
import json
import sys

CONTEXT_NODE_TYPE = "PromptContext"
CONTEXT_TYPE = "PROMPT_CONTEXT"


def convert_node_widgets_values(widgets_values):
    """Convert legacy SeededTextPool widgets_values to the current format.

    Returns the converted list, or the original value unchanged if
    no migration is needed.

    Known legacy layouts:

        2-element: [stream_key, pool_text]
                   -> [pool_text, false, 0]

        4-element Format A (test.json):
            [stream_key, pool_text, bypass_chance (bool), seed (int)]
            -> [pool_text, bypass_chance, seed]

        4-element Format B (test2.json):
            [stream_key, pool_text, seed (int), seed_mode (str)]
            -> [pool_text, false, seed]

        5-element Format C (Dynamic_PRO.json):
            [stream_key, pool_text, bypass_chance (bool), seed, seed_mode]
            -> [pool_text, bypass_chance, seed]

        5-element Format D (Dynamic_PRO.json subgraphs):
            [stream_key, pool_text, seed (int), seed_mode (str), extra (str)]
            -> [pool_text, false, seed]
    """
    if not isinstance(widgets_values, list):
        return widgets_values

    # Legacy 2-element: [stream_key, pool_text] -> [pool_text, false, 0]
    if len(widgets_values) == 2 and all(
        isinstance(v, str) for v in widgets_values
    ):
        return [widgets_values[1], False, 0]

    # Legacy 4-element: first two are always stream_key + pool_text
    if len(widgets_values) == 4 and all(
        isinstance(v, str) for v in widgets_values[:2]
    ):
        third, fourth = widgets_values[2], widgets_values[3]
        if isinstance(third, bool):
            # Format A: [stream_key, pool_text, bypass_chance, seed]
            #        -> [pool_text, bypass_chance, seed]
            return [widgets_values[1], third, fourth]
        if isinstance(fourth, str):
            # Format B: [stream_key, pool_text, seed, seed_mode]
            #        -> [pool_text, false, seed]
            return [widgets_values[1], False, third]

    # Legacy 5-element: old ComfyUI seed widget stores [value, mode]
    if len(widgets_values) == 5 and all(
        isinstance(v, str) for v in widgets_values[:2]
    ):
        third = widgets_values[2]
        if isinstance(third, bool):
            # Format C: [stream_key, pool_text, bypass_chance, seed, seed_mode]
            #        -> [pool_text, bypass_chance, seed]
            seed = widgets_values[3] if isinstance(widgets_values[3], (int, float)) else 0
            return [widgets_values[1], third, seed]
        if isinstance(third, (int, float)) and isinstance(widgets_values[3], str):
            # Format D: [stream_key, pool_text, seed, seed_mode, extra]
            #        -> [pool_text, false, seed]
            return [widgets_values[1], False, third]

    return widgets_values


def _strip_context_entries(items):
    """Drop PROMPT_CONTEXT entries from a node input/output (or subgraph
    interface) list, keeping everything else in order."""
    if not isinstance(items, list):
        return items
    return [
        item
        for item in items
        if not (isinstance(item, dict) and item.get("type") == CONTEXT_TYPE)
    ]


def _link_is_context(link):
    if isinstance(link, list):
        return len(link) >= 6 and link[5] == CONTEXT_TYPE
    if isinstance(link, dict):
        return link.get("type") == CONTEXT_TYPE
    return False


def _strip_context_links(links):
    """Drop PROMPT_CONTEXT links, keeping all other links."""
    if not isinstance(links, list):
        return links
    return [link for link in links if not _link_is_context(link)]


def _link_endpoints(link):
    if isinstance(link, list):
        if len(link) >= 5:
            return link[1], link[3]
        return None, None
    if isinstance(link, dict):
        return link.get("origin_id"), link.get("target_id")
    return None, None


def _valid_node_ids(nodes, input_node=None, output_node=None):
    ids = set()
    for node in nodes or []:
        node_id = node.get("id")
        if node_id is not None:
            ids.add(node_id)
    for endpoint in (input_node, output_node):
        if endpoint and endpoint.get("id") is not None:
            ids.add(endpoint["id"])
    return ids


def _drop_dangling_links(links, valid_ids):
    """Drop links whose origin or target node no longer exists."""
    if not isinstance(links, list):
        return links
    return [
        link
        for link in links
        if (lambda ends: ends[0] in valid_ids and ends[1] in valid_ids)(
            _link_endpoints(link)
        )
    ]


def _convert_node(node):
    if node.get("type") != "SeededTextPool":
        return
    if "widgets_values" in node:
        original = node["widgets_values"]
        converted = convert_node_widgets_values(original)
        if converted is not original:
            node["widgets_values"] = converted


def _clean_node_list(nodes):
    """Rewrite SeededTextPool widgets and remove context from a node list."""
    cleaned = []
    for node in nodes or []:
        if node.get("type") == CONTEXT_NODE_TYPE:
            continue
        _convert_node(node)
        if isinstance(node.get("inputs"), list):
            node["inputs"] = _strip_context_entries(node["inputs"])
        if isinstance(node.get("outputs"), list):
            node["outputs"] = _strip_context_entries(node["outputs"])
        cleaned.append(node)
    return cleaned


def _clean_subgraph(sg):
    """Remove context machinery from a subgraph definition in place."""
    sg["nodes"] = _clean_node_list(sg.get("nodes"))
    if isinstance(sg.get("links"), list):
        sg["links"] = _strip_context_links(sg["links"])
        sg["links"] = _drop_dangling_links(
            sg["links"],
            _valid_node_ids(
                sg.get("nodes"),
                sg.get("inputNode"),
                sg.get("outputNode"),
            ),
        )
    for key in ("inputs", "outputs"):
        if isinstance(sg.get(key), list):
            sg[key] = _strip_context_entries(sg[key])
    if isinstance(sg.get("inputNode"), dict):
        sg["inputNode"]["inputs"] = _strip_context_entries(
            sg["inputNode"].get("inputs")
        )
    if isinstance(sg.get("outputNode"), dict):
        sg["outputNode"]["outputs"] = _strip_context_entries(
            sg["outputNode"].get("outputs")
        )


def convert_workflow(data):
    """Rewrite a workflow document in place: convert SeededTextPool widgets
    and remove the PromptContext / PROMPT_CONTEXT machinery."""
    data["nodes"] = _clean_node_list(data.get("nodes"))
    if isinstance(data.get("links"), list):
        data["links"] = _strip_context_links(data["links"])
        data["links"] = _drop_dangling_links(
            data["links"],
            _valid_node_ids(data.get("nodes")),
        )
    for sg in data.get("definitions", {}).get("subgraphs", []):
        _clean_subgraph(sg)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Convert legacy Dynamic Prompt Engine workflows to the current "
            "SeededTextPool format and remove the old PromptContext channels."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to the old workflow JSON. Reads from stdin if omitted.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        help=(
            "Path for the converted workflow JSON. Writes to stdout if omitted."
        ),
    )
    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    convert_workflow(data)

    output = json.dumps(data, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
            f.write("\n")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())