import sys
sys.path.insert(0, r'c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend')

file_path = r'c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\market_service.py'

# Read
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Check and add sanitize function if missing
if 'def sanitize' not in content:
    old = '        if sample_jobs:'
    new = '''        # Helper para remover emojis e caracteres surrogates
        def sanitize(text: str) -> str:
            return text.encode('utf-8', 'ignore').decode('utf-8')

        if sample_jobs:'''
    content = content.replace(old, new, 1)
    print("Added sanitize function")

# Update INSERT to use sanitize
if 'sanitize(j["title"])' not in content:
    old_insert = '''                cursor.execute(\'\'\'
                    INSERT INTO market_raw_jobs (id, title, company, description, location, modality, source, source_url, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                \'\'\', (job_id, j["title"], j["company"], j["description"], j["location"], j["modality"], j["source"], source_url, pub_date.isoformat()))'''
    
    new_insert = '''                cursor.execute(\'\'\'
                    INSERT INTO market_raw_jobs (id, title, company, description, location, modality, source, source_url, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                \'\'\', (job_id, sanitize(j["title"]), sanitize(j["company"]), sanitize(j["description"]), sanitize(j["location"]), sanitize(j["modality"]), sanitize(j["source"]), source_url, pub_date.isoformat()))'''
    
    content = content.replace(old_insert, new_insert)
    print("Updated INSERT statement")
else:
    print("sanitize already in INSERT")

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("DONE")
