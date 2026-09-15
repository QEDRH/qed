# /// script
# requires-python = ">=3.11"
# dependencies = ["web3>=7,<9", "requests>=2.31"]
# ///
"""
deploy-by-proof: launch a token on Pons V2 (ponsfamily.com, Robinhood Chain) ONLY
after the Lean proof in qed/Qed/Basic.lean is verified.

Pipeline
  1. aristotle submit ... --wait      (prove / re-verify the rules in Basic.lean)
  2. lake build in qed/               (must succeed with no errors, no sorry)
  3. 0-value self-tx with the proof's SHA-256 as calldata (anchor), wait for it
  4. Pons V2 launch, the way www.ponsfamily.com/launchpad/create does it:
       a. POST the logo (multipart field "image") to the site's IPFS worker
          -> {"uri": "ipfs://<cid>"}; the URI is stored on-chain in the token
       b. read launchFee / canLaunch / getLaunchConfig(0) /
          previewLaunchEconomics(0, ETH) from PonsV2LaunchFactory
       c. build PonsV2LaunchFactory.launchToken(TokenParams, 0, address(0), [])
          locally (no backend, no signed authorization; the site calls the
          factory straight from the wallet), value = launchFee
       d. simulate it (eth_call), then broadcast
  5. print anchor tx hash, launch tx hash + SHA-256 of the proof file

If the proof check fails at any point the script prints "no proof, no launch."
and exits non-zero WITHOUT sending any transaction.

Usage
  uv run deploy.py                   # full pipeline, sends anchor + launch
  uv run deploy.py --dry-run         # everything except broadcasting (eth_call only)
  uv run deploy.py --skip-aristotle  # reuse the proof already in qed/Qed/Basic.lean

Environment
  PRIVATE_KEY        required; the launching wallet's key, 0x-prefixed 32-byte hex.
                     This public copy reads it from the process environment only
                     and never writes or logs it. Use a dedicated burner wallet.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import zlib
from pathlib import Path

import requests
from eth_abi import decode as abi_decode
from web3 import Web3

# --------------------------------------------------------------------------- #
# Configuration                                                                #
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parent
QED_DIR = ROOT / "qed"
PROOF_FILE = QED_DIR / "Qed" / "Basic.lean"
LAUNCH_RECORD = QED_DIR / "LAUNCH_RECORD.md"

# Robinhood Chain (Arbitrum Orbit, gas token ETH)
CHAIN_ID = 4663
RPC_URL = os.environ.get("ROBINHOOD_RPC_URL", "https://rpc.mainnet.chain.robinhood.com")
EXPLORER_TX = "https://robinhoodchain.blockscout.com/tx/"

# Pons V2 launchpad (ponsfamily.com). The site's create page is a Next.js app
# that calls PonsV2LaunchFactory directly from the connected wallet via
# wagmi/viem: there is no backend and no signed authorization (unlike launchpads that sign launches in a backend).
# Addresses are hard-coded in the site's bundle (getPonsV2FactoryAddress) and
# match https://github.com/ponsdotdev/ponsfamily (contractsV2/, verified source).
PONS_FACTORY = "0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e"          # PonsV2LaunchFactory
PONS_LAUNCH_DEPLOYER = "0x3711ceA4feaDE896C913C68F01Eda97Cb06D1A42"  # PonsV2LaunchDeployer (factory.launchDeployer())
PONS_MEME_HOOK = "0xE5e702641Ea86F4ae6cC3cDaeD2B886f976Be044"        # PonsV2MemeHook (factory.memeHook())
PONS_LAUNCH_AND_BUY_ROUTER = "0xe33E9E479dF8802cb0866d5d05258bEc4cF62948"  # site uses it only for a dev buy; unused here
PONS_LAUNCH_CONFIG_ID = 0   # the site always passes 0: 1e9 supply, 1% curve fee, 4.2 ETH graduation
PAIR_TOKEN = "0x0000000000000000000000000000000000000000"  # address(0) = native ETH quote (site default)
CREATOR_TAX_BPS = 0         # site default (extra creator tax slider at 0); capped on-chain by maxCreatorTaxBps
BUYBACK_ENABLED = False     # the site always sends false
SNIPE_TAX_EXEMPTIONS: list[str] = []  # extra wallets; the sender is exempted on-chain automatically

# Logo upload, as the site does it: multipart POST with field "image" to this
# Cloudflare worker; it answers {"uri": "ipfs://<cid>"}. PNG/JPEG/WebP/GIF, < 5 MB.
PONS_IPFS_UPLOAD_URL = "https://pons-vercel-data-gateway.ozzy-6de.workers.dev/public/ipfs/image"
PONS_APP_ORIGIN = "https://www.ponsfamily.com"
PONS_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
PONS_IMAGE_MAX_BYTES = 5 * 1024 * 1024
IPFS_URI_RE = re.compile(r"^ipfs://[a-zA-Z0-9]+$")            # site: isValidIpfsUri

# Site-side form rules (ponsfamily.com bundle, module 422799). The contract's own
# caps are looser (name 64, symbol 16, logo 512, description 2048 bytes).
NAME_RE = re.compile(r"^[A-Za-z0-9]+(?: [A-Za-z0-9]+)*$")      # <= 32 chars
SYMBOL_RE = re.compile(r"^[A-Z0-9]+$")                         # <= 10 chars
X_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
DESCRIPTION_MAX = 256                                          # and no links

# Token to launch
TOKEN_NAME = "test3"
TOKEN_SYMBOL = "TEST3"
TOKEN_DESCRIPTION = "test3: a deploy-by-proof test token. Launch gated on a machine-checked Lean proof."
TOKEN_TWITTER = ""  # optional X handle or URL; stored on-chain as https://x.com/<handle> like the site does
TOKEN_IMAGE = ROOT / "logo.png"  # a placeholder is generated only if this file is missing
IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}

_SOCIALS = [{"name": n, "type": "string"} for n in ("twitter", "telegram", "discord", "website", "farcaster")]
TOKEN_PARAMS_COMPONENTS = [
    {"name": "name", "type": "string"}, {"name": "symbol", "type": "string"},
    {"name": "logo", "type": "string"}, {"name": "description", "type": "string"},
    {"name": "socials", "type": "tuple", "components": _SOCIALS},
    {"name": "creatorFeeRecipient", "type": "address"}, {"name": "creatorTaxBps", "type": "uint16"},
    {"name": "buybackEnabled", "type": "bool"}, {"name": "expectedEconomics", "type": "bytes32"},
    {"name": "salt", "type": "bytes32"},
]
LAUNCH_CONFIG_COMPONENTS = [
    {"name": "supply", "type": "uint256"}, {"name": "curveFeeBps", "type": "uint256"},
    {"name": "phantomQuote", "type": "uint256"}, {"name": "graduationThreshold", "type": "uint256"},
    {"name": "poolFee", "type": "uint24"}, {"name": "tickSpacing", "type": "int24"}, {"name": "enabled", "type": "bool"},
]
# Only the 4-arg launchToken overload is listed (the one the site encodes), so
# web3 never has to disambiguate overloads.
PONS_FACTORY_ABI = [
    {"type": "function", "name": "launchToken", "stateMutability": "payable",
     "inputs": [{"name": "params", "type": "tuple", "components": TOKEN_PARAMS_COMPONENTS},
                {"name": "launchConfigId", "type": "uint256"}, {"name": "pairToken", "type": "address"},
                {"name": "snipeTaxExemptions", "type": "address[]"}],
     "outputs": [{"name": "token", "type": "address"}, {"name": "curve", "type": "address"}]},
    {"type": "function", "name": "previewLaunchEconomics", "stateMutability": "view",
     "inputs": [{"name": "launchConfigId", "type": "uint256"}, {"name": "pairToken", "type": "address"}],
     "outputs": [{"type": "bytes32"}]},
    {"type": "function", "name": "getLaunchConfig", "stateMutability": "view",
     "inputs": [{"name": "id", "type": "uint256"}],
     "outputs": [{"type": "tuple", "components": LAUNCH_CONFIG_COMPONENTS}]},
    {"type": "function", "name": "canLaunch", "stateMutability": "view",
     "inputs": [{"name": "launcher", "type": "address"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "launchEnabled", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "launchFee", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "maxCreatorTaxBps", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "approvedPairTokens", "stateMutability": "view",
     "inputs": [{"name": "pairToken", "type": "address"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "launchDeployer", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"type": "function", "name": "memeHook", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]},
    {"type": "event", "name": "TokenLaunched", "anonymous": False,
     "inputs": [{"name": "token", "type": "address", "indexed": True}, {"name": "curve", "type": "address", "indexed": True},
                {"name": "deployer", "type": "address", "indexed": True}, {"name": "pairToken", "type": "address", "indexed": False},
                {"name": "launchConfigId", "type": "uint256", "indexed": False},
                {"name": "graduationThreshold", "type": "uint256", "indexed": False}]},
]
# Custom errors PonsV2LaunchFactory / PonsV2LaunchDeployer can revert with, for readable failures.
PONS_ERRORS = {Web3.keccak(text=sig)[:4].hex().removeprefix("0x"): sig for sig in (
    "LaunchFeeNotPaid()", "NotWhitelisted()", "InvalidTokenParams()", "MetadataTooLong()", "CreatorTaxTooHigh()",
    "LaunchConfigDisabled()", "InvalidLaunchConfigId()", "PairTokenNotApproved()", "CombinedFeeTooHigh()",
    "LaunchEconomicsMismatch(bytes32,bytes32)", "LaunchDeployerNotSet()", "LaunchDependenciesNotWired()",
    "ExemptionListTooLong()", "GraduationSeedNotViable()", "FeeTransferFailed()", "ReentrancyGuardReentrantCall()",
)}

# Aristotle prompt: re-verify the rules already stated in Basic.lean
ARISTOTLE_PROMPT = (
    "Verify and, if necessary, complete the proofs of every theorem in "
    "Qed/Basic.lean. Do not change any definition or theorem statement. "
    "The file must build with no errors, no sorry, and no additional axioms."
)

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def die_no_proof(reason: str) -> None:
    print(f"[proof] FAILED: {reason}", file=sys.stderr)
    print("no proof, no launch.")
    sys.exit(1)


def log(msg: str) -> None:
    print(f"[deploy] {msg}", flush=True)


def load_private_key() -> str:
    """Signer key from the environment only. No key files are read or written."""
    key = os.environ.get("PRIVATE_KEY", "").strip()
    if not key:
        sys.exit("PRIVATE_KEY is not set in the environment")
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", key):
        sys.exit("PRIVATE_KEY is not a 0x-prefixed 32-byte hex string")
    return key


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_config() -> None:
    missing = [
        name
        for name, val in globals().items()
        if isinstance(val, str) and val == "__FILL_ME__"
    ]
    if missing:
        sys.exit(f"deploy.py config not filled in: {', '.join(missing)}")


# --------------------------------------------------------------------------- #
# Step 1: Aristotle                                                            #
# --------------------------------------------------------------------------- #


def run_aristotle() -> None:
    if shutil.which("aristotle") is None:
        die_no_proof("aristotle CLI not found on PATH")
    if not os.environ.get("ARISTOTLE_API_KEY"):
        die_no_proof("ARISTOTLE_API_KEY not set in environment")

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "result.tar.gz"
        cmd = [
            "aristotle", "submit", ARISTOTLE_PROMPT,
            "--project-dir", str(QED_DIR),
            "--wait",
            "--destination", str(archive),
        ]
        log("running: " + " ".join(cmd[:3]) + " ...")
        proc = subprocess.run(cmd, text=True, capture_output=True)
        tail = (proc.stdout + proc.stderr)[-2000:]
        if proc.returncode != 0:
            die_no_proof(f"aristotle exited {proc.returncode}\n{tail}")
        if not archive.exists():
            die_no_proof("aristotle finished but produced no result archive")

        with tarfile.open(archive) as tf:
            members = [m for m in tf.getmembers() if m.name.endswith("Qed/Basic.lean")]
            if not members:
                die_no_proof("result archive has no Qed/Basic.lean")
            tf.extractall(tmp, members=members, filter="data")
            extracted = Path(tmp) / members[0].name

        shutil.copyfile(extracted, PROOF_FILE)
        log(f"aristotle result written to {PROOF_FILE.relative_to(ROOT)}")


# --------------------------------------------------------------------------- #
# Step 2: lake build + sorry / axiom check                                     #
# --------------------------------------------------------------------------- #


def check_proof() -> str:
    if not PROOF_FILE.exists():
        die_no_proof(f"{PROOF_FILE} does not exist")

    src = PROOF_FILE.read_text()
    if re.search(r"\bsorry\b", src):
        die_no_proof("proof file contains `sorry`")
    if not re.search(r"^\s*theorem\s+le_initialValue\b", src, re.M):
        die_no_proof("proof file no longer states theorem le_initialValue")

    log("running lake build in qed/ ...")
    proc = subprocess.run(["lake", "build"], cwd=QED_DIR, text=True, capture_output=True)
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        die_no_proof(f"lake build exited {proc.returncode}\n{out[-2000:]}")
    if re.search(r"^error:|\berror\b.*Qed/Basic\.lean", out, re.M | re.I):
        die_no_proof(f"lake build reported errors\n{out[-2000:]}")
    if "declaration uses 'sorry'" in out:
        die_no_proof("lake build reports a declaration uses sorry")

    # Axiom audit: only the three standard Lean axioms are allowed.
    with tempfile.NamedTemporaryFile("w", suffix=".lean", dir=QED_DIR, delete=False) as f:
        f.write("import Qed.Basic\n#print axioms Qed.le_initialValue\n")
        probe = Path(f.name)
    try:
        ax = subprocess.run(["lake", "env", "lean", str(probe)], cwd=QED_DIR, text=True, capture_output=True)
    finally:
        probe.unlink(missing_ok=True)
    ax_out = ax.stdout + ax.stderr
    if ax.returncode != 0:
        die_no_proof(f"axiom probe failed\n{ax_out[-1000:]}")
    allowed = {"propext", "Classical.choice", "Quot.sound"}
    m = re.search(r"depends on axioms: \[(.*?)\]", ax_out, re.S)
    used = {a.strip() for a in m.group(1).split(",")} if m else set()
    if used - allowed:
        die_no_proof(f"proof uses non-standard axioms: {sorted(used - allowed)}")

    digest = sha256_file(PROOF_FILE)
    log(f"proof verified: lake build ok, no sorry, axioms {sorted(used)}")
    log(f"proof sha256: {digest}")
    return digest


# --------------------------------------------------------------------------- #
# Chain helpers                                                                #
# --------------------------------------------------------------------------- #


def connect(private_key: str):
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 60}))
    if not w3.is_connected():
        sys.exit(f"cannot connect to RPC {RPC_URL}")
    chain_id = w3.eth.chain_id
    if chain_id != CHAIN_ID:
        sys.exit(f"RPC chain id {chain_id} != expected {CHAIN_ID}")
    acct = w3.eth.account.from_key(private_key)
    balance = w3.eth.get_balance(acct.address)
    log(f"chain {chain_id} ok; sender {acct.address}; balance {w3.from_wei(balance, 'ether')} ETH")
    return w3, acct


def buffered_gas_price(w3) -> int:
    """Current gas price plus 30% headroom so a base-fee tick can't stall the tx."""
    return w3.eth.gas_price * 13 // 10


