#!/usr/bin/env python3
"""
Generate docs/demo.html — a styled HTML representation of the permit demo.

Run:   python3 generate_screenshot.py
Opens: docs/demo.html in your browser (screenshot it for README)
"""

import subprocess
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


_ANSI_TO_CSS = {
    "1":  "font-weight:bold",
    "2":  "opacity:0.55",
    "31": "color:#ff5f5f",
    "32": "color:#5fff87",
    "33": "color:#ffd75f",
    "36": "color:#5fd7ff",
    "0":  None,          # reset — handled via span close
}


def _ansi_to_html(text: str) -> str:
    """Convert ANSI escape codes to HTML <span> tags."""
    out = []
    depth = 0  # open span count

    i = 0
    while i < len(text):
        if text[i] == "\033" and i + 1 < len(text) and text[i + 1] == "[":
            end = text.find("m", i + 2)
            if end == -1:
                i += 1
                continue
            codes = text[i + 2:end].split(";")
            i = end + 1

            if codes == ["0"] or codes == [""]:
                # reset
                out.append("</span>" * depth)
                depth = 0
            else:
                styles = []
                for code in codes:
                    css = _ANSI_TO_CSS.get(code)
                    if css:
                        styles.append(css)
                if styles:
                    out.append(f'<span style="{";".join(styles)}">')
                    depth += 1
        else:
            ch = text[i]
            if ch == "&":
                out.append("&amp;")
            elif ch == "<":
                out.append("&lt;")
            elif ch == ">":
                out.append("&gt;")
            else:
                out.append(ch)
            i += 1

    out.append("</span>" * depth)
    return "".join(out)


def capture_demo() -> str:
    """Run demo.py and capture its output."""
    result = subprocess.run(
        [sys.executable, "demo.py"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    return result.stdout


def build_html(raw_output: str) -> str:
    lines = raw_output.split("\n")
    body_lines = []
    for line in lines:
        body_lines.append(_ansi_to_html(line))
    body = "\n".join(body_lines)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>permit — demo</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #1e1e2e;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 32px 24px;
    min-height: 100vh;
  }}
  .window {{
    background: #181825;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 24px 80px rgba(0,0,0,0.6);
    width: 760px;
    font-family: "SF Mono", "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
  }}
  .titlebar {{
    background: #313244;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  .dot-red  {{ background: #ff5f57; }}
  .dot-yel  {{ background: #febc2e; }}
  .dot-grn  {{ background: #28c840; }}
  .title {{
    flex: 1;
    text-align: center;
    color: #6c7086;
    font-size: 12px;
    font-family: -apple-system, sans-serif;
  }}
  pre {{
    color: #cdd6f4;
    font-size: 13px;
    line-height: 1.55;
    padding: 20px 24px 28px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }}
</style>
</head>
<body>
<div class="window">
  <div class="titlebar">
    <div class="dot dot-red"></div>
    <div class="dot dot-yel"></div>
    <div class="dot dot-grn"></div>
    <div class="title">permit — demo</div>
  </div>
  <pre>{body}</pre>
</div>
</body>
</html>"""


def main():
    print("Running demo.py...")
    raw = capture_demo()

    print("Building HTML...")
    html = build_html(raw)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "demo.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)

    print(f"Saved to: {out_path}")
    print("Opening in browser — screenshot it and save as docs/demo.png for the README.")

    import subprocess
    subprocess.run(["open", out_path], check=False)


if __name__ == "__main__":
    main()
