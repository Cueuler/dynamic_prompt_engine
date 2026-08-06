"""Tests for convert_legacy_workflow.py."""

import unittest

from convert_legacy_workflow import convert_node_widgets_values, convert_workflow


class ConvertNodeWidgetsValuesTest(unittest.TestCase):
    def test_two_element_legacy(self):
        result = convert_node_widgets_values(
            ["character_2_expression", "smile\nblushing"]
        )
        self.assertEqual(result, ["smile\nblushing", False, 0])

    def test_four_element_legacy(self):
        result = convert_node_widgets_values(
            ["character_2_expression", "smile\nblushing", True, 42]
        )
        self.assertEqual(result, ["smile\nblushing", True, 42])

    def test_current_three_element_unchanged(self):
        result = convert_node_widgets_values(["smile\nblushing", False, 0])
        self.assertEqual(result, ["smile\nblushing", False, 0])

    def test_non_list_unchanged(self):
        result = convert_node_widgets_values("not a list")
        self.assertEqual(result, "not a list")

    def test_four_element_format_b(self):
        """Format B: [stream_key, pool_text, seed, seed_mode] -> [pool_text, false, seed]."""
        result = convert_node_widgets_values(
            ["01_quality", "masterpiece, best quality", 0, "randomize"]
        )
        self.assertEqual(result, ["masterpiece, best quality", False, 0])

    def test_five_element_format_c(self):
        """Format C: [stream_key, pool_text, bypass_chance, seed, seed_mode]."""
        result = convert_node_widgets_values(
            ["01_quality", "masterpiece, best quality", False, 937002384346469, "randomize"]
        )
        self.assertEqual(result, ["masterpiece, best quality", False, 937002384346469])

    def test_five_element_format_c_bypass_true(self):
        """Format C with bypass on, string seed -> bypass preserved, seed 0."""
        result = convert_node_widgets_values(
            ["", "wings\nwings", True, "randomize", "randomize"]
        )
        self.assertEqual(result, ["wings\nwings", True, 0])

    def test_five_element_format_d(self):
        """Format D: [stream_key, pool_text, seed, seed_mode, extra]."""
        result = convert_node_widgets_values(
            ["", "{skinny|athletic} body", 0, "randomize", "randomize"]
        )
        self.assertEqual(result, ["{skinny|athletic} body", False, 0])


