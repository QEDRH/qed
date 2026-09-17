# QED launch record

Deploy-by-proof launches on Robinhood Chain (chain id 4663). A launch is gated on
`Qed/Rules.lean`: all six theorems (`QED.no_mint`, `QED.conservation`,
`QED.supply_le_initial`, `QED.burn_exact`, `QED.fee_is_one_percent`, `QED.fee_le_amount`)
must build with no `sorry` and standard axioms only before any transaction is sent.

## QED

Status: not launched yet. Proof complete, launch dry run passing.

| Field | Value |
|---|---|
| Proof file | `Qed/Rules.lean` |
| Proof SHA-256 | `4fd236b31383b98fadf409e5d664882f8b25d2e932691a7cfb50332e7fc0f55c` |
| Aristotle run | task `b9d26195-3ea1-4efd-98dd-eb8e0a46a67e`, project `224d6c1c-d5c7-4fe3-9ec3-ebfe222029b5`: filled in all six proofs, no theorem statement changed |
| Proof check | `lake build` passes, zero `sorry`, axioms used: `propext`, `Classical.choice`, `Quot.sound` |
| Token | QED / QED, 1,000,000,000 supply |
| Venue | Pons V2 `PonsV2LaunchFactory` `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e`, launchConfigId 0, paired with native ETH, creator tax 100 bps |
| Dry run (2026-09-17 UTC) | anchor and launch both simulated successfully, nothing broadcast |

When QED launches, `deploy.py` appends the real entry (anchor tx, launch tx, token and
bonding curve addresses) as a new section at the bottom of this file.

## Rehearsals

Everything in this section is a rehearsal. These were throwaway test tokens launched to
exercise the pipeline end to end: the proof gate, the anchor transaction and the launch
call. None of them is QED. They were gated on an earlier rehearsal rules file, which
`Qed/Rules.lean` has since replaced. The first two used other launch routes that were
tried before settling on Pons V2.

### Rehearsal: 2026-09-14 — TEST via Airlock.create (direct)

| Field | Value |
|---|---|
| Proof file | the rehearsal rules file (since replaced by `Qed/Rules.lean`) |
| Proof SHA-256 | `77f733e0ae4731d100ab2815af200f290fc66a266a707bf5c8e365b364baf2cf` |
| Aristotle run | project `cc840c38-fef3-47f2-943f-3d5ea124127d`, re-verified before launch |
| Chain | Robinhood Chain (4663) |
| Sender | `0xD9488E6d6f77485eF60C5Fdf0B05e494f7916D4F` |
| Anchor tx (0 ETH self-transfer, calldata = proof SHA-256) | `0x7edf524ce0c9622a39f782958300766c05b558b1787243fb13adec07fc6b7393` (block 62964658) |
| Launch tx (`Airlock.create`) | `0x3ee669da32dfd3f419f8d73dcc1145cd3502435813c286806fec3d5a305f091f` (block 62964931) |
| Token | `0x4CA2C2DC7Bec8A88b52519b8b092508356114c26` — test / TEST, 1,000,000,000 supply |
| Pool | `0x6Ac7246DbfD87233D55160e71e91c5083bE74B2B` (Uniswap V3, LockableUniswapV3Initializer) |
| Numeraire | SPCX `0x4a0E65A3EcceC6dBe60AE065F2e7bb85Fae35eEa` |
| Airlock | `0xeb7c034704ef8dcd2d32324c1545f62fb4ad0862` |
| Explorer | https://robinhoodchain.blockscout.com/tx/3ee669da32dfd3f419f8d73dcc1145cd3502435813c286806fec3d5a305f091f |

### Rehearsal: 2026-09-14 18:07 UTC — TESTII via launchpad factory `0x1Eef016F22A943abC7DD11422EDeE9D235942104`

| Field | Value |
|---|---|
| Proof SHA-256 | `77f733e0ae4731d100ab2815af200f290fc66a266a707bf5c8e365b364baf2cf` |
| Sender | `0xD9488E6d6f77485eF60C5Fdf0B05e494f7916D4F` |
| Anchor tx | `a524634ec0f99cf1b271bbd4dcdd6e17acefd6d83995a185351ed48c02bb51cf` |
| Launch tx | `a0ba80fa706e06fa9c8eb0aaf78e5ace7a8c0b89cb36f71d384e582b42f29f97` |
| Token | `0x666ed8c77f43ec1536308ce2bc1fa2e777431e18` — test2 / TESTII |
| Pool / hook | `0x666ed8c77f43ec1536308ce2bc1fa2e777431e18` |
| tokenURI | `ipfs://bafkreiaqfqfj7uk2vj5no4p43vvf6okshkeogkndzaeha6xmnn6nn53mmu` |
| Launcher | `0x1Eef016F22A943abC7DD11422EDeE9D235942104` |
| Explorer | https://robinhoodchain.blockscout.com/tx/a0ba80fa706e06fa9c8eb0aaf78e5ace7a8c0b89cb36f71d384e582b42f29f97 |

