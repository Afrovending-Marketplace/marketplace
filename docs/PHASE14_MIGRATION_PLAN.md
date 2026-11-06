# AfroVending — Phase 14: Legacy Migration & Production Launch Preparation (2026-11-06)

**Status: PREPARED, NOT EXECUTED.** Nothing was migrated into the app database. DNS was not changed, live payments are off, nothing was published to production, and no emails went to customers or vendors. The old site and its database have not been touched.

## 1. Current website status (checked 2026-11-06)
| Check | Result |
|---|---|
| `afrovending.com` (apex) | **Does not resolve (SERVFAIL).** The registry delegates the domain to `ns1/ns2/ns3.digitalocean.com`, but DigitalOcean **refuses** queries for it (lame delegation). The zone is missing from the DigitalOcean account, or the account is gone. |
| `www.afrovending.com` | A separate DigitalOcean zone answers for it, but it has **no A/AAAA/CNAME record**, so there is no address. |
| HTTP/SSL | Not reachable on either hostname, so the certificate can't be checked. |
| Registration (RDAP, Verisign) | Registered 2021-01-16 and **expires 2027-01-16**. Status: client delete/renew/transfer/update prohibited (registrar lock). DNSSEC: not signed. |
| Last public copy | The Wayback Machine snapshot from 2026-02-09 shows the site was online then (title "Afrovending Online Marketplace"). |

**Conclusion:** the live site is currently down for everyone. Shoppers can't reach it, and no website data can be read from it until hosting and DNS are restored, or until you get the exports directly from the hosting account or the developer.

## 2. Platform identification (from the archived pages, not confirmed)
- The storefront is **Next.js** (`/_next/static/chunks/…`, Turbopack build). It is a custom build, not WordPress, Shopify, Wix or Squarespace.
- Images are served from `/storage/categoryImages/…` and `/storage/storeBanners/…`. This is the standard **Laravel** public-storage layout, so the backend is most likely Laravel with a **MySQL/MariaDB** database. Hosting was on DigitalOcean.
- Public URL patterns (from 88 archived URLs): `/product/{slug}`, `/category/{slug}` (43 categories), `/store/{slug}`, `/stores`, `/product-tag/{tag}`, `/shop`, `/flash-sales`, `/about-us`, `/contact-us`, `/faqs`, `/privacy-policy`, `/terms-and-conditions`, `/return-policy`, `/other-fees`, `/drop-off-warehouse`, `/support-topics`, `/become-a-vendor`, `/login`, `/register`, `/forgot-password`, `/cart`, `/checkout`.
- Evidence is saved in `/app/migration/research/` (archived home page and URL list).

**Recommended way to get the data:** ask whoever runs the DigitalOcean droplet (or the original developer) for:
1. A full **mysqldump** of the old database.
2. A zip of the **storage/app/public** folder (images).
3. The CSV files below.

I can build the CSV files from the SQL dump myself once I can see its tables. If no export is possible, I'll propose a **read-only API account** on the old backend for your approval; that hasn't been built.

## 3. Export checklist — files I need (CSV, UTF-8, with a header row; JSON arrays also accepted)
Put the files in one folder. Required columns are in **bold**. Leave out any column you don't have.

