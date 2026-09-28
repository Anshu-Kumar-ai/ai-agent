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
    f.write(html[:50000])

print(f"HTML length: {len(html)}")

# Try to find patterns
import re

# Try various patterns
patterns = [
    r'class="result__snippet">([^<]+)</a>',
    r'class="result__snippet">([^<]+)</span>',
    r'data-result="snippet">([^<]+)</a>',
    r'data-result="snippet">([^<]+)</span>',
    r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>([^<]+)</a>',
    r'class="result__url">([^<]+)</a>',
    r'class="result__url">([^<]+)</span>',
    r'data-result="url">([^<]+)</a>',
    r'data-result="url">([^<]+)</span>',
    r'<a[^>]*class="[^"]*result[^"]*"[^>]*>([^<]{20,})</a>',
]

for pattern in [r'class="result__snippet">([^<]+)</a>', r'class="result__snippet">([^<]+)</span>']:
    matches = re.findall(pattern, html)
    print(f"Pattern: {pattern}")
    print(f"  Matches: {len(matches)}")
    if matches:
        for m in matches[:3]:
            print(f"  {m[:100]}")
    print()

for pattern in [r'class="result__url">([^<]+)</a>', r'class="result__url">([^<]+)</span>']:
    matches = re.findall(pattern, html)
    print(f"Pattern: {pattern}")
    print(f"  Matches: {len(matches)}")
    if matches:
        for m in matches[:3]:
            print(f"  {m[:100]}")
    print()

# Also look for any result-like structures
print("\nLooking for 'result' in HTML:")
for line in html.split('\n'):
    if 'result' in line.lower() and ('snippet' in line.lower() or 'url' in line.lower()):
        print(line[:200])
        break