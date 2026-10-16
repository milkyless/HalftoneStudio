"""確認 film-halftone 外掛程序是否已註冊進 GIMP 的 PDB。"""
lines = []

try:
    proc = pdb["film-halftone"]
    lines = ["PROC_OK", "blurb: %s" % proc.blurb]
    for arg in proc.params:
        lines.append("  - %s (%s)" % (arg.name, arg.type))
except Exception as exc:  # noqa: BLE001
    lines = ["PROC_MISSING: %r" % (exc,)]

with open("C:/Users/Milky/Desktop/Z/test/proc_out.txt", "w") as fh:
    fh.write("\n".join(lines))
