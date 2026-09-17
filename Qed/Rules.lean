import Mathlib

/-!
# $QED — token rules

A model of the $QED token on Robinhood Chain. The only operations are
`transfer` and `burn`. There is no mint. Supply starts at one billion and
can only fall. Every transfer charges a fixed fee rate set at launch.

Every theorem below is a rule the coin promises. If Aristotle cannot prove
one, the coin does not launch.
-/

namespace QED

/-- Total supply at launch. -/
def initialSupply : ℕ := 1000000000

/-- Fee on every transfer, in basis points, fixed at launch. 100 = 1%. -/
def feeBps : ℕ := 100

/-- Fee charged on a transfer of `amount`. -/
def fee (amount : ℕ) : ℕ := amount * feeBps / 10000

/-- The state of the token: circulating supply, tokens burned, fees collected. -/
structure State where
  supply : ℕ
  burned : ℕ
  fees : ℕ

/-- The state at launch. -/
def genesis : State := ⟨initialSupply, 0, 0⟩

/-- The only two operations. A transfer leaves supply unchanged and collects
the fee. A burn removes `k` tokens from supply permanently. There is no
operation that increases supply. -/
inductive Step : State → State → Prop
  | transfer (s : State) (amount : ℕ) :
      Step s ⟨s.supply, s.burned, s.fees + fee amount⟩
  | burn (s : State) (k : ℕ) (h : k ≤ s.supply) :
      Step s ⟨s.supply - k, s.burned + k, s.fees⟩

/-- A state is reachable if some finite sequence of operations leads to it
from genesis. -/
def Reachable : State → Prop := Relation.ReflTransGen Step genesis

/-- Rule 1: no single operation ever increases supply. -/
theorem no_mint {s t : State} (h : Step s t) : t.supply ≤ s.supply := by
  cases h with
  | transfer amount => exact le_rfl
  | burn k hk => exact Nat.sub_le _ _

/-- Rule 2: supply plus burned tokens always equals one billion. Nothing is
created and nothing disappears unaccounted. -/
theorem conservation {s : State} (h : Reachable s) :
    s.supply + s.burned = initialSupply := by
  induction h with
  | refl => simp [genesis]
  | tail hprev hstep ih =>
      cases hstep with
      | transfer amount => simpa using ih
      | burn k hk => simp only; omega

/-- Rule 3: supply never exceeds one billion, after any sequence of
operations. -/
theorem supply_le_initial {s : State} (h : Reachable s) :
    s.supply ≤ initialSupply := by
  have hcons := conservation h
  omega

/-- Rule 4: a burn of `k` removes exactly `k` from supply. -/
theorem burn_exact (s : State) (k : ℕ) (h : k ≤ s.supply) :
    (⟨s.supply - k, s.burned + k, s.fees⟩ : State).supply + k = s.supply := by
  simp only
  omega

/-- Rule 5: the fee is exactly 1% of the amount, rounded down. -/
theorem fee_is_one_percent (amount : ℕ) : fee amount = amount / 100 := by
  rw [fee, feeBps, show (10000 : ℕ) = 100 * 100 from rfl,
    Nat.mul_div_mul_right _ _ (by norm_num)]

/-- Rule 6: the fee never exceeds the amount transferred. -/
theorem fee_le_amount (amount : ℕ) : fee amount ≤ amount := by
  rw [fee_is_one_percent]
  exact Nat.div_le_self _ _

end QED
