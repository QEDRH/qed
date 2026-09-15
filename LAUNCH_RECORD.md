# Launch record

Deploy-by-proof launches gated on `Qed/Basic.lean` (theorem `Qed.le_initialValue`).

## 2026-09-14 — TEST via Airlock.create (direct)

| Field | Value |
|---|---|
| Proof file | `Qed/Basic.lean` |
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

## 2026-09-14 18:07 UTC — TESTII via launchpad factory `0x1Eef016F22A943abC7DD11422EDeE9D235942104`

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

## 2026-09-15 10:18 UTC — TEST3 via Pons V2 PonsV2LaunchFactory (paired with ETH)

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
