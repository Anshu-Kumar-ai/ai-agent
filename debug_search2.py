import urllib.request
import urllib.parse

query = 'python asyncio tutorial'
search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

req = urllib.request.Request(
    search_url,
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
)

try:
    with urllib.request.urlopen(req, timeout=15) as response:
        html = response.read().decode('utf-8', errors='replace')
except Exception as e:
    print(f"Error: {e}")
    exit(1)

# Save HTML for inspection
with open('duckduckgo_debug.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"HTML length: {len(html)}")
print("\nFirst 5000 chars:")
print(html[:5000])