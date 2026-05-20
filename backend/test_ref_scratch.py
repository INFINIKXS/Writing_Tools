from references.ref_list_verifier import verify_single_reference, parse_raw_reference_fast
import json

ref1 = "https://doi.org/10.1136/bmjph-2023-000097"
ref2 = "Brewer, M., Dang, T., & Tominey, E. (2024). Universal Credit: Welfare reform and mental health. Journal of health economics, 98, 102940. https://doi.org/10.1016/j.jhealeco.2024.102940"

print("Parsing #1:")
parsed1 = parse_raw_reference_fast(ref1)
print(json.dumps(parsed1, indent=2))

print("Verifying #1:")
res1 = verify_single_reference(ref1, "apa")
print(json.dumps(res1, indent=2))

print("\nParsing #2:")
parsed2 = parse_raw_reference_fast(ref2)
print(json.dumps(parsed2, indent=2))

print("Verifying #2:")
res2 = verify_single_reference(ref2, "apa")
print(json.dumps(res2, indent=2))