class ConvertWorkflowTest(unittest.TestCase):
    def test_converts_only_seeded_text_pool_nodes(self):
        workflow = {
            "nodes": [
                {
                    "id": 1,
                    "type": "SeededTextPool",
                    "widgets_values": ["character_2_expression", "smile\nblushing"],
                },
                {"id": 2, "type": "TextPoolRouter", "widgets_values": [0]},
                {
                    "id": 3,
                    "type": "PrimitiveString",
                    "widgets_values": ["masterpiece, best quality"],
                },
            ]
        }
        convert_workflow(workflow)
        self.assertEqual(
            workflow["nodes"][0]["widgets_values"], ["smile\nblushing", False, 0]
        )
        self.assertEqual(workflow["nodes"][1]["widgets_values"], [0])
        self.assertEqual(
            workflow["nodes"][2]["widgets_values"], ["masterpiece, best quality"]
        )

    def test_node_without_widgets_values_unchanged(self):
        workflow = {"nodes": [{"id": 1, "type": "SeededTextPool"}]}
        convert_workflow(workflow)
        self.assertNotIn("widgets_values", workflow["nodes"][0])

    def test_converts_format_b_in_workflow(self):
        """Format B from test2.json: seed+seed_mode at indices 2/3."""
        workflow = {
            "nodes": [
                {
                    "id": 96,
                    "type": "SeededTextPool",
                    "widgets_values": [
                        "01_quality", "masterpiece, best quality", 0, "randomize"
                    ],
                },
                {
                    "id": 97,
                    "type": "SeededTextPool",
                    "widgets_values": [
                        "01_rating", "very awa\\nvery aesthetic", 0, "randomize"
                    ],
                },
            ]
        }
        convert_workflow(workflow)
        self.assertEqual(
            workflow["nodes"][0]["widgets_values"],
            ["masterpiece, best quality", False, 0],
        )
        self.assertEqual(
            workflow["nodes"][1]["widgets_values"],
            ["very awa\\nvery aesthetic", False, 0],
        )

    def test_converts_nodes_inside_subgraphs(self):
        """New-style workflows store nodes inside definitions.subgraphs."""
        workflow = {
            "nodes": [],
            "definitions": {
                "subgraphs": [
                    {
                        "name": "BODY + NUDITY",
                        "nodes": [
                            {
                                "id": 1664,
                                "type": "SeededTextPool",
                                "widgets_values": [
                                    "", "{skinny|athletic} body", 0, "randomize", "randomize"
                                ],
                            },
                            {
                                "id": 1665,
                                "type": "TagJoin",
                                "widgets_values": ["joined"],
                            },
                        ],
                    },
                ]
            },
        }
        convert_workflow(workflow)
        sub = workflow["definitions"]["subgraphs"][0]["nodes"]
        self.assertEqual(sub[0]["widgets_values"], ["{skinny|athletic} body", False, 0])
        self.assertEqual(sub[1]["widgets_values"], ["joined"])

    def test_removes_prompt_context_node(self):
        workflow = {
            "nodes": [
                {"id": 100, "type": "PromptContext", "widgets_values": [42]},
                {"id": 96, "type": "SeededTextPool"},
            ]
        }
        convert_workflow(workflow)
        self.assertEqual([n["id"] for n in workflow["nodes"]], [96])

    def test_strips_context_slots_from_nodes(self):
        workflow = {
            "nodes": [
                {
                    "id": 96,
                    "type": "SeededTextPool",
                    "inputs": [
                        {"name": "pool_text", "type": "STRING"},
                        {"name": "context", "type": "PROMPT_CONTEXT"},
                    ],
                    "outputs": [
                        {"name": "text", "type": "STRING"},
                        {"name": "seed", "type": "INT"},
                        {"name": "context", "type": "PROMPT_CONTEXT"},
                    ],
                }
            ]
        }
        convert_workflow(workflow)
        node = workflow["nodes"][0]
        self.assertEqual([i["name"] for i in node["inputs"]], ["pool_text"])
        self.assertEqual([o["name"] for o in node["outputs"]], ["text", "seed"])

    def test_removes_context_links_list_form(self):
        workflow = {
            "nodes": [
                {"id": 1, "type": "SeededTextPool"},
                {"id": 2, "type": "TagJoin"},
            ],
            "links": [
                [1, 1, 0, 2, 0, "STRING"],
                [2, 100, 0, 1, 3, "PROMPT_CONTEXT"],
            ],
        }
        convert_workflow(workflow)
        self.assertEqual(workflow["links"], [[1, 1, 0, 2, 0, "STRING"]])

    def test_removes_context_links_dict_form(self):
        workflow = {
            "nodes": [
                {"id": 1, "type": "SeededTextPool"},
                {"id": 2, "type": "TagJoin"},
            ],
            "links": [
                {"id": 1, "origin_id": 1, "target_id": 2, "type": "STRING"},
                {"id": 2, "origin_id": 100, "target_id": 1, "type": "PROMPT_CONTEXT"},
            ],
        }
        convert_workflow(workflow)
        self.assertEqual(len(workflow["links"]), 1)
        self.assertEqual(workflow["links"][0]["type"], "STRING")

    def test_drops_links_dangling_after_node_removal(self):
        workflow = {
            "nodes": [
                {"id": 1, "type": "SeededTextPool"},
                {"id": 2, "type": "TagJoin"},
            ],
            "links": [
                [1, 296, 0, 100, 0, "INT"],  # Seed -> PromptContext (removed)
                [2, 1, 0, 2, 0, "STRING"],
            ],
        }
        convert_workflow(workflow)
        self.assertEqual(workflow["links"], [[2, 1, 0, 2, 0, "STRING"]])

    def test_strips_context_from_subgraph_interface(self):
        workflow = {
            "nodes": [],
            "definitions": {
                "subgraphs": [
                    {
                        "nodes": [{"id": 1, "type": "SeededTextPool"}],
                        "links": [
                            {
                                "id": 1,
                                "origin_id": -10,
                                "origin_slot": 2,
                                "target_id": 1,
                                "target_slot": 0,
                                "type": "PROMPT_CONTEXT",
                            }
                        ],
                        "inputs": [
                            {"name": "text", "type": "STRING"},
                            {"name": "context", "type": "PROMPT_CONTEXT"},
                        ],
                        "outputs": [{"name": "seed", "type": "INT"}],
                        "inputNode": {
                            "id": -10,
                            "inputs": [
                                {"name": "text", "type": "STRING"},
                                {"name": "context", "type": "PROMPT_CONTEXT"},
                            ],
                        },
                        "outputNode": {
                            "id": -20,
                            "outputs": [{"name": "seed", "type": "INT"}],
                        },
                    }
                ]
            },
        }
        convert_workflow(workflow)
        sg = workflow["definitions"]["subgraphs"][0]
        self.assertEqual([i["name"] for i in sg["inputs"]], ["text"])
        self.assertEqual([i["name"] for i in sg["inputNode"]["inputs"]], ["text"])
        self.assertEqual(sg["links"], [])


if __name__ == "__main__":
    unittest.main()
