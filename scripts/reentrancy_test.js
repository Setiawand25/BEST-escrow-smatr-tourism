const hre = require("hardhat"); const { ethers } = hre; const fs = require("fs");
(async () => {
  const [admin, plat, aff, sdg, hotel, guest] = await ethers.getSigners();
  const res = {};
  for (const [mode, name] of [[0, "push"], [1, "accrue"]]) {
    const tok = await (await ethers.getContractFactory("ReentrantToken")).deploy();
    const esc = await (await ethers.getContractFactory("BookingEscrow")).deploy(await tok.getAddress(), plat.address, aff.address, sdg.address, 500, 300, 200, mode);
    const ea = await esc.getAddress();
    await (await tok.mint(guest.address, 10n**12n)).wait();
    await (await tok.connect(guest).approve(ea, ethers.MaxUint256)).wait();
    const t = (await ethers.provider.getBlock("latest")).timestamp;
    // two paid bookings; booking 1 cancelled and refunded while the token attempts re-entry
    for (let i = 0; i < 2; i++) { await (await esc.connect(guest).createBooking(hotel.address, 5_000_000n, t + 1000, t + 2000, ethers.ZeroHash)).wait(); await (await esc.connect(guest).confirmPayment(i + 1)).wait(); }
    await (await tok.setTarget(ea, 1)).wait();
    await (await esc.connect(guest).cancel(1)).wait();
    let outerOk = true; try { await (await esc.connect(guest).refund(1)).wait(); } catch { outerOk = false; }
    const escBal = await tok.balanceOf(ea);
    res[name] = { outerRefundSucceeded: outerOk, reentryAttempts: Number(await tok.reentryAttempts()), reentrySuccesses: Number(await tok.reentrySuccesses()),
                  escrowBalanceAfter: escBal.toString(), expectedEscrow: "5000000" };
  }
  console.log(res); fs.writeFileSync("results/reentrancy.json", JSON.stringify(res, null, 1));
})();
