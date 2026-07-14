"""
templates.py — LLVM IR template definitions.

Each template is a plain string with two format placeholders:
  {id}  — an integer index, used to create unique names
  {c}   — a small positive integer constant chosen at generation time

Templates are grouped by the optimisation they demonstrate so that the
generator can select an appropriate variety for each run.

To add a new template, define a string constant and append an entry to
TEMPLATE_LIBRARY with the correct ``name`` and ``category`` keys.
"""
from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# Category constants (used in TEMPLATE_LIBRARY entries)
# ---------------------------------------------------------------------------
CAT_CONSTANT_FOLDING   = "constant_folding"
CAT_DEAD_CODE          = "dead_code_elimination"
CAT_LOOP               = "loop_optimisation"
CAT_CSE                = "common_subexpression_elimination"
CAT_BRANCH             = "branch_optimisation"
CAT_SWITCH             = "switch_lowering"
CAT_VECTOR             = "vectorisation_hint"
CAT_INLINE             = "inlining_hint"

# ---------------------------------------------------------------------------
# Constant-folding templates
# ---------------------------------------------------------------------------

# A long chain of add i32 instructions — O3 folds the whole chain to a
# single constant, shrinking the binary by 60–75 %.
CONST_FOLD_CHAIN = """\
define i32 @main() {{
entry:
  %v0 = add i32 {id}, 1
  %v1 = add i32 %v0, 1
  %v2 = add i32 %v1, 1
  %v3 = add i32 %v2, 1
  %v4 = add i32 %v3, 1
  %v5 = add i32 %v4, 1
  %v6 = add i32 %v5, 1
  %v7 = add i32 %v6, 1
  %v8 = add i32 %v7, 1
  %v9 = add i32 %v8, 1
  %v10 = add i32 %v9, 1
  %v11 = add i32 %v10, 1
  %v12 = add i32 %v11, 1
  %v13 = add i32 %v12, 1
  %v14 = add i32 %v13, 1
  %v15 = add i32 %v14, 1
  %v16 = add i32 %v15, 1
  %v17 = add i32 %v16, 1
  %v18 = add i32 %v17, 1
  %v19 = add i32 %v18, 1
  ret i32 %v19
}}"""

# Mixed arithmetic that O3 evaluates at compile time
CONST_FOLD_MIXED = """\
define i32 @main() {{
entry:
  %a = mul i32 {id}, {c}
  %b = add i32 %a, {c}
  %c0 = mul i32 %b, 2
  %d = sub i32 %c0, {c}
  %e = add i32 %d, 0
  %f = mul i32 %e, 1
  %g = xor i32 %f, 0
  %h = or i32 %g, 0
  %i = and i32 %h, -1
  ret i32 %i
}}"""

# ---------------------------------------------------------------------------
# Dead-code elimination templates
# ---------------------------------------------------------------------------

# Hundreds of computed values that are never used — O3 eliminates them all
DEAD_CODE_CHAIN = """\
define i32 @main() {{
entry:
  %result = add i32 {id}, {c}
  %d0  = mul i32 2, 3
  %d1  = mul i32 %d0, 4
  %d2  = mul i32 %d1, 5
  %d3  = add i32 %d2, 7
  %d4  = xor i32 %d3, 11
  %d5  = sub i32 %d4, 3
  %d6  = mul i32 %d5, 2
  %d7  = add i32 %d6, %d0
  %d8  = and i32 %d7, 255
  %d9  = or  i32 %d8, 16
  %d10 = mul i32 %d9, %d1
  %d11 = xor i32 %d10, %d2
  %d12 = sub i32 %d11, %d3
  ret i32 %result
}}"""

