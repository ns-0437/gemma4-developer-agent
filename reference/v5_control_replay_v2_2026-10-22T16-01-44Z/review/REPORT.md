# Repaired V5 CPU replay: PASS

Both runtime identity gates and all eight controls passed. No candidate performance was measured.

| Task | Arm | Pytest exit | Test patch | Reference patch | Cleanup |
|---|---|---:|---:|---:|---|
| rich_3278 | baseline | 1 | 0 | not applied | pass |
| rich_3278 | reference | 0 | 0 | 0 | pass |
| rich_3535 | baseline | 1 | 0 | not applied | pass |
| rich_3535 | reference | 0 | 0 | 0 | pass |
| rich_3675 | baseline | 1 | 0 | not applied | pass |
| rich_3675 | reference | 0 | 0 | 0 | pass |
| rich_3942 | baseline | 1 | 0 | not applied | pass |
| rich_3942 | reference | 0 | 0 | 0 | pass |

Preserved 27 hashed files; all hashes still match. 26 remote basenames match outputs; the additional file is the kernel log.

basename multiset matched; remote API provides no full paths and reported sizes differ from downloaded bytes, so remote byte completeness is unverified

all 10 normalized cell sources and notebook metadata match repaired launch

output endpoint ignores version suffix; current source matched repaired v2 and evidence contains its runtime gates

Compiler: 0.2.13, 20 Python modules. Swegemma: 0.2.11, 34 modules. Four preconditions confirm imports from each checkout. Workspace probes succeeded on all arms; no node canonicalization was needed. No GPU launch or submission performed.
