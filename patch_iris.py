import os

with open("main.py", "r") as f:
    code = f.read()

old_block = """            if (in_view or cap_active or hand_active) and not force_off:
                self._dlp_off_timer = 0.0
                if not self._dlp_on:
                    self._gpio.output(27, self._gpio.HIGH)
                    self._dlp_on = True
            else:
                self._dlp_off_timer += dt
                if self._dlp_off_timer >= 1.5 and self._dlp_on and app_allows:
                    self._gpio.output(27, self._gpio.LOW)
                    self._dlp_on = False
                    reason = 'orientation' if bad_orientation else 'still' if still_sleep else 'out of view'
                    print(f'[IRIS] DLP off ({reason})')"""

new_block = """            if (in_view or cap_active or hand_active) and not force_off:
                self._dlp_off_timer = 0.0
                if not self._dlp_on:
                    self._gpio.output(27, self._gpio.HIGH)
                    self._dlp_on = True
                    import core.display as _cd
                    self.input.set_led(_cd.ACCENT[0], _cd.ACCENT[1], _cd.ACCENT[2], 0)
                    print('[IRIS] DLP waking up')
            else:
                self._dlp_off_timer += dt
                if self._dlp_off_timer >= 1.5 and self._dlp_on and app_allows:
                    self._gpio.output(27, self._gpio.LOW)
                    self._dlp_on = False
                    import core.display as _cd
                    dim_r = max(0, int(_cd.ACCENT[0] * 0.1))
                    dim_g = max(0, int(_cd.ACCENT[1] * 0.1))
                    dim_b = max(0, int(_cd.ACCENT[2] * 0.1))
                    self.input.set_led(dim_r, dim_g, dim_b, 1)
                    reason = 'orientation' if bad_orientation else 'still' if still_sleep else 'out of view'
                    print(f'[IRIS] DLP off ({reason}) - LED Dimmed')"""

if old_block in code:
    with open("main.py", "w") as f:
        f.write(code.replace(old_block, new_block))
    print("\n[+] SUCCESS: main.py has been patched with the LED sleep logic!")
else:
    print("\n[-] FAILED: Could not find the exact old block. Did the indentation change?")
