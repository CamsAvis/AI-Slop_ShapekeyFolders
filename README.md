# Shapekeys \*\*

Blender 5.1+ addon that adds a folder-tree view of shape keys above the native *Shape Keys* panel in Properties > Object Data.

## Features

- Folder grouping by slash-prefixed names (`Expressions/Smile` → `Expressions/` folder)
- Dedicated `VRC` folder for `vrc.*` keys
- Dedicated `Face Tracking` folder for VRCFT Unified Blendshape and SRanipal names
- `Ungrouped` folder pinned to the bottom for keys without a separator
- Scrollable, resizable `template_list` with multi-select via checkbox and modifier-aware clicks (shift = range, ctrl = toggle)
- Right-side toolbar: add (with `Create New` / `Create from Visible` submenu), remove, move within folder, select/deselect all, reset all values to 0
- Double-click name → rename popup (full `kb.name`, can move keys between folders)
- Right-click row → context menu: Rename, Delete, Make Basis, Apply to Basis, Duplicate
- Folder rows show `(*)` next to the name when any contained key has a non-zero value, plus a far-right `X` button that recursively zeros every key in that folder
- Search bar with case-insensitive substring or regex matching; matching folders auto-expand
- Search debounce (toggleable, default 200 ms) configurable in addon preferences

## Install

1. Download `shape_key_folders.py`
2. Blender → Edit → Preferences → Add-ons → Install... → pick the file
3. Enable "Shapekeys \*\*"
