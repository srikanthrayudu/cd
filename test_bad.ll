define i32 @main() {
entry:
  %v = call i32 asm sideeffect "nonsense_instruction", "=r"()
  ret i32 %v
}
