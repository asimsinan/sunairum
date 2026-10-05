import re, json, os
P="/app/storage/46ba2118-50d3-49d7-b254-846a6222a9ed/proj_at3gp"
html=open(P+"/validation/candidates/slide_07/01_creative_normalized_f3e95c00c5.html",encoding="utf-8").read()
sp=P+"/scene/slide_07.json"
scene=json.load(open(sp,encoding="utf-8")) if os.path.exists(sp) else {}
print("scene version=", scene.get("version"))

def probe(tag,h):
    m=re.search(r".{20}<code>k</code>.{6}",h)
    ctx = repr(m.group(0)) if m else "NO MATCH"
    state = "PRESENT" if " <code>k</code> " in h else "LOST"
    print("%-46s %-8s %s" % (tag, state, ctx))

probe("00 input (candidate 01)",html)
from tasks.html_constitution import ensure_slide_root
from tasks.html_pipeline import (sanitize_html_audience_copy, normalize_inline_text_boundaries,
    normalize_figure_hosts, sanitize_html_presentation_chrome)
from tasks.scene_html_author import normalize_scene_authored_html
from tasks.scene_local_repair import repair_scene_html_until_stable

h=ensure_slide_root(html); probe("01 ensure_slide_root",h)
h,_=sanitize_html_audience_copy(h); probe("02 sanitize_html_audience_copy",h)
h,_=normalize_inline_text_boundaries(h); probe("03 normalize_inline_text_boundaries",h)
h,_=normalize_scene_authored_html(h,scene); probe("04 normalize_scene_authored_html",h)
h,_=normalize_figure_hosts(h); probe("05 normalize_figure_hosts",h)
h=sanitize_html_presentation_chrome(h, slide_number=7, total_slides=14); probe("06 sanitize_chrome",h)
h3,rep,loc=repair_scene_html_until_stable(h,scene)
probe("07 repair_scene_html_until_stable",h3)
open("/app/ws_out.html","w",encoding="utf-8").write(h3)
