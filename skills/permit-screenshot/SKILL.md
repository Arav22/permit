---
name: permit-screenshot
description: Capture a screenshot of the current screen and analyze it
argument-hint: [optional: "what should I look for in this screenshot?"]
allowed-tools: [Bash, Read]
---

# permit-screenshot — Visual Context Capture

You are capturing a screenshot so the user can get visual feedback on their current screen.

## Steps

1. **Detect OS:**
   ```bash
   uname -s
   ```

2. **Capture the screenshot:**
   - macOS: `screencapture -x /tmp/permit-screenshot.png`
   - Linux: `scrot /tmp/permit-screenshot.png 2>/dev/null || import -window root /tmp/permit-screenshot.png 2>/dev/null`

3. **Read the screenshot** using the Read tool on `/tmp/permit-screenshot.png`

4. **Describe what you see:** Be specific about:
   - What app or window is visible
   - Any error messages or warnings
   - The overall state of the screen
   - Anything that looks wrong or interesting

5. **Ask:** "What would you like me to do with this screenshot?"

## Common use cases

- **UI debugging:** "Does the layout look right?"
- **Error capture:** "What does this error dialog say?"
- **Visual regression:** "Does this match the design?"
- **Documentation:** "Save this as a screenshot for the README"

## Notes

- Screenshot is saved to `/tmp/permit-screenshot.png` (overwritten each time)
- macOS: `screencapture -x` captures silently without sound
- If screen capture fails (no display, permission denied), say so clearly
- The image may show sensitive content — do not describe passwords or keys if visible
