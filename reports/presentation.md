# Presentation: Differential Compiler Testing via LLM-Generated LLVM IR

## Slide 1: Introduction
**Title:** LLM-Driven Compiler Testing for LLVM IR
**Main Points:**
- Compilers contain complex optimization passes that can inadvertently introduce bugs.
- Differential testing is a proven method to find these bugs without a manual test oracle.
- Challenge: Generating *valid* LLVM IR for fuzzing is difficult due to strict SSA and PHI constraints.

## Slide 2: The LLM Advantage
**Why Large Language Models?**
- Traditional fuzzers struggle with validity in low-level IR.
- LLMs can recognize structural patterns and generate semantically diverse code structures.
- By prompting models (few-shot), we can build comprehensive IR test cases quickly while covering more complex idioms like nested loops.

## Slide 3: System Architecture
**Modular Design:**
- *Data Module:* Seed LLVM IR Corpus & LLM Generator.
- *Mutation Engine:* Traditional structural edits (CFG changes, opcode swaps).
- *Validation Pipeline:* Syntactic/Type checks via `llvm-as` and `opt -verify`.
- *Execution / Testing:* Comparing `-O0` outputs vs `-O3` outputs for anomalies.

## Slide 4: Results & Metrics
**Key Findings:**
- Tracked Valid Synthesis % (Syntax/Type valid).
- Identified runtime compiler crashes (ICEs) and output mismatches.
- Discrepancy analysis enables systematic triaging of compiler pass regressions.

## Slide 5: Conclusion & Future Work
**Takeaways:**
- LLM generation merged with rigorous tool-based validation works efficiently for IR fuzzing.
- Future prospects: Multi-LLM ensembles, formally verified validations (Alive2), and expanded cross-compiler testing.

