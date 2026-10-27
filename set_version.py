import re, sys
new_ver = sys.argv[1] if len(sys.argv) > 1 else "1.6.4"
path = r"d:\Projetos\limpaPC\app.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
updated = re.sub(r'(APP_VERSION\s*=\s*)"[\d.]+"', f'\\g<1>"{new_ver}"', content)
with open(path, "w", encoding="utf-8") as f:
    f.write(updated)
m = re.search(r'APP_VERSION\s*=\s*"([\d.]+)"', updated)
print("APP_VERSION:", m.group(1) if m else "nao encontrado")
