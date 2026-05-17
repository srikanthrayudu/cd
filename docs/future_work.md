# Future Work

While the current system proves the baseline efficacy of LLM-generated LLVM IR evaluation, multiple extensions can improve defect detection rates and reliability:

1. **Multi-LLM Ensemble Generation**
   By querying disparate models (e.g., GPT-4, Llama 3, StarCoder) in parallel, the system can leverage their differing architectural biases to generate a more structurally diverse test suite.

2. **Formally Guided Validation (e.g., Alive2)**
   Instead of solely relying on the compiler runtime tools (`opt -verify`) and differential comparison, future extensions could pipe mutated tests through formal verification tools like `Alive2` to statically verify equivalence prior to, or corroborating, an execution discrepancy.

3. **Feedback-Driven Prompts**
   Incorporating execution coverage back into the LLM prompts could guide the model into creating IR cases that hit uncovered optimization paths, transforming the pipeline into a true guided-fuzzer.

4. **Wider Cross-Compiler Contexts**
   Expanding the execution engine to also compile via GCC or test against differing major iterations of LLVM (e.g., LLVM 14 vs. LLVM 18) to uncover broader portability or regression flaws.

