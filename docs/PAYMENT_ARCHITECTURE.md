# AfroVending Phase 07 — Payment Architecture (REVISED v2, awaiting approval)

Date: 2026-10-22 · Status: APPROVED by owner 2026-10-22, implemented in Phase 07 · Mode: Stripe TEST/SANDBOX only — live payments, live transfers and live dispute adjustments disabled until admin approval.

## 0. Decisions already made by the business
| Topic | Decision |
|---|---|
| Launch scope | US vendors, USD, Stripe Connect |
| Processing fees | Each vendor bears its proportional share of the actual Stripe fee |
| Commission | Default 10%; vendor override → category override → default |
| Payout eligibility | 7 days after confirmed payment (configurable) |
| Lost disputes | Deducted from the responsible vendor's earnings |

## 1. Model: Stripe Connect separate charges and transfers (SC&T)
- **Fit confirmed (Stripe docs):** SC&T is Stripe's model for one customer payment split across several sellers. Platform (US) and connected accounts (US) are in the same region — supported. Future cross-border transfers are supported between US, CA, UK, EEA and CH; other countries need a different setup → country allowlist is configuration, not code.
- **Consequence:** the charge belongs to AfroVending's platform account. Stripe debits the **platform** for processing fees, refunds and disputes. AfroVending allocates those costs to vendors contractually through its own ledger (vendor agreement update required before live launch).
- **Connected accounts:** Express. Connect is **not yet enabled** on the AfroVending sandbox (verified via API). Until the sandbox is claimed and Connect switched on, vendors use **SIMULATED connected accounts**; transfers to them are ledger-only and labelled SIMULATED. Customer card payments use real Stripe test mode. Same code path once Connect is on.

## 2. Money flow
```
Customer ──one payment (PaymentIntent, test mode)──▶ AfroVending platform Stripe balance
                                                        │  Stripe deducts actual processing fee (read from balance transaction)
                                                        │
               Ledger (immutable): per vendor order ──▶ gross items, shipping, tax collected,
                                                        commission, fee allocation, vendor earnings
                                                        │
        day 0–7: PENDING  ──(hold period)──▶ ELIGIBLE ──(account eligible + funds)──▶ TRANSFER (Stripe Transfer,
                                                                                    source_transaction = charge,
                                                                                    transfer_group = order)
                                                        │                                   │
                                     admin/dispute HOLD can stop at any step               ▼
                                                                         Vendor connected account balance
                                                                                   │ Stripe bank payout schedule
                                                                                   ▼
                                                                       PAID (payout.paid webhook) — tracked separately
AfroVending keeps: commission + tax collected (held for remittance, pending tax review)
```

## 3. Commission & processing-fee calculation (all server-side, integer cents)
1. Each order item stores, permanently: rate source (vendor/category/default), rate in basis points, eligible amount, commission cents. Rate changes never touch past items.
2. Eligible amount = item price × qty − allocated discount. Shipping and sales tax excluded.
3. Commission per item = round-half-up(eligible × bps / 10000).
4. Processing fee: taken from the **actual** Stripe balance transaction after payment (no hardcoded rates). Allocated to vendor orders proportionally to each vendor order's charged total (items + shipping + tax) — this covers both the percentage and the fixed part, so the fixed fee is shared, not repeated.
5. Rounding: largest-remainder method — floor each share, hand leftover cents to the largest fractional remainders (ties: higher amount, then vendor id). Sum of allocations always equals the actual fee.
6. Vendor net = items after discount + shipping − commission − fee allocation (± later refunds/adjustments).
7. Tax collected is held by the platform (marketplace-facilitator assumption; configurable, business review required).

### Example (illustrative fee $3.53 — real value comes from Stripe)
| | Vendor A | Vendor B | Total |
|---|---|---|---|
| Items | 60.00 | 40.00 | 100.00 |
| Shipping | 5.00 | 0.00 | 5.00 |
| Tax (estimate rate) | 3.75 | 2.50 | 6.25 |
| Charged | 68.75 | 42.50 | **111.25** (one payment) |
| Commission 10% | 6.00 | 4.00 | 10.00 |
| Fee share (raw) | 2.1815 | 1.3485 | 3.53 |
| Fee allocated (largest remainder) | 2.18 | 1.35 | **3.53** |
| Vendor net | **56.82** | **34.65** | 91.47 |
Platform check: 111.25 − 3.53 fee − 91.47 transfers = 16.25 = 10.00 commission + 6.25 tax held. ✔

Category/vendor override example: Vendor B has a 12% vendor rate → B commission 4.80 (vendor rate wins over a 15% category rate and the 10% default).

