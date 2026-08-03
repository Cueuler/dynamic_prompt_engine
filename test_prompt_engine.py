import json
import sys
import os

sys.path.insert(0, os.path.abspath("custom_nodes"))

from dynamic_prompt_engine.prompt_engine_nodes import (
    SeededTextPool,
    TextPoolRouter,
    TagJoin,
    SeededInputPick,
    OneTwoPersonToggle,
    derive_stream_seed,
    stream_key_from_unique_id,
)


def run_prompt_engine(seed_val):
    with open("dynamic_prompt_engine_api.json", "r") as f:
        graph = json.load(f)

    pool_node = SeededTextPool()
    router_node = TextPoolRouter()
    join_node = TagJoin()
    toggle_node = OneTwoPersonToggle()
    pick_node = SeededInputPick()
    node_outputs = {}

    # Root seed holder (literal seed on smallest pool id).
    for nid, node in graph.items():
        if node.get("class_type") != "SeededTextPool":
            continue
        if not isinstance(node["inputs"].get("seed"), list):
            node["inputs"]["seed"] = seed_val
            break

    def resolve_val(inp_val):
        if isinstance(inp_val, list) and len(inp_val) == 2:
            ref_id, ref_slot = str(inp_val[0]), int(inp_val[1])
            if ref_id not in node_outputs:
                exec_node(ref_id)
            return node_outputs[ref_id][ref_slot]
        return inp_val

    def exec_node(nid):
        if nid in node_outputs or nid not in graph:
            return
        data = graph[nid]
        ctype = data["class_type"]
        resolved_inputs = {
            key: resolve_val(value) for key, value in data.get("inputs", {}).items()
        }

        if ctype == "SeededTextPool":
            out = pool_node.select_from_pool(
                pool_text=resolved_inputs["pool_text"],
                seed=resolved_inputs["seed"],
                bypass_chance=resolved_inputs.get("bypass_chance", False),
                unique_id=nid,
            )
        elif ctype == "TextPoolRouter":
            out = router_node.route_text(
                resolved_inputs.pop("index"),
                **{
                    k: v
                    for k, v in resolved_inputs.items()
                    if k != "seed"
                },
            )
        elif ctype == "OneTwoPersonToggle":
            out = toggle_node.select_section(
                seed=resolved_inputs.get("seed", 0),
                one_label=resolved_inputs.get("one_label", "1girl"),
                two_label=resolved_inputs.get("two_label", "2girls"),
                one_character=resolved_inputs.get("one_character", ""),
                two_or_more_characters=resolved_inputs.get(
                    "two_or_more_characters", ""
                ),
            )
        elif ctype == "SeededInputPick":
            seed = resolved_inputs.pop("seed", 0)
            out = pick_node.pick_input(seed=seed, unique_id=nid, **resolved_inputs)
        elif ctype == "TagJoin":
            resolved_inputs.pop("seed", None)
            out = join_node.join_tags(unique_id=nid, **resolved_inputs)
            if isinstance(out, dict):
                out = out["result"]
        else:
            out = (None,)

        node_outputs[nid] = out

    exec_node("140")
    prompt_str = node_outputs["140"][0]
    return prompt_str, node_outputs


def pool_by_title(graph, title_substr):
    for node_id, node in graph.items():
        if node.get("class_type") != "SeededTextPool":
            continue
        title = node.get("_meta", {}).get("title", "")
        if title_substr in title:
            return node_id, node["inputs"]["pool_text"]
    raise KeyError(title_substr)


def composition_block(outs, pool_ids, keys):
    parts = [outs[pool_ids[key]][0] for key in keys]
    return ", ".join(part for part in parts if part)


