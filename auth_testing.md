# Auth testing playbook (AfroVending Phase 02)

1. Mongo: `db.users.findOne({roles:"super_admin"},{password_hash:1})` hash starts with `$2b$`. Indexes: users.email unique, sessions.expires_at TTL, auth_tokens.token_hash unique + expires_at TTL, rate_limits.key unique + TTL.
2. API (must use HTTPS public URL — cookies are Secure, SameSite=None):
   curl -c c.txt -X POST $URL/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"afrovending.online@gmail.com","password":"<see test_credentials.md>"}'
   curl -b c.txt $URL/api/v1/auth/me
3. Test users: `delivered+<tag>@resend.dev`, name prefix `TEST_`. Email provider rate-limits bursts (429) — registration still succeeds with verification_email_sent=false.
4. Login lockout: 5 failures per IP+email → 429 for 15 min (clear `rate_limits` collection to reset during tests).
5. Requests with a foreign `Origin` header on POST/PUT/PATCH/DELETE are rejected with 403.
