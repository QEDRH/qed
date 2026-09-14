# /// script
# requires-python = ">=3.11"
# dependencies = ["web3>=7,<9", "requests>=2.31"]
# ///
"""
deploy-by-proof: launch a token on launchpad (Robinhood Chain) ONLY after the
Lean proof in qed/Qed/Basic.lean is verified.

Pipeline
  1. aristotle submit ... --wait      (prove / re-verify the rules in Basic.lean)
  2. lake build in qed/               (must succeed with no errors, no sorry)
  3. 0-value self-tx with the proof's SHA-256 as calldata (anchor), wait for it
  4. launchpad launch, the way launchpad.example does it:
       a. sign in with the wallet via Privy (SIWE)         -> bearer token
       b. POST /ipfs/upload-image, POST /ipfs/upload-metadata -> tokenURI
       c. POST /robinhood/prepare-launch                   -> signed calldata for
          LaunchFactory.launch(CreateParams, LaunchAuthorization, signature)
       d. verify the returned calldata locally, simulate it, then broadcast
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
  LONG_ACCESS_TOKEN  optional; a Privy access token for launchpad.example. If set, the
                     SIWE sign-in step is skipped and this token is used instead.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import uuid
import zlib
from pathlib import Path

import requests
from eth_abi import decode as abi_decode, encode as abi_encode
from eth_account.messages import encode_defunct
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

# launchpad launch factory (UUPS proxy; impl LaunchFactory, verified on Sourcify).
# Source of truth: https://sourcify.dev/server/v2/contract/4663/0x7B7b87fd1Fb05864cD572C7306038552286c73d9
LONG_LAUNCHER = "0x1Eef016F22A943abC7DD11422EDeE9D235942104"
AIRLOCK = "0xeb7c034704ef8dcd2d32324c1545f62fb4ad0862"
# Floor enforced on-chain by LaunchFactory._enforceFloor (read live on 2026-09-14):
TRUSTED_TOKEN_FACTORY = "0x1B37D3a72082029c44B35B604Ea473617580b69a"    # DopplerERC20V1Factory
REQUIRED_POOL_INITIALIZER = "0x4e3468951D49f2EEa976eD0D6e75fFCb44a9a544"  # DopplerHookInitializer
REQUIRED_INTEGRATOR = "0x92d435C96E63c43E12d6D0AB28f6b0B04072F765"

# launchpad web-app backend, as wired in launchpad.example's bundle. The API key is the
# public one embedded in the frontend; the bearer token comes from Privy sign-in.
LONG_API_URL = "https://api.launchpad.example/v1"
LONG_API_KEY = "lxyz_49534dc2febae30294149790a8152f44bf915ebbe0332213"
LONG_APP_ORIGIN = "https://launchpad.example"
PRIVY_APP_ID = "cmppfotax00ql0clcbz4vvt4b"
PRIVY_API = "https://auth.privy.io/api/v1"

# Numeraire: SPCX (SpaceX Robinhood stock token), 18 decimals, BeaconProxy.
NUMERAIRE = "0x4a0E65A3EcceC6dBe60AE065F2e7bb85Fae35eEa"

# Token to launch
TOKEN_NAME = "test2"
TOKEN_SYMBOL = "TESTII"  # launchpad tickers are A-Z only (1-15 chars); "TEST2" is rejected on-chain
TOKEN_DESCRIPTION = "test2: a deploy-by-proof test token. Launch gated on a machine-checked Lean proof."
TOKEN_SOCIALS: list[tuple[str, str]] = [("Twitter", "https://x.com/example")]  # (label, url)
TOKEN_IMAGE = ROOT / "logo.png"  # a placeholder is generated only if this file is missing
IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}

LAUNCHER_ABI = [
    {"type": "function", "name": "launch", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "data", "type": "tuple", "components": [
             {"name": "initialSupply", "type": "uint256"},
             {"name": "numTokensToSell", "type": "uint256"},
             {"name": "numeraire", "type": "address"},
             {"name": "tokenFactory", "type": "address"},
             {"name": "tokenFactoryData", "type": "bytes"},
             {"name": "governanceFactory", "type": "address"},
             {"name": "governanceFactoryData", "type": "bytes"},
             {"name": "poolInitializer", "type": "address"},
             {"name": "poolInitializerData", "type": "bytes"},
             {"name": "liquidityMigrator", "type": "address"},
             {"name": "liquidityMigratorData", "type": "bytes"},
             {"name": "integrator", "type": "address"},
             {"name": "salt", "type": "bytes32"}]},
         {"name": "auth", "type": "tuple", "components": [
             {"name": "launcher", "type": "address"},
             {"name": "paramsHash", "type": "bytes32"},
             {"name": "expectedAsset", "type": "address"},
             {"name": "deadline", "type": "uint256"}]},
         {"name": "signature", "type": "bytes"}],
     "outputs": [
         {"name": "asset", "type": "address"}, {"name": "pool", "type": "address"},
         {"name": "governance", "type": "address"}, {"name": "timelock", "type": "address"},
         {"name": "migrationPool", "type": "address"}]},
    {"type": "function", "name": "isTickerAvailable", "stateMutability": "view",
     "inputs": [{"name": "ticker", "type": "string"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "getTickerRecord", "stateMutability": "view",
     "inputs": [{"name": "ticker", "type": "string"}],
     "outputs": [{"type": "tuple", "components": [
         {"name": "token", "type": "address"}, {"name": "deployedAt", "type": "uint48"},
         {"name": "reservedUntil", "type": "uint48"}]}]},
    {"type": "function", "name": "isSigner", "stateMutability": "view",
     "inputs": [{"type": "address"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "hashLaunchAuthorization", "stateMutability": "view",
     "inputs": [{"name": "auth", "type": "tuple", "components": [
         {"name": "launcher", "type": "address"}, {"name": "paramsHash", "type": "bytes32"},
         {"name": "expectedAsset", "type": "address"}, {"name": "deadline", "type": "uint256"}]}],
     "outputs": [{"type": "bytes32"}]},
    {"type": "function", "name": "paused", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]},
]
CREATE_PARAMS_TYPE = "(uint256,uint256,address,address,bytes,address,bytes,address,bytes,address,bytes,address,bytes32)"
TOKEN_FACTORY_DATA_TYPES = ["string", "string", "(uint64,uint64)[]", "address[]", "uint256[]", "uint256[]",
                            "string", "uint256", "uint48", "address", "address[]"]

ERC20_ABI = [
    {"type": "function", "name": "symbol", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
    {"type": "function", "name": "decimals", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
]

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




def load_env_value(key: str) -> str | None:
    return os.environ.get(key, "").strip() or None


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
# Step 4: launchpad launch (mirrors launchpad.example)                               #
# --------------------------------------------------------------------------- #


class LongClient:
    """Thin client for the endpoints launchpad.example calls when launching."""

    def __init__(self, acct):
        self.acct = acct
        self.http = requests.Session()
        self.http.headers.update({"Origin": LONG_APP_ORIGIN, "Referer": LONG_APP_ORIGIN + "/create",
                                  "User-Agent": "deploy-by-proof/1.0"})
        self.token: str | None = None

    # -- auth ---------------------------------------------------------------
    def sign_in(self) -> str:
        """Privy sign-in with Ethereum (EIP-4361), as the site's Privy SDK does."""
        preset = load_env_value("LONG_ACCESS_TOKEN")
        if preset:
            log("launchpad: using LONG_ACCESS_TOKEN from .env")
            self.token = preset
            return preset
        addr = self.acct.address
        headers = {"privy-app-id": PRIVY_APP_ID, "privy-ca-id": str(uuid.uuid4()),
                   "Content-Type": "application/json"}
        r = self.http.post(f"{PRIVY_API}/siwe/init", json={"address": addr}, headers=headers, timeout=30)
        if r.status_code != 200:
            sys.exit(f"privy siwe/init failed {r.status_code}: {r.text[:300]}")
        nonce = r.json()["nonce"]
        issued = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        host = LONG_APP_ORIGIN.split("://", 1)[1]
        message = (
            f"{host} wants you to sign in with your Ethereum account:\n{addr}\n\n"
            "By signing, you are proving you own this wallet and logging in. "
            "This does not initiate a transaction or cost any fees.\n\n"
            f"URI: {LONG_APP_ORIGIN}\nVersion: 1\nChain ID: {CHAIN_ID}\nNonce: {nonce}\n"
            f"Issued At: {issued}\nResources:\n- https://privy.io"
        )
        sig = self.acct.sign_message(encode_defunct(text=message)).signature.hex()
        if not sig.startswith("0x"):
            sig = "0x" + sig
        body = {"message": message, "signature": sig, "chainId": f"eip155:{CHAIN_ID}",
                "walletClientType": "unknown", "connectorType": "injected", "mode": "login-or-sign-up"}
        r = self.http.post(f"{PRIVY_API}/siwe/authenticate", json=body, headers=headers, timeout=30)
        if r.status_code != 200:
            sys.exit(f"privy siwe/authenticate failed {r.status_code}: {r.text[:300]}")
        data = r.json()
        token = data.get("token") or data.get("privy_access_token") or data.get("access_token")
        if not token:
            sys.exit(f"privy authenticate returned no token; keys: {sorted(data)}")
        self.token = token
        log(f"launchpad: signed in as {addr} via Privy")
        return token

    def _api_headers(self, bearer: bool) -> dict:
        h = {"x-api-key": LONG_API_KEY}
        if bearer:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    # -- metadata -----------------------------------------------------------
    def upload_image(self, path: Path) -> str:
        with path.open("rb") as f:
            r = self.http.post(f"{LONG_API_URL}/ipfs/upload-image", headers=self._api_headers(False),
                               files={"image": (path.name, f, IMAGE_MIME.get(path.suffix.lower(), "application/octet-stream"))},
                               timeout=120)
        if not r.ok:
            sys.exit(f"launchpad upload-image failed {r.status_code}: {r.text[:300]}")
        cid = r.json()["result"]
        log(f"launchpad: image uploaded -> {cid}")
        return cid

    def upload_metadata(self, image_cid: str) -> str:
        body = {
            "name": TOKEN_NAME.strip(),
            "description": TOKEN_DESCRIPTION.strip(),
            "fee_receiver": self.acct.address,
            "image_hash": f"ipfs://{image_cid}",
            "social_links": [{"label": label, "url": url} for label, url in TOKEN_SOCIALS if url],
            "vesting_recipients": [{"address": "0x0000000000000000000000000000000000000000", "amount": 0}],
            "categories": [],
        }
        r = self.http.post(f"{LONG_API_URL}/ipfs/upload-metadata", json=body,
                           headers=self._api_headers(False), timeout=60)
        if not r.ok:
            sys.exit(f"launchpad upload-metadata failed {r.status_code}: {r.text[:300]}")
        meta = r.json()["result"]
        token_uri = meta if str(meta).startswith("ipfs://") else f"ipfs://{meta}"
        log(f"launchpad: metadata uploaded -> {token_uri}")
        return token_uri  # launchpad.example sends metadata_hash as `ipfs://<cid>` to prepare-launch

    # -- authorization ------------------------------------------------------
    def prepare_launch(self, token_uri: str) -> dict:
        body = {
            "launcher": self.acct.address,
            "name": TOKEN_NAME.strip(),
            "ticker": TOKEN_SYMBOL.strip().upper(),
            "numeraire": Web3.to_checksum_address(NUMERAIRE),
            "tokenURI": token_uri,
            "feeReceiver": self.acct.address,
        }
        r = self.http.post(f"{LONG_API_URL}/robinhood/prepare-launch", json=body,
                           headers=self._api_headers(True), timeout=120)
        try:
            data = r.json()
        except ValueError:
            data = None
        if not r.ok or not isinstance(data, dict):  # the API answers 201 Created on success
            msg = (data or {}).get("message") if isinstance(data, dict) else None
            sys.exit(f"launchpad prepare-launch failed {r.status_code}: {msg or r.text[:300]}")
        for k in ("to", "data", "expectedAsset", "deadline"):
            if k not in data:
                sys.exit(f"prepare-launch response missing {k}: {sorted(data)}")
        if str(data.get("value", "0")) not in ("0", "0x0"):
            sys.exit("prepare-launch asked for a non-zero value; refusing")
        log(f"launchpad: prepare-launch ok; expectedAsset {data['expectedAsset']}, deadline {data['deadline']}")
        return data


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


