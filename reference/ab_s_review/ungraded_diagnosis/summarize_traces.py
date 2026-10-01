import json, glob, os, re, collections, hashlib, sys

RAW = "reference/ab_s_run_2026-10-01/pilot"
LOCALIZE = {"read_file", "code_analyzer"}
EDIT_TOOLS = {"edit_file", "write_file", "apply_patch", "str_replace"}
# run_command shell forms that modify the repo
MOD_CMD = re.compile(r"(^|[|;&]\s*)(sed\s+-i|patch\s|git\s+apply|tee\s|cp\s|mv\s|>\s*\S|>>\s*\S|python3?\s+-c\s*.{0,80}(open\(|write))", re.S)
LOCALIZE_CMD = re.compile(r"\b(git\s+grep|grep|find|ls|cat|sed\s+-n|head|tail|awk)\b")

def sig(tc):
    a = tc.get("arguments") or {}
    try:
        blob = json.dumps(a, sort_keys=True)
    except Exception:
        blob = repr(a)
    return tc["function_name"] + "|" + hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:10]

def short(c, n=110):
    a = c.get("args") if "args" in c else (c.get("arguments") or {})
    if "command" in a:
        s = str(a["command"])
    elif "filepath" in a:
        s = str(a["filepath"])
    else:
        s = json.dumps(a)[:400]
    s = " ".join(s.split())
    return s[:n]

def obs_of(step):
    o = step.get("observation")
    if o is None:
        return None, None, ""
    c = o.get("content")
    if isinstance(c, str):
        try:
            j = json.loads(c)
        except Exception:
            return "<unparsed>", None, c[:400]
        st = j.get("status")
        err = j.get("error") or j.get("error_message")
        det = j.get("details") or {}
        body = j.get("stdout") or j.get("stderr") or det.get("stderr") or det.get("stdout") or ""
        if st == "error" and not err:
            err = "exit_code=%s, empty stdout+stderr" % det.get("exit_code")
        if err and st is None:
            st = "rejected"
        return st, err, (err if err else str(body))[:600]
    return "<nonstr>", None, str(c)[:400]

def err_category(err, body):
    t = (err or "") + " " + (body or "")
    if "mandatory input parameters are not present" in t:
        return "malformed-args (missing mandatory param)"
    if "not found" in t.lower() and "old_string" in t:
        return "edit_file old_string not found"
    if "unexpected EOF" in t or "syntax error: unexpected end of file" in t:
        return "shell: unterminated quote / EOF"
    if "unrecognized argument" in t or "fatal:" in t:
        return "git: bad arguments"
    if "empty stdout+stderr" in t:
        return "nonzero exit, no output"
    if "Traceback" in t:
        return "python traceback in run_command"
    if "command not found" in t:
        return "shell: command not found"
    if "No such file" in t:
        return "shell: no such file"
    if "timed out" in t.lower() or "timeout" in t.lower():
        return "timeout"
    return (t.strip().split("\n")[0][:70] or "unknown")

rows = []
for d in sorted(glob.glob(RAW + "/[AS]__*")):
    run = os.path.basename(d)
    t = json.load(open(glob.glob(d + "/traces/*.json")[0], encoding="utf-8"))
    summ = json.load(open(d + "/summary.json", encoding="utf-8"))
    calls = []  # (step_id, tool, args, sig, status, err, body)
    for s in t["steps"]:
        for tc in (s.get("tool_calls") or []):
            st, err, body = obs_of(s)
            calls.append(dict(step=s["step_id"], tool=tc["function_name"],
                              args=tc.get("arguments") or {}, sig=sig(tc),
                              status=st, err=err, body=body, tc=tc))

    first_loc = next((c for c in calls if c["tool"] in LOCALIZE or
                      (c["tool"] == "run_command" and LOCALIZE_CMD.search(str(c["args"].get("command", ""))))), None)
    def is_edit(c):
        if c["tool"] in EDIT_TOOLS: return True
        if c["tool"] == "run_command" and MOD_CMD.search(str(c["args"].get("command", ""))): return True
        return False
    edits = [c for c in calls if is_edit(c)]
    first_edit = edits[0] if edits else None
    accepted_edits = [c for c in edits if c["status"] in ("ok",) or (c["status"] is None and not c["err"])]
    rejected_edits = [c for c in edits if c["err"] or c["status"] == "error"]

    # repeat runs of identical signature
    runs_adj = []
    i = 0
    while i < len(calls):
        j = i
        while j + 1 < len(calls) and calls[j + 1]["sig"] == calls[i]["sig"]:
            j += 1
        if j > i:
            # did the observation change within the block?
            bodies = {calls[k]["body"] for k in range(i, j + 1)}
            runs_adj.append((calls[i], j - i + 1, len(bodies)))
        i = j + 1
    runs_adj.sort(key=lambda x: -x[1])

    errs = collections.Counter(err_category(c["err"], c["body"]) for c in calls if c["err"] or c["status"] == "error")
    last_ok = None
    for c in calls:
        if c["status"] == "ok":
            last_ok = c
    patch_dir = d + "/patches"
    patches = glob.glob(patch_dir + "/*.patch") if os.path.isdir(patch_dir) else []
    psize = [(os.path.basename(p), os.path.getsize(p)) for p in patches]

    print("=" * 78)
    print(run, "| outcome:", summ.get("outcome") or summ.get("status"), "| calls:", len(calls))
    print("  first localization : step %s  %s  %s" % (first_loc["step"], first_loc["tool"], short(first_loc)) if first_loc else "  first localization : NONE")
    if first_edit:
        print("  first edit attempt : step %s  %s  %s  -> status=%s %s" % (
            first_edit["step"], first_edit["tool"], short(first_edit), first_edit["status"],
            ("ERR:" + err_category(first_edit["err"], first_edit["body"])) if (first_edit["err"] or first_edit["status"] == "error") else ""))
    else:
        print("  first edit attempt : NONE")
    print("  edits: attempted=%d accepted=%d rejected=%d" % (len(edits), len(accepted_edits), len(rejected_edits)))
    print("  error categories   :", dict(errs))
    print("  top adjacent repeat blocks (sig, len, distinct observation bodies):")
    for c, n, nb in runs_adj[:3]:
        print("     step %-3s x%-3d distinct_obs=%d  %s  %s" % (c["step"], n, nb, c["tool"], short(c, 80)))
    # non-adjacent duplicate signatures
    cnt = collections.Counter(c["sig"] for c in calls)
    adjtot = sum(n - 1 for _, n, _ in runs_adj)
    duptot = sum(v - 1 for v in cnt.values() if v > 1)
    print("  duplicate calls: total_dup=%d adjacent_dup=%d separated_dup=%d distinct_sigs=%d" % (duptot, adjtot, duptot - adjtot, len(cnt)))
    print("  last ok action     : step %s %s %s" % (last_ok["step"], last_ok["tool"], short(last_ok, 80)) if last_ok else "  last ok action: NONE")
    print("  last call          : step %s %s %s (status=%s)" % (calls[-1]["step"], calls[-1]["tool"], short(calls[-1], 70), calls[-1]["status"]))
    print("  patches on disk    :", psize or "none")
