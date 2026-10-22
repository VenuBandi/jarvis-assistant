"""Render the Jarvis overlay of a staged page (opened via #jarvis) at iPhone size, light + dark, with live data.

Usage : python3 tracker/render_jarvis.py tracker/index_stage_jarvis.html [width] [height]
Output: artifacts/logs/render/<page>_jarvis_<theme>.png + printed probe (JS errors, overlay visible, no h-scroll)
"""
import json
import re
import sys
import tempfile
from pathlib import Path

import render_check as rc

PROBE = """<script>
window.addEventListener("load", () => setTimeout(() => {
  const j = document.getElementById("jv"), d = document.createElement("pre"); d.id = "__jprobe";
  d.textContent = JSON.stringify({errs: window.__errs || [], open: !!j && !j.hidden, state: j && j.dataset.st,
    chips: document.querySelectorAll("#jvChips button").length, log: (document.getElementById("jvLog")||{}).childElementCount,
    scroll_w: j ? j.scrollWidth : -1, inner_w: j ? j.clientWidth : 0});  /* the overlay itself (render_check's own probe <pre> widens the document) */
  document.body.appendChild(d);
}, 900));
</script>"""


def main():
    page = sys.argv[1]
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 390
    hgt = int(sys.argv[3]) if len(sys.argv) > 3 else 844
    rc.OUT.mkdir(parents=True, exist_ok=True)
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for theme in ("light", "dark"):
            f = Path(tmp) / f"j_{theme}.html"
            f.write_text(rc.page_with_data(page, theme).replace("</body>", PROBE + "</body>", 1))
            url = f.as_uri() + "#jarvis"
            dom = rc.chrome([f"--window-size={max(w, 500)},{hgt}", "--dump-dom", url]).stdout
            m = re.search(r'<pre id="__jprobe">(.*?)</pre>', dom, re.S)
            p = json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")) if m else None
            png = rc.OUT / f"{Path(page).stem}_jarvis_{theme}.png"
            frame = Path(tmp) / f"frame_{theme}.html"
            frame.write_text(f'<!doctype html><body style="margin:0;background:#888"><iframe src="{url}" '
                             f'style="width:{w}px;height:{hgt}px;border:0;display:block"></iframe></body>')
            rc.chrome([f"--window-size={w + 110},{hgt}", "--force-device-scale-factor=2", f"--screenshot={png}",
                       "--allow-file-access-from-files", frame.as_uri()])
            good = bool(p) and not p["errs"] and p["open"] and p["chips"] == 4 and p["scroll_w"] <= p["inner_w"]
            ok &= good
            print(f"{'ok ' if good else 'BAD'} jarvis {theme:5s} {p} png={png.relative_to(rc.server.ROOT) if png.exists() else 'none'}")
    print("OK" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
