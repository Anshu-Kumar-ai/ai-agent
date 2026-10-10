with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'r') as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines):
    if 'string_literals = re.findall' in line:
        print('Found on line', i+1)
        # Use double-quoted raw string to avoid escaping issues
        # r"[\"']" in a raw double-quoted string: \" escapes the double quote, ' is literal
        lines[i] = '            string_literals = re.findall(r"[\\"\\\']([^\\"\\\']*(?:[/\\\\\\\\][^\\"\\\']*)+)[\\"\\\']", arg)'
        print('Fixed to:', lines[i])

content = '\n'.join(lines)

with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'w') as f:
    f.write(content)

print('Done!')