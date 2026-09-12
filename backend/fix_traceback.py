import codecs

file_path = r"main.py"

with codecs.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

if 'import traceback' not in content:
    # Add after 'import tempfile'
    old = 'import tempfile'
    new = 'import tempfile\nimport traceback'
    content = content.replace(old, new, 1)
    with codecs.open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Added traceback import")
else:
    print("traceback already imported")
