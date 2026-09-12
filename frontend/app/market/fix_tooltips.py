import os
import shutil

src = r'c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\frontend\app\market\page.tsx'
tmp = r'C:\Users\xxxsa\AppData\Local\Temp\temp_page.tsx'
dst = r'C:\Users\xxxsa\AppData\Local\Temp\temp_page2.tsx'

# Copy to temp
shutil.copy2(src, tmp)

# Read, modify, write to another temp
with open(tmp, 'r', encoding='utf-8') as f:
    content = f.read()

# Add title attribute to tech name spans
old1 = '<span className="text-xs font-semibold text-slate-200 w-32 truncate">{tech.name}</span>'
new1 = '<span className="text-xs font-semibold text-slate-200 w-32 truncate" title={tech.name}>{tech.name}</span>'
content = content.replace(old1, new1)

# Add title attribute to modality name spans
old2 = '<span className="text-xs font-semibold text-slate-300 w-28 truncate">{mod.name}</span>'
new2 = '<span className="text-xs font-semibold text-slate-300 w-28 truncate" title={mod.name}>{mod.name}</span>'
content = content.replace(old2, new2)

with open(dst, 'w', encoding='utf-8') as f:
    f.write(content)

# Copy back
shutil.copy2(dst, src)
print('Done')