# Dead computation mixed with live code
DEAD_CODE_MIXED = """\
define i32 @main() {{
entry:
  %live0 = add i32 {id}, {c}
  %dead0 = mul i32 %live0, 13
  %dead1 = mul i32 %dead0, 7
  %dead2 = xor i32 %dead1, 255
  %dead3 = add i32 %dead2, %dead1
  %dead4 = sub i32 %dead3, %dead0
  %live1 = add i32 %live0, 1
  %dead5 = mul i32 %live1, 99
  %dead6 = or  i32 %dead5, %dead4
  ret i32 %live1
}}"""

# ---------------------------------------------------------------------------
# Common-subexpression elimination (CSE)
# ---------------------------------------------------------------------------

# The same expression computed many times — O3 computes it once
REDUNDANT_CHAIN = """\
define i32 @main() {{
entry:
  %base = add i32 {id}, 0
  %key  = mul i32 %base, {c}
  %r0  = mul i32 %base, {c}
  %r1  = mul i32 %base, {c}
  %r2  = mul i32 %base, {c}
  %r3  = mul i32 %base, {c}
  %r4  = mul i32 %base, {c}
  %r5  = mul i32 %base, {c}
  %r6  = mul i32 %base, {c}
  %r7  = mul i32 %r0, %r1
  %r8  = add i32 %r7, %r2
  %r9  = sub i32 %r8, %r3
  %r10 = xor i32 %r9, %r4
  ret i32 %r10
}}"""

# ---------------------------------------------------------------------------
# Loop-optimisation templates
# ---------------------------------------------------------------------------

# Short loop with a fixed iteration count — O3 unrolls completely
LOOP_COLLAPSIBLE = """\
define i32 @main() {{
entry:
  br label %loop

loop:
  %i   = phi i32 [ 0, %entry ], [ %next_i, %loop ]
  %acc = phi i32 [ 0, %entry ], [ %next_acc, %loop ]
  %next_acc = add i32 %acc, %i
  %next_i   = add i32 %i, 1
  %cond = icmp slt i32 %next_i, 10
  br i1 %cond, label %loop, label %exit

exit:
  ret i32 %acc
}}"""

# Loop-invariant computation that LICM can hoist out of the loop body
LOOP_WITH_INVARIANT = """\
define i32 @main() {{
entry:
  br label %loop

loop:
  %i   = phi i32 [ 0, %entry ], [ %next_i, %loop ]
  %acc = phi i32 [ 0, %entry ], [ %next_acc, %loop ]
  %inv = mul i32 {c}, {c}
  %next_acc = add i32 %acc, %inv
  %next_i   = add i32 %i, 1
  %cond = icmp slt i32 %next_i, 20
  br i1 %cond, label %loop, label %exit

exit:
  ret i32 %acc
}}"""

# ---------------------------------------------------------------------------
# Branch-optimisation templates
# ---------------------------------------------------------------------------

# Always-true branch — O3 eliminates the false path and the branch itself
BRANCH_FANOUT = """\
define i32 @main() {{
entry:
  %cond0 = icmp eq i32 0, 0
  br i1 %cond0, label %branch_a, label %branch_b

branch_a:
  %a0 = add i32 {id}, {c}
  %a1 = mul i32 %a0, 2
  %a2 = sub i32 %a1, 1
  br label %merge

branch_b:
  %b0 = sub i32 {id}, {c}
  %b1 = add i32 %b0, 1
  %b2 = mul i32 %b1, 3
  br label %merge

merge:
  %result = phi i32 [ %a2, %branch_a ], [ %b2, %branch_b ]
  ret i32 %result
}}"""

# Multi-way branch (switch-like pattern)
MULTI_WAY_BRANCH = """\
define i32 @main() {{
entry:
  %key = add i32 {id}, 0
  %c0  = icmp eq i32 %key, 1
  br i1 %c0, label %case1, label %check2

check2:
  %c1  = icmp eq i32 %key, 2
  br i1 %c1, label %case2, label %check3

check3:
  %c2  = icmp eq i32 %key, 3
  br i1 %c2, label %case3, label %default

case1:
  %v1 = add i32 {c}, 10
  br label %done

case2:
  %v2 = mul i32 {c}, 2
  br label %done

case3:
  %v3 = sub i32 {c}, 1
  br label %done

default:
  %vd = add i32 0, 0
  br label %done

done:
  %out = phi i32 [ %v1, %case1 ], [ %v2, %case2 ], [ %v3, %case3 ], [ %vd, %default ]
  ret i32 %out
}}"""

