import random


class OneTwoPersonToggle:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["random", "1girl", "2girls"], {"default": "random"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            }
        }

    RETURN_TYPES = ("INT", "STRING", "BOOLEAN", "INT")
    RETURN_NAMES = ("branch_index", "count_label", "is_two_or_more", "seed")
    FUNCTION = "choose"
    CATEGORY = "OneTwoPerson"

    def choose(self, mode, seed):
        if mode == "1girl":
            branch_index = 0
            is_two_or_more = False
            count_label = "1girl"
        elif mode == "2girls":
            branch_index = 1
            is_two_or_more = True
            count_label = "2girls"
        else:  # random
            rng = random.Random(seed)
            branch_index = rng.randint(0, 1)
            if branch_index == 0:
                is_two_or_more = False
                count_label = "1girl"
            else:
                is_two_or_more = True
                count_label = "2girls"
        return (branch_index, count_label, is_two_or_more, seed)
