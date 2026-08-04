class BranchSelect2:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "index": ("INT", {"default": 0, "min": 0, "max": 1}),
                "solo": ("STRING", {"default": "", "multiline": True}),
                "duo": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "select"
    CATEGORY = "OneTwoPerson"

    def select(self, index, solo, duo):
        if index == 0:
            return (solo,)
        elif index == 1:
            return (duo,)
        else:
            raise ValueError(f"BranchSelect2: index must be 0 or 1, got {index}")
