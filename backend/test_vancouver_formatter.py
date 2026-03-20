import json
from main import format_reference

def run_tests():
    # 1. Standard (Now checks the 6-author limit rule + ET AL)
    m1 = {
        "type": "Journal Article",
        "authors": ["Petitti, D.B.", "Crooks, V.C.", "Buckwalter, J.G.", "Chui, V.", "Jones, A.", "Smith, B.", "Long, C."],
        "title": "Blood Pressure Levels: A Mendelian Randomisation study",
        "source": "Archives of Neurology",
        "source_abbreviated": "Arch Neurol",
        "year": "2005",
        "day_month": "Jan",
        "volume": "62",
        "issue": "1",
        "pages": "112-116",
    }
    r1 = format_reference(m1, "vancouver")
    assert r1["formatted"] == "Petitti DB, Crooks VC, Buckwalter JG, Chui V, Jones A, Smith B, et al. Blood pressure levels: a mendelian randomisation study. Arch Neurol. 2005 Jan;62(1):112-6.", f"Fail 1: {r1['formatted']}"

    # 2. Journal Article with Notes and Acronyms in Title
    m2 = {
        "type": "Journal Article",
        "authors": ["Walsh, B."],
        "title": "the importance of Leptin to reproduction with mRNA and DNA", # should be sentence cased properly
        "source": "BMJ",
        "year": "2005",
        "day_month": "Mar 26",
        "volume": "330",
        "issue": "7493",
        "pages": "699",
        "epub_date": "2005 Mar 9",
        "doi": "10.1542/peds.2004-1441",
    }
    r2 = format_reference(m2, "vancouver")
    assert r2["formatted"] == "Walsh B. The importance of Leptin to reproduction with mRNA and DNA. BMJ. 2005 Mar 26;330(7493):699. Epub 2005 Mar 9. doi:10.1542/peds.2004-1441.", f"Fail 2: {r2['formatted']}"

    # 3. Non-English
    m3 = {
        "type": "Journal Article",
        "authors": ["Berrino, F."],
        "title": "Case-control evaluation of screening efficacy",
        "source": "Epidemiol Prev",
        "year": "2004",
        "day_month": "Nov-Dec",
        "volume": "28",
        "issue": "6",
        "pages": "354-9",
        "language": "Italian",
    }
    r3 = format_reference(m3, "vancouver")
    assert r3["formatted"] == "Berrino F. [Case-control evaluation of screening efficacy]. Epidemiol Prev. 2004 Nov-Dec;28(6):354-9. Italian.", f"Fail 3: {r3['formatted']}"

    # 4. No Volume or Issue
    m4 = {
        "type": "Journal Article",
        "authors": ["Schwartz-Cassell, T."],
        "title": "Feeding assistants",
        "source": "Contemp Longterm Care",
        "year": "2005",
        "day_month": "Jan",
        "pages": "26-8",
    }
    r4 = format_reference(m4, "vancouver")
    assert r4["formatted"] == "Schwartz-Cassell T. Feeding assistants. Contemp Longterm Care. 2005 Jan:26-8.", f"Fail 4: {r4['formatted']}"

    # 5. Organization as Author
    m5 = {
        "type": "Journal Article",
        "authors": ["American Diabetes Association"],
        "title": "Diabetes update",
        "source": "Nursing",
        "year": "2003",
        "day_month": "Nov",
        "issue": "Suppl",
        "pages": "19-20",
    }
    r5 = format_reference(m5, "vancouver")
    assert r5["formatted"] == "American Diabetes Association. Diabetes update. Nursing. 2003 Nov;Suppl:19-20.", f"Fail 5: {r5['formatted']}"
    # Wait, the prompt says Vol(Issue). If there's no volume, is issue just `;(Suppl)` or `(Suppl)`?
    # Our code emits `;(Suppl)` which actually matches the chain builder if van_loc_parts includes "(Suppl)" ?
    # Let's check how main.py handles volume missing but issue present.
    
    print("All tests passed!")

if __name__ == "__main__":
    run_tests()
