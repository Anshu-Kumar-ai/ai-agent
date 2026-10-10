# Read the current file
with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'r') as f:
    content = f.read()

# Fix the regex on line 113
# The issue is with the character class ["\'] - we need to escape properly
# Let's use a different approach - write the whole line with proper escaping

# Find and replace the exact line
old_line = '            string_literals = re.findall(r\'["\\\\\\']([^"\\\\\\']*(?:[/\\\\\\\\][^"\\\\\\']*)+)[\"\\\\\']\', arg)'
new_line = '            string_literals = re.findall(r"[\\"\\\']([^\\"\\\']*(?:[/\\\\][^\\"\\\']*)+)[\\"\\\']", arg)'

# Actually, let's just use the regex without the problematic character class
# The pattern ["\'] matches either " or '
# We can write it as: r'["\']([^"\']*(?:[/\\][^"\']*)+)[\"\']'
# In Python source: r'["\']([^"\']*(?:[/\\][^"\']*)+)[\"\']'

# But the escaping in the file is different. Let's just write a simple correct version.
# The key insight: in a raw string, we can use single quotes around the regex
# and use ["\'] to match either quote

content = content.replace(
    'string_literals = re.findall(r\'["\\\\\\']([^"\\\\\\']*(?:[/\\\\\\\\][^"\\\\\\']*)+)[\"\\\\\']\', arg)',
    'string_literals = re.findall(r\'["\']([^"\']*(?:[/\\\\][^"\']*)+)[\"\']\', arg)'
)

with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'w') as f:
    f.write(content)

print('Fixed!')