| File | Columns | Notes |
|---|---|---|
| categories.csv | **legacy_id, name**, slug, parent_legacy_id, map_to_slug | `map_to_slug` merges a category into an existing one on the new site (fashion, beauty, food-groceries, home-living, arts-crafts, jewelry, electronics, books, cultural-products). |
| customers.csv | **legacy_id, email, name**, phone, email_verified, status, created_at, marketing_opt_in | **No passwords or password hashes.** marketing_opt_in is stored for review only. Nobody is subscribed automatically. |
| vendors.csv | **legacy_id, owner_email, store_name**, owner_name, slug, description, phone, city, region, country, status, created_at, logo_url, banner_url | The owner account is matched by email. **No bank, card or Stripe credentials.** |
| products.csv | **legacy_id, vendor_legacy_id, category_legacy_id, title**, slug, description, status, tags (separated by \|), image_urls (separated by \|), created_at, sku, price, stock | sku, price and stock are needed only when a product has no variants. |
| variants.csv | **legacy_id, product_legacy_id, sku, price**, option_names (e.g. Size\|Color), option_values (e.g. M\|Red), stock, status | Prices are decimal USD, e.g. 12.50. |
| addresses.csv | **legacy_id, customer_legacy_id, full_name, line1, city, country**, label, line2, region, postal_code, phone, is_default | |
| orders.csv | **legacy_id, order_number, customer_legacy_id, total, placed_at**, vendor_legacy_id, status, currency, subtotal, shipping, tax, discount | Historical records only. |
| order_items.csv | **order_legacy_id, title, quantity, unit_price**, product_legacy_id, variant_legacy_id, sku | |
| wishlists.csv | **customer_legacy_id, product_legacy_id**, created_at | Optional. |
| redirects.csv | **from_path, to_path** | Optional extra 301 redirects. |
| legacy_urls.txt | one old URL per line | Optional. Used to list old URLs that have no redirect yet. |
| images/ folder | the `storage/app/public` tree | `image_urls` like `/storage/products/x.png` are read from this folder. |

**Do not send:** passwords or hashes, card data, bank details, Stripe or PayPal keys, admin accounts, or session tokens.

**Not imported automatically:**
- Reviews: their purchases can't be re-verified, so they would be held for your decision rather than published.
- Financial ledgers and payouts: these stay on the old system. Old orders are kept as read-only history.

## 4. Field-by-field mapping
| Legacy | New collection.field | Rule |
|---|---|---|
| customers.email | users.email | Lower-cased and validated. Invalid → reconciliation list, not imported. |
| customers.name / phone / created_at | users.name / phone / created_at | |
| customers.email_verified | users.email_verified_at | Set only if the old site verified it. Activating the account also verifies the email. |
| (password) | users.password_hash = **null** | `migration.activation_required = true` |
| customers.marketing_opt_in | users.migration.legacy_marketing_consent | users.marketing_opt_in is always **false**. |
| any admin or role flag | — | **Ignored.** Roles come only from the data: customer, plus vendor if they own a store. |
| vendors.* | vendors {slug, name, status active/suspended, owner_user_id} + vendor_stores {display_name, description, location, status} | Stores are imported as **draft**. `--publish-active` publishes stores that were live on the old site. |
| categories.* | categories (mapped by slug or `map_to_slug`, otherwise created) | |
| products.* | products {title, description, category, vendor_id, owner_user_id, slug (old slug kept when free), status draft/active, price_min/max, in_stock, tags, history} | |
| variants.* | product_variants {sku (unique), options, label, price_minor, status} + inventory {quantity_on_hand, quantity_reserved 0} | Decimal → cents with exact arithmetic. |
| products.image_urls | legacy_image_queue → files + product_images (WebP, EXIF removed) | Run with `--fetch-images --images-dir`. |
| addresses.* | addresses | |
| orders + order_items | **legacy_orders** (read_only) | A separate collection. No payment, ledger, payout or notification records are created. |
| wishlists.* | wishlists, with the reference price set to the current price | So no false "price drop" appears on day one. |
| old URLs | legacy_redirects {from_path → to_path, 301} | |

Every imported record carries `migration.source = legacy_afrovending` and `migration.legacy_id`. Re-running the import updates in place, so it is idempotent.

## 5. Import tool (staging only)
```
cd /app/backend
python -m afrovending.legacy.importer --source /path/to/export --dry-run            # validate only, writes nothing
python -m afrovending.legacy.importer --source /path/to/export                       # into <DB_NAME>_migration_staging
python -m afrovending.legacy.importer --source /path/to/export --fetch-images --images-dir /path/to/storage
```
- It refuses to write into the app database unless run with `--allow-live-db`. That flag must only be used after your migration approval.
- Each run writes a JSON report to `/app/migration/reports/`. The report has per-file counts, errors (file, row, field, reason), warnings, a reconciliation list, verification checks and account-activation readiness.

