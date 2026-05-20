bl_info = {
    "name": "Shapekeys **",
    "author": "CamsAvis",
    "version": (2, 0, 0),
    "blender": (5, 1, 0),
    "location": "Properties > Object Data > Shapekeys **",
    "description": (
        "Folder-tree view of shape keys with scrollable resizable list, "
        "multi-select, and toolbar (add/remove/move/rename)."
    ),
    "category": "Object",
}

import hashlib
import re
import time
import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import (
    AddonPreferences,
    Menu,
    Operator,
    Panel,
    PropertyGroup,
    UIList,
)


VRC_PREFIX = "vrc."
VRC_FOLDER = "VRC"
UNGROUPED_FOLDER = "Ungrouped"
FACE_TRACKING_FOLDER = "Face Tracking"

# VRCFT Unified Blendshapes (https://docs.vrcft.io/docs/tutorial-avatars/tutorial-avatars-extras/unified-blendshapes)
FACE_TRACKING_NAMES = frozenset({
    "EyeLookOutRight", "EyeLookInRight", "EyeLookUpRight", "EyeLookDownRight",
    "EyeLookOutLeft", "EyeLookInLeft", "EyeLookUpLeft", "EyeLookDownLeft",
    "EyeClosedRight", "EyeClosedLeft", "EyeSquintRight", "EyeSquintLeft",
    "EyeWideRight", "EyeWideLeft", "EyeDilationRight", "EyeDilationLeft",
    "EyeConstrictRight", "EyeConstrictLeft",
    "EyeClosed", "EyeWide", "EyeSquint", "EyeDilation", "EyeConstrict",
    "BrowPinchRight", "BrowPinchLeft", "BrowLowererRight", "BrowLowererLeft",
    "BrowInnerUpRight", "BrowInnerUpLeft", "BrowOuterUpRight", "BrowOuterUpLeft",
    "BrowDownRight", "BrowDownLeft", "BrowDown", "BrowInnerUp",
    "BrowUpRight", "BrowUpLeft", "BrowUp",
    "NoseSneerRight", "NoseSneerLeft", "NasalDilationRight", "NasalDilationLeft",
    "NasalConstrictRight", "NasalConstrictLeft",
    "NoseSneer", "NasalDilation", "NasalConstrict",
    "CheekSquintRight", "CheekSquintLeft", "CheekPuffRight", "CheekPuffLeft",
    "CheekSuckRight", "CheekSuckLeft",
    "CheekPuff", "CheekSuck", "CheekSquint",
    "JawOpen", "JawRight", "JawLeft", "JawForward", "JawBackward",
    "JawClench", "JawMandibleRaise", "MouthClosed",
    "LipSuckUpperRight", "LipSuckUpperLeft", "LipSuckLowerRight", "LipSuckLowerLeft",
    "LipSuckCornerRight", "LipSuckCornerLeft",
    "LipFunnelUpperRight", "LipFunnelUpperLeft", "LipFunnelLowerRight", "LipFunnelLowerLeft",
    "LipPuckerUpperRight", "LipPuckerUpperLeft", "LipPuckerLowerRight", "LipPuckerLowerLeft",
    "LipSuckUpper", "LipSuckLower", "LipSuck",
    "LipFunnelUpper", "LipFunnelLower", "LipFunnel",
    "LipPuckerUpper", "LipPuckerLower", "LipPucker",
    "MouthUpperUpRight", "MouthUpperUpLeft", "MouthLowerDownRight", "MouthLowerDownLeft",
    "MouthUpperDeepenRight", "MouthUpperDeepenLeft",
    "MouthUpperRight", "MouthUpperLeft", "MouthLowerRight", "MouthLowerLeft",
    "MouthCornerPullRight", "MouthCornerPullLeft",
    "MouthCornerSlantRight", "MouthCornerSlantLeft",
    "MouthFrownRight", "MouthFrownLeft", "MouthStretchRight", "MouthStretchLeft",
    "MouthDimpleRight", "MouthDimpleLeft",
    "MouthRaiserUpper", "MouthRaiserLower",
    "MouthPressRight", "MouthPressLeft", "MouthTightenerRight", "MouthTightenerLeft",
    "MouthUpperUp", "MouthLowerDown", "MouthOpen", "MouthRight", "MouthLeft",
    "MouthSmileRight", "MouthSmileLeft", "MouthSmile",
    "MouthSadRight", "MouthSadLeft", "MouthSad",
    "MouthStretch", "MouthDimple", "MouthTightener", "MouthPress",
    "TongueOut", "TongueUp", "TongueDown", "TongueRight", "TongueLeft",
    "TongueRoll", "TongueBendDown", "TongueCurlUp", "TongueSquish", "TongueFlat",
    "TongueTwistRight", "TongueTwistLeft",
    "SoftPalateClose", "ThroatSwallow",
    "NeckFlexRight", "NeckFlexLeft",
    # SRanipal / ARKit-style averaged variants and custom face-tracking shapes
    "BrowOuterUp",
    "EyeLookUp", "EyeLookDown", "EyeLookIn", "EyeLookOut",
    "Eyes Concave",
    "LipPuckerLeft", "LipPuckerRight",
    "Lips Curve Down",
    "MouthApeShape", "MouthFrown", "MouthRaiser",
    "TongueOutStep1", "TongueOutStep2",
})
ROOT_SENTINEL = "__root__"
LEAVES_KEY = "__leaves__"


