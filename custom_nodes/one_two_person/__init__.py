from .one_two_person_controller import OneTwoPersonToggle
from .branch_select2 import BranchSelect2
from .tag_join import TagJoin

NODE_CLASS_MAPPINGS = {
    "OneTwoPersonToggle": OneTwoPersonToggle,
    "BranchSelect2": BranchSelect2,
    "TagJoin": TagJoin,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OneTwoPersonToggle": "One/Two Person Toggle",
    "BranchSelect2": "Branch Select 2",
    "TagJoin": "Tag Join",
}
