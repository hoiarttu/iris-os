with open("main.py", "r") as f:
    code = f.read()

broken_line = "reason = 'orientation' if bad_orientation else 'still' python3 patch_iris.pyED: Could not find the exact old block. Did the indent"
fixed_lines = """reason = 'orientation' if bad_orientation else 'still' if still_sleep else 'out of view'
                    print(f'[IRIS] DLP off ({reason}) - LED Dimmed')"""

if broken_line in code:
    with open("main.py", "w") as f:
        f.write(code.replace(broken_line, fixed_lines))
    print("\n[+] SUCCESS: The mangled line has been fixed!")
else:
    print("\n[-] FAILED: Couldn't find the broken line. You might need to open 'nano main.py' and fix it manually.")