def send_and_wait(w3, acct, tx: dict, label: str) -> str:
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log(f"{label}: sent {tx_hash.hex()}; waiting for receipt ...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    if receipt.status != 1:
        sys.exit(f"{label} tx reverted: {tx_hash.hex()}")
    log(f"{label}: confirmed in block {receipt.blockNumber}")
    return tx_hash.hex()


# --------------------------------------------------------------------------- #
# Step 3: anchor the proof hash on-chain                                       #
# --------------------------------------------------------------------------- #


def anchor_proof(w3, acct, digest: str, dry_run: bool) -> str | None:
    """0-value self-transfer whose calldata is the raw 32-byte SHA-256 of the proof."""
    data = bytes.fromhex(digest)
    assert len(data) == 32
    tx = {
        "from": acct.address,
        "to": acct.address,
        "value": 0,
        "data": data,
        "chainId": w3.eth.chain_id,
    }
    gas = w3.eth.estimate_gas(tx)
    tx["gas"] = gas * 12 // 10
    tx["gasPrice"] = buffered_gas_price(w3)
    log(f"anchor: 0 ETH self-transfer carrying sha256 {digest}; gas estimate {gas}")
    if dry_run:
        log("anchor: dry run, transaction NOT sent")
        return None
    tx["nonce"] = w3.eth.get_transaction_count(acct.address)
    return send_and_wait(w3, acct, tx, "anchor")


# --------------------------------------------------------------------------- #
# Step 4: Pons V2 launch (mirrors www.ponsfamily.com/launchpad/create)         #
# --------------------------------------------------------------------------- #


def placeholder_png(path: Path, size: int = 256, rgb: tuple = (20, 20, 24)) -> None:
    """Write a solid-colour PNG without any imaging library."""
    row = b"\x00" + bytes(rgb) * size
    raw = row * size

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)


