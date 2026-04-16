from pathlib import Path

path = Path(r"C:\Users\pz9079\NTX Setup Manager\Setup Manager\ui\work_editor_support\tools_tab_builder.py")
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
for i in range(430, 438):
    print(i + 1, repr(lines[i]))