### Dry run on sample data (`/app/migration/sample_export`, labelled TEST, @example.com)
- Dry run: no writes. It caught all 5 errors planted in the sample files: an unknown vendor, an unknown category, a bad SKU, a negative price and a duplicate order number. It also caught 1 invalid email, 1 duplicate email (merged) and 1 order whose totals don't add up.
- Staging import: 4 accounts, 2 vendors and stores, 3 categories, 3 products, 4 variants with inventory, 2 historical orders, 1 address, 1 wishlist entry, 15 redirects and 1 image queued.
- Verification: 0 products without a vendor, 0 owner mismatches, 0 price mismatches, 0 variants without inventory, 0 admin roles and 0 passwords on migrated accounts.
- Re-runs: the 2nd and 3rd runs changed nothing (0 created, 0 updated). The import is idempotent.
- Old URLs: 59 archived URLs (mostly the 43 old categories) still need a mapping or redirect decision.
- **The real dry run waits for your files.**

## 6. Account migration and activation
- Migrated accounts have no password. Login fails with the normal "Incorrect email or password" message, which doesn't reveal whether the account exists.
- `/activate` page and `POST /api/v1/auth/activation/request`:
  - Always gives the same reply, so it doesn't reveal whether an email exists.
  - Rate-limited to 10 per hour per IP and 3 per hour per email.
  - Sends one **24-hour, single-use** link. Only the SHA-256 hash of the token is stored, and a new link replaces the old one.
- `POST /api/v1/auth/activation/complete`:
  - Requires a strong password, hashed with the existing method.
  - Rejects links that are used, expired or replaced.
  - On success it verifies the email, signs out all sessions and records an audit entry.
- Bulk sending (Super Admin only, admin two-step sign-in required):
  - `GET /api/v1/admin/migration/report` shows the readiness counts.
  - `PUT /admin/migration/activation-approval` needs the exact text "SEND ACTIVATION EMAILS".
  - `POST /admin/migration/activation-batch` sends at most 200 per call. Each account is claimed atomically, gets one email, failed sends are retried, and every send is logged (`migration_activation_log`) and audited.
  - **The approval is OFF.** Tokens are created only at sending time.
- Reconciliation types:
  - `invalid_email`: not imported.
  - `duplicate_email`: merged into one account; you review it.
  - `existing_account`: linked by email, and its password is left untouched.
  - `admin_email_conflict`: legacy records are not attached; manual review.
- Tests: test_phase14_migration 7/7. They cover activation, expiry, reuse, enumeration, the approval gate and Super-Admin-only access.

## 7. URL preservation
- `/product/{slug}` → `/products/{slug}`, `/category/{slug}` → `/categories/{slug}`, `/store/{slug}` → `/store/{slug}`.
- `/product-tag/{tag}` → `/search?q=tag`.
- Fixed pages: /about-us→/about, /contact-us→/contact, /faqs→/faq, /privacy-policy→/privacy, /become-a-vendor→/sell, /stores→/vendors, /category→/categories, /checkout→/cart.
- These work today in the browser: the 404 page checks `/api/v1/redirects/resolve` and redirects.
- **At cutover,** the frontend host should also send real **server-side 301s** from the `legacy_redirects` list (export it as CSV). Search engines need real 301s.
- **Needs your decision:** /terms-and-conditions, /return-policy, /other-fees, /drop-off-warehouse, /support-topics, /flash-sales (sample mapped to /shop), /species-products and /fashion-products.

## 8. Backups
- **New marketplace:** `scripts/backup_db.sh` makes a gzip mongodump with a SHA-256 file and per-collection counts. `scripts/restore_verify.sh <archive>` checks the checksum, restores into a scratch database, compares every collection's count and then drops the scratch database.
  - Drill on 2026-11-06: **PASS** (67 collections, 14,934 documents).
  - Backups are stored in `/app/backups` and excluded from git. For production, copy them off the server every day; keep 30 daily and 12 monthly copies.
