"""
Practical LLVM IR templates for demonstrating meaningful -O3 optimizations.
Focused on constant folding, dead code elimination, and loop optimization.
Each template targets optimization opportunities that create real binary size differences.
"""
from typing import List

# ============= CONSTANT FOLDING CHAIN TEMPLATES =============
# Massive constant folding chains that get reduced to single constants with -O3
# Binary size reduction: 60-75%

_CONST_FOLD_HUGE_1 = ["define i32 @main() {{", "entry:"]
_CONST_FOLD_HUGE_1.append("  %c0 = add i32 {{id}}, 1")
for i in range(1, 1000):
    _CONST_FOLD_HUGE_1.append(f"  %c{i} = add i32 %c{i-1}, 1")
_CONST_FOLD_HUGE_1.append("  ret i32 %c999")
_CONST_FOLD_HUGE_1.append("}}")
CONST_FOLD_HUGE_1 = "\n".join(_CONST_FOLD_HUGE_1)

# Mixed arithmetic operations all foldable to constants
# Binary size reduction: 50-70%
_CONST_FOLD_HUGE_2 = ["define i32 @main() {{", "entry:"]
_CONST_FOLD_HUGE_2.append("  %m0 = mul i32 {{id}}, 3")
for i in range(1, 800):
    _CONST_FOLD_HUGE_2.append(f"  %m{i} = mul i32 %m{i-1}, 1")
_CONST_FOLD_HUGE_2.append("  %a800 = add i32 0, 0")
for i in range(800, 1500):
    _CONST_FOLD_HUGE_2.append(f"  %a{i} = add i32 %a{i-1}, 0")
_CONST_FOLD_HUGE_2.append("  ret i32 %a1499")
_CONST_FOLD_HUGE_2.append("}}")
CONST_FOLD_HUGE_2 = "\n".join(_CONST_FOLD_HUGE_2)

# ============= DEAD CODE ELIMINATION TEMPLATES =============
# Hundreds of computations that are never used
# Binary size reduction: 40-60%

_DEAD_CODE_MASSIVE = ["define i32 @main() {{", "entry:"]
_DEAD_CODE_MASSIVE.append("  %val = add i32 {{id}}, 10")
_DEAD_CODE_MASSIVE.append("  %dead1 = mul i32 2, 2")
for i in range(2, 500):
    _DEAD_CODE_MASSIVE.append(f"  %dead{i} = mul i32 %dead{i-1}, 2")
_DEAD_CODE_MASSIVE.append("  %result = add i32 %val, 1")
_DEAD_CODE_MASSIVE.append("  ret i32 %result")
_DEAD_CODE_MASSIVE.append("}}")
DEAD_CODE_MASSIVE = "\n".join(_DEAD_CODE_MASSIVE)

# ============= COMMON SUBEXPRESSION ELIMINATION =============
# Same computations repeated many times
# Binary size reduction: 50-70%

_REDUNDANT_CHAIN = ["define i32 @main() {{", "entry:"]
_REDUNDANT_CHAIN.append("  %tmp = add i32 {{id}}, 0")
_REDUNDANT_CHAIN.append("  %a = mul i32 %tmp, 13")
for i in range(1, 600):
    _REDUNDANT_CHAIN.append(f"  %r{i} = mul i32 %tmp, 13")
_REDUNDANT_CHAIN.append("  ret i32 %r599")
_REDUNDANT_CHAIN.append("}}")
REDUNDANT_CHAIN = "\n".join(_REDUNDANT_CHAIN)

# ============= LOOP OPTIMIZATION TEMPLATES =============

# Loop with known bounds for complete unrolling
# Binary size reduction: 30-50%
_LOOP_COLLAPSIBLE = [
    "define i32 @main() {{",
    "entry:",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %ni, %loop ]",
    "  %sum = phi i32 [ 0, %entry ], [ %ns, %loop ]",
    "  %ns = add i32 %sum, %i",
    "  %ni = add i32 %i, 1",
    "  %cond = icmp slt i32 %ni, 10",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %sum",
    "}}",
]
LOOP_COLLAPSIBLE = "\n".join(_LOOP_COLLAPSIBLE)

# Loop with invariant computation that can be hoisted
# Binary size reduction: 20-40% (LICM optimization)
_LOOP_WITH_INVARIANT = [
    "define i32 @main() {{",
    "entry:",
    "  %inv = mul i32 99, 99",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %ni, %loop ]",
    "  %sum = phi i32 [ 0, %entry ], [ %ns, %loop ]",
    "  %tmp = mul i32 99, 99",
    "  %ns = add i32 %sum, %tmp",
    "  %ni = add i32 %i, 1",
    "  %cond = icmp slt i32 %ni, 20",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %sum",
    "}}",
]
LOOP_WITH_INVARIANT = "\n".join(_LOOP_WITH_INVARIANT)

# ============= INLINING OPTIMIZATION =============
# Simple functions that should be inlined
# Binary size reduction: 15-35%

_SMALL_CALL_CHAIN = [
    "define i32 @add_one(i32 %x) {{",
    "entry:",
    "  %r = add i32 %x, 1",
    "  ret i32 %r",
    "}}",
    "",
    "define i32 @times_two(i32 %x) {{",
    "entry:",
    "  %r = mul i32 %x, 2",
    "  ret i32 %r",
    "}}",
    "",
    "define i32 @main() {{",
    "entry:",
    "  %a = call i32 @add_one(i32 {{id}})",
    "  %b = call i32 @times_two(i32 %a)",
    "  %c = call i32 @add_one(i32 %b)",
    "  ret i32 %c",
    "}}",
]
SMALL_CALL_CHAIN = "\n".join(_SMALL_CALL_CHAIN)

