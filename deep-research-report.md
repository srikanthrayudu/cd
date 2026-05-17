# Executive Summary  

This report outlines a comprehensive project plan for investigating whether large language models (LLMs) can generate or mutate **semantically valid** LLVM IR (Intermediate Representation) test cases for differential compiler testing. We propose a modular system that uses LLMs and mutation rules to create LLVM IR programs, validates them, and then applies differential testing by compiling/executing with different compiler settings. The system will gather a seed corpus of valid IR, generate new IR via LLM prompts, apply grammar-based and structure-aware mutations, and filter out invalid IR. Valid IR will be run through LLVM tools (`llvm-as`, `opt -verify`) and executed with `lli` or compiled by `clang` at various optimization levels (e.g. O0 vs O3). Outputs will be compared to detect miscompilations or crashes. 

A thorough literature survey is presented (LLM code-generation, LLVM IR, SSA and PHI constraints, compiler fuzzing and differential testing, Csmith, YARPGen, IR-specific fuzzers like IRFuzzer/FLUX, and Alive2 for semantic validation). The proposed architecture is designed in modules (see **Figure 1** below). We describe a **Technology Stack** using Python and LLVM 14+, and LLM APIs (OpenAI, HuggingFace, etc.), and outline a reproducible setup on Ubuntu. Concrete example prompts and code snippets illustrate how to call an LLM (e.g. via OpenAI API) to generate or mutate IR. Validation rules (SSA, types, PHI dominance, LLVM tool commands) and mutation operators (opcode replacement, constant changes, control-flow edits) are detailed. We present a **Differential Testing Workflow** (O0 vs O3, pass sequences, multiple LLVM versions) with shell/py scripts for automation.  

The plan includes *experiments* to measure validity rates, compare LLM-based generation vs traditional fuzzers, detect compiler crashes, and assess IR diversity. We define metrics (syntax-valid%, semantically-valid%, crash rate, mismatch rate, etc.) and propose statistical analysis. Visualization ideas (tables, bar charts, mermaid diagrams) are included. A timeline (Gantt chart) lists milestones (literature review, environment setup, implementation of modules, evaluation, report writing), and a final **Deliverables Checklist** enumerates code, reports, metrics, and presentation slides. All source claims are backed by citations to primary literature.  

**Figure 1.** Modular system architecture (mermaid diagram code below) for LLM-driven LLVM IR generation, validation, and differential testing: Seed corpus → (A) LLM Generator → Generated IR → (B) Mutation Engine → Mutated IR → Validation → Valid/Invalid IR → Execution → Differential Testing → Evaluation Dashboard.  

```mermaid
flowchart LR
    subgraph Data_Module
      A1[Seed LLVM IR\nCorpus (module A)]
      A1 -->|Feed| B1(LLM Generator (module B))
      B1 --> C1[Generated LLVM IR]
      C1 --> D1[Mutation Engine (module B)]
      D1 --> E1[Mutated LLVM IR]
    end
    subgraph Validation_Module
      E1 --> F1{Validation Pipeline\n(module C)}
      F1 -->|Valid| G1[Valid IR Set]
      F1 -->|Invalid| H1[Invalid IR (discard)]
    end
    subgraph Testing_Module
      G1 --> I1[Execution Engine\n(module D)]
      I1 --> J1[Differential Testing\n(module E)]
      J1 --> K1[Discrepancy Logs]
      K1 --> L1[Evaluation & Dashboard\n(module F)]
    end
```  

# 1. Background and Literature Survey  

## 1.1 LLVM IR and SSA Form  
LLVM Intermediate Representation (LLVM IR) is a language-neutral, three-address-code IR used by the LLVM compiler framework【40†L406-L414】【46†L231-L239】. It is **static single-assignment (SSA)**: each variable (value) is assigned exactly once and can be referenced multiple times【40†L406-L414】. This SSA property simplifies many analyses (e.g. dataflow) and means values flow along basic blocks with PHI nodes to reconcile values from different control paths【46†L268-L276】【40†L406-L414】. LLVM IR has a fixed instruction set and strong typing – the type of each operand must match between definition and use【46†L258-L266】【40†L406-L414】. The IR is structured as functions of basic blocks ending in terminator instructions (branches or returns), with PHI nodes at block entries to select incoming values. For example:  

```llvm
; Example: simple LLVM IR in SSA form
define i32 @add(i32 %a, i32 %b) {
entry:
  %sum = add i32 %a, %b
  ret i32 %sum
}
```  

PHI nodes (not shown here) allow values from multiple predecessor blocks, e.g.:  
```llvm
define i32 @max(i32 %x, i32 %y) {
entry:
  %cmp = icmp sgt i32 %x, %y
  br i1 %cmp, label %then, label %else

then:
  %res1 = add i32 %x, 0
  br label %merge

else:
  %res2 = add i32 %y, 0
  br label %merge

merge:
  %result = phi i32 [ %res1, %then ], [ %res2, %else ]
  ret i32 %result
}
```  

Here the PHI node in `merge` picks `%res1` or `%res2` based on the taken branch. Crucially, PHI operands must come from predecessor blocks, respecting dominance constraints【46†L268-L276】; this makes random rewriting of control flow non-trivial. In short, LLVM IR enforces SSA and strict type/PHI rules, making *semantically valid* generation challenging.  

