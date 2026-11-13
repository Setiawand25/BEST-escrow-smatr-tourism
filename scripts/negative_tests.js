// Access-control and state-machine negative tests: every call below must revert.
const hre = require("hardhat"); const { ethers } = hre; const fs = require("fs");
async function reverts(p) { try { await (await p).wait(); return false; } catch { return true; } }
(async () => {
  const [admin, plat, aff, sdg, hotel, guest, attacker] = await ethers.getSigners();
  const tok = await (await ethers.getContractFactory("MockStablecoin")).deploy();
  const F = await ethers.getContractFactory("BookingEscrow");
  const esc = await F.deploy(await tok.getAddress(), plat.address, aff.address, sdg.address, 500, 300, 200, 0);
  await (await tok.mint(guest.address, 10n**12n)).wait();
  await (await tok.connect(guest).approve(await esc.getAddress(), ethers.MaxUint256)).wait();
  const now = async () => (await ethers.provider.getBlock("latest")).timestamp;
  const adv = async s => { await ethers.provider.send("evm_increaseTime", [s]); await ethers.provider.send("evm_mine", []); };
  const T = [];
  const t0 = await now();
  await (await esc.connect(guest).createBooking(hotel.address, 1_000_000n, t0 + 1000, t0 + 2000, ethers.ZeroHash)).wait(); // id 1
  T.push(["confirmPayment by non-guest", await reverts(esc.connect(attacker).confirmPayment(1))]);
  T.push(["completeStay before payment", await reverts(esc.connect(admin).completeStay(1))]);
  await (await esc.connect(guest).confirmPayment(1)).wait();
  T.push(["double confirmPayment", await reverts(esc.connect(guest).confirmPayment(1))]);
  T.push(["completeStay by non-operator", await reverts(esc.connect(attacker).completeStay(1))]);
  T.push(["completeStay before check-out", await reverts(esc.connect(admin).completeStay(1))]);
  T.push(["refund without cancellation", await reverts(esc.connect(guest).refund(1))]);
  T.push(["cancel by non-guest", await reverts(esc.connect(attacker).cancel(1))]);
  await adv(1500);
  T.push(["cancel after check-in", await reverts(esc.connect(guest).cancel(1))]);
  await adv(600);
  await (await esc.connect(admin).completeStay(1)).wait();
  T.push(["double completeStay", await reverts(esc.connect(admin).completeStay(1))]);
  T.push(["cancel after completion", await reverts(esc.connect(guest).cancel(1))]);
  const t1 = await now();
  await (await esc.connect(guest).createBooking(hotel.address, 1_000_000n, t1 + 1000, t1 + 2000, ethers.ZeroHash)).wait(); // id 2
  await (await esc.connect(guest).confirmPayment(2)).wait();
  await (await esc.connect(guest).cancel(2)).wait();
  await (await esc.connect(guest).refund(2)).wait();
  T.push(["double refund", await reverts(esc.connect(guest).refund(2))]);
  T.push(["completeStay after cancellation", await reverts(esc.connect(admin).completeStay(2))]);
  const t2 = await now();
  await (await esc.connect(guest).createBooking(hotel.address, 1_000_000n, t2 + 1000, t2 + 2000, ethers.ZeroHash)).wait(); // id 3 unpaid
  await (await esc.connect(guest).cancel(3)).wait();
  T.push(["refund of unpaid cancelled booking", await reverts(esc.connect(guest).refund(3))]);
  T.push(["withdraw with zero balance", await reverts(esc.connect(attacker).withdraw())]);
  T.push(["deploy with shares >= 100%", await reverts(F.deploy(await tok.getAddress(), plat.address, aff.address, sdg.address, 5000, 3000, 2000, 0).then(c => c.deploymentTransaction()))]);
  T.push(["deploy with zero SDG-fund address", await reverts(F.deploy(await tok.getAddress(), plat.address, aff.address, ethers.ZeroAddress, 500, 300, 200, 0).then(c => c.deploymentTransaction()))]);
  T.push(["createBooking with checkOut < checkIn", await reverts(esc.connect(guest).createBooking(hotel.address, 1n, 2000, 1000, ethers.ZeroHash))]);
  const bal = await tok.balanceOf(await esc.getAddress());
  T.push(["escrow empty after all flows", bal === 0n]);
  T.forEach(([n, ok]) => console.log(ok ? "PASS" : "FAIL", n));
  fs.writeFileSync("results/negative_tests.json", JSON.stringify(T, null, 1));
  console.log(`${T.filter(x => x[1]).length}/${T.length} passed`);
})();