# ============= BRANCH FOLDING =============
# Constant condition that can be eliminated
# Binary size reduction: 20-30%

_SIMPLE_BRANCH = [
    "define i32 @main() {{",
    "entry:",
    "  %cond = icmp sgt i32 10, 5",
    "  br i1 %cond, label %yes, label %no",
    "",
    "yes:",
    "  ret i32 1",
    "",
    "no:",
    "  ret i32 0",
    "}}",
]
SIMPLE_BRANCH = "\n".join(_SIMPLE_BRANCH)

# ============= SMALL LOOP UNROLLING =============
# Loop with small trip count that can be fully unrolled
# Binary size reduction: 25-40%

_SIMPLE_LOOP = [
    "define i32 @main() {{",
    "entry:",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %ni, %loop ]",
    "  %sum = phi i32 [ 0, %entry ], [ %ns, %loop ]",
    "  %ns = add i32 %sum, %i",
    "  %ni = add i32 %i, 1",
    "  %cond = icmp slt i32 %ni, 5",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %sum",
    "}}",
]
SIMPLE_LOOP = "\n".join(_SIMPLE_LOOP)

# ============= BASIC ARITHMETIC =============
# Simple math operations with constant folding opportunity
# Binary size reduction: 15-25%

_SIMPLE_MATH = [
    "define i32 @main() {{",
    "entry:",
    "  %a = add i32 {{id}}, 3",
    "  %b = mul i32 %a, 2",
    "  %c = sub i32 %b, 1",
    "  ret i32 %c",
    "}}",
]
SIMPLE_MATH = "\n".join(_SIMPLE_MATH)

# INVALID_1: deliberately references an undefined SSA value
# Tests: validator rejection and error-path handling
_INVALID = [
    "define i32 @main() {{",
    "entry:",
    "  %ok = add i32 {id}, {c}",
    "  %bad = add i32 %missing_variable, %ok",
    "  ret i32 %bad",
    "}}\n"
]
INVALID_1 = "\n".join(_INVALID)

# DIFF_1: intentionally invalid shift amount to provoke semantic differences
# Tests: differential checking and verifier failures
_DIFF = [
    "define i32 @main() {{",
    "entry:",
    "  %v = shl i32 1, 32",
    "  ret i32 %v",
    "}}\n"
]
DIFF_1 = "\n".join(_DIFF)

# TIMEOUT_1: tiny function used to test timeout/fast-path handling
# Tests: execution timeout plumbing and low-complexity control cases
_TIMEOUT = [
    "define i32 @main() {{",
    "entry:",
    "  %i = add i32 1, 1",
    "  %j = mul i32 %i, 2",
    "  ret i32 %j",
    "}}\n"
]
TIMEOUT_1 = "\n".join(_TIMEOUT)

# COMPILE_FAIL_1: inline assembly with a bogus mnemonic to force compiler failure
# Tests: compile-error reporting and fallback behavior
_COMPILE_FAIL = [
    "define i32 @main() {{",
    "entry:",
    '  %v = call i32 asm sideeffect "nonsense_instruction_for_id_{id}", "=r"()',
    "  ret i32 %v",
    "}}\n"
]
COMPILE_FAIL_1 = "\n".join(_COMPILE_FAIL)

# ============= LOOP TEMPLATES =============

# Loop 1: Simple forward-counting loop (while loop pattern)
# Tests: loop invariant code motion, induction variable elimination
_LOOP_SIMPLE_FORWARD = [
    "define i32 @main() {{",
    "entry:",
    "  %init_val = add i32 {id}, {c}",
    "  %limit = add i32 100, %init_val",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ %init_val, %entry ], [ %next_i, %loop ]",
    "  %sum = phi i32 [ 0, %entry ], [ %new_sum, %loop ]",
    "  %next_i = add i32 %i, 1",
    "  %new_sum = add i32 %sum, %i",
    "  %cond = icmp slt i32 %next_i, %limit",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %new_sum",
    "}}\n"
]
LOOP_SIMPLE_FORWARD = "\n".join(_LOOP_SIMPLE_FORWARD)

# Loop 2: Backward-counting loop (countdown)
# Tests: induction variable optimization, reverse loop patching
_LOOP_BACKWARD_COUNT = [
    "define i32 @main() {{",
    "entry:",
    "  %start = add i32 {id}, {c}",
    "  %limit = add i32 50, 0",
    "  br label %loop",
    "",
    "loop:",
    "  %counter = phi i32 [ %start, %entry ], [ %dec_counter, %loop ]",
    "  %prod = phi i32 [ 1, %entry ], [ %new_prod, %loop ]",
    "  %dec_counter = sub i32 %counter, 1",
    "  %new_prod = mul i32 %prod, %counter",
    "  %cond = icmp sgt i32 %dec_counter, %limit",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %new_prod",
    "}}\n"
]
LOOP_BACKWARD_COUNT = "\n".join(_LOOP_BACKWARD_COUNT)