LLVM IR is also platform- and language-agnostic (a middle-end IR), enabling frontends like Clang to emit IR for many languages, and backends (via `opt` and `llc`) to optimize and lower to machine code.  Typically, a front-end (e.g. Clang) emits unoptimized IR, and then various optimization *passes* run in `opt`, followed by a backend (llc) to generate assembly. This layered architecture (frontend → IR optimizer → backend) is widely described【46†L231-L239】【46†L247-L255】.  

## 1.2 Differential Compiler Testing  
Differential testing of compilers involves generating test programs and compiling them with multiple compilers or multiple settings of the same compiler to cross-compare outputs【19†L318-L326】【28†L11-L19】. Discrepancies (e.g. differing outputs or crashes) may indicate compiler bugs or undefined behavior. The seminal tool **Csmith** is a random C program generator that produces *UB-free* C code and uses differential testing (e.g. GCC vs Clang outputs) to find miscompilations【19†L318-L326】. Csmith and its derivatives have found hundreds of bugs in C compilers. Similarly, *equivalence modulo inputs (EMI)* or *Metamorphic testing* are related approaches where code is mutated while preserving semantics to expose bugs. In our context, we apply the same idea to LLVM IR: generate or mutate IR programs and compile/run with different optimization levels (e.g. O0 vs O3) or different LLVM versions, then compare results.  

The core advantage is that compilation and execution of valid inputs does not need a manually written “oracle” – differences between outputs can signal a bug. (For non-deterministic programs, multiple runs or sandboxed execution may be needed.) The user example of running `lli` or `clang` at O0 and O3 and diffing outputs captures this.  

## 1.3 Compiler Fuzzing and Related Work  

- **Csmith (UTah)**: An automated C/C++ program generator. It avoids undefined behavior and reports compiler crashes or miscompilations via differential testing【19†L318-L326】【28†L11-L19】. The original Csmith research (Yang et al., PLDI 2011) found many bugs. Csmith’s README notes: *“Csmith outputs C programs free of undefined behaviors... using differential testing as the test oracle”*【19†L318-L326】. This establishes the baseline approach of differential testing for compilers.  

- **YARPGen (Utah, Intel 2020)**: YARPGen (“Yet Another Random Program Generator”) targets C/C++ loop optimizations and data-parallel code. It generates *expressive* C/C++ code (including loops) while avoiding undefined behavior. It found **220+ compiler bugs** in GCC, LLVM, and Intel C++【28†L11-L19】.  Key ideas: *generation policies* to increase code diversity and trigger optimizations. For example, YARPGen’s novel policies increased the average number of optimizations applied by 20–40% compared to baselines【28†L17-L24】. YARPGen demonstrates that even after a fuzzer saturates, new generators find fresh bugs【28†L51-L58】. We draw on YARPGen’s approach to avoid UB and to compose complex IR.  

- **IRFuzzer (IR-focused LLVM fuzzer, 2024)**: An LLVM-specific fuzzer that mutates LLVM IR to test the backend (code generator). IRFuzzer highlights key challenges: *general-purpose fuzzers struggle with compiler input validity*【12†L99-L107】. For instance, AFL++ or libFuzzer on random bitstreams produce invalid IR, covering only parsers, not deep passes. IRFuzzer uses **validity-guided mutations** (FuzzMutate) to ensure generated IR is always syntactically correct, and *matcher table coverage* to better explore backend code paths. It generates structured control flow (loops, vector types, function defs) and instrumentation in LLVM to provide new feedback【12†L49-L58】【46†L149-L158】. IRFuzzer reported **74 new LLVM backend bugs** (49 fixed) through specialized mutations【46†L195-L202】【45†L84-L89】, showing the power of focused IR mutators. We borrow from IRFuzzer the idea of *guaranteed-valid* IR mutations and sophisticated CFG edits (like split-CFG to preserve dominators【45†L73-L81】).  

- **FLUX (LLVM IR Crossovers, 2023)**: FLUX combines pairs of existing LLVM IR tests (“crossovers”) to create new IR programs, feeding them into LLVM’s opt-fuzzer【24†L252-L260】. It uses LLVM’s own unit tests as a seed corpus and randomly splices IR fragments. FLUX found bugs by this crossover approach. We plan to similarly use an LLVM IR seed corpus (e.g. unit tests and real IR) and allow both LLM- and mutation-based generation.  

- **Grammar-aware Fuzzing**: Many modern approaches for language compilers use grammars (e.g. ANTLR, tree-sitter) to ensure syntactic validity【27†L98-L107】. By generating only syntactically valid inputs, fuzzers can reach semantic bugs. While LLVM IR is context-free (no grammar needed, since IR is already structured text), similar ideas apply: mutation/LLM prompts should respect IR syntax and typing. We will use LLVM’s `llvm-as` and `opt -verify` tools to catch syntax or type errors【40†L406-L414】.  

- **Alive2 (Formal Verification)**: Alive2 is a translation-validation tool for LLVM that uses SMT solving to check if an optimized IR is *semantically equivalent* (or a refinement) of the original【44†L41-L49】【8†L51-L59】. It helps understand undefined behavior: e.g. it showed that replacing a division-with-UB by a guarded version preserves semantics【8†L51-L59】. We cite Alive2 to emphasize the complexity of LLVM’s UB semantics and to suggest using such a tool (or its concepts) to **semantically filter** LLM-generated IR. For example, after generation we could optionally run Alive2 to check transformations, or use it in bug triage to confirm true miscompilations. At minimum, references like Lee et al. note that Alive2 catches real mis-optimizations by defining strict semantics【44†L41-L49】.  

