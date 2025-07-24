# parse robj->ptr references and replace them with objectGetVal(robj) and objectSetVal(robj)

from dataclasses import dataclass
from pathlib import Path
import re

@dataclass
class Ref:
    path: Path
    line: int
    char: int
    note: str

def load(base_path: Path, ref_listing_path: Path):
    with open(ref_listing_path, "r") as f:
        data = f.readlines()

    file = ""
    reflist: list[Ref] = []
    for line in data:
        if line.strip() == "":
            continue
        if not line.startswith(' '):
            file = line.strip()
            continue

        # parse lines like "  2443, 39: sdscatsds(user, descr->ptr);\n"
        # Extract line number, char position, and note
        try:
            parts = line.strip().split(":", 1)
            loc, note = parts[0], parts[1].strip()
            line_num, char_num = [int(x.strip()) for x in loc.split(",")]
            ref = Ref(base_path / file, line_num, char_num, note)
            reflist.append(ref)
        except Exception as e:
            print(f"Failed to parse line: {line.strip()} ({e})")

    return reflist

def get_obj_var(line: str):
    # extract the variable name from a line like "sdsdup(c->argv[argpos]->ptr"
    assert line.endswith("->ptr"), f"Line does not end with '->ptr': {line}"
    line = line[:-5].strip()  # exclude "->ptr"

    pairs = {
        ')': '(',
        ']': '[',
        '}': '{',
        }
    pairends = "([{"

    i = len(line) - 1
    unclosed = ""
    if line[i] == ')': # only start new parenthesis when no other unclosed pairs if it's an outer parenthesis wrapping the whole variable
        unclosed += '('
        i -= 1

    for i in range(i, -1, -1):
        char = line[i]
        if unclosed:
            if char in pairends:
                assert char == unclosed[-1]
                unclosed = unclosed[:-1]
        else:
            # no unclosed pairs, check stop conditions
            if char in pairends or char.isspace() or char in ')!':
                i += 1 # this char was invalid so don't include it
                break

        if char in pairs:
            unclosed += pairs[char]

    var = line[i:]
    stripped_var = var.strip()
    while stripped_var.startswith('(') and stripped_var.endswith(')'):
        stripped_var = stripped_var[1:-1].strip()
    return var, stripped_var

assert get_obj_var("sdsdup(c->argv[argpos]->ptr")[0] == "c->argv[argpos]"
assert get_obj_var("sdsdup(user->descr->ptr")[0] == "user->descr"
assert get_obj_var('addReplyErrorFormat(c, "Unknown node %s", (char *)c->argv[2]->ptr')[0] == "c->argv[2]"
assert get_obj_var("        sds key->ptr = argv[result.keys[i].pos]->ptr")[0] == "argv[result.keys[i].pos]"
assert get_obj_var("     sds err = getAclErrorMessage(result, u, cmd, c->argv[idx + 3]->ptr")[0] == "c->argv[idx + 3]"
assert get_obj_var("batch->keys[i] = ((robj *)batch->keys[i])->ptr")[0] == "((robj *)batch->keys[i])"
assert get_obj_var("if (!client->name || !client->name->ptr")[0] == "client->name"
assert get_obj_var("    set->ptr")[0] == "set"
assert get_obj_var("set->ptr")[0] == "set"

def get_assignment(line) -> str:
    assert line.startswith("ptr = "), f"Line does not start with 'ptr = ': {line}"
    first_semicolon = line.find(';')
    if first_semicolon == -1:
        raise ValueError(f"Line does not contain a semicolon")
    assignment = line[5:first_semicolon].strip()  # exclude "ptr = "
    return assignment

def replace_read_ref(ref: Ref, line) -> str:
    var, stripped_var = get_obj_var(line[:ref.char + 2])  # include "->ptr"


    new_line = line[:ref.char - 1 - (len(var) + 2)] + f"objectGetVal({stripped_var})" + line[ref.char - 1 + 3:]
    return new_line

def replace_write_ref(ref: Ref, line_num: int, lines: list[str]) -> str:
    line = lines[ref.line - 1]

    var, stripped_var = get_obj_var(line[:ref.char + 2])  # include "->ptr"
    assignment = get_assignment(line[ref.char-1:]) # include "ptr = "
    new_line = line[:ref.char - 1 - (len(var) + 2)] + f"objectSetVal({stripped_var}, {assignment})" + line[ref.char + 5 + len(assignment):]
    if " = " in assignment:
        print(f"Follow up on {ref.path}:{ref.line}:{ref.char} - assignment contains '=': {assignment}")
        print("  old:", line[:-1])
        print("  new:", new_line[:-1])
    return new_line

def replace_all(refs: list[Ref], dry_run=False):
    to_replace = refs.copy()
    skipped: list[Ref] = []

    i = 0
    file = None
    data: list[str] = []
    while to_replace:
        ref = to_replace.pop() # backwards in case there are multiple refs in the same line
        if file != ref.path:
            if file and not dry_run:
                assert data, f"No data loaded for {file}"
                # write previous file
                with open(file, "w") as f:
                    f.writelines(data)
            file = ref.path
            with open(file, 'r') as f:
                data = f.readlines()

        assert ref.line - 1 < len(data), f"Line {ref.line} out of range for {file}"
        line = data[ref.line - 1]
        assert ref.char + 2 <= len(line), f"Char {ref.char} out of range for {file} at line {ref.line}"

        if line[ref.char - 3:ref.char - 1] != "->":
            print(f"Skipping {ref.path}:{ref.line}:{ref.char} - not pointer deref")
            print(f"  line: {line[:-1]}")
            skipped.append(ref)
            continue
        if line[ref.char - 1:ref.char + 5] == "ptr = ":
            try:
                data[ref.line - 1] = replace_write_ref(ref, ref.line, data)
            except ValueError as e:
                print(f"Skipping {ref.path}:{ref.line}:{ref.char} - {e}")
                print(f"  line: {line[:-1]}")
                skipped.append(ref)
                continue
        else:
            # read ref
            data[ref.line - 1] = replace_read_ref(ref, line)

        i += 1

    if file and not dry_run:
        assert data, f"No data loaded for {file}"
        # write previous file
        with open(file, "w") as f:
            f.writelines(data)

    print(f"Replaced {i} references, skipped {len(skipped)} references")


reflist = load(Path("/home/ubuntu/SoftlyRaining"), Path("robj-ptr-refs.txt"))
replace_all(reflist, dry_run=False)