# ---------------------------------------------------------------------------
# Switch-lowering templates
# ---------------------------------------------------------------------------

# A switch converted to an if-chain; O3 can lower this to a jump table
SWITCH_LOWERING = """\
define i32 @main() {{
entry:
  %idx = add i32 {id}, 0
  switch i32 %idx, label %sw_default [
    i32 0, label %sw_case_0
    i32 1, label %sw_case_1
    i32 2, label %sw_case_2
    i32 3, label %sw_case_3
  ]

sw_case_0:
  %r0 = add i32 {c}, 0
  br label %sw_end

sw_case_1:
  %r1 = add i32 {c}, 1
  br label %sw_end

sw_case_2:
  %r2 = add i32 {c}, 2
  br label %sw_end

sw_case_3:
  %r3 = add i32 {c}, 3
  br label %sw_end

sw_default:
  %rd = add i32 0, -1
  br label %sw_end

sw_end:
  %res = phi i32 [ %r0, %sw_case_0 ], [ %r1, %sw_case_1 ], [ %r2, %sw_case_2 ],
                  [ %r3, %sw_case_3 ], [ %rd, %sw_default ]
  ret i32 %res
}}"""

# ---------------------------------------------------------------------------
# Vectorisation-hint template (integer SIMD pattern)
# ---------------------------------------------------------------------------

# Repeated independent integer operations — auto-vectoriser can group them
VECTOR_PATTERN = """\
define i32 @main() {{
entry:
  %a0 = add i32 {id}, 1
  %a1 = add i32 {id}, 2
  %a2 = add i32 {id}, 3
  %a3 = add i32 {id}, 4
  %b0 = mul i32 %a0, {c}
  %b1 = mul i32 %a1, {c}
  %b2 = mul i32 %a2, {c}
  %b3 = mul i32 %a3, {c}
  %c0 = add i32 %b0, %b1
  %c1 = add i32 %b2, %b3
  %result = add i32 %c0, %c1
  ret i32 %result
}}"""

# ---------------------------------------------------------------------------
# Inline-hint template (small helper called in a loop)
# ---------------------------------------------------------------------------

# Tiny helper function that a call-site loop calls repeatedly — O3 inlines it
ARRAY_PROMOTE = """\
define i32 @helper_{id}(i32 %x) {{
  %t0 = mul i32 %x, {c}
  %t1 = add i32 %t0, 1
  ret i32 %t1
}}

define i32 @main() {{
entry:
  %s0 = call i32 @helper_{id}(i32 1)
  %s1 = call i32 @helper_{id}(i32 2)
  %s2 = call i32 @helper_{id}(i32 3)
  %s3 = call i32 @helper_{id}(i32 4)
  %t0 = add i32 %s0, %s1
  %t1 = add i32 %s2, %s3
  %result = add i32 %t0, %t1
  ret i32 %result
}}"""

# ---------------------------------------------------------------------------
# Tail-call elimination template
# ---------------------------------------------------------------------------

# A tail-recursive accumulator — O3 converts the recursive call to a loop
CAT_TAIL_CALL = "tail_call_elimination"

TAIL_CALL_ACCUM = """\
define i32 @sum_{id}(i32 %n, i32 %acc) {{
  %done = icmp sle i32 %n, 0
  br i1 %done, label %base, label %recurse

base:
  ret i32 %acc

recurse:
  %next_n   = sub i32 %n, 1
  %next_acc = add i32 %acc, %n
  %result   = call i32 @sum_{id}(i32 %next_n, i32 %next_acc)
  ret i32 %result
}}

define i32 @main() {{
entry:
  %r = call i32 @sum_{id}(i32 {c}, i32 0)
  ret i32 %r
}}"""

