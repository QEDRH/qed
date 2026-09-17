# QED

$QED is a token on Robinhood Chain (chain id 4663) that launches by proof. Its rules are
written as theorems in Lean 4. [Aristotle](https://aristotle.harmonic.fun), Harmonic's
automated theorem prover, has to prove every one of them, and the Lean compiler has to
accept the result, before the launch script is allowed to send a single transaction.

No proof, no launch.

- Site: https://deploybyproof.com
- X: https://x.com/QEDRH
- Rules and proofs: [`Qed/Rules.lean`](Qed/Rules.lean)
- Launch pipeline: [`deploy.py`](deploy.py)
- Launch record, including rehearsals: [`LAUNCH_RECORD.md`](LAUNCH_RECORD.md)

## The rules

`Qed/Rules.lean` models the token: supply starts at one billion, the only operations are
`transfer` and `burn`, and there is no mint. Six theorems in namespace `QED` state what the
coin promises.

| # | Theorem | Rule |
|---|---|---|
| 1 | `QED.no_mint` | No single operation ever increases supply. |
| 2 | `QED.conservation` | Supply plus burned tokens always equals one billion. |
| 3 | `QED.supply_le_initial` | Supply never exceeds one billion, after any sequence of operations. |
| 4 | `QED.burn_exact` | A burn of `k` removes exactly `k` from supply. |
| 5 | `QED.fee_is_one_percent` | The fee is exactly 1% of the amount, rounded down. |
| 6 | `QED.fee_le_amount` | The fee never exceeds the amount transferred. |

The theorem statements were written by hand with `sorry` in place of each proof. Aristotle
filled in all six proofs without changing a definition or a statement. The file builds with
no `sorry`, and the proofs depend only on Lean's three standard axioms (`propext`,
`Classical.choice`, `Quot.sound`). Aristotle's own account of the run is in
[`ARISTOTLE_SUMMARY.md`](ARISTOTLE_SUMMARY.md).

These theorems are about the model in `Rules.lean`. They are a precise statement of the
rules, checked by machine. They are not a formal verification of the deployed contract
bytecode.

## Check it yourself

```
lake exe cache get   # optional, fetches prebuilt Mathlib
lake build           # must finish with no errors and no `sorry` warnings
```

To see which axioms a theorem depends on, put this in a scratch file in the project root
and run `lake env lean <file>`:

```lean
import Qed.Rules
#print axioms QED.conservation
```

To compare against the launch, hash the file and look it up in the launch record:

```
shasum -a 256 Qed/Rules.lean
```

The anchor transaction in the launch record carries the full text of `Qed/Rules.lean` as
calldata, so the rules that gated the launch can be read straight off the chain.

## The pipeline

`deploy.py` runs these steps in order and stops at the first failure, before anything is
sent:

1. **Prove.** Submit the project to Aristotle and wait for the verified `Qed/Rules.lean`.
2. **Check.** Run `lake build`. It must pass with no errors and no `sorry`. The file must
   still open namespace `QED` and still state all six theorems, and an axiom audit must
   show standard axioms only. Otherwise the script prints "no proof, no launch." and exits.
3. **Anchor.** Send a 0 ETH self-transfer whose calldata is the full UTF-8 text of
   `Qed/Rules.lean`, and wait for it to confirm.
4. **Launch.** Call `PonsV2LaunchFactory.launchToken` directly, the same way the
   ponsfamily.com create page does: upload the logo to IPFS, read the launch fee and
   launch config, build the calldata locally, decode it again to confirm it matches,
   simulate it, then broadcast.
5. **Record.** Append the proof hash, both transaction hashes and the token address to
   `LAUNCH_RECORD.md`.

`uv run deploy.py --dry-run` does all of the above except broadcasting.

Launch settings: name `QED`, ticker `QED`, native ETH pair, launch config 0 (one billion
supply, 1% curve fee, 4.2 ETH graduation), creator tax 100 bps paid to the launching
wallet, buyback off.

This public copy of `deploy.py` reads `PRIVATE_KEY` from the process environment only. It
never reads a key file and never writes or logs the key.

## Rehearsals

Before QED, the full pipeline was run end to end with throwaway test tokens (TEST, TESTII,
TEST3, TEST4, TEST5, TEST, TEST2) to exercise the proof gate, the anchor and the launch
call. Those tokens are not QED and have no connection to it beyond sharing this script.
They are listed as rehearsals in [`LAUNCH_RECORD.md`](LAUNCH_RECORD.md).
[`docs/index.html`](docs/index.html) is a browser-side verifier for one of them.

## Credit

The proofs in this project were written by [Aristotle](https://aristotle.harmonic.fun).

To cite Aristotle:
- Tag @Aristotle-Harmonic on GitHub PRs/issues
- Add as co-author to commits:
```
Co-authored-by: Aristotle (Harmonic) <aristotle-harmonic@harmonic.fun>
```
