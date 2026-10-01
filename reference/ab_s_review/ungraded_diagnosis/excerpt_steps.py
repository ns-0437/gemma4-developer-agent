import json, glob, os, sys, collections
RAW = "reference/ab_s_run_2026-10-01/pilot"
def obs(step):
    o = step.get("observation")
    if not o: return "<none>", ""
    c = o.get("content")
    try: j = json.loads(c)
    except Exception: return "<unparsed>", str(c)[:300]
    det = j.get("details") or {}
    txt = j.get("error") or j.get("error_message") or j.get("stdout") or det.get("stdout") or det.get("stderr") or j.get("content") or ""
    return str(j.get("status")), " ".join(str(txt).split())[:260]

want = {
 "A__rich_3278": [9,10,11,12,13,62],
 "A__rich_3535": [24,25,26,27,44,45,46,47],
 "S__rich_3278": [10,11,16,47,48,49,50,51],
 "S__rich_3535": [18,19,20,21,22],
 "A__rich_3942": [23,24,25,26,63,64,65],
 "S__rich_3942": [54,55,56,57,60,61,62,63,64,65],
}
for run, steps in want.items():
    t = json.load(open(glob.glob(RAW+"/"+run+"/traces/*.json")[0], encoding="utf-8"))
    byid = {s["step_id"]: s for s in t["steps"]}
    print("="*78); print(run)
    for sid in steps:
        s = byid.get(sid)
        if not s: continue
        tcs = s.get("tool_calls") or []
        st, txt = obs(s)
        for tc in tcs:
            a = tc.get("arguments") or {}
            k = a.get("command") or a.get("filepath") or json.dumps(a)[:200]
            print(" %3d %-12s %s" % (sid, tc["function_name"], " ".join(str(k).split())[:150]))
            if "old_string" in a: print("      old_string:", " ".join(str(a["old_string"]).split())[:120])
            if "new_string" in a and tc["function_name"]!="edit_file": pass
        if not tcs:
            print(" %3d %-12s msg=%s" % (sid, "("+s.get("source","?")+")", " ".join(str(s.get("message") or "").split())[:160]))
        print("      -> %s | %s" % (st, txt))