- **Old site: NOT backed up yet (blocker M1).** Before anything else, the DigitalOcean account owner must:
  1. Take a droplet snapshot.
  2. Make a mysqldump.
  3. Zip the storage folder.
  4. Send the SHA-256 checksums.
  Nothing on the old site will be deleted.

## 9. Production configuration check (preview environment)
| Item | Status |
|---|---|
| Secrets | JWT_SECRET, WEBHOOK_CRON_SECRET, ADMIN_*, FRONTEND_URL and APP_ENV each have separate live and test values. Email is the managed key. Stripe is the **sandbox** (claim it to go live). No secrets are in the code. |
| Payments | STRIPE_MODE is test. Connect is not enabled, so payouts are **SIMULATED**. **Live payments are OFF until you authorize them.** |
| Domain / SSL | Not connected. The domain's DNS is broken (section 1). SSL is issued automatically when the custom domain is connected at deploy time. |
| Email | Emergent managed email works. Branded sending from afrovending.com needs SPF, DKIM and DMARC records. Outside production, email only goes to an allowlist. |
| Monitoring | `/api/v1/health` (includes the database). Every request is logged with a request id. Audit logs exist. Cron results are kept in the cron run records. **An external uptime monitor and cron-failure alerts still need setting up (blocker M5).** |

## 10. DNS cutover and rollback plan
1. **T-7 days:** fix the DNS hosting (see M2). Recreate the zone at DigitalOcean, or move the nameservers to the new DNS host. Lower the TTL to 300 s. Record every existing record, especially MX and TXT for email.
2. **T-3 days:** get your sign-off on the final migration dry run. Take a verified backup of both the old and new systems.
3. **T-1 day:** freeze writes on the old site (maintenance mode). Run the final import with `--allow-live-db --publish-active` (needs your approval). Fetch images. Load the server-side redirects. Run the acceptance tests on the staging URL.
4. **T0:** connect `afrovending.com` and `www` to the new deployment through the platform's custom-domain flow. Wait for SSL to be issued. Check the redirects, sign-in, checkout (test mode) and email.
5. **T+1 hour:** watch health checks, the 5xx rate and the activation page. Bulk activation emails go out only after your separate approval.
6. **Rollback** (within 72 h, if a launch-critical check fails): point DNS back to the old host's records (kept from step 1; TTL 300 s, so about 5 minutes), take the old site out of maintenance mode, and keep the new database for analysis. Orders placed on the new site during the window are exported and handled manually.

## 11. Acceptance tests
- **Done on staging:** buyer, vendor and administrator flows were covered in Phases 06–13. The latest regressions pass: phase07, phase08, phase12, phase13 audit and wishlist.
- Phase 14: migration and activation 7/7, the backup/restore drill, and the wishlist price display.
- The **final** acceptance run happens on staging with the migrated data, after your files arrive.

## 12. Launch checklist (each item needs your approval)
| # | Item | Owner | Status |
|---|---|---|---|
| M1 | Snapshot and back up the old site (droplet, MySQL, storage) | You / host | **Open** |
| M2 | Fix the afrovending.com DNS (lame delegation; www has no records) | You / registrar | **Open** |
| M3 | Provide the export files (section 3) | You | **Open** |
| M4 | Approve the migration plan, then review the real dry-run report and reconciliation list | You | **Open** |
| M5 | Uptime monitor plus alerts for 5xx errors and cron failures | Platform | **Open** |
| M6 | Every admin enrolls two-step sign-in | Admins | **Open** |
| M7 | Verify the sending domain (SPF/DKIM/DMARC), then approve activation emails | You | **Open** |
| M8 | Enable Stripe Connect and authorize live payments | You | **Open** |
| M9 | Legal review of the Terms, Privacy Policy and vendor agreement | You / counsel | **Open** |
| M10 | Decide the unmapped legacy URLs | You | **Open** |
| M11 | Final import into production and DNS cutover | You | **Blocked by M1–M10** |
| Done | Import tool, activation flow, redirects, backup and restore drill, wishlist price display | — | Built and tested in staging |