# Loop 3: Nested loops (2-level nesting)
# Tests: loop depth analysis, nested optimization
_LOOP_NESTED = [
    "define i32 @main() {{",
    "entry:",
    "  %base = add i32 {id}, {c}",
    "  br label %outer_loop",
    "",
    "outer_loop:",
    "  %outer_i = phi i32 [ 0, %entry ], [ %outer_next, %outer_latch ]",
    "  %outer_sum = phi i32 [ 0, %entry ], [ %new_outer_sum, %outer_latch ]",
    "  br label %inner_loop",
    "",
    "inner_loop:",
    "  %inner_j = phi i32 [ 0, %outer_loop ], [ %inner_next, %inner_loop ]",
    "  %inner_sum = phi i32 [ %outer_sum, %outer_loop ], [ %new_inner_sum, %inner_loop ]",
    "  %inner_next = add i32 %inner_j, 1",
    "  %mul_val = mul i32 %outer_i, %inner_j",
    "  %new_inner_sum = add i32 %inner_sum, %mul_val",
    "  %inner_cond = icmp slt i32 %inner_next, 10",
    "  br i1 %inner_cond, label %inner_loop, label %outer_latch",
    "",
    "outer_latch:",
    "  %new_outer_sum = add i32 %new_inner_sum, %base",
    "  %outer_next = add i32 %outer_i, 1",
    "  %outer_cond = icmp slt i32 %outer_next, 5",
    "  br i1 %outer_cond, label %outer_loop, label %exit",
    "",
    "exit:",
    "  ret i32 %new_outer_sum",
    "}}\n"
]
LOOP_NESTED = "\n".join(_LOOP_NESTED)

# Loop 4: Loop with early exit (break condition)
# Tests: loop exit optimization, unreachable code elimination
_LOOP_EARLY_EXIT = [
    "define i32 @main() {{",
    "entry:",
    "  %threshold = add i32 {id}, {c}",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %next_i, %loop_body ]",
    "  %accum = phi i32 [ 0, %entry ], [ %new_accum, %loop_body ]",
    "  %mult = mul i32 %i, %threshold",
    "  %new_accum = add i32 %accum, %mult",
    "  %cond_exit = icmp sgt i32 %new_accum, 1000",
    "  br i1 %cond_exit, label %exit, label %loop_body",
    "",
    "loop_body:",
    "  %next_i = add i32 %i, 1",
    "  %cond_cont = icmp slt i32 %next_i, 100",
    "  br i1 %cond_cont, label %loop, label %exit",
    "",
    "exit:",
    "  %result = phi i32 [ %new_accum, %loop ], [ %new_accum, %loop_body ]",
    "  ret i32 %result",
    "}}\n"
]
LOOP_EARLY_EXIT = "\n".join(_LOOP_EARLY_EXIT)

# Loop 5: Loop with loop-invariant code motion opportunity
# Tests: LICM (Loop Invariant Code Motion) optimization
_LOOP_INVARIANT = [
    "define i32 @main() {{",
    "entry:",
    "  %inv1 = add i32 {id}, {c}",
    "  %inv2 = mul i32 %inv1, 7",
    "  %inv3 = add i32 %inv2, 3",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %next_i, %loop ]",
    "  %res = phi i32 [ 0, %entry ], [ %new_res, %loop ]",
    "  %inv_calc = add i32 %inv3, %inv1",
    "  %inv_mul = mul i32 %inv_calc, 2",
    "  %i_mul = mul i32 %i, %inv_mul",
    "  %new_res = add i32 %res, %i_mul",
    "  %next_i = add i32 %i, 1",
    "  %cond = icmp slt i32 %next_i, 50",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %new_res",
    "}}\n"
]
LOOP_INVARIANT = "\n".join(_LOOP_INVARIANT)

# Loop 6: Loop unrolling opportunity (tight inner loop)
# Tests: loop unrolling, strength reduction
_LOOP_UNROLL = [
    "define i32 @main() {{",
    "entry:",
    "  %base = add i32 {id}, {c}",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %i_add_4, %loop ]",
    "  %sum = phi i32 [ 0, %entry ], [ %sum_final, %loop ]",
    "  %i_1 = add i32 %i, 1",
    "  %i_2 = add i32 %i, 2",
    "  %i_3 = add i32 %i, 3",
    "  %i_4 = add i32 %i, 4",
    "  %s1 = add i32 %sum, %i_1",
    "  %s2 = add i32 %s1, %i_2",
    "  %s3 = add i32 %s2, %i_3",
    "  %sum_final = add i32 %s3, %i_4",
    "  %i_add_4 = add i32 %i, 4",
    "  %cond = icmp slt i32 %i_add_4, 100",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %sum_final",
    "}}\n"
]
LOOP_UNROLL = "\n".join(_LOOP_UNROLL)

# ============= CONTROL FLOW TEMPLATES =============

# Control Flow 1: Switch-like multiple branches (simulated with cascading if-else)
# Tests: branch prediction, case folding
_CONTROL_MULTI_BRANCH = [
    "define i32 @main() {{",
    "entry:",
    "  %val = add i32 {id}, {c}",
    "  %mod = urem i32 %val, 5",
    "  br label %case_check_0",
    "",
    "case_check_0:",
    "  %cond0 = icmp eq i32 %mod, 0",
    "  br i1 %cond0, label %case_0, label %case_check_1",
    "",
    "case_0:",
    "  %res0 = mul i32 %val, 10",
    "  br label %exit",
    "",
    "case_check_1:",
    "  %cond1 = icmp eq i32 %mod, 1",
    "  br i1 %cond1, label %case_1, label %case_check_2",
    "",
    "case_1:",
    "  %res1 = add i32 %val, 100",
    "  br label %exit",
    "",
    "case_check_2:",
    "  %cond2 = icmp eq i32 %mod, 2",
    "  br i1 %cond2, label %case_2, label %case_check_3",
    "",
    "case_2:",
    "  %res2 = sub i32 %val, 50",
    "  br label %exit",
    "",
    "case_check_3:",
    "  %cond3 = icmp eq i32 %mod, 3",
    "  br i1 %cond3, label %case_3, label %default",
    "",
    "case_3:",
    "  %res3 = mul i32 %val, %val",
    "  br label %exit",
    "",
    "default:",
    "  %res_default = add i32 %val, 1",
    "  br label %exit",
    "",
    "exit:",
    "  %result = phi i32 [ %res0, %case_0 ], [ %res1, %case_1 ], [ %res2, %case_2 ], [ %res3, %case_3 ], [ %res_default, %default ]",
    "  ret i32 %result",
    "}}\n"
]
CONTROL_MULTI_BRANCH = "\n".join(_CONTROL_MULTI_BRANCH)