# ----- PropertyGroups -----

class SHAPEKEYFOLDER_PG_state(PropertyGroup):
    path: StringProperty()
    expanded: BoolProperty(default=True)


class SHAPEKEYFOLDER_PG_view_row(PropertyGroup):
    name: StringProperty()
    row_type: EnumProperty(items=[
        ('FOLDER', 'Folder', ''),
        ('KEY', 'Key', ''),
    ], default='KEY')
    depth: IntProperty(default=0)
    folder_path: StringProperty()
    key_index: IntProperty(default=-1)
    selected: BoolProperty(default=False)


# ----- Addon Preferences -----

class SHAPEKEYFOLDER_AP_prefs(AddonPreferences):
    bl_idname = __name__

    separator: StringProperty(
        name="Folder Separator",
        description=(
            "Character(s) used in shape key names to split into folders "
            "(e.g. '/' makes 'Expressions/Smile' nest under an 'Expressions' folder)"
        ),
        default="/",
        maxlen=4,
    )

    group_vrc: BoolProperty(
        name="Group VRChat Shape Keys",
        description="Group all 'vrc.*' keys under a single 'vrc' folder",
        default=True,
    )

    group_ungrouped: BoolProperty(
        name="Group Ungrouped Shape Keys",
        description="Place keys without a folder separator into an 'Ungrouped' folder",
        default=True,
    )

    group_face_tracking: BoolProperty(
        name="Group Face Tracking Shape Keys",
        description=(
            "Group keys whose names match VRCFT Unified Blendshapes "
            "into a 'Face Tracking' folder (only applies to keys without a slash prefix)"
        ),
        default=True,
    )

    list_rows: IntProperty(
        name="Default Visible Rows",
        description="Default number of rows shown in the list before scrolling kicks in",
        default=15,
        min=4,
        max=60,
    )

    search_debounce_enabled: BoolProperty(
        name="Debounce Search",
        description=(
            "Wait until typing pauses before rebuilding the filtered list. "
            "Disable to filter live on every keystroke (can lag on big rigs)"
        ),
        default=True,
    )

    search_debounce_ms: IntProperty(
        name="Search Debounce (ms)",
        description="Idle time after the last keystroke before the filtered list refreshes",
        default=200,
        min=0,
        soft_max=1000,
        max=5000,
        subtype='TIME',
    )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "separator")
        col.prop(self, "group_vrc")
        col.prop(self, "group_face_tracking")
        col.prop(self, "group_ungrouped")
        col.prop(self, "list_rows")
        col.separator()
        col.prop(self, "search_debounce_enabled")
        row = col.row()
        row.enabled = self.search_debounce_enabled
        row.prop(self, "search_debounce_ms")


def _get_prefs(context):
    return context.preferences.addons[__name__].preferences


# ----- Folder state helpers -----

def _find_state(obj, path):
    for s in obj.shape_key_folder_states:
        if s.path == path:
            return s
    return None


def _is_folder_expanded(obj, path):
    s = _find_state(obj, path)
    return True if s is None else s.expanded


# ----- Tree builder -----

def _build_tree(key_blocks, separator, group_vrc=True, group_ungrouped=True, group_face_tracking=True):
    root = {}
    for idx, kb in enumerate(key_blocks):
        name = kb.name

        if idx == 0:
            root.setdefault(LEAVES_KEY, []).append((idx, kb, name))
            continue

        if group_vrc and name.startswith(VRC_PREFIX) and len(name) > len(VRC_PREFIX):
            leaf_name = name[len(VRC_PREFIX):]
            cursor = root.setdefault(VRC_FOLDER, {})
            cursor.setdefault(LEAVES_KEY, []).append((idx, kb, leaf_name))
            continue

        parts = [p for p in name.split(separator) if p]
        if len(parts) > 1:
            cursor = root
            for p in parts[:-1]:
                cursor = cursor.setdefault(p, {})
            cursor.setdefault(LEAVES_KEY, []).append((idx, kb, parts[-1]))
            continue

        display_name = parts[0] if parts else name
        if group_face_tracking and display_name in FACE_TRACKING_NAMES:
            cursor = root.setdefault(FACE_TRACKING_FOLDER, {})
            cursor.setdefault(LEAVES_KEY, []).append((idx, kb, display_name))
            continue
        target = root.setdefault(UNGROUPED_FOLDER, {}) if group_ungrouped else root
        target.setdefault(LEAVES_KEY, []).append((idx, kb, display_name))
    return root


def _compute_folder_paths(key_blocks, separator, group_vrc, group_ungrouped, group_face_tracking=True):
    paths = []
    for idx, kb in enumerate(key_blocks):
        name = kb.name
        if idx == 0:
            paths.append(ROOT_SENTINEL)
            continue
        if group_vrc and name.startswith(VRC_PREFIX) and len(name) > len(VRC_PREFIX):
            paths.append(VRC_FOLDER)
            continue
        parts = [p for p in name.split(separator) if p]
        if len(parts) > 1:
            paths.append(separator.join(parts[:-1]))
            continue
        display_name = parts[0] if parts else name
        if group_face_tracking and display_name in FACE_TRACKING_NAMES:
            paths.append(FACE_TRACKING_FOLDER)
            continue
        paths.append(UNGROUPED_FOLDER if group_ungrouped else ROOT_SENTINEL)
    return paths


