import sys
sys.stdout.reconfigure(encoding='utf-8')

from rag import supabase

# Print ALL chunks from provisional results PDF in full
res = supabase.table('documents').select('id, content, metadata').execute()

prov_chunks = [r for r in res.data if 'provisional' in (r['metadata'] or {}).get('source', '').lower()]
print(f"Total provisional PDF chunks: {len(prov_chunks)}\n")

for i, row in enumerate(prov_chunks):
    content = (row['content'] or '').encode('ascii', errors='replace').decode('ascii')
    print(f"=== Chunk {i+1} (id={row['id']}) ===")
    print(content[:600])
    print()
