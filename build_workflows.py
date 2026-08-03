import json


def section_from_title(title, node_id):
    """Infer UI column from node title after stream_key removal."""
    title = (title or "").lower()
    if "character 2" in title or "character_2" in title:
        return "character_2"
    if "character 1" in title or "character_1" in title:
        return "character_1"
    if title.startswith("pool: 01_") or "quality" in title or "rating" in title or "meta" in title:
        return "quality"
    if title.startswith("pool: 02_") or "composition" in title or "solo" in title or "pair" in title:
        return "composition"
    if title.startswith("pool: scene") or "scene" in title:
        return "scene"
    nid = int(node_id)
    if 96 <= nid <= 101:
        return "quality"
    if 107 <= nid <= 162:
        return "composition"
    if 210 <= nid <= 231:
        return "character_1"
    if 232 <= nid <= 261:
        return "character_2"
    if 270 <= nid <= 273:
        return "scene"
    return "other"


def generate_editable_ui_workflow():
    """Generate a UI-format graph from the runnable custom-node API graph."""
    with open("dynamic_prompt.json", "r") as f:
        ui_graph = json.load(f)
    with open("dynamic_prompt_engine_api.json", "r") as f:
        api_graph = json.load(f)

    custom_types = {
        "SeededTextPool",
        "TextPoolRouter",
        "SeededInputPick",
        "OneTwoPersonToggle",
        "TagJoin",
    }
    base_nodes = list(ui_graph["nodes"])
    base_links = list(ui_graph.get("links", []))
    next_link_id = max((link[0] for link in base_links), default=0) + 1
    links = list(base_links)
    custom_nodes = []
    source_links = {}

    def input_slot(class_type, name, raw_inputs):
        seed_linked = isinstance(raw_inputs.get("seed"), list)
        if class_type == "SeededTextPool":
            if name != "seed":
                raise ValueError(f"SeededTextPool has no linked input named {name}")
            return 0
        if class_type == "TextPoolRouter":
            if name == "index":
                return 0
            if name.startswith("input_"):
                # index widget stays unbound; linked inputs start at 0 in UI inputs array
                return int(name.rsplit("_", 1)[1])
            raise ValueError(f"TextPoolRouter has no linked input named {name}")
        if class_type == "SeededInputPick":
            if name == "seed":
                return 0
            pick_n = int(name.rsplit("_", 1)[1])
            return pick_n + (1 if seed_linked else 0)
        if class_type == "OneTwoPersonToggle":
            if name == "seed":
                return 0
            base = 1 if seed_linked else 0
            if name == "one_character":
                return base
            if name == "two_or_more_characters":
                return base + 1
            raise ValueError(f"OneTwoPersonToggle has no linked input named {name}")
        if class_type == "TagJoin":
            if not name.startswith("tag_"):
                raise ValueError(f"TagJoin has no linked input named {name}")
            return int(name.rsplit("_", 1)[1])
        raise ValueError(f"{class_type} has no linked input slots")

    def input_type(name):
        if name in {"seed", "index"}:
            return "INT"
        return "STRING"

    def output_definition(class_type):
        if class_type == "TagJoin":
            return [("prompt", "STRING")]
        if class_type == "TextPoolRouter":
            return [("text", "STRING")]
        return [("text", "STRING"), ("seed", "INT")]

    def widgets_for(class_type, raw_inputs):
        if class_type == "SeededTextPool":
            seed = raw_inputs.get("seed", 0)
            return [
                raw_inputs.get("pool_text", ""),
                bool(raw_inputs.get("bypass_chance", False)),
                seed if not isinstance(seed, list) else 0,
            ]
        if class_type == "TextPoolRouter":
            idx = raw_inputs.get("index", 0)
            return [idx if not isinstance(idx, list) else 0]
        if class_type == "SeededInputPick":
            seed = raw_inputs.get("seed", 0)
            return [seed if not isinstance(seed, list) else 0]
        if class_type == "OneTwoPersonToggle":
            seed = raw_inputs.get("seed", 0)
            return [
                raw_inputs.get("one_label", "1girl"),
                raw_inputs.get("two_label", "2girls"),
                seed if not isinstance(seed, list) else 0,
            ]
        if class_type == "TagJoin":
            return [""]
        return []

    positions = {}
    counters = {
        "quality": 0,
        "composition": 0,
        "character_1": 0,
        "character_2": 0,
        "scene": 0,
        "other": 0,
    }
    for node_id, node in api_graph.items():
        if node["class_type"] not in custom_types:
            continue
        if node["class_type"] != "SeededTextPool":
            continue
        title = node.get("_meta", {}).get("title", "")
        section = section_from_title(title, node_id)
        column = {
            "quality": 600,
            "composition": 1500,
            "character_1": 2800,
            "character_2": 3800,
            "scene": 5100,
            "other": 6000,
        }[section]
        index = counters[section]
        counters[section] += 1
        positions[int(node_id)] = [column + (index % 2) * 400, 800 + (index // 2) * 450]

    positions.update(
        {
            155: [2350, 800],
            162: [2350, 1200],
            163: [2350, 1600],
            264: [4650, 800],
            265: [5100, 800],
            280: [4800, 800],
            281: [4800, 2050],
            282: [5300, 800],
            283: [5300, 2050],
            284: [5800, 800],
            285: [5800, 2050],
            286: [4600, 5000],
            287: [4600, 5300],
            288: [6300, 800],
            289: [6300, 2050],
            290: [6800, 800],
            140: [7300, 800],
        }
    )
    for scene_id, position in zip(
        range(270, 274),
        ([5100, 4000], [5500, 4000], [5100, 4450], [5500, 4450]),
    ):
        positions[scene_id] = position

    node_by_id = {}
    for node_id_text, node in api_graph.items():
        class_type = node["class_type"]
        if class_type not in custom_types:
            continue
        node_id = int(node_id_text)
        raw_inputs = node.get("inputs", {})
        inputs = []
        for name, value in raw_inputs.items():
            if not (isinstance(value, list) and len(value) == 2):
                continue
            source_id, source_slot = int(value[0]), int(value[1])
            link_id = next_link_id
            next_link_id += 1
            links.append(
                [
                    link_id,
                    source_id,
                    source_slot,
                    node_id,
                    input_slot(class_type, name, raw_inputs),
                    input_type(name),
                ]
            )
            inputs.append({"name": name, "type": input_type(name), "link": link_id})
            source_links.setdefault((source_id, source_slot), []).append(link_id)

        outputs = [
            {"name": name, "type": data_type, "links": []}
            for name, data_type in output_definition(class_type)
        ]
        # Initial sizes only; runtime resize uses ComfyUI computeSize (no custom mins).
        size = (
            [320, 280]
            if class_type == "SeededTextPool"
            else [280, 160]
            if class_type in {"TextPoolRouter", "SeededInputPick", "OneTwoPersonToggle"}
            else [280, 140]
        )
        ui_node = {
            "id": node_id,
            "type": class_type,
            "pos": positions.get(node_id, [6000, 800]),
            "size": size,
            "flags": {},
            "order": node_id,
            "mode": 0,
            "inputs": inputs,
            "outputs": outputs,
            "properties": {"Node name for S&R": class_type},
            "widgets_values": widgets_for(class_type, raw_inputs),
            "title": node.get("_meta", {}).get("title", class_type),
        }
        node_by_id[node_id] = ui_node
        custom_nodes.append(ui_node)

    for node_id, ui_node in node_by_id.items():
        for slot, output in enumerate(ui_node["outputs"]):
            output["links"] = source_links.get((node_id, slot), [])

    final_prompt_link = next_link_id
    next_link_id += 1
    links.append([final_prompt_link, 140, 0, 3, 0, "STRING"])
    source_links.setdefault((140, 0), []).append(final_prompt_link)
    node_by_id[140]["outputs"][0]["links"].append(final_prompt_link)
    for node in base_nodes:
        if node["id"] == 3:
            node["inputs"].insert(
                0, {"name": "text", "type": "STRING", "link": final_prompt_link}
            )
    for link in links:
        if link[3] == 3 and link[5] == "CLIP":
            link[4] = 1

    ui_graph["nodes"] = base_nodes + custom_nodes
    ui_graph["links"] = links
    ui_graph["last_node_id"] = max(node["id"] for node in ui_graph["nodes"])
    ui_graph["last_link_id"] = next_link_id - 1
    ui_graph["groups"] = [
        {
            "title": "01 · Quality / meta / rating",
            "bounding": [560, 760, 1250, 1450],
            "color": "#3f51b5",
        },
        {
            "title": "02 · Composition",
            "bounding": [1460, 760, 1250, 3500],
            "color": "#2196f3",
        },
        {
            "title": "03 · Character 1",
            "bounding": [2760, 760, 850, 5200],
            "color": "#4caf50",
        },
        {
            "title": "04 · Character 2",
            "bounding": [3760, 760, 1300, 5200],
            "color": "#ff9800",
        },
        {
            "title": "05 · Scene",
            "bounding": [5060, 3960, 900, 1300],
            "color": "#9c27b0",
        },
    ]
    with open("dynamic_prompt_engine.json", "w") as f:
        json.dump(ui_graph, f, indent=2)
    print("Regenerated editable UI workflow from the atomic API graph.")


if __name__ == "__main__":
    generate_editable_ui_workflow()
