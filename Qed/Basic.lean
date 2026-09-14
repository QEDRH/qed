import Mathlib

/-!
# Monotone decrease from a fixed starting value

We model a quantity evolving in discrete steps as a function `q : ℕ → ℤ`, where
`q n` is its value after `n` operations.  The quantity starts at `1000000000`,
and each operation either leaves it unchanged or decreases it by a positive
integer.  We prove that after any finite number of operations the quantity is at
most `1000000000`.
-/

namespace Qed

/-- The starting value of the quantity. -/
def initialValue : ℤ := 1000000000

/-- `IsValidRun q` says that `q : ℕ → ℤ` describes the evolution of the quantity:
it starts at `initialValue`, and each step either leaves the value unchanged or
decreases it by some positive integer. -/
def IsValidRun (q : ℕ → ℤ) : Prop :=
  q 0 = initialValue ∧
  ∀ n : ℕ, q (n + 1) = q n ∨ ∃ d : ℤ, 0 < d ∧ q (n + 1) = q n - d

/-- Each step of a valid run does not increase the quantity. -/
theorem step_le {q : ℕ → ℤ} (hq : IsValidRun q) (n : ℕ) : q (n + 1) ≤ q n := by
  rcases hq.2 n with h | ⟨d, hd, h⟩
  · exact le_of_eq h
  · omega

/-- After any finite sequence of operations the quantity is at most `1000000000`. -/
theorem le_initialValue {q : ℕ → ℤ} (hq : IsValidRun q) (n : ℕ) :
    q n ≤ initialValue := by
  induction n with
  | zero => exact le_of_eq hq.1
  | succ k ih => exact (step_le hq k).trans ih

end Qed
