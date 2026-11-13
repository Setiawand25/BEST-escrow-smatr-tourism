// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title BookingEscrow — reference implementation of the Booking and Revenue-Sharing
///        contracts (Sec. IV-B/IV-C). Six-state life cycle; stablecoin escrow; integer
///        basis-point split with the remainder assigned to the hotel (exact conservation).
/// @notice No personal data is stored on-chain: a booking is identified by a salted hash
///         of its off-chain record (PDP/GDPR data minimisation).
contract BookingEscrow is AccessControl, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
    uint16 public constant BPS = 10_000;

    enum State { None, Created, PendingPayment, Confirmed, Completed, Cancelled, Refunded }
    enum Mode { Push, Accrue }

    struct Booking {
        address guest;      // slot 0: guest (20 B) + state (1 B) + checkIn (5 B) + checkOut (5 B)
        State state;
        uint40 checkIn;
        uint40 checkOut;
        address hotel;      // slot 1
        uint128 amount;     // slot 2 (stablecoin base units)
        bytes32 recordHash; // slot 3: salted hash of the off-chain booking record
    }

    IERC20 public immutable token;
    address public immutable platform;
    address public immutable affiliate;
    address public immutable sdgFund;
    uint16 public immutable bpsPlatform;
    uint16 public immutable bpsAffiliate;
    uint16 public immutable bpsSdg;
    Mode public immutable mode;

    uint256 public nextId = 1;
    mapping(uint256 => Booking) public bookings;
    mapping(address => uint256) public accrued; // pull-payment balances (Mode.Accrue)

    event BookingCreated(uint256 indexed id, address indexed guest, address indexed hotel, uint128 amount, bytes32 recordHash);
    event PaymentConfirmed(uint256 indexed id);
    event StayCompleted(uint256 indexed id, uint256 hotelShare, uint256 platformShare, uint256 affiliateShare, uint256 sdgShare);
    event BookingCancelled(uint256 indexed id);
    event Refunded(uint256 indexed id, uint256 amount);
    event Withdrawn(address indexed account, uint256 amount);

    error BadState(State expected, State actual);
    error BadShares();
    error NotGuest();
    error TooEarly();
    error NothingToWithdraw();
    error TooLate();
    error ZeroAddress();

    constructor(
        IERC20 token_, address platform_, address affiliate_, address sdgFund_,
        uint16 bpsPlatform_, uint16 bpsAffiliate_, uint16 bpsSdg_, Mode mode_
    ) {
        if (uint256(bpsPlatform_) + bpsAffiliate_ + bpsSdg_ >= BPS) revert BadShares();
        if (address(token_) == address(0) || platform_ == address(0) || affiliate_ == address(0) || sdgFund_ == address(0))
            revert ZeroAddress();
        token = token_;
        platform = platform_;
        affiliate = affiliate_;
        sdgFund = sdgFund_;
        bpsPlatform = bpsPlatform_;
        bpsAffiliate = bpsAffiliate_;
        bpsSdg = bpsSdg_;
        mode = mode_;
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(OPERATOR_ROLE, msg.sender);
    }

    /// Created -> PendingPayment happens atomically in this call (quote issued and held).
    function createBooking(address hotel, uint128 amount, uint40 checkIn, uint40 checkOut, bytes32 recordHash)
        external returns (uint256 id)
    {
        if (hotel == address(0)) revert ZeroAddress();
        if (checkOut < checkIn) revert TooEarly();
        id = nextId++;
        bookings[id] = Booking({
            guest: msg.sender, state: State.PendingPayment, checkIn: checkIn, checkOut: checkOut,
            hotel: hotel, amount: amount, recordHash: recordHash
        });
        emit BookingCreated(id, msg.sender, hotel, amount, recordHash);
    }

    /// PendingPayment -> Confirmed: guest escrows the stablecoin amount.
    function confirmPayment(uint256 id) external nonReentrant {
        Booking storage b = bookings[id];
        if (b.state != State.PendingPayment) revert BadState(State.PendingPayment, b.state);
        if (msg.sender != b.guest) revert NotGuest();
        b.state = State.Confirmed;                                      // effects
        token.safeTransferFrom(msg.sender, address(this), b.amount);   // interaction
        emit PaymentConfirmed(id);
    }

    /// Confirmed -> Completed: operator releases escrow after check-out; revenue split.
    function completeStay(uint256 id) external nonReentrant onlyRole(OPERATOR_ROLE) {
        Booking storage b = bookings[id];
        if (b.state != State.Confirmed) revert BadState(State.Confirmed, b.state);
        if (block.timestamp < b.checkOut) revert TooEarly();
        b.state = State.Completed;

        uint256 amt = b.amount;
        uint256 p = amt * bpsPlatform / BPS;
        uint256 a = amt * bpsAffiliate / BPS;
        uint256 s = amt * bpsSdg / BPS;
        uint256 h = amt - p - a - s; // remainder pattern: exact conservation by construction

        if (mode == Mode.Push) {
            token.safeTransfer(b.hotel, h);
            if (p > 0) token.safeTransfer(platform, p);
            if (a > 0) token.safeTransfer(affiliate, a);
            if (s > 0) token.safeTransfer(sdgFund, s);
        } else {
            accrued[b.hotel] += h;
            accrued[platform] += p;
            accrued[affiliate] += a;
            accrued[sdgFund] += s;
        }
        emit StayCompleted(id, h, p, a, s);
    }

    /// Pull payment for Mode.Accrue (checks-effects-interactions).
    function withdraw() external nonReentrant {
        uint256 amt = accrued[msg.sender];
        if (amt == 0) revert NothingToWithdraw();
        accrued[msg.sender] = 0;
        token.safeTransfer(msg.sender, amt);
        emit Withdrawn(msg.sender, amt);
    }

    /// PendingPayment|Confirmed -> Cancelled (guest; a paid booking only before check-in).
    function cancel(uint256 id) external {
        Booking storage b = bookings[id];
        if (msg.sender != b.guest) revert NotGuest();
        if (b.state != State.PendingPayment && b.state != State.Confirmed) revert BadState(State.Confirmed, b.state);
        if (b.state == State.Confirmed && block.timestamp >= b.checkIn) revert TooLate(); // no cancel after check-in
        if (b.state == State.PendingPayment) b.amount = 0; // unpaid: nothing held in escrow
        b.state = State.Cancelled;
        emit BookingCancelled(id);
    }

    /// Cancelled -> Refunded: full refund of escrow (refund policy is a design parameter).
    function refund(uint256 id) external nonReentrant {
        Booking storage b = bookings[id];
        if (b.state != State.Cancelled) revert BadState(State.Cancelled, b.state);
        uint256 amt = b.amount;
        if (amt == 0) revert NothingToWithdraw();
        b.state = State.Refunded;
        b.amount = 0;
        token.safeTransfer(b.guest, amt);
        emit Refunded(id, amt);
    }
}
