with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'r') as f:
    content = f.read()

# Fix the regex on line 113 - it needs to also match drive-relative paths like C:foo.txt
# Current regex requires a path separator, but C:foo.txt doesn't have one
# Change from: ([^\"']*(?:[/\\][^\"']*)+)  - requires at least one separator
# To: ([^\"']*(?:[/\\][^\"']*)*) - allows zero or more separators

content = content.replace(
    'string_literals = re.findall(r"[\\\"\\']([^\\\"\\']*(?:[/\\\\\\\\][^\\\"\\']*)+)[\\\"\\']", arg)',
    'string_literals = re.findall(r"[\\\"\\']([^\\\"\\']*(?:[/\\\\\\\\][^\\\"\\']*)*)[\\\"\\']", arg)'
)

with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'w') as f:
    f.write(content)

print('Fixed!')