# ----- View row rebuild -----

def _get_fingerprint(obj, prefs):
    sk = getattr(obj.data, "shape_keys", None)
    if not sk:
        return ""
    parts = [
        str(len(sk.key_blocks)),
        "\n".join(kb.name for kb in sk.key_blocks),
        prefs.separator,
        "1" if prefs.group_vrc else "0",
        "1" if prefs.group_ungrouped else "0",
        "1" if prefs.group_face_tracking else "0",
        ";".join(f"{s.path}={'1' if s.expanded else '0'}" for s in obj.shape_key_folder_states),
        obj.shape_key_search or "",
        "1" if obj.shape_key_search_regex else "0",
    ]
    return hashlib.md5("\n\x01\n".join(parts).encode("utf-8", errors="replace")).hexdigest()


def _compute_nonzero_folders(obj, prefs):
    sk = getattr(obj.data, "shape_keys", None)
    if not sk:
        return set()
    sep = prefs.separator if prefs.separator else "/"
    paths = _compute_folder_paths(
        sk.key_blocks, sep,
        prefs.group_vrc, prefs.group_ungrouped,
        getattr(prefs, "group_face_tracking", True),
    )
    result = set()
    for ki, kb in enumerate(sk.key_blocks):
        if kb.value == 0.0:
            continue
        kp = paths[ki]
        if not kp or kp == ROOT_SENTINEL:
            continue
        parts = kp.split("/")
        for i in range(1, len(parts) + 1):
            result.add("/".join(parts[:i]))
    return result


def _branch_has_match(node, matcher, key_blocks):
    for ki, _kb, _dn in node.get(LEAVES_KEY, []):
        if 0 <= ki < len(key_blocks) and matcher(key_blocks[ki].name):
            return True
    for k, child in node.items():
        if k == LEAVES_KEY:
            continue
        if _branch_has_match(child, matcher, key_blocks):
            return True
    return False


def _rebuild_view_rows(obj, prefs, force=False):
    sk = getattr(obj.data, "shape_keys", None)
    if not sk:
        obj.shape_key_view_rows.clear()
        obj.shape_key_view_fingerprint = ""
        return

    fp = _get_fingerprint(obj, prefs)
    if not force and fp == obj.shape_key_view_fingerprint and len(obj.shape_key_view_rows) > 0:
        return

    selected_indices = {
        r.key_index for r in obj.shape_key_view_rows
        if r.row_type == 'KEY' and r.selected
    }

    sep = prefs.separator if prefs.separator else "/"
    tree = _build_tree(
        sk.key_blocks, sep,
        group_vrc=prefs.group_vrc,
        group_ungrouped=prefs.group_ungrouped,
        group_face_tracking=prefs.group_face_tracking,
    )

    query = (obj.shape_key_search or "").strip()
    matcher = None
    if query:
        if obj.shape_key_search_regex:
            try:
                pat = re.compile(query, re.IGNORECASE)
                matcher = lambda name, _p=pat: _p.search(name) is not None
            except re.error:
                matcher = None
        else:
            ql = query.lower()
            matcher = lambda name, _q=ql: _q in name.lower()
    searching = matcher is not None

    rows = obj.shape_key_view_rows
    rows.clear()

    def emit(node, parent_path, depth):
        for ki, _kb, display_name in node.get(LEAVES_KEY, []):
            if searching and not matcher(sk.key_blocks[ki].name):
                continue
            r = rows.add()
            r.row_type = 'KEY'
            r.depth = depth
            r.key_index = ki
            r.name = display_name
            r.selected = ki in selected_indices
        folder_names = [k for k in node.keys() if k != LEAVES_KEY]
        if depth == 0 and UNGROUPED_FOLDER in folder_names:
            folder_names.remove(UNGROUPED_FOLDER)
            folder_names.append(UNGROUPED_FOLDER)
        for fname in folder_names:
            child = node[fname]
            child_path = fname if not parent_path else (parent_path + "/" + fname)
            if searching and not _branch_has_match(child, matcher, sk.key_blocks):
                continue
            r = rows.add()
            r.row_type = 'FOLDER'
            r.depth = depth
            r.folder_path = child_path
            r.name = fname
            if searching or _is_folder_expanded(obj, child_path):
                emit(child, child_path, depth + 1)

    emit(tree, "", 0)
    if obj.shape_key_view_active_index >= len(rows):
        obj.shape_key_view_active_index = max(0, len(rows) - 1)
    obj.shape_key_view_fingerprint = fp


def _mark_stale(obj):
    obj.shape_key_view_fingerprint = ""


_pending_rebuilds = set()