def x_profile_url(handle_or_url: str) -> str:
    """normalizeXHandle + toXProfileUrl from the site: '@foo', 'x.com/foo', 'https://twitter.com/foo' -> https://x.com/foo."""
    h = handle_or_url.strip().lstrip("@")
    if not h:
        return ""
    if re.match(r"^(https?://)?(www\.)?(x|twitter)\.com/", h, re.I):
        h = re.sub(r"^(https?://)?(www\.)?(x|twitter)\.com/+", "", h, flags=re.I).split("/")[0].split("?")[0]
    if not X_HANDLE_RE.fullmatch(h):
        sys.exit(f"TOKEN_TWITTER {handle_or_url!r} is not a valid X handle (1-15 of A-Za-z0-9_)")
    return f"https://x.com/{h}"


def validate_token_identity() -> tuple[str, str, str]:
    """The checks the site's form applies before it lets you submit."""
    name, symbol, desc = TOKEN_NAME.strip(), TOKEN_SYMBOL.strip().upper(), TOKEN_DESCRIPTION.strip()
    if not (0 < len(name) <= 32 and NAME_RE.fullmatch(name)):
        sys.exit("Token names must use letters, numbers, and spaces with at most 32 characters.")
    if not (0 < len(symbol) <= 10 and SYMBOL_RE.fullmatch(symbol)):
        sys.exit("Token symbols must use letters and numbers with at most 10 characters.")
    if len(desc) > DESCRIPTION_MAX:
        sys.exit(f"Descriptions must be {DESCRIPTION_MAX} characters or fewer.")
    if re.search(r"https?://|www\s*\.|\b[a-z0-9-]+\.(com|io|xyz|net|org|fun|family|app|co)\b", desc, re.I):
        sys.exit("Links are not allowed in token descriptions.")
    return name, symbol, desc


