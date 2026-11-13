// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

interface IEscrow { function refund(uint256 id) external; function withdraw() external; }

/// Test-only hostile token: on every transfer out of the escrow it tries to re-enter
/// refund()/withdraw() and records whether the re-entrant call succeeded.
contract ReentrantToken is ERC20 {
    address public escrow; uint256 public targetId; uint256 public reentrySuccesses; uint256 public reentryAttempts;
    bool private inAttack;
    constructor() ERC20("Hostile", "HST") {}
    function setTarget(address e, uint256 id) external { escrow = e; targetId = id; }
    function mint(address to, uint256 a) external { _mint(to, a); }
    function _update(address from, address to, uint256 value) internal override {
        super._update(from, to, value);
        if (from == escrow && escrow != address(0) && !inAttack) {
            inAttack = true;
            reentryAttempts += 2;
            try IEscrow(escrow).refund(targetId) { reentrySuccesses++; } catch {}
            try IEscrow(escrow).withdraw() { reentrySuccesses++; } catch {}
            inAttack = false;
        }
    }
}