def _schedule_rebuild(obj_name):
    if obj_name in _pending_rebuilds:
        return
    _pending_rebuilds.add(obj_name)

    def cb():
        _pending_rebuilds.discard(obj_name)
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            return None
        try:
            prefs = bpy.context.preferences.addons[__name__].preferences
        except KeyError:
            return None
        try:
            _rebuild_view_rows(obj, prefs)
        except Exception:
            pass
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PROPERTIES':
                    area.tag_redraw()
        return None

    bpy.app.timers.register(cb, first_interval=0.0)


# ----- UIList -----

class SHAPEKEYFOLDER_UL_keys(UIList):
    _nonzero_folders = frozenset()

    def draw_filter(self, context, layout):
        pass

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flt_flags = [self.bitflag_filter_item] * len(items)
        return flt_flags, []

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        obj = data
        sk = getattr(obj.data, "shape_keys", None)
        kb = sk.key_blocks if sk else None

        if item.row_type == 'FOLDER':
            has_nonzero = item.folder_path in SHAPEKEYFOLDER_UL_keys._nonzero_folders
            row = layout.row(align=True)
            row.alignment = 'EXPAND'
            left = row.row(align=True)
            left.alignment = 'LEFT'
            for _ in range(item.depth):
                left.label(text="", icon='BLANK1')
            expanded = _is_folder_expanded(obj, item.folder_path)
            op_tria = left.operator(
                SHAPEKEYFOLDER_OT_toggle_folder.bl_idname,
                text="",
                icon='TRIA_DOWN' if expanded else 'TRIA_RIGHT',
                emboss=False,
            )
            op_tria.path = item.folder_path
            is_ungrouped = item.folder_path == UNGROUPED_FOLDER
            label_text = item.name + (" (*)" if has_nonzero else "")
            if is_ungrouped:
                op = left.operator(
                    SHAPEKEYFOLDER_OT_toggle_folder.bl_idname,
                    text=label_text,
                    emboss=False,
                )
            else:
                op = left.operator(
                    SHAPEKEYFOLDER_OT_toggle_folder.bl_idname,
                    text=label_text,
                    icon='FILEBROWSER' if expanded else 'FILE_FOLDER',
                    emboss=False,
                )
            op.path = item.folder_path
            right = row.row(align=True)
            right.alignment = 'RIGHT'
            if has_nonzero:
                op_x = right.operator(
                    SHAPEKEYFOLDER_OT_clear_folder_values.bl_idname,
                    text="", icon='X', emboss=False,
                )
                op_x.path = item.folder_path
            else:
                right.label(text="", icon='BLANK1')
            return

        ki = item.key_index
        if kb is None or ki < 0 or ki >= len(kb):
            layout.label(text="(stale row)")
            return
        key = kb[ki]
        is_basis = (ki == 0)

        row = layout.row(align=True)
        for _ in range(item.depth):
            row.label(text="", icon='BLANK1')

        row.label(text="", icon='SHAPEKEY_DATA')

        is_active = (ki == obj.active_shape_key_index)

        if is_basis:
            name_sub = row.row()
            name_sub.alignment = 'LEFT'
            op = name_sub.operator(
                SHAPEKEYFOLDER_OT_set_active_key.bl_idname,
                text=item.name,
                emboss=False,
                depress=is_active,
            )
            op.index = ki
            op.view_row_index = index
            return

        row.prop(item, "selected", text="")

        idx_sub = row.row()
        idx_sub.alignment = 'LEFT'
        idx_sub.active = False
        idx_sub.label(text=f"{ki:03d}")

        split = row.split(factor=0.45)
        name_sub = split.row()
        name_sub.alignment = 'LEFT'
        op = name_sub.operator(
            SHAPEKEYFOLDER_OT_set_active_key.bl_idname,
            text=item.name,
            emboss=False,
            depress=is_active,
        )
        op.index = ki
        op.view_row_index = index

        right_sub = split.row(align=True)
        right_sub.prop(key, "value", text="", slider=True)
        right_sub.prop(
            key, "mute", text="",
            icon='HIDE_ON' if key.mute else 'HIDE_OFF',
            emboss=False,
        )


# ----- Operators -----