_CONTROL_NESTED_BRANCH = [
    "define i32 @main() {{",
    "entry:",
    "  %a = add i32 {id}, {c}",
    "  %cond_a = icmp sgt i32 %a, 5",
    "  br i1 %cond_a, label %branch_a, label %branch_b",
    "",
    "branch_a:",
    "  %cond_a1 = icmp sgt i32 %a, 10",
    "  br i1 %cond_a1, label %a_deep1, label %a_deep2",
    "",
    "a_deep1:",
    "  %a1_val = mul i32 %a, 2",
    "  br label %a_merge",
    "",
    "a_deep2:",
    "  %a2_val = add i32 %a, 3",
    "  br label %a_merge",
    "",
    "a_merge:",
    "  %a_res = phi i32 [ %a1_val, %a_deep1 ], [ %a2_val, %a_deep2 ]",
    "  br label %final_merge",
    "",
    "branch_b:",
    "  %cond_b1 = icmp slt i32 %a, 0",
    "  br i1 %cond_b1, label %b_deep1, label %b_deep2",
    "",
    "b_deep1:",
    "  %b1_val = sub i32 %a, 5",
    "  br label %b_merge",
    "",
    "b_deep2:",
    "  %b2_val = mul i32 %a, 3",
    "  br label %b_merge",
    "",
    "b_merge:",
    "  %b_res = phi i32 [ %b1_val, %b_deep1 ], [ %b2_val, %b_deep2 ]",
    "  br label %final_merge",
    "",
    "final_merge:",
    "  %final = phi i32 [ %a_res, %a_merge ], [ %b_res, %b_merge ]",
    "  ret i32 %final",
    "}}\n"
]
CONTROL_NESTED_BRANCH = "\n".join(_CONTROL_NESTED_BRANCH)

# ============= OPTIMIZATION OPPORTUNITY TEMPLATES =============

_OPT_BITWISE_CHAIN = [
    "define i32 @main() {{",
    "entry:",
    "  %v0 = add i32 {id}, {c}",
    "  %b1 = and i32 %v0, 255",
    "  %b2 = or i32 %b1, 1",
    "  %b3 = xor i32 %b2, 128",
    "  %b4 = and i32 %b3, 127",
    "  %b5 = or i32 %b4, 2",
    "  %b6 = shl i32 %b5, 1",
    "  %b7 = lshr i32 %b6, 1",
    "  %b8 = xor i32 %b7, %b5",
    "  %b9 = and i32 %b8, 255",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %next_i, %loop ]",
    "  %res = phi i32 [ %b9, %entry ], [ %new_res, %loop ]",
    "  %and_i = and i32 %i, %res",
    "  %or_i = or i32 %and_i, 1",
    "  %new_res = xor i32 %or_i, %res",
    "  %next_i = add i32 %i, 1",
    "  %cond = icmp slt i32 %next_i, 20",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %res",
    "}}\n"
]
OPT_BITWISE_CHAIN = "\n".join(_OPT_BITWISE_CHAIN)

_OPT_REDUNDANT_ARITH = [
    "define i32 @main() {{",
    "entry:",
    "  %base = add i32 {id}, {c}",
    "  %a = mul i32 %base, 7",
    "  %b = add i32 %base, 3",
    "  %c = mul i32 %base, 7",
    "  %d = mul i32 %a, %b",
    "  %e = mul i32 %c, %b",
    "  %f = add i32 %d, %e",
    "  %g = sub i32 %f, %a",
    "  %h = add i32 %base, 3",
    "  %i = mul i32 %g, %h",
    "  %j = mul i32 %g, %b",
    "  %result = add i32 %i, %j",
    "  ret i32 %result",
    "}}\n"
]
OPT_REDUNDANT_ARITH = "\n".join(_OPT_REDUNDANT_ARITH)

_OPT_ASSOC_COMMUT = [
    "define i32 @main() {{",
    "entry:",
    "  %v = add i32 {id}, {c}",
    "  %r1 = add i32 %v, 5",
    "  %r2 = add i32 10, %r1",
    "  %r3 = mul i32 %r2, 3",
    "  %r4 = mul i32 2, %r3",
    "  %r5 = add i32 %r4, 15",
    "  %r6 = add i32 20, %r5",
    "  %r7 = mul i32 4, %r6",
    "  %r8 = mul i32 %r7, 2",
    "  ret i32 %r8",
    "}}\n"
]
OPT_ASSOC_COMMUT = "\n".join(_OPT_ASSOC_COMMUT)

_OPT_STRENGTH_REDUCTION = [
    "define i32 @main() {{",
    "entry:",
    "  %v = add i32 {id}, {c}",
    "  %m1 = mul i32 %v, 2",
    "  %m2 = mul i32 %m1, 4",
    "  %m3 = mul i32 %m2, 8",
    "  %m4 = mul i32 %m3, 16",
    "  %d1 = sdiv i32 %m4, 2",
    "  %d2 = sdiv i32 %d1, 4",
    "  %d3 = sdiv i32 %d2, 8",
    "  %d4 = sdiv i32 %d3, 16",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %next_i, %loop ]",
    "  %prod = phi i32 [ %d4, %entry ], [ %new_prod, %loop ]",
    "  %m_loop = mul i32 %prod, 2",
    "  %new_prod = add i32 %m_loop, %i",
    "  %next_i = add i32 %i, 1",
    "  %cond = icmp slt i32 %next_i, 10",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %prod",
    "}}\n"
]
OPT_STRENGTH_REDUCTION = "\n".join(_OPT_STRENGTH_REDUCTION)

