import requests, urllib.parse

title = 'Obesity and risk of female reproductive conditions: A Mendelian randomisation study'
url = f'https://api.crossref.org/works?query.bibliographic="{urllib.parse.quote(title)}"&rows=3'
r = requests.get(url, headers={'User-Agent': 'Test'})
data = r.json()
items = data.get('message', {}).get('items', [])
for i in items:
    print(i.get('DOI'), "|", i.get('title', [''])[0])

pub_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={urllib.parse.quote(title)}[Title]&retmode=json"
pr = requests.get(pub_url).json()
pmids = pr.get("esearchresult", {}).get("idlist", [])
print("PubMed PMIDS:", pmids)
