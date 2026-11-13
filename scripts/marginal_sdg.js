// Marginal gas of the SDG allocation: completeStay with bpsSdg=200 vs bpsSdg=0 (steady state).
const hre = require("hardhat"); const { ethers } = hre; const fs = require("fs");
async function steady(mode, bpsSdg) {
  const s = await ethers.getSigners(); const [admin, plat, aff, sdg, hotel, guest] = s;
  const tok = await (await ethers.getContractFactory("MockStablecoin")).deploy();
  const esc = await (await ethers.getContractFactory("BookingEscrow")).deploy(await tok.getAddress(), plat.address, aff.address, sdg.address, 500, 300, bpsSdg, mode);
  await (await tok.mint(guest.address, 10n**15n)).wait();
  await (await tok.connect(guest).approve(await esc.getAddress(), ethers.MaxUint256)).wait();
  const g = [];
  for (let i = 0; i < 30; i++) {
    const id = await esc.nextId();
    await (await esc.connect(guest).createBooking(hotel.address, 283_500_000n + BigInt(i*7919), 0, 0, ethers.ZeroHash)).wait();
    await (await esc.connect(guest).confirmPayment(id)).wait();
    const r = await (await esc.connect(admin).completeStay(id)).wait();
    if (i >= 5) g.push(Number(r.gasUsed));
  }
  return g.reduce((a,b)=>a+b,0)/g.length;
}
(async () => {
  const out = {};
  for (const [m, name] of [[0,"push"],[1,"accrue"]]) {
    const w = await steady(m, 200), wo = await steady(m, 0);
    out[name] = { withSdg: w, withoutSdg: wo, marginal: w - wo };
  }
  console.log(out); fs.writeFileSync("results/marginal_sdg.json", JSON.stringify(out, null, 1));
})();