class SHAPEKEYFOLDER_OT_toggle_folder(Operator):
    bl_idname = "object.shape_key_folder_toggle"
    bl_label = "Toggle Shape Key Folder"
    bl_description = "Expand or collapse a shape-key folder"
    bl_options = {'INTERNAL'}

    path: StringProperty()

    def execute(self, context):
        obj = context.object
        if obj is None:
            return {'CANCELLED'}
        s = _find_state(obj, self.path)
        if s is None:
            s = obj.shape_key_folder_states.add()
            s.path = self.path
            s.expanded = False
        else:
            s.expanded = not s.expanded
        _mark_stale(obj)
        _rebuild_view_rows(obj, _get_prefs(context))
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_set_active_key(Operator):
    bl_idname = "object.shape_key_set_active"
    bl_label = "Set Active / Select Shape Key"
    bl_description = (
        "Click: select & set active. Shift-click: range select. "
        "Ctrl-click: toggle in selection. Double-click: rename."
    )
    bl_options = {'INTERNAL', 'UNDO'}

    index: IntProperty()
    view_row_index: IntProperty(default=-1)

    _last_click_time = 0.0
    _last_click_index = -1
    _DOUBLE_CLICK_WINDOW = 0.45

    def invoke(self, context, event):
        cls = SHAPEKEYFOLDER_OT_set_active_key
        now = time.monotonic()
        is_double = (
            self.index == cls._last_click_index
            and (now - cls._last_click_time) < cls._DOUBLE_CLICK_WINDOW
        )
        cls._last_click_time = now
        cls._last_click_index = self.index

        if is_double or (event.type == 'LEFTMOUSE' and event.value == 'DOUBLE_CLICK'):
            bpy.ops.object.shape_key_rename_popup('INVOKE_DEFAULT', index=self.index)
            return {'FINISHED'}

        obj = context.object
        if obj is None or not getattr(obj.data, "shape_keys", None):
            return {'CANCELLED'}
        kb_len = len(obj.data.shape_keys.key_blocks)
        if not (0 <= self.index < kb_len):
            return {'CANCELLED'}

        rows = obj.shape_key_view_rows
        prev_view = obj.shape_key_view_active_index
        cur_view = self.view_row_index

        if event.shift and 0 <= prev_view < len(rows) and 0 <= cur_view < len(rows):
            lo, hi = (prev_view, cur_view) if prev_view <= cur_view else (cur_view, prev_view)
            for i in range(lo, hi + 1):
                if rows[i].row_type == 'KEY':
                    rows[i].selected = True
        elif event.ctrl and 0 <= cur_view < len(rows):
            rows[cur_view].selected = not rows[cur_view].selected

        obj.active_shape_key_index = self.index
        if 0 <= cur_view < len(rows):
            obj.shape_key_view_active_index = cur_view
        return {'FINISHED'}

    def execute(self, context):
        obj = context.object
        if obj and getattr(obj.data, "shape_keys", None):
            if 0 <= self.index < len(obj.data.shape_keys.key_blocks):
                obj.active_shape_key_index = self.index
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_select_all(Operator):
    bl_idname = "object.shape_key_select_all"
    bl_label = "Select / Deselect All"
    bl_description = "Select or deselect all shape keys in the list"
    bl_options = {'INTERNAL'}

    action: EnumProperty(items=[
        ('SELECT', "Select", ""),
        ('DESELECT', "Deselect", ""),
    ], default='SELECT')

    def execute(self, context):
        obj = context.object
        if obj is None:
            return {'CANCELLED'}
        flag = self.action == 'SELECT'
        for r in obj.shape_key_view_rows:
            if r.row_type == 'KEY':
                r.selected = flag
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_add_at_end(Operator):
    bl_idname = "object.shape_key_add_at_end"
    bl_label = "Add Shape Key"
    bl_description = "Add a new shape key at the end of the list"
    bl_options = {'REGISTER', 'UNDO'}

    from_mix: BoolProperty(default=False)

    def execute(self, context):
        obj = context.object
        if obj is None:
            return {'CANCELLED'}
        bpy.ops.object.shape_key_add(from_mix=self.from_mix)
        state = _find_state(obj, UNGROUPED_FOLDER)
        if state is None:
            state = obj.shape_key_folder_states.add()
            state.path = UNGROUPED_FOLDER
        state.expanded = True
        _mark_stale(obj)
        _rebuild_view_rows(obj, _get_prefs(context))
        new_idx = obj.active_shape_key_index
        for view_idx, r in enumerate(obj.shape_key_view_rows):
            if r.row_type == 'KEY' and r.key_index == new_idx:
                obj.shape_key_view_active_index = view_idx
                break
        return {'FINISHED'}


class SHAPEKEYFOLDER_MT_add_menu(Menu):
    bl_idname = "SHAPEKEYFOLDER_MT_add_menu"
    bl_label = "Add Shape Key"

    def draw(self, context):
        layout = self.layout
        op = layout.operator(SHAPEKEYFOLDER_OT_add_at_end.bl_idname, text="Create New")
        op.from_mix = False
        op = layout.operator(
            SHAPEKEYFOLDER_OT_add_at_end.bl_idname,
            text="Create from Visible Shapekeys",
        )
        op.from_mix = True