_OPT_COMPARISON_CHAIN = [
    "define i32 @main() {{",
    "entry:",
    "  %v = add i32 {id}, {c}",
    "  %cmp1 = icmp sgt i32 %v, 10",
    "  %cmp2 = icmp slt i32 %v, 100",
    "  %and1 = and i1 %cmp1, %cmp2",
    "  br i1 %and1, label %in_range, label %out_range",
    "",
    "in_range:",
    "  %cmp3 = icmp eq i32 %v, 50",
    "  br i1 %cmp3, label %equal_50, label %not_50",
    "",
    "equal_50:",
    "  %res_eq = mul i32 %v, %v",
    "  br label %exit",
    "",
    "not_50:",
    "  %cmp4 = icmp sgt i32 %v, 50",
    "  br i1 %cmp4, label %greater_50, label %less_50",
    "",
    "greater_50:",
    "  %res_gt = add i32 %v, 100",
    "  br label %exit",
    "",
    "less_50:",
    "  %res_lt = sub i32 100, %v",
    "  br label %exit",
    "",
    "out_range:",
    "  %res_out = mul i32 %v, 2",
    "  br label %exit",
    "",
    "exit:",
    "  %result = phi i32 [ %res_eq, %equal_50 ], [ %res_gt, %greater_50 ], [ %res_lt, %less_50 ], [ %res_out, %out_range ]",
    "  ret i32 %result",
    "}}\n"
]
OPT_COMPARISON_CHAIN = "\n".join(_OPT_COMPARISON_CHAIN)

# ============= NEW TEMPLATES (LOOPS, CONTROL FLOW, OPTIMIZATIONS) =============
# Naming convention: CATEGORY_VARIANT

# Priority 1: Loop with loop-carried dependency
# Tests: loop-carried dependencies and scalar replacement limits
_LOOP_CARRIED_DEPENDENCY = [
    "define i32 @main() {{",
    "entry:",
    "  %init = add i32 {id}, {c}",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %next_i, %loop ]",
    "  %carry = phi i32 [ %init, %entry ], [ %new_carry, %loop ]",
    "  %tmp = add i32 %carry, %i",
    "  %new_carry = add i32 %tmp, 1",
    "  %next_i = add i32 %i, 1",
    "  %cond = icmp slt i32 %next_i, 30",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %new_carry",
    "}}\n"
]
LOOP_CARRIED_DEPENDENCY = "\n".join(_LOOP_CARRIED_DEPENDENCY)

# Priority 2: Strided array accesses using alloca + GEP + load/store
# Tests: mem2reg, alias analysis, and scalar replacement opportunities
_LOOP_STRIDED_ARRAY_ALLOCA_GEP = [
    "define i32 @main() {{",
    "entry:",
    "  %n = add i32 {id}, {c}",
    "  %arr = alloca i32, i32 16",
    "  %i = alloca i32, i32 1",
    "  store i32 0, ptr %i",
    "  br label %loop",
    "",
    "loop:",
    "  %iv = load i32, ptr %i",
    "  %is_stride = mul i32 %iv, 2",
    "  %ptr = getelementptr i32, ptr %arr, i32 %is_stride",
    "  %old = load i32, ptr %ptr",
    "  %new = add i32 %old, %n",
    "  store i32 %new, ptr %ptr",
    "  %next = add i32 %iv, 1",
    "  store i32 %next, ptr %i",
    "  %cond = icmp slt i32 %next, 8",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  %result_ptr = getelementptr i32, ptr %arr, i32 0",
    "  %res = load i32, ptr %result_ptr",
    "  ret i32 %res",
    "}}\n"
]
LOOP_STRIDED_ARRAY_ALLOCA_GEP = "\n".join(_LOOP_STRIDED_ARRAY_ALLOCA_GEP)

# Do-while / post-test loop pattern
# Tests: post-test loop lowering and induction variable handling
_LOOP_DO_WHILE_POSTTEST = [
    "define i32 @main() {{",
    "entry:",
    "  %acc = add i32 {id}, {c}",
    "  br label %body",
    "",
    "body:",
    "  %acc1 = add i32 %acc, 1",
    "  %cond = icmp slt i32 %acc1, %acc",
    "  br i1 %cond, label %body, label %exit",
    "",
    "exit:",
    "  ret i32 %acc1",
    "}}\n"
]
LOOP_DO_WHILE_POSTTEST = "\n".join(_LOOP_DO_WHILE_POSTTEST)

# Small realistic-count loop (5-20 iterations)
# Tests: realistic LICM and small-loop heuristics
_LOOP_SMALL_COUNT = [
    "define i32 @main() {{",
    "entry:",
    "  %sum = add i32 {id}, {c}",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %ni, %loop ]",
    "  %sumv = phi i32 [ %sum, %entry ], [ %nsum, %loop ]",
    "  %nsum = add i32 %sumv, %i",
    "  %ni = add i32 %i, 1",
    "  %cond = icmp slt i32 %ni, 12",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %nsum",
    "}}\n"
]
LOOP_SMALL_COUNT = "\n".join(_LOOP_SMALL_COUNT)