# ---------------------------------------------------------------------------
# GVN (global value numbering) template
# ---------------------------------------------------------------------------

CAT_GVN = "global_value_numbering"

GVN_PATTERN = """\
define i32 @main() {{
entry:
  %base  = add i32 {id}, {c}
  %expr1 = mul i32 %base, {c}
  %expr2 = add i32 %expr1, {c}
  %expr3 = mul i32 %base, {c}
  %expr4 = add i32 %expr3, {c}
  %sum1  = add i32 %expr2, %expr4
  %expr5 = mul i32 %base, {c}
  %expr6 = add i32 %expr5, {c}
  %sum2  = add i32 %sum1, %expr6
  ret i32 %sum2
}}"""

# ---------------------------------------------------------------------------
# Alloca / mem2reg promotion template
# ---------------------------------------------------------------------------

CAT_MEM2REG = "mem2reg_promotion"

MEM2REG_PATTERN = """\
define i32 @main() {{
entry:
  %slot = alloca i32
  store i32 {c}, i32* %slot
  %v0 = load i32, i32* %slot
  %v1 = add i32 %v0, {id}
  store i32 %v1, i32* %slot
  %v2 = load i32, i32* %slot
  %v3 = mul i32 %v2, {c}
  store i32 %v3, i32* %slot
  %result = load i32, i32* %slot
  ret i32 %result
}}"""

# ---------------------------------------------------------------------------
# Multi-function call graph template
# ---------------------------------------------------------------------------
# Three small functions call each other in a chain; O3 inlines all of them
# and constant-folds the result, while O0 preserves every call frame.

CAT_CALL_GRAPH = "call_graph_inlining"

MULTI_FUNC_CALL_GRAPH = """\
define i32 @leaf_{id}(i32 %x) {{
  %r0 = mul i32 %x, {c}
  %r1 = add i32 %r0, 1
  ret i32 %r1
}}

define i32 @mid_{id}(i32 %x) {{
  %m0 = call i32 @leaf_{id}(i32 %x)
  %m1 = add i32 %m0, {c}
  ret i32 %m1
}}

define i32 @main() {{
entry:
  %a = call i32 @mid_{id}(i32 {id})
  %b = call i32 @mid_{id}(i32 {c})
  %result = add i32 %a, %b
  ret i32 %result
}}"""

# ---------------------------------------------------------------------------
# Memory alloca chain template
# ---------------------------------------------------------------------------
# Multiple alloca slots with store/load chains — mem2reg promotes these to
# SSA registers under O1+, eliminating every memory operation.

CAT_ALLOCA_CHAIN = "alloca_chain_promotion"

MEMORY_ALLOCA_CHAIN = """\
define i32 @main() {{
entry:
  %s0 = alloca i32
  %s1 = alloca i32
  %s2 = alloca i32
  store i32 {id}, i32* %s0
  store i32 {c},  i32* %s1
  %v0 = load i32, i32* %s0
  %v1 = load i32, i32* %s1
  %t0 = add i32 %v0, %v1
  store i32 %t0, i32* %s2
  %v2 = load i32, i32* %s2
  %t1 = mul i32 %v2, {c}
  store i32 %t1, i32* %s0
  %v3 = load i32, i32* %s0
  %t2 = add i32 %v3, %v1
  store i32 %t2, i32* %s1
  %result = load i32, i32* %s1
  ret i32 %result
}}"""

# ---------------------------------------------------------------------------
# Global constant propagation template
# ---------------------------------------------------------------------------
# A module-level constant is read inside a function; O3 propagates the
# constant value directly, removing the load and any address computation.

CAT_GLOBAL_CONST = "global_constant_propagation"

