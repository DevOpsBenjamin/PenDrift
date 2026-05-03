import sys
from pathlib import Path

file_path = Path(r"i:\PenDrift\server-python\app\routers\templates.py")
content = file_path.read_text(encoding="utf-8")

old_line = '    preset_id = body.get("settingsPresetId") or find_default_preset_id()'
new_logic = '    preset_arg = body.get("settingsPresetId")\n    preset_id = preset_arg if (preset_arg and preset_arg != "default") else find_default_preset_id()'

new_content = content.replace(old_line, new_logic)

if new_content != content:
    file_path.write_text(new_content, encoding="utf-8")
    print("Successfully updated templates.py")
else:
    print("Could not find the target line in templates.py")