# Aggressively unrolled loop (step 8)
# Tests: unrolling heuristics and peephole strength reduction
_LOOP_UNROLLED_STEP8 = [
    "define i32 @main() {{",
    "entry:",
    "  %s = add i32 {id}, {c}",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %i_next, %loop ]",
    "  %a1 = add i32 %s, %i",
    "  %a2 = add i32 %s, %i",
    "  %a3 = add i32 %s, %i",
    "  %a4 = add i32 %s, %i",
    "  %a5 = add i32 %s, %i",
    "  %a6 = add i32 %s, %i",
    "  %a7 = add i32 %s, %i",
    "  %a8 = add i32 %s, %i",
    "  %i_next = add i32 %i, 8",
    "  %cond = icmp slt i32 %i_next, 64",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %a8",
    "}}\n"
]
LOOP_UNROLLED_STEP8 = "\n".join(_LOOP_UNROLLED_STEP8)

# SIMD-like independent operations in loop (vectorization candidate)
# Tests: loop vectorization and independent op scheduling
_LOOP_SIMD_LIKE = [
    "define i32 @main() {{",
    "entry:",
    "  %base = add i32 {id}, {c}",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %ni, %loop ]",
    "  %a = mul i32 %i, 2",
    "  %b = add i32 %a, %base",
    "  %cval = sub i32 %b, 1",
    "  %ni = add i32 %i, 1",
    "  %cond = icmp slt i32 %ni, 40",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %cval",
    "}}\n"
]
LOOP_SIMD_LIKE = "\n".join(_LOOP_SIMD_LIKE)

# Heavy loop-invariant work to stress LICM
# Tests: LICM and hoisting of common computations out of loop
_LOOP_INVARIANT_HEAVY = [
    "define i32 @main() {{",
    "entry:",
    "  %x = add i32 {id}, {c}",
    "  %heavy = mul i32 %x, 123",
    "  %heavy2 = add i32 %heavy, 7",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %ni, %loop ]",
    "  %tmp = mul i32 %i, %heavy2",
    "  %acc = add i32 %tmp, %i",
    "  %ni = add i32 %i, 1",
    "  %cond = icmp slt i32 %ni, 20",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %acc",
    "}}\n"
]
LOOP_INVARIANT_HEAVY = "\n".join(_LOOP_INVARIANT_HEAVY)

# Aggressively unrolled tight loop (explicit unroll)
# Tests: unrolled code quality and register pressure handling
_LOOP_UNROLLED_TIGHT = [
    "define i32 @main() {{",
    "entry:",
    "  %res = add i32 {id}, {c}",
    "  %r0 = add i32 %res, 1",
    "  %r1 = add i32 %r0, 2",
    "  %r2 = add i32 %r1, 3",
    "  %r3 = add i32 %r2, 4",
    "  %r4 = add i32 %r3, 5",
    "  %r5 = add i32 %r4, 6",
    "  %r6 = add i32 %r5, 7",
    "  %r7 = add i32 %r6, 8",
    "  ret i32 %r7",
    "}}\n"
]
LOOP_UNROLLED_TIGHT = "\n".join(_LOOP_UNROLLED_TIGHT)

# ============= CONTROL FLOW (NEW) =============

# CONTROL_SWITCH: uses LLVM 'switch' to test lowering to jump table
# Tests: switch lowering and jump-table generation
_CONTROL_SWITCH = [
    "define i32 @main() {{",
    "entry:",
    "  %v = add i32 {id}, {c}",
    "  %swt = urem i32 %v, 6",
    "  switch i32 %swt, label %default [",
    "    i32 0, label %case0",
    "    i32 1, label %case1",
    "    i32 2, label %case2",
    "    i32 3, label %case3",
    "    i32 4, label %case4",
    "    i32 5, label %case5",
    "]",
    "",
    "case0:",
    "  br label %merge",
    "case1:",
    "  br label %merge",
    "case2:",
    "  br label %merge",
    "case3:",
    "  br label %merge",
    "case4:",
    "  br label %merge",
    "case5:",
    "  br label %merge",
    "default:",
    "  br label %merge",
    "",
    "merge:",
    "  %r = phi i32 [ 0, %case0 ], [ 1, %case1 ], [ 2, %case2 ], [ 3, %case3 ], [ 4, %case4 ], [ 5, %case5 ], [ -1, %default ]",
    "  ret i32 %r",
    "}}\n"
]
CONTROL_SWITCH = "\n".join(_CONTROL_SWITCH)

# CONTROL_TAIL_RECURSION_SIM: simulate tail recursion shape convertible to loop
# Tests: tail-call elimination / tail-recursion lowering
_CONTROL_TAIL_RECURSION_SIM = [
    "define i32 @main() {{",
    "entry:",
    "  %n = add i32 {id}, {c}",
    "  %acc = add i32 0, 0",
    "  br label %recurse",
    "",
    "recurse:",
    "  %cond = icmp eq i32 %n, 0",
    "  br i1 %cond, label %ret, label %loop_step",
    "",
    "loop_step:",
    "  %acc2 = add i32 %acc, %n",
    "  %n2 = sub i32 %n, 1",
    "  br label %recurse",
    "",
    "ret:",
    "  ret i32 %acc",
    "}}\n"
]
CONTROL_TAIL_RECURSION_SIM = "\n".join(_CONTROL_TAIL_RECURSION_SIM)

# CONTROL_EXCEPTION_SIM: multiple labels and PHI chains to simulate exception/unwind paths
# Tests: complex PHI merging and exceptional control transfer
_CONTROL_EXCEPTION_SIM = [
    "define i32 @main() {{",
    "entry:",
    "  %ok = add i32 {id}, {c}",
    "  %cond = icmp sgt i32 %ok, 10",
    "  br i1 %cond, label %try, label %catch",
    "",
    "try:",
    "  %t = mul i32 %ok, 2",
    "  br label %done",
    "",
    "catch:",
    "  %c = sub i32 %ok, 2",
    "  br label %done",
    "",
    "done:",
    "  %res = phi i32 [ %t, %try ], [ %c, %catch ]",
    "  ret i32 %res",
    "}}\n"
]
CONTROL_EXCEPTION_SIM = "\n".join(_CONTROL_EXCEPTION_SIM)

