# Comparison version 2: completed notebook, incomplete experiment

Kaggle CLI reports COMPLETE. All downloaded raw files are preserved in the sibling `compare-run2` directory; `raw_sha256.json` records their hashes. The offline reviewer used the frozen version-2 notebook, SHA256 `97873af2210b0f26276efce30c14d1b4c0491320f008e983c20c174328bfdbbc`, not version 1.

All eight baseline/reference control arms passed acceptance in the GPU session. Runtime logs show four NVIDIA L4 GPUs and vLLM tp=4. Model startup took 9.6 minutes. Server shutdown is recorded. Quota charged was not measured here.

| Planned run | Result |
|---|---|
| rich_3278 / A | 60-turn budget exhausted; no submitted patch; grading never ran |
| rich_3278 / B | Ended without submit_patch; no submitted patch; grading never ran |
| rich_3535 / B | Not attempted |
| rich_3535 / A | Not attempted |
| rich_3675 / A | Not attempted |
| rich_3675 / B | Not attempted |
| rich_3942 / B | Not attempted |
| rich_3942 / A | Not attempted |

A spent 377.5 seconds in the agent loop (403.1 seconds including setup). Its trace repeatedly rewrites and runs a reproduction in /tmp, without a demonstrated source edit. B spent 244.0 seconds in the agent loop (269.7 seconds including setup). It emitted 42 edit_file calls missing the required old_string parameter, which were rejected. These are attempted edits, not successful edits. B's final text contains malformed tool-call syntax rather than a successful submit_patch call.

The controller classified `Agent completed execution without calling submit_patch.` as an unclassified environment error and stopped the remaining six runs. That classification is too broad: the trace establishes failed tool use and missing submission, not an observed environment failure. The saved automated classification is preserved rather than silently rewritten.

No graded comparison exists, so neither candidate is a winner. The CPU patch-transport repair held; it does not fix agent repetition or malformed tool calls. Synthetic test counts did not establish coverage of this newly observed termination message.

Next work: add a regression for this exact termination message so it is classified separately from infrastructure failure; investigate the malformed tool-call payloads and repeated identical calls before selecting a bounded recovery experiment. Do not launch another GPU run or submit a candidate on these results alone. The authorized single GPU launch has been used.

The automated trace audit remains diagnostic, not proof of filesystem isolation. Raw model output versus parser transformation still needs investigation before blaming the model alone for malformed arguments. The existing metrics also undercount errors represented as a plain `error` field; do not treat their tool_errors column as a complete error count.
