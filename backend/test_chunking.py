import search_store

user_text = "This quasi-experimental prospective study conducted pre- and post-test assessments. The final study sample of 60 participants, including 30 participants each in the MBI and control groups."

query_clean = search_store._normalize(user_text)

conn = search_store._get_conn()
# we will just test the snippet deduplication logic
chunks = [
    "quasi-experimental prospective study",
    "prospective study conducted pre-",
    "final study sample of 60",
    "sample of 60 participants, including"
]

print("Done")