class SHAPEKEYFOLDER_OT_clear_all_values(Operator):
    bl_idname = "object.shape_key_clear_all_values"
    bl_label = "Reset All Shape Key Values"
    bl_description = "Set every shape key's value to 0"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        sk = getattr(obj.data, "shape_keys", None) if obj else None
        if not sk:
            return {'CANCELLED'}
        for kb in sk.key_blocks:
            kb.value = 0.0
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_clear_folder_values(Operator):
    bl_idname = "object.shape_key_folder_clear_values"
    bl_label = "Reset Folder Shape Key Values"
    bl_description = "Set every shape key inside this folder (recursively) to 0"
    bl_options = {'REGISTER', 'UNDO'}

    path: StringProperty()

    def execute(self, context):
        obj = context.object
        sk = getattr(obj.data, "shape_keys", None) if obj else None
        if not sk or not self.path:
            return {'CANCELLED'}
        prefs = _get_prefs(context)
        sep = prefs.separator if prefs.separator else "/"
        paths = _compute_folder_paths(
            sk.key_blocks, sep,
            prefs.group_vrc, prefs.group_ungrouped,
            getattr(prefs, "group_face_tracking", True),
        )
        prefix = self.path + "/"
        for ki, kb in enumerate(sk.key_blocks):
            kp = paths[ki]
            if kp == self.path or kp.startswith(prefix):
                kb.value = 0.0
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_invoke_native(Operator):
    bl_idname = "object.shape_key_invoke_native"
    bl_label = "Invoke Native Shape Key Operator"
    bl_description = "Sets the given shape key as active and calls a native shape key operator"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()
    op_id: StringProperty()

    def execute(self, context):
        obj = context.object
        if obj is None or not getattr(obj.data, "shape_keys", None):
            return {'CANCELLED'}
        kb = obj.data.shape_keys.key_blocks
        if not (0 <= self.index < len(kb)):
            return {'CANCELLED'}
        obj.active_shape_key_index = self.index
        parts = self.op_id.split(".", 1)
        if len(parts) != 2:
            return {'CANCELLED'}
        try:
            getattr(getattr(bpy.ops, parts[0]), parts[1])()
        except Exception as e:
            self.report({'ERROR'}, f"{self.op_id}: {e}")
            return {'CANCELLED'}
        _mark_stale(obj)
        _rebuild_view_rows(obj, _get_prefs(context))
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_remove_single(Operator):
    bl_idname = "object.shape_key_remove_single"
    bl_label = "Delete Shape Key"
    bl_description = "Delete this single shape key (Basis cannot be deleted)"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()

    def invoke(self, context, event):
        obj = context.object
        if obj is None or not getattr(obj.data, "shape_keys", None):
            return {'CANCELLED'}
        kb = obj.data.shape_keys.key_blocks
        if not (0 <= self.index < len(kb)) or self.index == 0:
            self.report({'INFO'}, "Cannot delete Basis")
            return {'CANCELLED'}
        name = kb[self.index].name
        return context.window_manager.invoke_confirm(
            self, event, message=f"Delete '{name}'?",
        )

    def execute(self, context):
        obj = context.object
        if obj is None or not getattr(obj.data, "shape_keys", None):
            return {'CANCELLED'}
        kb = obj.data.shape_keys.key_blocks
        if 0 <= self.index < len(kb) and self.index >= 1:
            obj.active_shape_key_index = self.index
            bpy.ops.object.shape_key_remove(all=False)
            new_len = (
                len(obj.data.shape_keys.key_blocks)
                if obj.data.shape_keys else 0
            )
            if obj.active_shape_key_index >= new_len:
                obj.active_shape_key_index = max(0, new_len - 1)
            _mark_stale(obj)
            _schedule_rebuild(obj.name)
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_remove_selected(Operator):
    bl_idname = "object.shape_key_remove_selected"
    bl_label = "Remove Selected Shape Keys"
    bl_description = "Delete all selected shape keys (Basis is never deleted)"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def _selected_indices(obj):
        return sorted({
            r.key_index for r in obj.shape_key_view_rows
            if r.row_type == 'KEY' and r.selected and r.key_index >= 1
        })

    def invoke(self, context, event):
        obj = context.object
        if obj is None or not getattr(obj.data, "shape_keys", None):
            return {'CANCELLED'}
        sel = self._selected_indices(obj)
        if not sel:
            self.report({'INFO'}, "No shape keys selected")
            return {'CANCELLED'}
        n = len(sel)
        msg = f"Delete {n} shape key{'s' if n != 1 else ''}?"
        return context.window_manager.invoke_confirm(self, event, message=msg)

    def execute(self, context):
        obj = context.object
        if obj is None or not getattr(obj.data, "shape_keys", None):
            return {'CANCELLED'}
        kb = obj.data.shape_keys.key_blocks
        names = [kb[i].name for i in self._selected_indices(obj)]
        for name in names:
            if name in kb:
                idx = kb.find(name)
                if idx >= 1:
                    obj.active_shape_key_index = idx
                    bpy.ops.object.shape_key_remove(all=False)
        new_len = (
            len(obj.data.shape_keys.key_blocks)
            if obj.data.shape_keys else 0
        )
        if obj.active_shape_key_index >= new_len:
            obj.active_shape_key_index = max(0, new_len - 1)
        _mark_stale(obj)
        _schedule_rebuild(obj.name)
        return {'FINISHED'}


def _move_within_folder(obj, prefs, direction):
    sk = getattr(obj.data, "shape_keys", None)
    if not sk:
        return
    kb = sk.key_blocks
    sep = prefs.separator if prefs.separator else "/"

    selected_names = set()
    for r in obj.shape_key_view_rows:
        if r.row_type == 'KEY' and r.selected and r.key_index >= 1:
            if 0 <= r.key_index < len(kb):
                selected_names.add(kb[r.key_index].name)
    if not selected_names:
        return

    processed = set()
    while True:
        names = [k.name for k in kb]
        paths = _compute_folder_paths(
            kb, sep, prefs.group_vrc, prefs.group_ungrouped,
            getattr(prefs, "group_face_tracking", True),
        )

        target_idx = None
        if direction == 'UP':
            for i, n in enumerate(names):
                if n in selected_names and n not in processed:
                    target_idx = i
                    break
        else:
            for i in range(len(names) - 1, -1, -1):
                n = names[i]
                if n in selected_names and n not in processed:
                    target_idx = i
                    break
        if target_idx is None:
            break

        my_folder = paths[target_idx]
        sibling = None
        if direction == 'UP':
            for m in range(target_idx - 1, 0, -1):
                if paths[m] == my_folder:
                    sibling = m
                    break
        else:
            for m in range(target_idx + 1, len(names)):
                if paths[m] == my_folder:
                    sibling = m
                    break

        if sibling is not None:
            obj.active_shape_key_index = target_idx
            steps = abs(target_idx - sibling)
            for _ in range(steps):
                bpy.ops.object.shape_key_move(type=direction)
        processed.add(names[target_idx])


