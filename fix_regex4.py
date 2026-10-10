with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'r') as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines):
    if 'string_literals = re.findall' in line:
        print('Found on line', i+1)
        # The issue: in a raw string r'["\']', the backslash is literal
        # We need r'["\']' which means the character class contains " and '
        # But in a raw string, \" is not an escape - it's literal backslash+quote
        # The correct pattern is r'["\']' but we need to write it properly in Python source
        # Using single quotes around the raw string: r'["\']' 
        # This means: character class containing " and '
        lines[i] = "            string_literals = re.findall(r'[\"']([^\"']*(?:[/\\\\][^\"']*)+)[\"']', arg)"
        print('Fixed to:', lines[i])

content = '\n'.join(lines)

with open('C:/Users/anshu/Agent/AI-Agent/app/tools/terminal_tools.py', 'w') as f:
    f.write(content)

print('Done!')