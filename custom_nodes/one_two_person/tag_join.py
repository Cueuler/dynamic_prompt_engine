class TagJoin:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "enable": ("BOOLEAN", {"default": True}),
                "tag_1": ("STRING", {"default": ""}),
                "tag_2": ("STRING", {"default": ""}),
                "tag_3": ("STRING", {"default": ""}),
                "tag_4": ("STRING", {"default": ""}),
                "tag_5": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "join"
    CATEGORY = "OneTwoPerson"

    def join(self, enable=True, **kwargs):
        if not enable:
            return ("",)

        # Collect all tag inputs (ignore 'enable')
        parts = []
        for i in range(1, 6):
            tag = kwargs.get(f"tag_{i}", "")
            stripped = tag.strip()
            if stripped:
                parts.append(stripped)

        result = ", ".join(parts) if parts else ""
        return (result,)
