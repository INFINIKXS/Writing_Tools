import os
import sys
import sqlite3

# Import from current dir
import search_store

def test():
    search_store.init_db()
    # Insert a dummy document with 3 pages
    text1 = "This quasi-experimental prospective study conducted pre- and post-test assessments. The final study sample of 60 participants, including 30 participants each in the MBI and control groups. "
    text2 = "The intervention group received eight 2.5-h MBI sessions over 2 months. All sessions were live-streamed on Zoom in the evenings due to the COVID-19 pandemic limitations. Willing participants joined the WhatsApp group. "
    text3 = "Nurses who directly cared for patients with COVID-19 were recruited using convenient sampling. Maslach Burnout Inventory-Human Services Survey for Medical Personnel MBI-HSS (MP). "
    
    # Simulate PDF extraction introducing a typo and spanning pages 
    extracted_text2 = "The intervention group received eight 2.5-h MBI sessions over 2 months. All sessions were live-streamed onZoom in the evenings due to the COVID-19 pandemic limitations. Willing participants joined the WhatsApp group. "
    
    doc_id = search_store.index_document("test.pdf", [text1, extracted_text2, text3])

    # User's copy-pasted query (perfect text from somewhere, maybe crossing pages)
    query = text1 + text2 + text3
    print(f"Query length: {len(query)}")
    
    res = search_store.search(query)
    print(f"Results for full exact query: {len(res)}")
    
    # Try a strategy 3 implementation: 
    # breaking the long query into chunks and searching those
    query_clean = search_store._normalize(query)
    if not res and len(query_clean) > 80:
        words = query_clean.split()
        chunk_len = 15
        chunks = []
        for i in range(0, len(words), chunk_len//2):
            chunk = " ".join(words[i:i+chunk_len])
            if len(chunk) > 30:
                chunks.append(chunk)
                
        # search for each chunk using substring
        conn = search_store._get_conn()
        content_rows = conn.execute("SELECT p.doc_id, p.page_num, p.content, d.filename FROM pages_fts p JOIN documents d ON p.doc_id = d.doc_id WHERE p.doc_id=?", (doc_id,)).fetchall()
        
        fallback_results = []
        matched_pages = set()
        for row in content_rows:
            content_normalized = search_store._normalize(row["content"]).lower()
            for chunk in chunks:
                if chunk.lower() in content_normalized and row["page_num"] not in matched_pages:
                    snippet = search_store._extract_context(row["content"], chunk)
                    fallback_results.append({
                        "doc_id": row["doc_id"],
                        "page_num": row["page_num"],
                        "match_type": "chunk_fallback",
                        "snippet": snippet["text"]
                    })
                    matched_pages.add(row["page_num"])
                    break
        print(f"Fallback results: {len(fallback_results)}")
        for r in fallback_results:
            print(f"  Page {r['page_num']}: {r['snippet']}")
    
    search_store.delete_document(doc_id)

if __name__ == "__main__":
    test()