def verify_prepared_calldata(w3, acct, launcher, prepared: dict) -> dict:
    """Decode the calldata launchpad returned and check it is exactly a launch of OUR token."""
    to = Web3.to_checksum_address(prepared["to"])
    if to != Web3.to_checksum_address(LONG_LAUNCHER):
        sys.exit(f"prepare-launch targets {to}, expected LaunchFactory {LONG_LAUNCHER}")
    data = bytes.fromhex(prepared["data"][2:] if prepared["data"].startswith("0x") else prepared["data"])
    try:
        fn, args = launcher.decode_function_input(data)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"prepared calldata does not decode as LaunchFactory.launch: {e}")
    if fn.fn_name != "launch":
        sys.exit(f"prepared calldata calls {fn.fn_name}, not launch")
    cp, auth, sig = args["data"], args["auth"], args["signature"]

    # LaunchAuthorization must be for us, for this asset, and match the params hash.
    if Web3.to_checksum_address(auth["launcher"]) != acct.address:
        sys.exit(f"authorization is for launcher {auth['launcher']}, not {acct.address}")
    expected_asset = Web3.to_checksum_address(prepared["expectedAsset"])
    if Web3.to_checksum_address(auth["expectedAsset"]) != expected_asset:
        sys.exit("authorization expectedAsset != response expectedAsset")
    cp_tuple = tuple(cp[k] for k in ("initialSupply", "numTokensToSell", "numeraire", "tokenFactory",
                                     "tokenFactoryData", "governanceFactory", "governanceFactoryData",
                                     "poolInitializer", "poolInitializerData", "liquidityMigrator",
                                     "liquidityMigratorData", "integrator", "salt"))
    params_hash = Web3.keccak(abi_encode([CREATE_PARAMS_TYPE], [cp_tuple]))
    if bytes(auth["paramsHash"]) != params_hash:
        sys.exit("authorization paramsHash does not match the CreateParams in the calldata")
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    if not (now < int(auth["deadline"]) <= now + 3600):
        sys.exit(f"authorization deadline {auth['deadline']} is outside (now, now+1h]")

    # The launch must be for our token, paired with SPCX, through the on-chain floor.
    name, symbol, *_rest = abi_decode(TOKEN_FACTORY_DATA_TYPES, cp["tokenFactoryData"])
    token_uri = _rest[4]
    if name != TOKEN_NAME.strip() or symbol.upper() != TOKEN_SYMBOL.strip().upper():
        sys.exit(f"calldata launches {name}/{symbol}, expected {TOKEN_NAME}/{TOKEN_SYMBOL}")
    checks = {
        "numeraire": (cp["numeraire"], NUMERAIRE),
        "tokenFactory": (cp["tokenFactory"], TRUSTED_TOKEN_FACTORY),
        "poolInitializer": (cp["poolInitializer"], REQUIRED_POOL_INITIALIZER),
        "integrator": (cp["integrator"], REQUIRED_INTEGRATOR),
    }
    for k, (got, want) in checks.items():
        if Web3.to_checksum_address(got) != Web3.to_checksum_address(want):
            sys.exit(f"calldata {k} = {got}, expected {want}")
    if cp["numTokensToSell"] > cp["initialSupply"]:
        sys.exit("numTokensToSell > initialSupply")

    # Signature must recover to a signer the factory trusts.
    digest = launcher.functions.hashLaunchAuthorization(
        (auth["launcher"], auth["paramsHash"], auth["expectedAsset"], auth["deadline"])).call()
    signer = w3.eth.account._recover_hash(digest, signature=sig)
    if not launcher.functions.isSigner(signer).call():
        sys.exit(f"authorization signed by {signer}, which LaunchFactory does not trust")

    log(f"calldata verified: {name}/{symbol} vs numeraire {cp['numeraire']}, supply {cp['initialSupply'] // 10**18:,}, "
        f"sell {cp['numTokensToSell'] // 10**18:,}, tokenURI {token_uri}, signer {signer}")
    return {"to": to, "data": data, "expectedAsset": expected_asset, "symbol": symbol,
            "tokenURI": token_uri, "deadline": int(auth["deadline"])}