### Rehearsal: 2026-09-15 10:18 UTC — TEST3 via Pons V2 PonsV2LaunchFactory (paired with ETH)

| Field | Value |
|---|---|
| Proof SHA-256 | `77f733e0ae4731d100ab2815af200f290fc66a266a707bf5c8e365b364baf2cf` |
| Sender | `0xD9488E6d6f77485eF60C5Fdf0B05e494f7916D4F` |
| Anchor tx | `5422db7d0b4696ea30cf610aecbc6da568202c3a5bbcb9a5718bf975834d6a73` |
| Launch tx | `ddc439c34efa192680878a0cb3fdda0b15c86932ee4d39743af0c142227f359a` |
| Token | `0x59A74F6da82043514Df221743a8C70D2d8565feB` — test3 / TEST3 |
| Bonding curve | `0xaACf3604Efd568AcE145722f38dbfc8610383b7B` |
| Logo | `ipfs://bafybeihwqbyausolhwzaerucno265k4qmwyss4zxq7oc2wg5bf4bkwfozy` (on-chain `logo()`), twitter link omitted |
| Launch fee | 0.0005 ETH, expectedEconomics `a9fc75d4203a33fe660e8fa32c74c3aa41c1fda4bf23d3a39b6bc22a1f8b1ca7`, salt `1445e339f32003783a9c635c30ac1bdf57634e3de7978bc9b3116910f5c75e93` |
| Factory | `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` (launchConfigId 0, pairToken `0x0000000000000000000000000000000000000000`) |
| Explorer | https://robinhoodchain.blockscout.com/tx/ddc439c34efa192680878a0cb3fdda0b15c86932ee4d39743af0c142227f359a |

### Rehearsal: 2026-09-15 11:26 UTC — TEST4 via Pons V2 PonsV2LaunchFactory (paired with ETH)

| Field | Value |
|---|---|
| Proof SHA-256 | `77f733e0ae4731d100ab2815af200f290fc66a266a707bf5c8e365b364baf2cf` |
| Sender | `0xD9488E6d6f77485eF60C5Fdf0B05e494f7916D4F` |
| Anchor tx (0 ETH self-transfer, calldata = full text of the rehearsal rules file) | `eaec1ed893c4eb9b4a4384c1bc65117f61129429043227584182fa59ddd179aa` |
| Launch tx | `7a3dfce19a6a590d9a8b7180039fa3d413f77c82d484dad542f3fb8b1c63f2b7` |
| Token | `0xfF70cc58b9E0F87D5EB3199225EFA2b65f4B67D4` — test4 / TEST4 |
| Description (on-chain) | deploy-by-proof. Proof SHA-256: 77f733e0ae4731d100ab2815af200f290fc66a266a707bf5c8e365b364baf2cf. Full proof on-chain in tx 0xeaec1ed893c4eb9b4a4384c1bc65117f61129429043227584182fa59ddd179aa. No proof, no launch. |
| Bonding curve | `0x73832b74fAFcC9b33B7e7935E8C383bDBe6f2507` |
| Logo | `ipfs://bafybeihwqbyausolhwzaerucno265k4qmwyss4zxq7oc2wg5bf4bkwfozy` (on-chain `logo()`), twitter link omitted |
| Launch fee | 0.0005 ETH, expectedEconomics `a9fc75d4203a33fe660e8fa32c74c3aa41c1fda4bf23d3a39b6bc22a1f8b1ca7`, salt `3a89ca9ed74bfcb5230897aa3620ac06b71638420349fa8db2d40ee6bdecd71b` |
| Factory | `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` (launchConfigId 0, pairToken `0x0000000000000000000000000000000000000000`) |
| Explorer | https://robinhoodchain.blockscout.com/tx/7a3dfce19a6a590d9a8b7180039fa3d413f77c82d484dad542f3fb8b1c63f2b7 |

### Rehearsal: 2026-09-15 13:57 UTC — TEST5 via Pons V2 PonsV2LaunchFactory (paired with ETH)

| Field | Value |
|---|---|
| Proof SHA-256 | `f96f4d7f5efd34889b1133362ef5c9a1771699e3636b7b3f46c63f0ae8dceadc` |
| Sender | `0xD9488E6d6f77485eF60C5Fdf0B05e494f7916D4F` |
| Anchor tx (0 ETH self-transfer, calldata = full text of the rehearsal rules file) | `b19350df446729a19930b207a698c56699c951e76295e18c7d449c8d6dbdd6a0` |
| Launch tx | `0602af2ef8de66cb094de40f13355e356f804baa4445e5745ade1e2ac84e4f9b` |
| Token | `0x7a1Ffc526A32795C86CA3e67A87C5023484e5C6B` — test5 / TEST5 |
| Description (on-chain) | deploy-by-proof. Proof SHA-256: f96f4d7f5efd34889b1133362ef5c9a1771699e3636b7b3f46c63f0ae8dceadc. Full proof on-chain in tx 0xb19350df446729a19930b207a698c56699c951e76295e18c7d449c8d6dbdd6a0. No proof, no launch. |
| Bonding curve | `0x984E7464C2530F5BFC1a4b03Ed60206BFA8474f7` |
| Logo | `ipfs://bafybeihwqbyausolhwzaerucno265k4qmwyss4zxq7oc2wg5bf4bkwfozy` (on-chain `logo()`), twitter link omitted |
| Launch fee | 0.0005 ETH, expectedEconomics `a9fc75d4203a33fe660e8fa32c74c3aa41c1fda4bf23d3a39b6bc22a1f8b1ca7`, salt `af736eab9a54bcd5e8f9c088246b3c08e2a5c8e97f594c2dc10a739e4c6ab733` |
| Factory | `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` (launchConfigId 0, pairToken `0x0000000000000000000000000000000000000000`) |
| Explorer | https://robinhoodchain.blockscout.com/tx/0602af2ef8de66cb094de40f13355e356f804baa4445e5745ade1e2ac84e4f9b |