GLOBAL_CONST_PROPAGATION = """\
@SCALE_{id} = constant i32 {c}
@BIAS_{id}  = constant i32 {id}

define i32 @main() {{
entry:
  %scale = load i32, i32* @SCALE_{id}
  %bias  = load i32, i32* @BIAS_{id}
  %a = mul i32 %scale, {id}
  %b = add i32 %a, %bias
  %c0 = mul i32 %b, %scale
  %d = sub i32 %c0, %bias
  ret i32 %d
}}"""

# ---------------------------------------------------------------------------
# Loop with memory access template
# ---------------------------------------------------------------------------
# A loop that reads and writes a stack slot on every iteration; LICM can
# hoist the load out of the loop, and mem2reg can eliminate the slot entirely.

CAT_LOOP_MEMORY = "loop_memory_access"

LOOP_MEMORY_ACCESS = """\
define i32 @main() {{
entry:
  %slot = alloca i32
  store i32 0, i32* %slot
  br label %loop

loop:
  %i = phi i32 [ 0, %entry ], [ %i_next, %loop ]
  %cur = load i32, i32* %slot
  %inv = mul i32 {c}, {id}
  %upd = add i32 %cur, %inv
  store i32 %upd, i32* %slot
  %i_next = add i32 %i, 1
  %cond = icmp slt i32 %i_next, 8
  br i1 %cond, label %loop, label %exit

exit:
  %result = load i32, i32* %slot
  ret i32 %result
}}"""

# ---------------------------------------------------------------------------
# Template library — the single collection every other module references
# ---------------------------------------------------------------------------

TEMPLATE_LIBRARY: List[dict] = [
    {"name": "const_fold_chain",        "template": CONST_FOLD_CHAIN,        "category": CAT_CONSTANT_FOLDING},
    {"name": "const_fold_mixed",        "template": CONST_FOLD_MIXED,        "category": CAT_CONSTANT_FOLDING},
    {"name": "dead_code_chain",         "template": DEAD_CODE_CHAIN,         "category": CAT_DEAD_CODE},
    {"name": "dead_code_mixed",         "template": DEAD_CODE_MIXED,         "category": CAT_DEAD_CODE},
    {"name": "redundant_chain",         "template": REDUNDANT_CHAIN,         "category": CAT_CSE},
    {"name": "loop_collapsible",        "template": LOOP_COLLAPSIBLE,        "category": CAT_LOOP},
    {"name": "loop_invariant",          "template": LOOP_WITH_INVARIANT,     "category": CAT_LOOP},
    {"name": "branch_fanout",           "template": BRANCH_FANOUT,           "category": CAT_BRANCH},
    {"name": "multi_way_branch",        "template": MULTI_WAY_BRANCH,        "category": CAT_BRANCH},
    {"name": "switch_lowering",         "template": SWITCH_LOWERING,         "category": CAT_SWITCH},
    {"name": "vector_pattern",          "template": VECTOR_PATTERN,          "category": CAT_VECTOR},
    {"name": "array_promote",           "template": ARRAY_PROMOTE,           "category": CAT_INLINE},
    {"name": "tail_call_accum",         "template": TAIL_CALL_ACCUM,         "category": CAT_TAIL_CALL},
    {"name": "gvn_pattern",             "template": GVN_PATTERN,             "category": CAT_GVN},
    {"name": "mem2reg_pattern",         "template": MEM2REG_PATTERN,         "category": CAT_MEM2REG},
    # Richer templates: multi-function, memory operations, global constants
    {"name": "multi_func_call_graph",    "template": MULTI_FUNC_CALL_GRAPH,   "category": CAT_CALL_GRAPH},
    {"name": "memory_alloca_chain",      "template": MEMORY_ALLOCA_CHAIN,     "category": CAT_ALLOCA_CHAIN},
    {"name": "global_const_propagation", "template": GLOBAL_CONST_PROPAGATION,"category": CAT_GLOBAL_CONST},
    {"name": "loop_memory_access",       "template": LOOP_MEMORY_ACCESS,      "category": CAT_LOOP_MEMORY},
]
