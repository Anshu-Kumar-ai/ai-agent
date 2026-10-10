# Read the current file
with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'r') as f:
    content = f.read()

# Fix the regex on line 113
# The current line has a malformed regex - fix it
content = content.replace(
    'string_literals = re.findall(r\'["\\\\\\']([^"\\\\\\']*(?:[/\\\\\\\\][^"\\\\\\']*)+)[\\"]\', arg)',
    'string_literals = re.findall(r\'["\\\\']([^"\\\\']*(?:[/\\\\\\\\][^"\\\\']*)+)[\"\\\\']\', arg)'
)

with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'w') as f:
    f.write(content)

print('Fixed!')