def upload_logo(path: Path) -> str:
    """POST the logo to the site's IPFS worker exactly as the create page does; returns ipfs://<cid>."""
    mime = IMAGE_MIME.get(path.suffix.lower())
    if mime not in PONS_IMAGE_MIMES:
        sys.exit(f"{path.name}: use a PNG, JPEG, WebP, or GIF image")
    size = path.stat().st_size
    if size == 0 or size > PONS_IMAGE_MAX_BYTES:
        sys.exit(f"{path.name}: images must be smaller than 5 MB (got {size} bytes)")
    headers = {"Origin": PONS_APP_ORIGIN, "Referer": PONS_APP_ORIGIN + "/launchpad/create",
               "User-Agent": "deploy-by-proof/1.0", "Accept": "application/json"}
    with path.open("rb") as f:
        r = requests.post(PONS_IPFS_UPLOAD_URL, headers=headers, files={"image": (path.name, f, mime)}, timeout=120)
    try:
        data = r.json()
    except ValueError:
        data = {}
    uri = data.get("uri") if isinstance(data, dict) else None
    if not r.ok or not uri or not IPFS_URI_RE.fullmatch(uri):
        sys.exit(f"pons IPFS upload failed {r.status_code}: {(data or {}).get('error') or r.text[:300]}")
    log(f"pons: logo uploaded -> {uri} ({size} bytes)")
    return uri