- **LLMs for Code/IR Generation**: Recent work shows LLMs can learn compiler IR semantics. For instance, Barroso et al. fine-tuned a 14B-parameter model to translate GCC’s GIMPLE IR to LLVM IR, outperforming other models【6†L73-L82】【43†L1-L4】. They observe LLMs *“offer a data-driven alternative that can infer structural correspondences and learn semantics from diverse corpora”*【6†L164-L168】. Likewise, large LLMs (GPT-4, CodeLlama, StarCoder etc.) can often generate syntactically correct code given prompts【6†L73-L82】. We adapt these insights: rather than hand-coding IR mutations only, we will craft *prompts* to an LLM (e.g. GPT-4) to generate new IR functions or mutate existing IR. The LLM can leverage patterns from many examples to guess new valid IR structures (for instance, loop patterns, PHI usage, or idiomatic instruction sequences). This is a relatively unexplored area (applying LLMs to low-level IR fuzzing), motivating our research.  

**Key Observations:** LLVM IR has strict correctness rules (SSA, PHI, types)【40†L406-L414】【46†L268-L276】. Existing fuzzers (Csmith, YARPGen, IRFuzzer, FLUX) either target C or use naive IR mutations, but often face validity issues【12†L100-L108】【28†L11-L19】. Recent advances (grammar-aware fuzzers and LLMs) suggest new opportunities: LLMs can generate code patterns and grammars ensure syntactic validity. Thus, combining an LLM’s generative ability with LLVM’s verification tools could yield a rich test generation pipeline.  

# 2. Proposed System Architecture  

We propose a **modular architecture** with six main components (Figure 1) to implement the pipeline end-to-end. Each module can be developed and tested independently, then integrated via scripts/CI. The overall workflow is:

1. **Seed Corpus (Module A)**: Gather existing valid LLVM IR files. These seeds (from LLVM regression tests, `clang -emit-llvm` on open-source code, ComPile-like dataset, etc.) form the initial inputs for mutation and fine-tuning.  
2. **LLM Generator (Module B)**: Use an LLM to *generate new IR* or *mutate existing IR*. Includes: 
   - Prompt-based generation (few-shot example prompts to produce whole functions or modules in IR). 
   - Instruction-level or function-level mutation prompts (e.g. ask LLM to replace one instruction or insert a loop). 
   - Structure-aware prompts (e.g. ask for IR with a given control flow).  
   (We will define concrete prompt templates and possibly few-shot examples for each scenario.)  

3. **Mutation Engine (Module B)**: Traditional programmatic mutator for IR (like a custom fuzzer): 
   - Opcode replacement (e.g. replace `add` with `mul`).  
   - Constant mutations (change immediate values).  
   - Control-flow edits (insert/split basic blocks, add loops or branches).  
   - Basic-block insertion/deletion, SSA renaming (alpha-renaming variables).  
   - Use strategies from IRFuzzer (sCFG insertion to preserve dominator structures【45†L73-L81】).  
   This complements the LLM (which may suggest more “semantic” changes) by covering systematic syntactic edits.  

4. **Validation Pipeline (Module C)**: A filter that checks each generated/mutated IR file for correctness before testing. Checks include:  
   - **Syntax & Type Check**: Run `llvm-as` (LLVM assembler) and `opt -verify` on the IR. If these fail, the IR is syntax- or type-invalid.  
   - **SSA Verification**: Ensure SSA form is preserved (each variable defined once, PHI dominance satisfied). LLVM’s `opt -verify` typically catches invalid PHI or use-before-define errors.  
   - **Undefined Instruction Detection**: Catch instructions or patterns not allowed (e.g. illegal cast, mis-typed instruction).  
   - **Dead Code / UB Checks**: Optionally use Alive2 or a lightweight interpreter to catch obvious UB (like div0). But primarily rely on `opt -verify`.  
   Valid IR is written to a “valid_ir/” folder; invalid IR is logged and optionally stored for debugging.  

5. **Execution Engine (Module D)**: For each valid IR, run it in different ways:  
   - Interpret/execute with `lli`. Capture stdout, stderr, exit code, crash.  
   - Compile to native with `clang -O0` and `clang -O3` (and optionally other flags). Run the resulting executables similarly.  
   - Collect run outputs (stdout, exit code, time) for each setting.  
   - Optionally test other compilers/backends: e.g. run with an older LLVM version, or with GCC/ICC if IR can be consumed (Clang can compile LLVM IR by `clang file.ll -o`).  
   Logs from each run are saved (raw and parsed).  

6. **Differential Testing (Module E)**: Compare outputs from different runs:  
   - Compare O0 vs O3 results; mismatches or crashes indicate potential miscompilation or UB (further analysis needed).  
   - Compare across LLVM versions or compiler backends for portability bugs.  
   - Record any discrepancy (non-zero diff or different exit codes). Mark whether it was a compiler crash or mismatched output.  
   This module produces a **bug report** dataset (test case ID, conditions, outcome).  

7. **Evaluation Dashboard (Module F)**: Aggregate results and generate metrics/visuals:  
   - **Metrics**: Syntax-valid rate, type-valid rate, execution-success rate, crash rate, mismatch rate, code coverage proxies, generation time, mutation uniqueness.  
   - **Comparative Tables**: e.g. LLM-generated vs mutation-generated IR stats.  
   - **Charts**: Bar charts of valid% vs invalid%, pie charts of bug categories, etc. (tools: matplotlib or Plotly).  
   - **Visualizations**: Mermaid diagrams (architecture, timeline), code heatmaps (if instrumented), coverage graphs (if we integrate coverage collection).  
   The dashboard could be a Jupyter notebook or web report linking to logs and charts for exploration.  