class SHAPEKEYFOLDER_OT_move_selected_up(Operator):
    bl_idname = "object.shape_key_move_selected_up"
    bl_label = "Move Up Within Folder"
    bl_description = "Move every selected shape key up one slot within its folder"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None:
            return {'CANCELLED'}
        _move_within_folder(obj, _get_prefs(context), 'UP')
        _mark_stale(obj)
        _rebuild_view_rows(obj, _get_prefs(context))
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_move_selected_down(Operator):
    bl_idname = "object.shape_key_move_selected_down"
    bl_label = "Move Down Within Folder"
    bl_description = "Move every selected shape key down one slot within its folder"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if obj is None:
            return {'CANCELLED'}
        _move_within_folder(obj, _get_prefs(context), 'DOWN')
        _mark_stale(obj)
        _rebuild_view_rows(obj, _get_prefs(context))
        return {'FINISHED'}


class SHAPEKEYFOLDER_OT_rename_popup(Operator):
    bl_idname = "object.shape_key_rename_popup"
    bl_label = "Rename Shape Key"
    bl_description = "Rename the full shape key name (including folder path)"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()
    new_name: StringProperty(name="Name")

    def invoke(self, context, event):
        obj = context.object
        if obj is None or not getattr(obj.data, "shape_keys", None):
            return {'CANCELLED'}
        kb = obj.data.shape_keys.key_blocks
        if not (0 <= self.index < len(kb)):
            return {'CANCELLED'}
        self.new_name = kb[self.index].name
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        self.layout.prop(self, "new_name", text="Name")

    def execute(self, context):
        obj = context.object
        if obj is None or not getattr(obj.data, "shape_keys", None):
            return {'CANCELLED'}
        kb = obj.data.shape_keys.key_blocks
        if 0 <= self.index < len(kb) and self.new_name:
            kb[self.index].name = self.new_name
            _mark_stale(obj)
        _rebuild_view_rows(obj, _get_prefs(context))
        return {'FINISHED'}


# ----- Panel -----

