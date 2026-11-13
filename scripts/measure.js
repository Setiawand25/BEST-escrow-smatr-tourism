// Measures gas of every life-cycle function on the Hardhat (Cancun) EVM and checks the
// revenue-split conservation invariant on-chain. Output: results/gas.json
const hre = require("hardhat");
const fs = require("fs");
const { ethers } = hre;

function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; }; }

async function gasOf(txp) { const tx = await txp; const r = await tx.wait(); return Number(r.gasUsed); }

async function run(mode, N, seed) {
  const signers = await ethers.getSigners();
  const [admin, platform, affiliate, sdg] = signers;
  const hotels = signers.slice(4, 14);   // 10 hotels
  const guests = signers.slice(14, 44);  // 30 guests
  const Tok = await ethers.getContractFactory("MockStablecoin");
  const tok = await Tok.deploy(); await tok.waitForDeployment();
  const Esc = await ethers.getContractFactory("BookingEscrow");
  const esc = await Esc.deploy(await tok.getAddress(), platform.address, affiliate.address, sdg.address, 500, 300, 200, mode);
  await esc.waitForDeployment();
  const deployGas = Number((await esc.deploymentTransaction().wait()).gasUsed);
  for (const g of guests) {
    await (await tok.mint(g.address, 10n ** 15n)).wait();
    await (await tok.connect(g).approve(await esc.getAddress(), ethers.MaxUint256)).wait(); // one-time approval
  }
  const approveGas = await gasOf(tok.connect(signers[44]).approve(await esc.getAddress(), ethers.MaxUint256));
  const R = rng(seed);
  const g = { create: [], confirm: [], complete: [], completeFirst: [], cancel: [], refund: [], withdraw: [] };
  let violations = 0, checked = 0;
  const seenHotel = new Set();
  for (let i = 0; i < N; i++) {
    const guest = guests[Math.floor(R() * guests.length)];
    const hotel = hotels[Math.floor(R() * hotels.length)];
    // lognormal booking value around US$283.5 (median), sigma 0.5, 6-decimal units
    const u1 = Math.max(R(), 1e-12), u2 = R();
    const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
    const amount = BigInt(Math.round(283.5 * Math.exp(0.5 * z) * 1e6)) + BigInt(Math.floor(R() * 100)); // non-round
    const hash = ethers.keccak256(ethers.toUtf8Bytes(`record-${i}-${seed}`));
    const cancelThis = R() < 0.15;
    const id = await esc.nextId();
    const t = (await ethers.provider.getBlock("latest")).timestamp;
    g.create.push(await gasOf(esc.connect(guest).createBooking(hotel.address, amount, t + 86400, t + 2 * 86400, hash)));
    g.confirm.push(await gasOf(esc.connect(guest).confirmPayment(id)));
    if (cancelThis) {
      g.cancel.push(await gasOf(esc.connect(guest).cancel(id)));
      g.refund.push(await gasOf(esc.connect(guest).refund(id)));
      continue;
    }
    await ethers.provider.send("evm_increaseTime", [2 * 86400 + 1]); await ethers.provider.send("evm_mine", []);
    const tx = await esc.connect(admin).completeStay(id);
    const rc = await tx.wait();
    const gas = Number(rc.gasUsed);
    if (!seenHotel.has(hotel.address) || i === 0) { g.completeFirst.push(gas); seenHotel.add(hotel.address); } else g.complete.push(gas);
    const ev = rc.logs.map(l => { try { return esc.interface.parseLog(l); } catch { return null; } }).find(e => e && e.name === "StayCompleted");
    const sum = ev.args[1] + ev.args[2] + ev.args[3] + ev.args[4];
    checked++; if (sum !== amount) violations++;
  }
  if (mode === 1) {
    for (const who of [hotels[0], platform, sdg]) {
      if ((await esc.accrued(who.address)) > 0n) g.withdraw.push(await gasOf(esc.connect(who).withdraw()));
    }
  }
  // escrow must end empty (all completed paid/accrued, all cancelled refunded)
  const escBal = await tok.balanceOf(await esc.getAddress());
  let accruedTotal = 0n;
  if (mode === 1) for (const a of [...hotels, platform, affiliate, sdg]) accruedTotal += await esc.accrued(a.address);
  return { mode: mode === 0 ? "push" : "accrue", N, deployGas, approveGas, gas: g, checked, violations,
           escrowResidual: (escBal - accruedTotal).toString() };
}

function stats(a) { if (!a.length) return null; const s = [...a].sort((x, y) => x - y);
  return { n: a.length, mean: a.reduce((x, y) => x + y, 0) / a.length, min: s[0], max: s[s.length - 1], median: s[Math.floor(s.length / 2)] }; }

async function main() {
  const N = Number(process.env.N || 400);
  const out = [];
  for (const mode of [0, 1]) {
    const r = await run(mode, N, 20261022 + mode);
    r.stats = Object.fromEntries(Object.entries(r.gas).map(([k, v]) => [k, stats(v)]));
    delete r.gas; out.push(r);
    console.log(JSON.stringify(r, null, 1));
  }
  fs.mkdirSync("results", { recursive: true });
  fs.writeFileSync("results/gas.json", JSON.stringify(out, null, 1));
}
main().catch(e => { console.error(e); process.exit(1); });