def launch(w3, acct, dry_run: bool) -> dict:
    launcher = w3.eth.contract(address=Web3.to_checksum_address(LONG_LAUNCHER), abi=LAUNCHER_ABI)
    if launcher.functions.paused().call():
        sys.exit("LaunchFactory is paused")
    numeraire = w3.eth.contract(address=Web3.to_checksum_address(NUMERAIRE), abi=ERC20_ABI)
    log(f"numeraire {NUMERAIRE}: symbol={numeraire.functions.symbol().call()} "
        f"decimals={numeraire.functions.decimals().call()}")
    ticker = TOKEN_SYMBOL.strip().upper()
    try:
        available = launcher.functions.isTickerAvailable(ticker).call()
    except Exception as e:  # noqa: BLE001
        err = str(e)
        if "0xe666e3c7" in err:  # InvalidTickerCharacter(uint256 index, bytes1 character)
            raw = err.split("0xe666e3c7", 1)[1][:128]
            idx, ch = int(raw[:64], 16), bytes.fromhex(raw[64:66]).decode(errors="replace")
            sys.exit(f"LaunchFactory rejects ticker {ticker!r}: invalid character {ch!r} at index {idx} "
                     f"(launchpad tickers must be letters only)")
        if "0x4f9730f8" in err:  # InvalidTickerLength(uint256)
            sys.exit(f"LaunchFactory rejects ticker {ticker!r}: length must be 1-15 characters")
        raise
    if not available:
        rec = launcher.functions.getTickerRecord(ticker).call()
        sys.exit(f"ticker {ticker} is reserved by {rec[0]} until {dt.datetime.fromtimestamp(rec[2], dt.timezone.utc)}")
    log(f"ticker {ticker} is available on LaunchFactory")

    client = LongClient(acct)
    client.sign_in()
    if not TOKEN_IMAGE.exists():
        placeholder_png(TOKEN_IMAGE)
        log(f"generated placeholder image {TOKEN_IMAGE.name}")
    image_cid = client.upload_image(TOKEN_IMAGE)
    token_uri = client.upload_metadata(image_cid)
    prepared = client.prepare_launch(token_uri)
    v = verify_prepared_calldata(w3, acct, launcher, prepared)

    tx = {"from": acct.address, "to": v["to"], "data": v["data"], "value": 0, "chainId": w3.eth.chain_id}
    try:
        ret = w3.eth.call(tx)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"simulation of LaunchFactory.launch reverted: {e}")
    asset, pool, gov, timelock, mig = abi_decode(["address"] * 5, ret)
    if Web3.to_checksum_address(asset) != v["expectedAsset"]:
        sys.exit(f"simulation returned asset {asset}, expected {v['expectedAsset']}")
    gas = w3.eth.estimate_gas(tx)
    gas_price = buffered_gas_price(w3)
    cost = gas * gas_price
    balance = w3.eth.get_balance(acct.address)
    log(f"launch: simulated ok -> asset {asset}, pool/hook {pool}; gas estimate {gas}, "
        f"gas price (buffered) {w3.from_wei(gas_price, 'gwei')} gwei, max cost ~{w3.from_wei(cost * 12 // 10, 'ether')} ETH")
    if balance < cost * 12 // 10:
        sys.exit("insufficient ETH for gas; fund the wallet and retry")

    if dry_run:
        log("launch: dry run, transaction NOT sent")
        return {"tx": None, "asset": asset, "pool": pool, "tokenURI": v["tokenURI"]}

    tx.update({"nonce": w3.eth.get_transaction_count(acct.address), "gas": gas * 12 // 10, "gasPrice": gas_price})
    tx_hash = send_and_wait(w3, acct, tx, "launch")
    log(f"launched {v['symbol']} asset {asset} with pool/hook {pool}")
    return {"tx": tx_hash, "asset": asset, "pool": pool, "tokenURI": v["tokenURI"]}


def append_launch_record(digest: str, anchor_hash: str, result: dict, sender: str) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"""
## {stamp} — {TOKEN_SYMBOL} via launchpad factory

| Field | Value |
|---|---|
| Proof SHA-256 | `{digest}` |
| Sender | `{sender}` |
| Anchor tx | `{anchor_hash}` |
| Launch tx | `{result['tx']}` |
| Token | `{result['asset']}` — {TOKEN_NAME} / {TOKEN_SYMBOL} |
| Pool / hook | `{result['pool']}` |
| tokenURI | `{result['tokenURI']}` |
| Launcher | `{LONG_LAUNCHER}` |
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
    if anchor_hash:
        print(f"anchor url   : {EXPLORER_TX}{anchor_hash}")
    if result["tx"]:
        print(f"launch url   : {EXPLORER_TX}{result['tx']}")


if __name__ == "__main__":
    main()