def test_suite():
    print("--- Running Dynamic Prompt Engine Test Suite ---")

    with open("dynamic_prompt_engine_api.json", "r") as f:
        graph = json.load(f)

    obsolete_composition_nodes = {
        "100",
        "102",
        "103",
        "104",
        "105",
        "106",
        "1030",
        "1031",
        "1360",
        "1361",
        "1362",
        "1363",
        "1364",
        "137",
        "138",
    }
    assert not obsolete_composition_nodes.intersection(graph)

    solo_titles = {
        "02_solo_pose": "Solo / Pose",
        "02_solo_action": "Solo / Action",
        "02_solo_hand_position": "Solo / Hand Position",
        "02_solo_leg_placement": "Solo / Leg Placement",
        "02_solo_gaze_direction": "Solo / Gaze Direction",
    }
    pair_titles = {
        "02_pair_body_pose": "Pair / Body Pose",
        "02_pair_relative_pose": "Pair / Relative Pose",
        "02_pair_action": "Pair / Action",
        "02_pair_hand_interaction": "Pair / Hand Interaction",
        "02_pair_leg_placement": "Pair / Leg Placement",
        "02_pair_gaze_direction": "Pair / Gaze Direction",
    }
    pool_ids = {}
    for key, substr in {**solo_titles, **pair_titles}.items():
        nid, _ = pool_by_title(graph, substr)
        pool_ids[key] = nid

    root = str(
        min(
            int(nid)
            for nid, n in graph.items()
            if n.get("class_type") == "SeededTextPool"
        )
    )
    assert not isinstance(graph[root]["inputs"]["seed"], list)
    assert "seed" not in graph["140"]["inputs"]
    assert graph["163"]["inputs"]["seed"] == [root, 1]
    assert graph["150"]["inputs"]["seed"] == [root, 1]
    assert graph["163"]["class_type"] == "OneTwoPersonToggle"
    assert graph["281"]["inputs"]["tag_0"] == ["163", 0]
    assert graph["150"]["inputs"]["bypass_chance"] is False
    print("[SUCCESS]: Seed is fan-out chained from root pool seed output!")

    p1, _ = run_prompt_engine(42)
    print(f"\n[Seed 42 Prompt]:\n{p1}")

    p1_repeat, _ = run_prompt_engine(42)
    assert p1 == p1_repeat
    print("\n[SUCCESS]: Seed 42 run is 100% reproducible!")

    p2, _ = run_prompt_engine(100)
    print(f"\n[Seed 100 Prompt]:\n{p2}")

    seed_1girl = None
    seed_2girls = None
    for seed in range(200):
        idx = derive_stream_seed(seed, OneTwoPersonToggle.STREAM_KEY) % 2
        prompt, outs = run_prompt_engine(seed)
        if idx == 0 and seed_1girl is None:
            seed_1girl = (seed, prompt, outs)
        elif idx == 1 and seed_2girls is None:
            seed_2girls = (seed, prompt, outs)
        if seed_1girl and seed_2girls:
            break

    print(f"\n[Found 1girl seed]: {seed_1girl[0]}")
    assert "1girl" in seed_1girl[1]
    assert composition_block(seed_1girl[2], pool_ids, list(solo_titles)) in seed_1girl[1]
    print("[SUCCESS]: 1-character run selected only the ordered solo composition block!")

    print(f"\n[Found 2girls seed]: {seed_2girls[0]}")
    assert "2girls" in seed_2girls[1]
    assert composition_block(seed_2girls[2], pool_ids, list(pair_titles)) in seed_2girls[1]
    print(
        "[SUCCESS]: 2-character run included body pose, relative pose, action, hands, legs, and gaze!"
    )

    pool_node = SeededTextPool()
    text_b1, seed_out = pool_node.select_from_pool(
        pool_text="red\ngreen\nblue", seed=123, unique_id="key_B"
    )
    assert seed_out == 123
    pool_node.select_from_pool(
        pool_text="apple\nbanana\ncherry\ndate", seed=123, unique_id="key_A_modified"
    )
    text_b2, _ = pool_node.select_from_pool(
        pool_text="red\ngreen\nblue", seed=123, unique_id="key_B"
    )
    assert text_b1 == text_b2
    print("\n[SUCCESS]: unique_id streams provide independent RNG streams!")

    empties = 0
    for seed in range(40):
        gated_text, gated_seed = pool_node.select_from_pool(
            pool_text="thigh straps\nanklet\nleg warmers",
            seed=seed,
            bypass_chance=True,
            unique_id="leg_accessories",
        )
        always_text, _ = pool_node.select_from_pool(
            pool_text="thigh straps\nanklet\nleg warmers",
            seed=seed,
            bypass_chance=False,
            unique_id="leg_accessories",
        )
        assert gated_seed == seed
        if gated_text == "":
            empties += 1
        else:
            assert gated_text == always_text
    assert 10 <= empties <= 30, f"Expected ~50% empties, got {empties}/40"
    print("[SUCCESS]: bypass_chance gates independently!")

    join = TagJoin()
    for unique_id in ("140", 140, ["140"]):
        workflow = {"nodes": [{"id": 140, "widgets_values": []}]}
        result = join.join_tags(
            text="",
            unique_id=unique_id,
            extra_pnginfo=[{"workflow": workflow}],
            tag_0="persisted",
            tag_1="  ",
        )
        assert result["result"] == ("persisted, ",)
        assert workflow["nodes"][0]["widgets_values"] == ["persisted, "]
    print("[SUCCESS]: TagJoin returns prompt and ignores empty tags!")

    picker = SeededInputPick()
    pick_a, pick_seed = picker.pick_input(
        42,
        unique_id="quality_pick",
        pick_0="masterpiece",
        pick_1="best quality",
        pick_2="high quality",
    )
    assert pick_seed == 42
    expected_idx = derive_stream_seed(42, stream_key_from_unique_id("quality_pick")) % 3
    assert pick_a == ["masterpiece", "best quality", "high quality"][expected_idx]
    print("[SUCCESS]: Seeded Input Pick passes seed through!")

    toggle = OneTwoPersonToggle()
    seed_one = next(
        s
        for s in range(200)
        if derive_stream_seed(s, OneTwoPersonToggle.STREAM_KEY) % 2 == 0
    )
    text_one, tseed = toggle.select_section(
        seed_one,
        one_label="1girl",
        two_label="2girls",
        one_character="solo body",
        two_or_more_characters="pair body",
    )
    assert tseed == seed_one and "1girl" in text_one
    print("[SUCCESS]: One/Two Person Toggle passes seed through!")

    router = TextPoolRouter()
    (routed,) = router.route_text(1, input_0="solo", input_1="pair")
    assert routed == "pair"
    (empty_selected,) = router.route_text(0, input_0="  ", input_1="pair")
    assert empty_selected == "pair"
    print("[SUCCESS]: TextPoolRouter index routing works!")

    # Explicit chain: A text+seed -> B consumes A's seed output
    text_a, seed_a = pool_node.select_from_pool(
        pool_text="a\nb", seed=77, unique_id="chain_a"
    )
    text_b, seed_b = pool_node.select_from_pool(
        pool_text="x\ny\nz", seed=seed_a, unique_id="chain_b"
    )
    assert seed_a == seed_b == 77
    assert text_a in {"a", "b"}
    assert text_b in {"x", "y", "z"}
    print("[SUCCESS]: Seed daisy-chain A.seed -> B.seed works!")


if __name__ == "__main__":
    test_suite()