# CONTROL_CHAINED_COMPARISONS: sequential comparisons and branches
# Tests: condition folding and reuse
_CONTROL_CHAINED_COMPARISONS = [
    "define i32 @main() {{",
    "entry:",
    "  %v = add i32 {id}, {c}",
    "  %c1 = icmp sgt i32 %v, 0",
    "  br i1 %c1, label %p1, label %n1",
    "",
    "p1:",
    "  %c2 = icmp slt i32 %v, 10",
    "  br i1 %c2, label %inrange, label %out",
    "",
    "inrange:",
    "  ret i32 1",
    "",
    "n1:",
    "  ret i32 -1",
    "",
    "out:",
    "  ret i32 0",
    "}}\n"
]
CONTROL_CHAINED_COMPARISONS = "\n".join(_CONTROL_CHAINED_COMPARISONS)

# CONTROL_MULTI_WAY_COMPLEX: 3+ nested branches with merges
# Tests: dominance and merge correctness
_CONTROL_MULTI_WAY_COMPLEX = [
    "define i32 @main() {{",
    "entry:",
    "  %a = add i32 {id}, {c}",
    "  %c1 = icmp sgt i32 %a, 5",
    "  br i1 %c1, label %A, label %B",
    "",
    "A:",
    "  %cA = icmp sgt i32 %a, 10",
    "  br i1 %cA, label %A1, label %A2",
    "",
    "A1:",
    "  br label %M",
    "A2:",
    "  br label %M",
    "",
    "B:",
    "  %cB = icmp slt i32 %a, 0",
    "  br i1 %cB, label %B1, label %B2",
    "",
    "B1:",
    "  br label %M",
    "B2:",
    "  br label %M",
    "",
    "M:",
    "  %r = phi i32 [ 1, %A1 ], [ 2, %A2 ], [ 3, %B1 ], [ 4, %B2 ]",
    "  ret i32 %r",
    "}}\n"
]
CONTROL_MULTI_WAY_COMPLEX = "\n".join(_CONTROL_MULTI_WAY_COMPLEX)

_CONTROL_BRANCH_FANOUT = [
    "define i32 @main() {{",
    "entry:",
    "  %v = add i32 {id}, {c}",
    "  %sel = urem i32 %v, 6",
    "  switch i32 %sel, label %default [",
    "    i32 0, label %case0",
    "    i32 1, label %case1",
    "    i32 2, label %case2",
    "    i32 3, label %case3",
    "    i32 4, label %case4",
    "    i32 5, label %case5",
    "  ]",
    "",
    "case0:",
    "  %r0 = add i32 %v, 11",
    "  br label %merge",
    "case1:",
    "  %r1 = sub i32 %v, 7",
    "  br label %merge",
    "case2:",
    "  %cond2 = icmp sgt i32 %v, 42",
    "  br i1 %cond2, label %case2a, label %case2b",
    "case2a:",
    "  %r2a = mul i32 %v, 2",
    "  br label %merge",
    "case2b:",
    "  %r2b = add i32 %v, 3",
    "  br label %merge",
    "case3:",
    "  %r3 = xor i32 %v, 31",
    "  br label %merge",
    "case4:",
    "  %r4 = mul i32 %v, %v",
    "  br label %merge",
    "case5:",
    "  %r5 = add i32 %v, 1",
    "  br label %merge",
    "default:",
    "  %rd = sub i32 %v, 1",
    "  br label %merge",
    "",
    "merge:",
    "  %r = phi i32 [ %r0, %case0 ], [ %r1, %case1 ], [ %r2a, %case2a ], [ %r2b, %case2b ], [ %r3, %case3 ], [ %r4, %case4 ], [ %r5, %case5 ], [ %rd, %default ]",
    "  ret i32 %r",
    "}}\n"
]
CONTROL_BRANCH_FANOUT = "\n".join(_CONTROL_BRANCH_FANOUT)

# ============= OPTIMIZATION-FOCUSED TEMPLATES (NEW) =============

# Inline candidates: simple call chain of tiny functions
# Tests: inlining heuristics (calls kept small and side-effect free)
_OPT_CALL_CHAIN_INLINE_CAND = [
    "define i32 @main() {{",
    "entry:",
    "  %v = add i32 {id}, {c}",
    "  %a = call i32 @fn1(i32 %v)",
    "  %b = call i32 @fn2(i32 %a)",
    "  ret i32 %b",
    "}}\n",
    "define i32 @fn1(i32 %x) {{",
    "entry:",
    "  %r = add i32 %x, 1",
    "  ret i32 %r",
    "}}\n",
    "define i32 @fn2(i32 %y) {{",
    "entry:",
    "  %r2 = mul i32 %y, 2",
    "  ret i32 %r2",
    "}}\n"
]
OPT_CALL_CHAIN_INLINE_CAND = "\n".join(_OPT_CALL_CHAIN_INLINE_CAND)

# Array alloca + GEP pattern (contiguous) for mem2reg
# Tests: mem2reg, alias analysis, and stack promotion
_OPT_ARRAY_ALLOCA_GEP = [
    "define i32 @main() {{",
    "entry:",
    "  %arr = alloca i32, i32 8",
    "  %i = alloca i32, i32 1",
    "  store i32 0, ptr %i",
    "  br label %loop",
    "",
    "loop:",
    "  %iv = load i32, ptr %i",
    "  %ptr = getelementptr i32, ptr %arr, i32 %iv",
    "  %old = load i32, ptr %ptr",
    "  %new = add i32 %old, 1",
    "  store i32 %new, ptr %ptr",
    "  %nv = add i32 %iv, 1",
    "  store i32 %nv, ptr %i",
    "  %cond = icmp slt i32 %nv, 8",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  %p0 = getelementptr i32, ptr %arr, i32 0",
    "  %r0 = load i32, ptr %p0",
    "  ret i32 %r0",
    "}}\n"
]
OPT_ARRAY_ALLOCA_GEP = "\n".join(_OPT_ARRAY_ALLOCA_GEP)