class SHAPEKEYFOLDER_PT_panel(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    bl_label = "Shapekeys **"
    bl_order = -1

    @classmethod
    def poll(cls, context):
        obj = context.object
        if obj is None or obj.type not in {'MESH', 'LATTICE', 'CURVE', 'SURFACE'}:
            return False
        return getattr(obj.data, "shape_keys", None) is not None

    def draw(self, context):
        obj = context.object
        prefs = _get_prefs(context)
        if len(obj.shape_key_view_rows) == 0 or \
           obj.shape_key_view_fingerprint != _get_fingerprint(obj, prefs):
            _schedule_rebuild(obj.name)

        SHAPEKEYFOLDER_UL_keys._nonzero_folders = _compute_nonzero_folders(obj, prefs)

        search_row = self.layout.row(align=True)
        search_row.label(text="", icon='VIEWZOOM')
        search_row.prop(obj, "shape_key_search", text="")
        regex_sub = search_row.row(align=True)
        regex_sub.scale_x = 0.4
        regex_sub.prop(obj, "shape_key_search_regex", text=".*", toggle=True)

        row = self.layout.row()
        row.template_list(
            "SHAPEKEYFOLDER_UL_keys", "",
            obj, "shape_key_view_rows",
            obj, "shape_key_view_active_index",
            rows=prefs.list_rows,
        )

        col = row.column(align=True)
        col.operator(
            "wm.call_menu",
            icon='ADD',
            text="",
        ).name = SHAPEKEYFOLDER_MT_add_menu.bl_idname
        col.operator(SHAPEKEYFOLDER_OT_remove_selected.bl_idname, icon='REMOVE', text="")
        col.separator()
        col.operator(SHAPEKEYFOLDER_OT_move_selected_up.bl_idname, icon='TRIA_UP', text="")
        col.operator(SHAPEKEYFOLDER_OT_move_selected_down.bl_idname, icon='TRIA_DOWN', text="")
        col.separator()
        col.operator(
            SHAPEKEYFOLDER_OT_select_all.bl_idname,
            icon='CHECKBOX_HLT', text="",
        ).action = 'SELECT'
        col.operator(
            SHAPEKEYFOLDER_OT_select_all.bl_idname,
            icon='CHECKBOX_DEHLT', text="",
        ).action = 'DESELECT'
        col.separator()
        col.operator(SHAPEKEYFOLDER_OT_clear_all_values.bl_idname, icon='X', text="")


# ----- Right-click context menu -----

def _row_context_menu_draw(self, context):
    bo = getattr(context, "button_operator", None)
    if bo is None:
        return
    if type(bo).__name__ != "OBJECT_OT_shape_key_set_active":
        return
    idx = getattr(bo, "index", -1)
    if idx < 0:
        return
    layout = self.layout
    op = layout.operator(SHAPEKEYFOLDER_OT_rename_popup.bl_idname, text="Rename")
    op.index = idx
    op = layout.operator(SHAPEKEYFOLDER_OT_remove_single.bl_idname, text="Delete")
    op.index = idx
    layout.separator()
    op = layout.operator(SHAPEKEYFOLDER_OT_invoke_native.bl_idname, text="Make Basis")
    op.index = idx
    op.op_id = "object.shape_key_make_basis"
    op = layout.operator(SHAPEKEYFOLDER_OT_invoke_native.bl_idname, text="Apply to Basis")
    op.index = idx
    op.op_id = "object.shape_key_apply_to_basis"
    op = layout.operator(SHAPEKEYFOLDER_OT_invoke_native.bl_idname, text="Duplicate")
    op.index = idx
    op.op_id = "object.shape_key_copy"


# ----- Handlers -----

@persistent
def _on_load_post(_dummy):
    for obj in bpy.data.objects:
        try:
            obj.shape_key_view_fingerprint = ""
        except (AttributeError, TypeError):
            pass


# ----- Registration -----

CLASSES = (
    SHAPEKEYFOLDER_PG_state,
    SHAPEKEYFOLDER_PG_view_row,
    SHAPEKEYFOLDER_AP_prefs,
    SHAPEKEYFOLDER_UL_keys,
    SHAPEKEYFOLDER_OT_toggle_folder,
    SHAPEKEYFOLDER_OT_set_active_key,
    SHAPEKEYFOLDER_OT_select_all,
    SHAPEKEYFOLDER_OT_add_at_end,
    SHAPEKEYFOLDER_MT_add_menu,
    SHAPEKEYFOLDER_OT_clear_all_values,
    SHAPEKEYFOLDER_OT_clear_folder_values,
    SHAPEKEYFOLDER_OT_invoke_native,
    SHAPEKEYFOLDER_OT_remove_single,
    SHAPEKEYFOLDER_OT_remove_selected,
    SHAPEKEYFOLDER_OT_move_selected_up,
    SHAPEKEYFOLDER_OT_move_selected_down,
    SHAPEKEYFOLDER_OT_rename_popup,
    SHAPEKEYFOLDER_PT_panel,
)


_search_debounce_tokens = {}


def _schedule_debounced_rebuild(obj_name, delay):
    token = _search_debounce_tokens.get(obj_name, 0) + 1
    _search_debounce_tokens[obj_name] = token

    def cb():
        if _search_debounce_tokens.get(obj_name) != token:
            return None
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            return None
        try:
            prefs = bpy.context.preferences.addons[__name__].preferences
        except KeyError:
            return None
        try:
            _rebuild_view_rows(obj, prefs)
        except Exception:
            pass
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PROPERTIES':
                    area.tag_redraw()
        return None

    bpy.app.timers.register(cb, first_interval=delay)


def _on_search_text_change(self, _context):
    _mark_stale(self)
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
    except KeyError:
        prefs = None
    if prefs and prefs.search_debounce_enabled and prefs.search_debounce_ms > 0:
        _schedule_debounced_rebuild(self.name, prefs.search_debounce_ms / 1000.0)
    else:
        _schedule_rebuild(self.name)


def _on_search_regex_change(self, _context):
    _mark_stale(self)
    _schedule_rebuild(self.name)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.shape_key_folder_states = CollectionProperty(
        type=SHAPEKEYFOLDER_PG_state,
    )
    bpy.types.Object.shape_key_view_rows = CollectionProperty(
        type=SHAPEKEYFOLDER_PG_view_row,
    )
    bpy.types.Object.shape_key_view_active_index = IntProperty(default=0)
    bpy.types.Object.shape_key_view_fingerprint = StringProperty()
    bpy.types.Object.shape_key_search = StringProperty(
        name="Search",
        description="Filter shape keys by name (case-insensitive substring or regex)",
        default="",
        update=_on_search_text_change,
        options={'TEXTEDIT_UPDATE'},
    )
    bpy.types.Object.shape_key_search_regex = BoolProperty(
        name="Regex",
        description="Treat search text as a regular expression (case-insensitive)",
        default=False,
        update=_on_search_regex_change,
    )
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)
    bpy.types.UI_MT_button_context_menu.append(_row_context_menu_draw)


def unregister():
    try:
        bpy.types.UI_MT_button_context_menu.remove(_row_context_menu_draw)
    except (AttributeError, ValueError):
        pass
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    for attr in (
        "shape_key_search_regex",
        "shape_key_search",
        "shape_key_view_fingerprint",
        "shape_key_view_active_index",
        "shape_key_view_rows",
        "shape_key_folder_states",
    ):
        if hasattr(bpy.types.Object, attr):
            delattr(bpy.types.Object, attr)
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


if __name__ == "__main__":
    register()
