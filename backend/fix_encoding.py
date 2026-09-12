import codecs
import sys
sys.path.insert(0, r'c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend')

file_path = r'c:\Users\xxxsa\OneDrive\Área de Trabalho\python\curriculo\backend\market_service.py'

# Read the file
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Check if sanitize function exists
if 'def sanitize' not in content:
    # Add sanitize function before the if sample_jobs block
    old_text = "        if sample_jobs:"
    new_text = """        # Helper para remover emojis e caracteres surrogates
        def sanitize(text: str) -> str:
            return text.encode('utf-8', 'ignore').decode('utf-8')

        if sample_jobs:"""
    content = content.replace(old_text, new_text, 1)
    print("Added sanitize function")
else:
    print("sanitize function already exists")

# Check if sanitize is used in the INSERT statement
if 'sanitize(j["title"])' not in content:
    # Add sanitize to all field accesses
    old_insert = '''                cursor.execute(\'\'\'
                    INSERT INTO market_raw_jobs (id, title, company, description, location, modality, source, source_url, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                \'\'\', (job_id, j["title"], j["company"], j["description"], j["location"], j["modality"], j["source"], source_url, pub_date.isoformat()))'''

    new_insert = '''                cursor.execute(\'\'\'
                    INSERT INTO market_raw_jobs (id, title, company, description, location, modality, source, source_url, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                \'\'\', (job_id, sanitize(j["title"]), sanitize(j["company"]), sanitize(j["description"]), sanitize(j["location"]), sanitize(j["modality"]), sanitize(j["source"]), source_url, pub_date.isoformat()))'''

    if old_insert in content:
        content = content.replace(old_insert, new_insert)
        print("Updated INSERT statement")
    else:
        print("Could not find INSERT statement to update")
else:
    print("sanitize already used in INSERT")

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