## 4. Refund rules
- Admin issues refunds per **vendor order** (full, or selected items/quantity, optional shipping). Other vendors in the same payment are unaffected.
- Customer refund = refunded items + refunded shipping + proportional tax. Single Stripe refund on the payment, idempotency key per refund request; total refunds capped at the vendor order's charged amount.
- Commission returned proportionally: commission × refunded eligible / original eligible.
- Processing fee: Stripe generally does not return fees on refunds; vendor fee allocation stays unless Stripe's refund balance transaction returns fees, then the returned amount is credited back to the vendor.
- Vendor debit = refunded items + refunded shipping − commission returned.
  - Before transfer: reduces pending/eligible balance.
  - After transfer: Stripe transfer reversal for the debit (if connected balance allows), otherwise a **vendor liability** entry recovered from future earnings.
- Example: refund one $20 item from Vendor B (+$1.25 tax) → customer gets 21.25; commission returned 2.00; Vendor B debit 18.00; tax held reduced 1.25. Vendor A unchanged. 18.00 + 1.25 + 2.00 = 21.25 ✔

## 5. Disputes / chargebacks
- Webhook `charge.dispute.created`: Stripe debits platform (amount + actual dispute fee). Hold placed on vendor orders in that payment, limited to the disputed amount; vendors notified with the evidence deadline; vendors can upload evidence.
- Admin attributes responsibility to specific vendor order(s)/items. Unrelated vendors are released; unattributed amounts fall to the platform. Admin can override vendor liability.
- Lost (`charge.dispute.closed` lost): responsible vendor debited for its attributed amount + its share of the dispute fee; insufficient balance → vendor liability recovered from future earnings. Commission on the lost amount is returned to the vendor.
- Won: holds released; any fee Stripe returns recorded as a separate entry.
- Live dispute adjustments disabled until approved.

## 6. Payout workflow
States per vendor order earning: `pending` → `eligible` (7 days after confirmed payment) → `transferred` (Stripe Transfer created) → `paid` (bank payout confirmed). `held` can apply at any pre-transfer step (refund, dispute, fraud, admin reason, documented).
- Release runs on a platform scheduled job (daily) and by admin action. Each release checks: vendor approved & not suspended, connected account `transfers`/`payouts` enabled, country/currency allowed, no hold, positive balance after liabilities, platform funds available.
- Idempotency: Stripe idempotency key = `transfer:{vendor_order_id}:{release_seq}` + unique DB index; a second release is a no-op.
- Timing: SC&T allows delaying transfers, so the 7-day period is enforced by AfroVending. Once transferred, the vendor's **bank payout** follows the connected account's Stripe payout schedule — tracked separately (transfer ≠ money in bank).

## 7. Ledger
Append-only `ledger_entries` (no update/delete API), unique `entry_key` for idempotency. Types: `gross_sale`, `shipping`, `tax_collected`, `discount`, `commission`, `processing_fee_allocation`, `refund`, `commission_reversal`, `fee_return`, `transfer`, `transfer_reversal`, `dispute_hold`, `dispute_release`, `dispute_debit`, `dispute_fee`, `vendor_liability`, `liability_recovery`, `adjustment`, `payout`. Balances are computed from entries. Corrections are new entries.

## 8. Responsibility matrix
| Item | Stripe charges | AfroVending allocates to |
|---|---|---|
| Processing fee | Platform | Vendors, proportionally |
| Refund amount | Platform | Refunding vendor (minus commission returned); tax from platform-held tax |
| Dispute amount + fee | Platform | Responsible vendor (admin-attributed); else platform |
| Negative connected balances | Platform (SC&T) | Vendor liability, recovered from future earnings |
| Commission | — | Platform revenue |

## 9. Backend verification (never trusted to Stripe or browser)
Customer owns the draft order; draft re-priced and unexpired; PaymentIntent amount/currency equal server totals; webhook metadata order id matches; vendor approved; connected account belongs to that vendor and is eligible; admins only for refunds, holds, commission and payout settings (all audit-logged). Orders become paid **only** from a verified webhook or server-side Stripe re-check — never a redirect.

## 10. Safety, future scope, tax/regulatory review
- `STRIPE_MODE=test`; server refuses live keys unless an admin-approved `live_payments_enabled` flag exists (not set in Phase 07).
- Every money field stores currency; commission/fee rules and country allowlist are keyed by currency/country → international vendors later without redesign.
- Card data only in Stripe-hosted fields; no card numbers stored.
- Business review: marketplace-facilitator sales tax (incl. Massachusetts), 1099-K reporting, money transmission (funds stay inside Stripe), vendor agreement & customer terms updates (fees, refunds, chargebacks, negative balances).
