import torch

class ResolutionSwitch:
    DESCRIPTION = (
        "Picks width/height from a preset string and builds an empty latent. "
        "Also outputs CLIP-scaled dimensions.\n"
        "\n"
        "Parse 'W x H (ratio)', e.g. '1024 x 1024 (1:1)' → width=1024, "
        "height=1024. scaled_width/scaled_height = int(dimension * clip_scale). "
        "Latent is zeros with shape [batch_size, 4, height/8, width/8].\n"
        "\n"
        "Examples: 1024×1024 and clip_scale=2 → scaled 2048×2048. "
        "832×1216 and clip_scale=1 → scaled 832×1216.\n"
        "\n"
        "Edge cases: integer truncation on scaled size (1152 * 1.5 → 1728). "
        "Latent spatial size uses height//8 and width//8. batch_size is 1…4096."
    )

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "resolution": (
                    [
                        "1024 x 1024 (1:1)",
                        "896 x 1152 (3:4)",
                        "832 x 1216 (2:3)",
                        "1216 x 832 (3:2)",
                        "1152 x 896 (4:3)",
                    ],
                    {"default": "1024 x 1024 (1:1)"}
                ),
                "batch_size": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 4096
                }),
                "clip_scale": ("FLOAT", {
                    "default": 2.0,
                    "min": 1.0,
                    "max": 4.0,
                    "step": 0.5
                }),
            },
        }

    RETURN_TYPES = ("INT", "INT", "LATENT", "INT", "INT")
    RETURN_NAMES = ("width", "height", "latent", "scaled_width", "scaled_height")
    FUNCTION = "get_resolution"
    CATEGORY = "Dynamic Prompt Engine"

    def get_resolution(self, resolution, batch_size, clip_scale):
        # Extract width and height from the string
        parts = resolution.split("x")
        width = int(parts[0].strip())
        # The second part contains the height and aspect ratio e.g., "1024 (1:1)"
        height = int(parts[1].split("(")[0].strip())
        
        scaled_width = int(width * clip_scale)
        scaled_height = int(height * clip_scale)

        # Create an empty latent tensor (shape: [batch, channels, height // 8, width // 8])
        latent = torch.zeros([batch_size, 4, height // 8, width // 8])
        
        return (width, height, {"samples": latent}, scaled_width, scaled_height)