```mermaid
gantt
    title Project Timeline (2025–2026)
    dateFormat  YYYY-MM-DD
    section Planning & Survey
      Literature Review          :done, survey, 2025-01-01, 45d
      Architecture Design        :done, arch, after survey, 15d
    section Setup & Data Prep
      Environment Setup          :done, setup, after arch, 2025-03-01, 10d
      Build Seed Corpus         :active, corpus, after setup, 2025-03-11, 30d
    section Core Implementation
      Validation Pipeline       :active, val, after setup, 2025-03-21, 30d
      LLM IR Generation         :crit, llmgen, after corpus, 2025-04-30, 45d
      Mutation Engine           :crit, mutate, after llmgen, 2025-06-15, 30d
      Differential Testing      :after mutate, 2025-07-15, 30d
      Evaluation & Metrics      :after Differential Testing, 2025-08-15, 30d
    section Reporting & Presentation
      Writing Reports          :2025-09-15, 2025-10-15
      Presentation Slides      :2025-10-16, 15d
```  

# 3. Implementation Plan  

This section details the concrete implementation: folder structure, tools/stack, and key scripts/code.

## 3.1 Folder Structure  
We will organize the project with a clear hierarchy, for example:  
```
project/
│
├── dataset/               # Module A: seed IR corpus
│   ├── llvm_unit_tests/   # original unit test .ll files
│   ├── external_ir/       # IR from compiling real programs
│   └── README.md
│
├── generated_ir/          # IR output from LLM (raw)
├── mutated_ir/            # IR after applying our mutation engine
├── valid_ir/              # IR files that passed validation
├── invalid_ir/            # IR files that failed validation (for inspection)
│
├── scripts/               # Utility scripts (e.g. gather seed, etc.)
│   ├── prepare_dataset.sh
│   ├── run_llm_generation.py
│   ├── mutate_ir.py
│   ├── validate_ir.sh
│   ├── run_differential.sh
│   └── ...
│
├── src/                   # Core modules (can be Python packages)
│   ├── llm_generator.py
│   ├── mutator.py
│   ├── validator.py
│   ├── executor.py
│   ├── diff_test.py
│   ├── metrics.py
│   └── ...
│
├── logs/                  # Raw logs from runs (stderr/stdout, diffs)
├── results/               # Aggregated results and metrics
├── evaluation/            # Generated charts and tables
├── dashboard/             # (Optional) web dashboard or notebook
├── docs/
│   ├── architecture.md
│   ├── setup_guide.md
│   └── ...
│
└── reports/               # Final reports and paper drafts
    ├── literature_review.md
    ├── project_report.md
    ├── ieee_paper.pdf
    └── presentation.pptx
```  
This structure separates raw data, code, logs, and reports. The `scripts/` directory contains runnable scripts (shell or Python) for batch operations (e.g. generating 100 IR with the LLM). The `src/` directory is for modular Python code. Outputs are organized so we can see how many IR were generated, how many valid, and what the testing found.

## 3.2 Tech Stack and Environment  

- **Programming Language:** Python 3.9+ for scripts and modules. We will use standard libraries (`subprocess`, `os`, `json`, etc.) and key packages: `llvmlite` (if needed), `matplotlib`, `pandas`, and LLM client libs (e.g. `openai`, `transformers`).  
- **LLVM Tools:** LLVM 14 or later. Required tools:  
  - `llvm-as`: assemble `.ll` to `.bc` (bitcode) for syntax/type checking.  
  - `llvm-dis`: optionally disassemble bitcode back to IR.  
  - `opt`: with `-verify` to check IR well-formedness and run passes.  
  - `lli`: to interpret and run IR directly.  
  - `clang`: to compile IR or C code (for seed generation). For differential, we use `clang -O0` and `clang -O3`.  
  These LLVM tools are installed via Ubuntu packages (e.g. `llvm`, `clang`, etc.).  
- **AI/LLM APIs:** The system should be agnostic to the model, but we will demonstrate with:  
  - OpenAI API (e.g. GPT-4 or GPT-3.5) for code generation.  
  - **Local models**: optionally integrate a local LLM (LLaMA-based via Ollama or HuggingFace) if GPU is available.  
  - If using HuggingFace, `transformers` and/or `text-generation-webui` can be used.  
- **Fuzzing Libraries:** We will rely on custom mutation code (in Python, modifying IR text). If needed, libraries like `antlr4` for parsing or `python-ir` could be used, but simple regex/AST edits might suffice.  
- **Visualization:** `matplotlib` or `plotly` for charts; Mermaid syntax embedded in markdown (like above) for architecture/timelines.  
- **CI/Automation:** We can use GitHub Actions (or simple `Makefile`/shell scripts) to automate running the pipeline on new data.  

**Setup (Ubuntu commands):** In `docs/setup_guide.md` we will instruct users to run something like:
```bash
sudo apt update
sudo apt install -y python3-pip llvm clang
pip3 install openai pandas matplotlib transformers
```
We note that an OpenAI key is required for using their API, but users could substitute with HuggingFace model by editing config. All such parameters (model choice, API key, timeouts, seeds count, etc.) are configurable. 

## 3.3 Seed Corpus (Module A)  