# Vector-like repeated arithmetic (SIMD candidate)
# Tests: vectorization and reduction handling
_OPT_VECTOR_SIMD_PATTERN = [
    "define i32 @main() {{",
    "entry:",
    "  %seed = add i32 {id}, {c}",
    "  br label %loop",
    "",
    "loop:",
    "  %i = phi i32 [ 0, %entry ], [ %ni, %loop ]",
    "  %acc = phi i32 [ %seed, %entry ], [ %acc_next, %loop ]",
    "  %v1 = mul i32 %i, 2",
    "  %v2 = add i32 %v1, 3",
    "  %acc_next = add i32 %acc, %v2",
    "  %ni = add i32 %i, 1",
    "  %cond = icmp slt i32 %ni, 32",
    "  br i1 %cond, label %loop, label %exit",
    "",
    "exit:",
    "  ret i32 %acc",
    "}}\n"
]
OPT_VECTOR_SIMD_PATTERN = "\n".join(_OPT_VECTOR_SIMD_PATTERN)

# Bitwise sequences that can be strength-reduced to shifts/masks
# Tests: strength reduction and combining bitwise ops
_OPT_BITWISE_STRENGTH_REDUCTION = [
    "define i32 @main() {{",
    "entry:",
    "  %v = add i32 {id}, {c}",
    "  %m1 = mul i32 %v, 8",
    "  %s1 = shl i32 %v, 3",
    "  %x = xor i32 %m1, %s1",
    "  ret i32 %x",
    "}}\n"
]
OPT_BITWISE_STRENGTH_REDUCTION = "\n".join(_OPT_BITWISE_STRENGTH_REDUCTION)

# Extra associativity/commutativity cases
# Tests: algebraic reassociation and constant folding
_OPT_ASSOC_COMMUT_EXTRA = [
    "define i32 @main() {{",
    "entry:",
    "  %a = add i32 {id}, {c}",
    "  %x = add i32 %a, 2",
    "  %y = add i32 3, %x",
    "  %z = mul i32 %y, 4",
    "  %w = mul i32 2, %z",
    "  ret i32 %w",
    "}}\n"
]
OPT_ASSOC_COMMUT_EXTRA = "\n".join(_OPT_ASSOC_COMMUT_EXTRA)

# ============= EXPORT TEMPLATES LIST =============

# Curated workload mix used by the generator and UI.
# The order is intentional: it balances arithmetic, control-flow, memory,
# and loop-heavy cases so comparisons feel consistent and professional.
TEMPLATE_LIBRARY = [
    {"name": "constant_fold_chain", "category": "Arithmetic simplification", "template": CONST_FOLD_HUGE_1},
    {"name": "dead_code_elimination", "category": "Dead code removal", "template": DEAD_CODE_MASSIVE},
    {"name": "redundant_chain", "category": "Common subexpression elimination", "template": REDUNDANT_CHAIN},
    {"name": "loop_collapsible", "category": "Loop unrolling", "template": LOOP_COLLAPSIBLE},
    {"name": "loop_invariant", "category": "Loop invariant code motion", "template": LOOP_WITH_INVARIANT},
    {"name": "small_loop", "category": "Loop simplification", "template": SIMPLE_LOOP},
    {"name": "call_chain_inline", "category": "Inlining", "template": SMALL_CALL_CHAIN},
    {"name": "simple_branch", "category": "Branch folding", "template": SIMPLE_BRANCH},
    {"name": "simple_math", "category": "Constant folding", "template": SIMPLE_MATH},
    {"name": "call_chain_inline_candidate", "category": "Inlining", "template": OPT_CALL_CHAIN_INLINE_CAND},
    {"name": "array_promote", "category": "Mem2reg / SROA", "template": OPT_ARRAY_ALLOCA_GEP},
    {"name": "vector_pattern", "category": "Loop vectorization", "template": OPT_VECTOR_SIMD_PATTERN},
    {"name": "bitwise_strength", "category": "Strength reduction", "template": OPT_BITWISE_STRENGTH_REDUCTION},
    {"name": "assoc_commut_extra", "category": "Reassociation", "template": OPT_ASSOC_COMMUT_EXTRA},
    {"name": "switch_lowering", "category": "Control flow simplification", "template": CONTROL_SWITCH},
    {"name": "branch_fanout", "category": "Control flow fan-out", "template": CONTROL_BRANCH_FANOUT},
    {"name": "tail_recursion", "category": "Tail-recursion lowering", "template": CONTROL_TAIL_RECURSION_SIM},
    {"name": "multi_way_branch", "category": "CFG merge", "template": CONTROL_MULTI_WAY_COMPLEX},
    {"name": "chained_comparisons", "category": "Branch folding", "template": CONTROL_CHAINED_COMPARISONS},
    {"name": "switch_lowering_2", "category": "Control flow simplification", "template": CONTROL_SWITCH},
    {"name": "branch_fanout_2", "category": "Control flow fan-out", "template": CONTROL_BRANCH_FANOUT},
    {"name": "multi_way_branch_2", "category": "CFG merge", "template": CONTROL_MULTI_WAY_COMPLEX},
]

TEMPLATES: List[str] = [item["template"] for item in TEMPLATE_LIBRARY]



