# AfroVending — Phase 14: Clean Launch Preparation (revised 2026-11-06)

**Owner decision (D-068):** the new marketplace replaces www.afrovending.com as a **CLEAN LAUNCH**.
- **Legacy data migration: Not Required — Clean Launch.**
- No old customers, vendors, products, orders, reviews or credentials are imported, and no migration emails are sent.
- The migration tooling built earlier in Phase 14 was **removed**: the importer, the activation endpoints, the /activate page, the migration admin API and the sample files.
- Nothing was changed in production. DNS was not changed, live payments are off, no launch emails were sent, and the old site is untouched.

## 1. Old website (preserve until the approved cutover)
- **Status on 2026-11-06:** unreachable. The registry points the domain to DigitalOcean's name servers, which refuse to answer for it (lame delegation), and `www` has no records. The domain is registered until 2027-01-16 and is under registrar lock.
- **Probable stack:** a Next.js storefront with a Laravel/MySQL backend on DigitalOcean (evidence in `docs/legacy_site_research/`).
- **Archival backup (LB-A, owner or host task):** before retirement, the DigitalOcean account holder should:
  1. Take a droplet snapshot.
  2. Make a `mysqldump` and zip `storage/app/public`.
  3. Record SHA-256 checksums.
  4. Keep the files in cold storage the owner controls (at least 2 copies; keep for at least 7 years for tax and order records).
  These files are an archive only. They will not be imported.

## 2. Clean-start confirmation (verified in preview)
- **App database:** 1 bootstrap Super Admin, 43 categories (9 top-level plus subcategories), and **0** vendors, products, orders, payments, stores and migrated accounts.
- **Production:** the deployment uses its own database. On first start, the migrations create indexes and categories only. The Super Admin is created by the protected CLI bootstrap; there is no public route.
- **Sample products and vendors** are now shown **only on preview hosts** (`*.preview.emergentagent.com`, localhost). On afrovending.com and the deployed host the catalog starts empty with normal empty states, and the "Preview" announcement bar is hidden.
- **New customers** register normally. **New vendors** go through onboarding and admin approval, then create their own listings.

## 3. Domain, SSL and SEO
| Item | Setup |
|---|---|
| Official host | **https://afrovending.com** (apex) |
| www | `www.afrovending.com` → 301 to the apex. Configure it in the hosting platform's custom-domain flow; the app also redirects in the browser as a fallback. |
| DNS records | Fix the delegation first (see LB-B). Then add the records the platform's custom-domain flow gives you, for both apex and www. Keep the existing MX/TXT email records. Use a 300 s TTL for the cutover. |
| SSL | Issued automatically by the platform when the custom domain is connected. Check both hosts with `curl -I`. |
| FRONTEND_URL (live secret) | Must be `https://afrovending.com`. It is used in the sitemap, email links and the payment return URL. |
| robots.txt | `/robots.txt` blocks /account, /admin, /vendor, /checkout, /cart and /api (allows /api/v1/seo/). Sitemap: `https://afrovending.com/api/v1/seo/sitemap.xml` |
| sitemap.xml | Lists static pages, active products, published stores and `/categories/{slug}` pages. It updates on its own as vendors list products. |
| Metadata / canonical | Every page sets title, description and Open Graph tags. The canonical URL always points to `https://afrovending.com/...` on either host. Products include JSON-LD structured data. |

## 4. Old URL redirects (only to related pages, never to the homepage)
| Old URL | New | Reason |
|---|---|---|
| /about-us, /contact-us, /faqs, /privacy-policy | /about, /contact, /faq, /privacy | Same page |
| **/terms-and-conditions** | /terms | Same document |
| **/return-policy** | /returns-policy | Same policy |
| **/support-topics** | /faq | The help centre is the FAQ |
| **/fashion-products** | /categories/fashion | Same category |
| **/species-products** | /categories/food-groceries-spices | Owner approved 2026-11-06. Active. |
| **/other-fees** | /sell | Owner approved 2026-11-06. Active. |
| **/flash-sales** | none (404) | There's no flash-sale feature yet. Add a redirect when campaigns go live. |
| **/drop-off-warehouse** | none (404) | The service doesn't exist on the new site. |
| /become-a-vendor, /stores, /category, /checkout | /sell, /vendors, /categories, /cart | Same purpose |
| /category/{40 old slugs} | the closest new category | For example hair-care → beauty-hair-care. Unrelated ones (fitness-gear, gardening-outdoor, herbal-supplements, african-music-entertainment, entertainment-accessories, african-health-wellness, traditional-remedies, wellness-accessories) show 404. |
| /product-tag/{tag} | /search?q={tag} | Related search |
| /product/{slug}, /store/{slug} | none (404) | The old listings don't exist in a clean launch. |