Collect a diverse set of valid LLVM IR files as seeds. Sources include:  
- **LLVM Regression Tests:** LLVM’s repository contains `.ll` tests (e.g. in `llvm/test/Transforms/` and others). We can clone LLVM and use `scripts/collect_unittest_functions.py` (from FLUX) to extract many small IR snippets【24†L272-L281】.  
- **Compiling Open-source C/C++:** Use `clang -S -emit-llvm` on various C/C++ projects (Csmith itself, SPEC benchmarks, etc.) at -O0 to produce unoptimized IR. This gives realistic IR covering many constructs (loops, structs, pointers).  
- **High-level languages:** Use LLVM frontends for Rust/Swift/etc. (if available) to also generate IR. (ComPile dataset suggests compiling many packages with Clang at -O0【40†L436-L444】.)  
- **Existing IR Fuzzers:** Tools like [IRFuzzer’s corpora](#) or [others] may have sample IR.  

We store all seeds in `dataset/llvm_unit_tests/` and `dataset/external_ir/`. A simple script can gather and dedupe them. For example, a shell script to copy all `.ll` from LLVM’s tests, and another to compile sample C files.  

## 3.4 LLM-based IR Generation (Module B)  

We develop two LLM workflows: **zero/few-shot generation** and **mutation prompting**.  

### 3.4.1 Few-Shot Generation  
We craft natural-language plus IR examples to prompt an LLM to emit new IR code. For example:  
```
Prompt:
"Generate a valid LLVM IR function that implements integer division by 2 (using arithmetic instructions, not bitshift). Follow SSA form. Example format:
define i32 @div2(i32 %x) {
entry:
  ; your code here
}
"
```
This instructs the LLM to write a complete function. We can include a few example pairs (C code / IR) in the prompt for context (few-shot). For instance:  

```text
### Example 1
; C code: int add1(int x) { return x + 1; }
; LLVM IR:
define i32 @add1(i32 %x) {
entry:
  %tmp = add i32 %x, 1
  ret i32 %tmp
}
### Example 2
; C code: int mul2(int x) { return x * 2; }
; LLVM IR:
define i32 @mul2(i32 %x) {
entry:
  %tmp = mul i32 %x, 2
  ret i32 %tmp
}
### Now generate:
; C code: int sub3(int x) { return x - 3; }
; LLVM IR:
```
In code, we would set `prompt` to that string and let the model complete. In Python, e.g.:  
```python
import openai
openai.api_key = "YOUR_KEY"
prompt = """### C code: int sub3(int x) { return x - 3; }
; LLVM IR:"""
res = openai.Completion.create(model="gpt-4", prompt=prompt, max_tokens=60)
print(res.choices[0].text)
```  
The LLM should output a small IR function. We log it to `generated_ir/`.  

We should write a Python wrapper (e.g. `llm_generator.py`) to handle rate limits, parallel requests, and postprocess outputs (trimming, adding header/footer). We also want the LLM to output IR (not explanations). If needed, instruct it explicitly (e.g. add “*Only output valid LLVM IR code, no extra text.*”).  

### 3.4.2 Mutation Prompting  
For mutating existing IR, we can feed the IR to the LLM and ask for specific edits. Example prompt:  

```text
; Original IR:
define i32 @square(i32 %a) {
entry:
  %tmp = mul i32 %a, %a
  ret i32 %tmp
}
; Task: Replace the multiplication with an addition, preserving SSA form.
; Mutated IR:
```
We send this to the LLM, and expect:
```
define i32 @square(i32 %a) {
entry:
  %tmp = add i32 %a, %a
  ret i32 %tmp
}
```
We can do more complex mutations: e.g. insert a branch and PHI, unroll loops, add dead code. The prompt can describe the transformation (or ask LLM to attempt a random one). For structure-aware prompts, we may specify loops: 
```
; Generate LLVM IR for a loop that adds numbers 1..N (assume N is an i32 parameter).
```
The LLM might generate a `while` loop with branch and PHI.  

**Example LLM Call (Python):**  
```python
prompt = """
; Original LLVM IR:
define i32 @double(i32 %a) {
entry:
  %tmp = add i32 %a, %a
  ret i32 %tmp
}
; Task: Mutate this IR by replacing the 'add' with 'mul' and keeping it valid.
; Mutated IR:
"""
res = openai.Completion.create(model="gpt-4", prompt=prompt, max_tokens=50)
mutated_ir = res.choices[0].text
print(mutated_ir)
```  
This should print a new IR function (with `mul`).  

We will implement these as functions in `llm_generator.py`. Care must be taken to validate that the LLM didn’t produce garbage (hence the next module).  

## 3.5 Mutation Engine (Module B, cont.)  
In addition to LLM-based changes, we write our own IR mutation scripts (`mutator.py`). For each valid IR file, we apply random transformations such as:  

- **Opcode Replacement:** For each arithmetic/logical instruction (add, sub, mul, etc.), randomly replace with a different one (e.g. `add`→`xor`).  
- **Constant Mutation:** Change integer literals (add/sub random constant). For pointer ops, change offsets.  
- **Control-Flow Edits:** Insert a new basic block or loop. For example, use the s_CFG method from IRFuzzer to insert a sub-CFG that preserves dominators【45†L73-L81】. For simplicity, we could split a block into two and insert a branch between them.  
- **Dead-Code Insertion:** Insert extra instructions whose results are unused (but type-correct), to increase complexity.  
- **PHI and SSA Renaming:** After edits, we might need to rename values to maintain SSA form or add PHI if we introduce new edges. We can rely on `opt -mem2reg` pass as a hack: after editing, run `opt -mem2reg` or another pass to rebuild SSA if needed (this may simplify but could also discard malicious edits). Another approach is to append new IR via `llvm-extract/llvm-merge` on functions and link.  

Each mutation script runs on one IR file and outputs a new IR file. We loop this to generate many candidates. We tag mutated files (e.g. naming). We log which operator was mutated (for stats).  

## 3.6 Validation Pipeline (Module C)  

For each generated or mutated IR file, we run a validation script `validate_ir.sh`:  
```bash
for file in generated_ir/*.ll mutated_ir/*.ll; do
  llvm-as "$file" -o tmp.bc 2> /dev/null || { echo "Syntax error in $file"; mv $file invalid_ir/; continue; }
  opt -verify tmp.bc -o tmp2.bc 2> /dev/null || { echo "Verify failed: $file"; mv $file invalid_ir/; continue; }
  llvm-dis tmp2.bc -o /dev/null
  mv "$file" valid_ir/
done
```
- `llvm-as` fails if the `.ll` has syntax/type errors.
- `opt -verify` fails if any IR invariants are broken (PHI errors, undef uses).
- If both succeed, we move the file to `valid_ir/`; otherwise to `invalid_ir/` for inspection.  
We count and report how many IRs remain valid. This is a key metric (valid% of generation). IRFuzzer noted that naive generation yields many invalid cases【12†L100-L108】, so our filter will keep the pipeline from crashing downstream tools.  

We may also run **Alive2’s `alive-tv`** (if we want semantic checking): give it pairs of IR (original vs mutated) to see if semantics changed. But as Alive2 needs formal specs of transformations, this is optional. At least, it highlights potential UB or logic changes. 

Validation rules summary (to implement):  
- **No Undefined Values:** Every `%x = ...` must have operands defined.  
- **PHI correctness:** PHI nodes only refer to predecessor blocks.  
- **Terminators:** Each block ends in exactly one `ret`, `br`, `switch`, etc.  
- **Type rules:** All operands match instruction type.  
- **Function signature consistency:** e.g. external functions must be declared.  

The LLVM tools already cover most. We’ll capture error messages in logs for analysis (e.g. `opt` prints exactly which rule failed).  

## 3.7 Execution Engine (Module D)  

For each `*.ll` in `valid_ir/`, we execute the following:  

- **Interpretation:** 
  ```bash
  lli "$file" > out/O0_${file%%.ll}.txt 2> out/O0_${file%%.ll}_err.txt
  ```
  We use `lli` as a quick way to run IR on CPU. (We could also run with llvm-interpret or create a minimal C harness.) Record stdout, stderr, exit code, and time. If `lli` crashes, that’s an ICE (internal compiler error on interpreter).  

- **Native Compilation:** 
  ```bash
  clang "$file" -O0 -o exec/O0_${file%%.ll} && exec/O0_${file%%.ll} > out/o0_${file%%.ll}.txt 2> out/o0_${file%%.ll}_err.txt
  clang "$file" -O3 -o exec/O3_${file%%.ll} && exec/O3_${file%%.ll} > out/o3_${file%%.ll}.txt 2> out/o3_${file%%.ll}_err.txt
  ```
  If `clang` fails (syntax of IR), we catch that (it shouldn’t if validation passed, but just in case). Then we run the executables. We apply a timeout (e.g. 5s) to avoid infinite loops. Any non-zero exit or crash is logged.  

- **Differential Checks:** We diff the outputs of O0 vs O3:
  ```bash
  diff -u out/o0_${file%%.ll}.txt out/o3_${file%%.ll}.txt > results/diff_${file%%.ll}.patch
  ```
  A non-empty diff means a mismatch. We record this as a potential bug. We also categorize: if one side crashed or signaled differently, it’s a crash mismatch.  
- **Logging:** All stdout/stderr and diff files are stored in `logs/`.  
- Optionally, run on multiple LLVM versions by using Docker or pre-built binaries (e.g. LLVM14 vs LLVM15). This can reveal version-specific bugs.  

Example shell script snippet (`run_differential.sh`):  
```bash
for file in valid_ir/*.ll; do
  base=$(basename "$file" .ll)
  # Interpret
  lli "$file" > "logs/${base}.lli.out" 2> "logs/${base}.lli.err"
  # Compile and run O0
  clang "$file" -O0 -o "tmpO0" && timeout 5 "./tmpO0" > "logs/${base}.o0.out" 2> "logs/${base}.o0.err"
  # Compile and run O3
  clang "$file" -O3 -o "tmpO3" && timeout 5 "./tmpO3" > "logs/${base}.o3.out" 2> "logs/${base}.o3.err"
  # Compare outputs
  diff -u "logs/${base}.o0.out" "logs/${base}.o3.out" > "logs/${base}.diff"
  # Record if any differences or crashes
  if [ -s "logs/${base}.diff" ] || [ -s "logs/${base}.o0.err" ] || [ -s "logs/${base}.o3.err" ]; then
      echo "$base: discrepancy or crash" >> results/differential_report.txt
  fi
done
```  
This captures ICEs, mismatches, and logs the test name.  

## 3.8 Evaluation & Automation (Module F)  

After running tests, we parse all log files (maybe with a Python script). We compute:  
- **Total IR generated** (LLM vs mutation counts).  
- **Syntax-valid count & %**.  
- **Number of IR executed (passed all steps)**.  
- **Crash Count:** how many `lli` or `clang` crashes.  
- **Mismatch Count:** how many O0 vs O3 mismatches.  
- **Unique bugs:** categorize (some diffs may be duplicate issues; we can hash diff outputs to count unique).  
- **Mutation Diversity:** e.g. histogram of change types (how often `add`→`mul` occurred, etc.).  
- **LLM Quality:** e.g. average IR length, construct coverage (loops vs no loops).  
- **Performance:** average generation time, execution time.  

These metrics are logged to a CSV or JSON, and visualized. For example:  
```python
import pandas as pd
df = pd.read_csv('results/differential_report.txt', sep=':', names=['Test','Outcome'])
print(df.groupby('Outcome').size())
```
We will produce bar charts: “IR Validity Rate”, “Crash Rate by Module”, “Mismatches by Source (LLM vs Random)”, etc. For structure, we might use a Pandas `DataFrame` and matplotlib to draw charts.  

Mermaid and markdown tables can summarize some results. For example:

| Generation Method | IRs Generated | Syntax-Valid (%) | Mismatch Found (%) |
|-------------------|--------------:|------------------:|-------------------:|
| LLM (GPT-4)       |           500 |              72%  |             3.2%   |
| LL(ama2) (HF)     |           500 |              65%  |             2.8%   |
| Fuzzer (grammar)  |           500 |              90%  |             5.6%   |

*(Table: Sample results, values simulated.)*

Charts: e.g. a bar chart of “% Valid IR” by method (LLM vs fuzzer). A timeline Gantt already above. Possibly a mermaid sequence diagram or flow chart for bug triage (but optional).  

# 4. Experiment Designs  

We plan a suite of experiments to evaluate the approach:  

- **Exp.1: Validity Rate of LLM-generated IR.**  
  *Goal:* Measure how many LLM-generated IR programs are syntactically and semantically valid.  
  *Method:* Generate N IR (e.g. N=1000) via LLM prompts (different models or prompt styles). Run the Validation Pipeline to count valid IR%. Baselines: compare with random IR mutations or grammar-based generation (if available).  
  *Metrics:* Syntax-valid%, type-valid% (from llvm-as/opt success).  
  *Expected Outcome:* LLM should do reasonably well (≥50% valid) if prompts are good; grammar-based may be higher.  

- **Exp.2: Comparison vs Traditional Fuzzing.**  
  *Goal:* Compare LLM-generated IR against IR from grammar-based or random mutation (e.g. FuzzMutate/IRFuzzer approach).  
  *Method:* Run both approaches on the same seed set:  
    - Grammar-based fuzzer (or AFL+ custom mutator) producing N IR.  
    - LLM generation producing N IR.  
  Compare validity, semantic complexity (#basic blocks, loops), novelty (unique instruction sequences).  
  *Metrics:* Validity rate, average IR size, structural features coverage. Possibly code coverage of opt/llc if instrumented.  
  *Baseline:* Fuzzer from IRFuzzer or FLUX.  

- **Exp.3: Compiler Crash Discovery.**  
  *Goal:* Measure how effective each approach is at finding compiler crashes (ICEs).  
  *Method:* Collect all cases where `lli` or `clang` crashed (non-zero exit or segmentation fault).  
  *Metrics:* #CRASHes per 1000 inputs. Possibly categorize by pass.  
  *Note:* Because differential testing catches crashes anyway, this is overlap with next experiment.  

- **Exp.4: Optimization Mismatch Detection.**  
  *Goal:* Find miscompilations (O0 vs O3 output mismatch) discovered by each method.  
  *Method:* For all IR, count mismatches. Verify mismatches by re-running or manually checking small cases.  
  *Metrics:* Mismatch rate, unique mismatch cases.  
  *Analysis:* Use Alive2 or manual reasoning to triage whether mismatch is a real bug or UB in code.  
  *Baseline:* Traditional IR fuzzing (e.g. IRFuzzer or grammar approach), and also compare within LLM itself (few-shot vs zero-shot).  

- **Exp.5: Semantic Diversity of Generated IR.**  
  *Goal:* Assess how diverse the IR programs are in semantics/structure.  
  *Method:* Use static analysis or a tool (e.g. Souper-like encoding) to cluster IR by structure, or measure path complexity (#branches). Optionally run `opt -unit-at-a-time` to see how many different optimizations apply.  
  *Metrics:*  
    - *Mutation Uniqueness:* fraction of IR that are non-duplicates (hashed by content).  
    - *Instruction Distribution:* frequency of each opcode in generated IR vs seed.  
    - *Coverage:* If we instrument opt with SanitizerCoverage (like FLUX did) we can estimate how many code branches of LLVM are exercised by LLM vs fuzzer.  
  *Outcome:* Expect LLM to generate some novel patterns (e.g. nested loops, weird PHI usage) that fuzzers might not.  

For each experiment, we document methodology (scripts used, data size), results (tables, charts), and analysis (discuss why LLM did better/worse). 

**Statistical Analysis:** If we compare two methods, we can run multiple trials (seeds, random seeds for LLM) and use t-tests or confidence intervals on rates (validity, crash, mismatch) to see significance. All raw data and code will be available to reproduce graphs. 

# 5. Scripts and Automation  

To ensure reproducibility, we will write scripts (Bash/Python) for batch tasks:  
- **Dataset preparation (`prepare_dataset.sh`):** Clone LLVM, compile sample code, collect IR into `dataset/`.  
- **Batch IR generation (`run_llm_generation.py`):** Calls the LLM in a loop to generate many IR, saves to `generated_ir/`.  
- **Batch mutation (`mutate_ir.py`):** Takes all seed or generated IR and applies random edits, outputting to `mutated_ir/`.  
- **Validation pipeline (`validate_ir.sh`):** Filters IR as above.  
- **Differential testing (`run_differential.sh`):** Compiles/runs valid IR and diffs outputs.  
- **Metric aggregation (`metrics.py`):** Parses logs and outputs CSV/plots.  

Each script will have command-line arguments (input directory, output directory, model choice, etc.) and log its progress. For example, `validate_ir.sh` might output `n_valid` and `n_invalid` at the end. We’ll use `logging` in Python modules to record actions and errors. 

We will also create a simple `Makefile` or `run_all.sh` that chains these steps (with optional stages), so a user can type `bash run_pipeline.sh` to execute the whole pipeline end-to-end.  

# 6. Example Code & Prompts  

Below are illustrative examples of prompts, IR code, and scripts. These are not full implementations but show the approach:

```python
# Example: Prompting an LLM (OpenAI API) to generate LLVM IR
import openai
openai.api_key = "YOUR_API_KEY"

prompt = """; C code: int fibonacci(int n) { if (n < 2) return n; return fibonacci(n-1) + fibonacci(n-2); }
; LLVM IR function for fibonacci in SSA form:
define i32 @fibonacci(i32 %n) {
entry:
  %cmp = icmp slt i32 %n, 2
  br i1 %cmp, label %ret, label %rec
ret:
  ret i32 %n
rec:
  %n1 = sub i32 %n, 1
  %call1 = call i32 @fibonacci(i32 %n1)
  %n2 = sub i32 %n, 2
  %call2 = call i32 @fibonacci(i32 %n2)
  %sum = add i32 %call1, %call2
  ret i32 %sum
}
; End
"""
response = openai.Completion.create(model="gpt-4", prompt=prompt, max_tokens=100)
print(response.choices[0].text)
```
```
; Example original LLVM IR for mutation
define i32 @double(i32 %a) {
entry:
  %tmp = add i32 %a, %a
  ret i32 %tmp
}

; Prompt the LLM to mutate it:
prompt = """
; Original IR:
define i32 @double(i32 %a) {
entry:
  %tmp = add i32 %a, %a
  ret i32 %tmp
}
; Task: Change the 'add' instruction to 'mul' to square the value instead.
; Mutated IR:
"""
res = openai.Completion.create(model="gpt-4", prompt=prompt, max_tokens=50)
print(res.choices[0].text)
```

```bash
# Example validation commands (Module C)
llvm-as test.ll -o test.bc          # assemble to bitcode
opt -verify test.bc -o /dev/null    # verify IR; output nothing if OK
```

```bash
# Example differential testing (Module D)
clang test.ll -O0 -o prog_O0 && ./prog_O0 > out_O0.txt
clang test.ll -O3 -o prog_O3 && ./prog_O3 > out_O3.txt
diff out_O0.txt out_O3.txt > diff.txt
```

```python
# Example Python snippet to compute metrics
import os, subprocess, pandas as pd

# Count valid vs invalid IR
total = len(os.listdir('generated_ir'))
valid = len(os.listdir('valid_ir'))
print(f"Generated {total} IR; {valid} valid ({100*valid/total:.1f}%).")

# Read mismatch log
df = pd.read_csv('results/differential_report.txt', sep=':', names=['test','status'])
print(df['status'].value_counts())
```

# 7. Timeline, Milestones, Deliverables  

A high-level timeline (shown above) segments tasks by weeks/months. Major milestones:  

- *Month 1*: Complete literature survey (this section), finalize modular design.  
- *Month 2*: Setup environment, gather seed corpus (C/C++ compile, LLVM tests).  
- *Month 3*: Implement validation pipeline and test on seed IR.  
- *Month 4*: Develop LLM prompt scripts and mutation engine; generate first IR samples.  
- *Month 5*: Integrate differential testing; run experiments (initial pilot).  
- *Month 6*: Collect metrics, analyze results; refine prompts/mutations.  
- *Month 7*: Finalize evaluation, prepare reports and presentation.  

Each module has an owner (developer). Weekly progress is tracked via a kanban board (optional). Risks: LLM may generate many invalid IR (mitigate by prompt engineering and filtering), and compute limits on model usage (we allow configurable model selection).  

# 8. Final Deliverables Checklist  

Upon completion, deliver the following items:

- **Source Code:** All scripts and modules (`.py`, `.sh`), with comments.  
- **Dataset:** Seed IR files and any generated IR (in `dataset/`, `generated_ir/` folders).  
- **Setup Guide:** A step-by-step installation and run manual (`docs/setup_guide.md`).  
- **Architecture Diagram:** Included above (and detailed in `docs/architecture.md`).  
- **Research Report:** Markdown report covering all sections (this document).  
- **IEEE Paper Draft:** Polished write-up of major findings (`reports/ieee_paper.pdf`).  
- **Presentation Slides:** Key slides summarizing project and results (`reports/presentation.pptx`).  
- **Experiment Logs:** Raw logs from runs (in `logs/`) and parsed results (`results/`).  
- **Evaluation Charts:** Plots and tables comparing approaches (`evaluation/`).  
- **Future Work:** Document potential extensions (e.g. multi-LLM ensemble, guided prompts, cross-language IR).  

Each deliverable will be version-controlled, with a final review by the advisor. All code will be made reproducible (seeded randomness, dockerfile or environment yaml if needed). We will note any assumptions (e.g. LLM compute budget, LLVM versions tested, randomness seeds).  

All sources of information used above are cited (see references). The implementation details will ensure both beginners and experts can follow: from simple examples (commented code, basic IR tips in `docs/`) to in-depth analysis in the report.

