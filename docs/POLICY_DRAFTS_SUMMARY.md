# AfroVending Policy Drafts — Review Summary (2026-11-09)

**Status of all seven policies: Version 1 — Draft — Pending Legal Review.** None is approved or published. The public pages show "This policy is being finalised". The drafts are not legal advice.

Where to review and edit: **Admin → Policy management** (`/admin/policies`). Source drafts are in `backend/afrovending/policies/*.md`.

## Policy Management workflow (implemented)
- **Statuses:** Draft → Pending Legal Review → Approved → Published → Archived.
- **Version history:** each version keeps its number, effective date, change summary, an event history (who, when, note) and the record of who accepted it.
- **Content admins:**
  - create drafts and edit unpublished drafts;
  - submit drafts for legal review;
  - see feedback.
- **Content admins can't:** approve, classify, publish or archive.
- **Super Admin only** (two-step sign-in required):
  - request changes;
  - record legal approval: reviewer name, firm, review date and notes, plus a required confirmation that an external review was actually completed;
  - classify a change as Material or Non-material, and set the effective date;
  - publish, which requires typing PUBLISH, and archive.
- **Version locking:** approved and published versions can't be edited. Changes need a new draft.
- **Publishing:** the current published version stays public until its replacement is published, then it is archived automatically.
- **Audit log:** every edit, submission, approval, publication, archive and acceptance is recorded.

## Acceptance and enforcement (implemented, server-side)
**Who accepts what:**

| Who | Policies they accept |
|---|---|
| Customers | Terms of Service and Privacy Policy (the Privacy Policy is an acknowledgment, not consent) |
| Vendors | Vendor Agreement and Prohibited Products Policy |

**When:**
- At registration, through an unchecked checkbox.
- At vendor application, through an unchecked checkbox.
- Again after any first publication or **Material** change, through a sign-in prompt with an unchecked box, a change summary and a link to the policy.
- Closing the prompt does not count as acceptance.

**Each acceptance record** stores the user, policy, version, version ID, effective date, time, IP address, user agent and context.

**Effect of an outstanding acceptance:**
- Customers can't check out.
- Vendors can't submit new products, accept new orders, be approved, or receive new orders in checkout.
- Existing orders, refunds and disputes keep working.

**Production pre-launch lock** (APP_ENV=production): until the required policies are published, the following are refused (503 policies_unavailable):

| Activity | Policies that must be published |
|---|---|
| Registration | Terms, Privacy |
| Vendor application, approval and product submission | Vendor Agreement, Prohibited Products |
| Checkout | Terms, Privacy, Shipping, Returns |
| Contact form | Privacy |

The lock does not apply in preview, so testing can continue.

**Launch Day Checklist:** seven new automatic items, `policy_<slug>`. Each shows "Legal approval: yes/no · Published: yes/no". An item turns Verified only once a version with a recorded legal review is published.

## Important clauses by policy
1. **Terms of Service:**
   - AfroVending is the platform operator and Vendors are the sellers; users must be 18+ and in the U.S.
   - Orders split into vendor orders; payment counts only once confirmed by Stripe.
   - Customers can cancel before the vendor accepts; escalation to AfroVending.
   - Reviews limited to verified purchases; marketing only with opt-in.
   - Massachusetts law, with M.G.L. c. 93A rights preserved.
   - Material-change re-acceptance.
2. **Privacy Policy:**
   - Lists the data collected, including Stripe-only card handling.
   - No sale or sharing of data for cross-context advertising.
   - Analytics only with consent; marketing only with opt-in.
   - Rights requests through the account or by email; 30-day error-log retention.
   - Massachusetts 93H breach-notice language.
3. **Vendor Agreement:**
   - Onboarding and approval; Founding Vendor badge has no fee or ranking effect.
   - Listing review, handling times, pickup, and the 48-hour return response.
   - Plans: Starter $0/10%, Growth $24.99/7%, Premium $49.99/5%. **Paid plans are marked not yet purchasable.**
   - Commission order: vendor-specific rate, then category rate, then plan rate.
   - Stripe Connect payouts **marked not yet operational**; 7-day hold; chargebacks and negative balances; immutable ledger.
   - Restricted selling while acceptance is outstanding.
4. **Shipping & Delivery Policy:**
   - Each vendor ships separately; U.S. only; vendor-set options.
   - Handling time in business days (default 3); tracking and partial shipments.
   - Pickup appointments within 14 days.
5. **Returns & Refunds Policy:**
   - Free cancellation before the vendor accepts.
   - 14-day return window after delivery or pickup; 48-hour vendor response, then escalation.
   - Refunds to the original payment method; refunded unshipped units are cancelled.
   - Partial refunds; chargeback guidance.
6. **Cookie Policy:**
   - Essential cookies (access_token 15 min, refresh_token 7 days, cart, consent record).
   - Optional analytics, off by default; **third-party analytics stated as not currently enabled**; no advertising cookies.
7. **Prohibited Products Policy:**
   - 20 prohibited categories, and 12 restricted categories needing prior approval (food, cosmetics, supplements, CBD (not at launch), children's products, wildlife materials, artefacts, blades and others).
   - Enforcement: listing removal, notice, suspension, 14-day appeal, audit log.

## Unresolved questions for legal counsel
1. Business address, county for venue, optional phone number, and confirmation of the state of organization (shown as placeholders).
2. **Seller of record and sales tax:** marketplace-facilitator obligations in Massachusetts and other states, and how tax is shown at checkout.
3. Whether to use arbitration and a class-action waiver (provider, opt-out window, small claims), for consumers and for vendors.
4. The advance-notice period for material changes (Terms, Vendor Agreement), and whether a notice email is required. Production email is still off.
5. **Privacy:**
   - state privacy-law applicability thresholds (CCPA/CPRA and others), and response timelines;
   - whether to honour Global Privacy Control signals;
   - a Massachusetts 201 CMR 17.00 written information security program;
   - the final list of service providers.
6. Record retention period for order and financial records (shown as "e.g. 7 years").
7. Age threshold (18+) and the COPPA approach.
8. A DMCA designated agent and its registration.
9. Commission base, whether Stripe processing fees pass to vendors, chargeback fee pass-through, the fee-change notice period (shown as 30 days) and the discrepancy reporting window (shown as 60 days).
10. Return shipping cost for change-of-mind returns, the non-returnable items list, original-shipping refunds, how long to wait before uncollected pickup orders are handled, and Massachusetts refund-disclosure rules (940 CMR 3.13).
11. The FTC Mail Order Rule (16 CFR 435): delay notices and how responsibility is split between AfroVending and vendors.
12. **Stripe restricted-business review** for tobacco, alcohol, adult items, supplements, CBD, spiritual items with claims, collectible currency and gift cards.
13. Vendor insurance requirements and limitation-of-liability carve-outs.
14. Whether referral-attribution storage is essential or optional.

## Not implemented / not enabled (by design)
- No policy is approved or published, and the legal checklist items stay Blocked.
- No notification emails are sent for policy changes; production email stays disabled until approved.
- Live orders, DNS and deployment are unchanged.