These redirects are handled by the 404 page using `/api/v1/redirects/resolve`, which is a browser-side 301 equivalent. Search engines follow these, and the old site's index will drop out over time.

## 5. Launch testing
- The automated suites cover registration, vendor onboarding and approval, product management, cart, checkout with Stripe test payments, fulfillment, refunds, notifications, administrator permissions, and the Phase 13 audit tests.
- `tests/test_phase14_launch.py` covers redirects, the removed migration endpoints, robots and sitemap, and the backup/restore drill.
- The independent testing results for this revision are in iteration_24: 57/57 regression tests plus 26/26 clean-launch tests passed.
- After testing, I fixed the clean-launch interface items it raised: the home page hides empty product and vendor sections, /vendors has an empty state, real vendors are labelled "Verified" instead of "Verified (sample)", the "applications open soon" text and developer phase notes are gone, and a route-level canonical reset stops stale canonicals. Preview hosts are marked noindex. I checked these by screenshot at desktop and mobile widths.

## 6. Backup and rollback
- **New database:**
  - `scripts/backup_db.sh` makes a gzip archive with a SHA-256 checksum and per-collection counts.
  - `scripts/restore_verify.sh` restores into a scratch database and compares the counts. The drill passed.
  - In production, back up every day, copy the backup off the server, and keep 30 daily and 12 monthly copies.
- **Rollback of the cutover:** keep the old DNS records (once they're restored). If a launch-critical check fails within 72 hours:
  1. Put the old records back (about 5 minutes at a 300 s TTL).
  2. Use the platform rollback for app problems.
  Customer data from the window stays in the new database.

## 7. Revised Phase 14 checklist
| # | Task | Status |
|---|---|---|
| Done | Clean-start check, sample data limited to preview, www→apex canonical, robots and sitemap, related-only redirects, backup/restore drill, support runbook | Done (staging) |
| LB-A | Archival backup of the old site (snapshot, MySQL dump, storage) | **Open, owner/host** |
| LB-B | Fix the afrovending.com DNS delegation (zone missing at DigitalOcean, or move the name servers) | **Open, owner** |
| LB-C | Connect apex and www in the platform's custom-domain flow and set FRONTEND_URL live to https://afrovending.com | Open, needs DNS approval |
| LB-D | Stripe Connect enabled, then live payments authorized | **Open, owner approval** |
| LB-E | Every admin enrolls two-step sign-in | Open |
| LB-F | Sending domain verified (SPF/DKIM/DMARC). Launch and marketing emails need your approval | Open |
| LB-G | Legal review of the Terms, Privacy Policy and vendor agreement | Open |
| LB-H | Uptime monitor, plus alerts for 5xx errors and cron failures | Open |
| LB-I | Confirm /species-products and /other-fees redirects | Done (approved and active) |
| LB-J | Launch-week banner "Now open — be one of our first vendors": the Content Admin sets start = launch day, end = +7 days, status active (Admin → Content) | Seeded INACTIVE in production; active in preview for review |
| LB-K | Launch Readiness Checklist in the app (Admin → Launch readiness): track every item above with evidence; record the public launch date only after the approved cutover | Built; the checklist tracks status only |
| LB-L | Founding Vendor badge: vendors approved before launch or within 30 days after the recorded launch (the pre-launch recruitment period counts). Public page /founding-vendors. No fee or ranking benefit | Built |

| Final | Retire the old site, switch DNS, go live publicly | **Requires your explicit approval** |