def decode_revert(err: Exception) -> str:
    msg = str(err)
    m = re.search(r"0x([0-9a-fA-F]{8})", msg)
    if m and m.group(1).lower() in PONS_ERRORS:
        return f"{PONS_ERRORS[m.group(1).lower()]} ({msg[:200]})"
    return msg[:400]


def launch(w3, acct, dry_run: bool) -> dict:
    factory = w3.eth.contract(address=Web3.to_checksum_address(PONS_FACTORY), abi=PONS_FACTORY_ABI)
    pair = Web3.to_checksum_address(PAIR_TOKEN)
    if len(w3.eth.get_code(factory.address)) == 0:
        sys.exit(f"no code at PonsV2LaunchFactory {PONS_FACTORY}")

    # -- preflight reads: the same multicall the create page issues -----------
    fee = factory.functions.launchFee().call()
    enabled = factory.functions.launchEnabled().call()
    can_launch = factory.functions.canLaunch(acct.address).call()
    max_tax = factory.functions.maxCreatorTaxBps().call()
    deployer = factory.functions.launchDeployer().call()
    hook = factory.functions.memeHook().call()
    cfg = factory.functions.getLaunchConfig(PONS_LAUNCH_CONFIG_ID).call()
    supply, curve_fee_bps, phantom_quote, grad_threshold, pool_fee, tick_spacing, cfg_enabled = cfg
    if not can_launch:
        sys.exit(f"PonsV2LaunchFactory.canLaunch({acct.address}) is false (launchEnabled={enabled}); refusing")
    if not cfg_enabled:
        sys.exit(f"launch config {PONS_LAUNCH_CONFIG_ID} is disabled")
    if Web3.to_checksum_address(deployer) != Web3.to_checksum_address(PONS_LAUNCH_DEPLOYER):
        sys.exit(f"factory.launchDeployer() = {deployer}, expected {PONS_LAUNCH_DEPLOYER}")
    if Web3.to_checksum_address(hook) != Web3.to_checksum_address(PONS_MEME_HOOK):
        sys.exit(f"factory.memeHook() = {hook}, expected {PONS_MEME_HOOK}")
    if int(pair, 16) != 0 and not factory.functions.approvedPairTokens(pair).call():
        sys.exit(f"pair token {pair} is not approved by the factory")
    if CREATOR_TAX_BPS > max_tax:
        sys.exit(f"CREATOR_TAX_BPS {CREATOR_TAX_BPS} > maxCreatorTaxBps {max_tax}")
    economics = factory.functions.previewLaunchEconomics(PONS_LAUNCH_CONFIG_ID, pair).call()
    log(f"pons: launchFee {w3.from_wei(fee, 'ether')} ETH, pair {'ETH (native)' if int(pair, 16) == 0 else pair}, "
        f"config {PONS_LAUNCH_CONFIG_ID}: supply {supply // 10**18:,}, curve fee {curve_fee_bps} bps, "
        f"phantom quote {w3.from_wei(phantom_quote, 'ether')} ETH, graduation {w3.from_wei(grad_threshold, 'ether')} ETH, "
        f"tick spacing {tick_spacing}")
    log(f"pons: expectedEconomics {economics.hex()}")

    # -- metadata: on-chain strings, logo via the site's IPFS worker ----------
    name, symbol, desc = validate_token_identity()
    if not TOKEN_IMAGE.exists():
        placeholder_png(TOKEN_IMAGE)
        log(f"generated placeholder image {TOKEN_IMAGE.name}")
    logo_uri = upload_logo(TOKEN_IMAGE)
    socials = (x_profile_url(TOKEN_TWITTER), "", "", "", "")  # site form: twitter, telegram; discord/website/farcaster empty
    salt = secrets.token_bytes(32)  # site: crypto.getRandomValues(32 bytes)
    params = (name, symbol, logo_uri, desc, socials, acct.address, CREATOR_TAX_BPS, BUYBACK_ENABLED, bytes(economics), salt)
    exemptions = [Web3.to_checksum_address(a) for a in SNIPE_TAX_EXEMPTIONS]
    data = factory.encode_abi("launchToken", args=[params, PONS_LAUNCH_CONFIG_ID, pair, exemptions])
    data = bytes.fromhex(data[2:] if data.startswith("0x") else data)  # web3 v7 returns a hex string

    # -- self-check: decode what we are about to send -------------------------
    fn, args = factory.decode_function_input(data)
    p = args["params"]
    if fn.fn_name != "launch" + "Token" or p["name"] != name or p["symbol"] != symbol or p["logo"] != logo_uri \
            or p["socials"]["twitter"] != socials[0] or Web3.to_checksum_address(p["creatorFeeRecipient"]) != acct.address \
            or bytes(p["expectedEconomics"]) != bytes(economics) or bytes(p["salt"]) != salt \
            or args["launchConfigId"] != PONS_LAUNCH_CONFIG_ID or Web3.to_checksum_address(args["pairToken"]) != pair:
        sys.exit("encoded launchToken calldata does not round-trip to the intended parameters")
    log(f"calldata verified: launchToken({name}/{symbol}, logo {logo_uri}, twitter {socials[0] or '-'}, "
        f"creatorFeeRecipient {acct.address}, creatorTax {CREATOR_TAX_BPS} bps, buyback {BUYBACK_ENABLED}, "
        f"salt {salt.hex()}) selector {data[:4].hex()}, {len(data)} bytes")

    # -- simulate, price, (broadcast) -----------------------------------------
    tx = {"from": acct.address, "to": factory.address, "data": data, "value": fee, "chainId": w3.eth.chain_id}
    try:
        ret = w3.eth.call(tx)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"simulation of PonsV2LaunchFactory.launchToken reverted: {decode_revert(e)}")
    token, curve = abi_decode(["address", "address"], ret)
    token, curve = Web3.to_checksum_address(token), Web3.to_checksum_address(curve)
    gas = w3.eth.estimate_gas(tx)
    gas_price = buffered_gas_price(w3)
    cost = gas * gas_price
    balance = w3.eth.get_balance(acct.address)
    log(f"launch: simulated ok -> token {token}, curve {curve}; gas estimate {gas}, "
        f"gas price (buffered) {w3.from_wei(gas_price, 'gwei')} gwei, max cost ~{w3.from_wei(cost * 12 // 10 + fee, 'ether')} ETH "
        f"(incl. {w3.from_wei(fee, 'ether')} ETH launch fee)")
    if balance < cost * 12 // 10 + fee:
        sys.exit("insufficient ETH for gas + launch fee; fund the wallet and retry")

    result = {"tx": None, "asset": token, "curve": curve, "logo": logo_uri, "salt": salt.hex(),
              "fee": fee, "economics": economics.hex()}
    if dry_run:
        log("launch: dry run, transaction NOT sent")
        return result

    tx.update({"nonce": w3.eth.get_transaction_count(acct.address), "gas": gas * 12 // 10, "gasPrice": gas_price})
    tx_hash = send_and_wait(w3, acct, tx, "launch")
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    launched = [ev for ev in factory.events.TokenLaunched().process_receipt(receipt)
                if ev["address"].lower() == factory.address.lower()]
    if not launched:
        sys.exit(f"launch tx {tx_hash} succeeded but emitted no TokenLaunched from the factory")
    ev = launched[0]["args"]
    if Web3.to_checksum_address(ev["token"]) != token:
        log(f"warning: TokenLaunched.token {ev['token']} != simulated {token}; recording the on-chain one")
        token, curve = Web3.to_checksum_address(ev["token"]), Web3.to_checksum_address(ev["curve"])
    log(f"launched {symbol} token {token} with bonding curve {curve}")
    result.update({"tx": tx_hash, "asset": token, "curve": curve})
    return result


def append_launch_record(digest: str, anchor_hash: str, result: dict, sender: str) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"""
## {stamp} — {TOKEN_SYMBOL} via Pons V2 PonsV2LaunchFactory (paired with ETH)

| Field | Value |
|---|---|
| Proof SHA-256 | `{digest}` |
| Sender | `{sender}` |
| Anchor tx | `{anchor_hash}` |
| Launch tx | `{result['tx']}` |
| Token | `{result['asset']}` — {TOKEN_NAME} / {TOKEN_SYMBOL} |
| Bonding curve | `{result['curve']}` |
| Logo | `{result['logo']}` (on-chain `logo()`), twitter {x_profile_url(TOKEN_TWITTER)} |
| Launch fee | {Web3.from_wei(result['fee'], 'ether')} ETH, expectedEconomics `{result['economics']}`, salt `{result['salt']}` |
| Factory | `{PONS_FACTORY}` (launchConfigId {PONS_LAUNCH_CONFIG_ID}, pairToken `{PAIR_TOKEN}`) |
| Explorer | {EXPLORER_TX}{result['tx']} |
"""
    with LAUNCH_RECORD.open("a") as f:
        f.write(entry)
    log(f"appended launch record to {LAUNCH_RECORD.relative_to(ROOT)}")



# --------------------------------------------------------------------------- #
# main                                                                         #
# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="simulate only; never broadcast")
    ap.add_argument("--skip-aristotle", action="store_true", help="skip step 1 and verify the existing proof file")
    args = ap.parse_args()

    check_config()
    private_key = load_private_key()

    if not args.skip_aristotle:
        run_aristotle()
    digest = check_proof()

    w3, acct = connect(private_key)
    anchor_hash = anchor_proof(w3, acct, digest, args.dry_run)
    result = launch(w3, acct, args.dry_run)
    if result["tx"] and anchor_hash:
        append_launch_record(digest, anchor_hash, result, acct.address)

    print()
    print("=== deploy-by-proof ===")
    print(f"proof file   : {PROOF_FILE.relative_to(ROOT)}")
    print(f"proof sha256 : {digest}")
    print(f"anchor tx    : {anchor_hash or '(dry run, not sent)'}")
    print(f"launch tx    : {result['tx'] or '(dry run, not sent)'}")
    print(f"token        : {result['asset']}")
    print(f"curve        : {result['curve']}")
    print(f"logo         : {result['logo']}")
    if anchor_hash:
        print(f"anchor url   : {EXPLORER_TX}{anchor_hash}")
    if result["tx"]:
        print(f"launch url   : {EXPLORER_TX}{result['tx']}")


if __name__ == "__main__":
    main()