### Rehearsal: 2026-09-17 16:06 UTC — TEST via Pons V2 PonsV2LaunchFactory (paired with ETH)

| Field | Value |
|---|---|
| Proof SHA-256 | `0570ce4eb2d81fa00b6e6e168e76af405f31ee07f411386ad787e04dcde9657d` |
| Sender | `0x0DbFA817F7f5E0ce0387051260790f0faE385743` |
| Anchor tx (0 ETH self-transfer, calldata = full text of the rehearsal rules file) | `a151380f26b0a03d900f594ce475f00595f0d8660a2867af3f82354d1b7206ce` |
| Launch tx | `5950934ce2344b3a594ef337940576948ae9a1aec6abaf2afc2f89c3e3cf99f8` |
| Token | `0x0db9B7653777b6dA7e8E80A7ECC1BC7EE9340ED6` — Test / TEST |
| Description (on-chain) | deploy-by-proof. Proof SHA-256: 0570ce4eb2d81fa00b6e6e168e76af405f31ee07f411386ad787e04dcde9657d. Full proof on-chain in tx 0xa151380f26b0a03d900f594ce475f00595f0d8660a2867af3f82354d1b7206ce. No proof, no launch. |
| Bonding curve | `0xe9b478E5b647B85502F75B723d13E9E275388fD7` |
| Logo | `ipfs://bafkreibwmzmv74tczvl4gxzvpxlk554ftqxg5iumyn2vj64of3sscgidqa` (on-chain `logo()`), twitter link omitted |
| Launch fee | 0.0005 ETH, expectedEconomics `a9fc75d4203a33fe660e8fa32c74c3aa41c1fda4bf23d3a39b6bc22a1f8b1ca7`, salt `e400b4a6d116516ca69820c47eaea91190b0630040f22e9b4a49a01e41ef1b88` |
| Factory | `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` (launchConfigId 0, pairToken `0x0000000000000000000000000000000000000000`) |
| Explorer | https://robinhoodchain.blockscout.com/tx/5950934ce2344b3a594ef337940576948ae9a1aec6abaf2afc2f89c3e3cf99f8 |

### Rehearsal: 2026-09-17 17:58 UTC — TEST2 via Pons V2 PonsV2LaunchFactory (paired with ETH)

| Field | Value |
|---|---|
| Proof SHA-256 | `0570ce4eb2d81fa00b6e6e168e76af405f31ee07f411386ad787e04dcde9657d` |
| Sender | `0x0DbFA817F7f5E0ce0387051260790f0faE385743` |
| Anchor tx (0 ETH self-transfer, calldata = full text of the rehearsal rules file) | `332019eac70776d7896e35bd22ec712784049a4bf53902a1ef6ca40eb64be43a` |
| Launch tx | `426ee38e71c89d34e68b0a0d64fa3424a85e46d653737a08376c07682c7d86dd` |
| Token | `0xe049a60bf3069AC62717AF193D54520D56f9E888` — Test2 / TEST2 |
| Description (on-chain) | deploy-by-proof. Proof SHA-256: 0570ce4eb2d81fa00b6e6e168e76af405f31ee07f411386ad787e04dcde9657d. Full proof on-chain in tx 0x332019eac70776d7896e35bd22ec712784049a4bf53902a1ef6ca40eb64be43a. No proof, no launch. |
| Bonding curve | `0xa04E6767E404886eCA92A819Ef8B0D5E308D62fb` |
| Logo | `ipfs://bafkreibwmzmv74tczvl4gxzvpxlk554ftqxg5iumyn2vj64of3sscgidqa` (on-chain `logo()`), twitter and website set to placeholder test values |
| Launch fee | 0.0005 ETH, expectedEconomics `a9fc75d4203a33fe660e8fa32c74c3aa41c1fda4bf23d3a39b6bc22a1f8b1ca7`, salt `41ef50e8caf55bcbc2469c316d4033bfa336fab8913648bc400bc223e705eafb` |
| Factory | `0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e` (launchConfigId 0, pairToken `0x0000000000000000000000000000000000000000`) |
| Explorer | https://robinhoodchain.blockscout.com/tx/426ee38e71c89d34e68b0a0d64fa3424a85e46d653737a08376c07682c7d86dd |
