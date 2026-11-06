"""Content safety for reviews, vendor responses and order messages: sanitising, contact/link/payment detection, masking and abuse flags."""
import re
import unicodedata

from afrovending.core.db import db
from afrovending.core.models import utcnow

RULES_KEY = "moderation.rules"
DEFAULT_RULES = {
    "approved_domains": ["afrovending.com"],
    "payment_terms": ["paypal", "venmo", "cash app", "cashapp", "zelle", "western union", "moneygram", "wire transfer", "bank transfer", "bitcoin",
                      "usdt", "gift card", "pay me directly", "pay outside", "off the site", "off-site payment", "off platform", "outside afrovending"],
    "payment_domains": ["paypal.me", "paypal.com", "venmo.com", "cash.app", "zellepay.com", "wise.com", "revolut.me", "buymeacoffee.com"],
    "threat_terms": ["kill you", "hurt you", "i will find you", "find where you live", "burn your", "you will regret", "watch your back", "beat you"],
    "abuse_terms": ["fuck", "shit", "bitch", "bastard", "retard", "idiot", "moron", "dumbass", "asshole", "whore", "slut", "cunt"],
    "spam_terms": ["click here", "free money", "visit my store", "check out my shop", "promo code", "discount code", "earn $", "dm me", "whatsapp me", "telegram"],
}
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2060\ufeff]")
_TAG = re.compile(r"<[^>]{0,500}>")
_ORDER_REF = re.compile(r"\bAV[T]?-[0-9A-F]{4,8}(?:-[0-9A-F]{3,10})?\b", re.I)
_DOT = r"(?:\s*\.\s*|\s*\(\s*dot\s*\)\s*|\s*\[\s*dot\s*\]\s*|\s+dot\s+)"
_EMAIL = re.compile(r"[a-z0-9._%+\-]+\s*(?:@|\(\s*at\s*\)|\[\s*at\s*\])\s*[a-z0-9\-]+(?:" + _DOT + r"[a-z0-9\-]+)*" + _DOT + r"[a-z]{2,}", re.I)
_EMAIL_SPOKEN = re.compile(r"\b[a-z0-9._%+\-]+\s+at\s+[a-z0-9\-]+(?:\s+dot\s+|\s*\(\s*dot\s*\)\s*|\s*\[\s*dot\s*\]\s*)[a-z]{2,}\b", re.I)
_TLDS = "com|net|org|io|co|me|shop|store|biz|info|ly|gg|app|xyz|us|uk|link|site|online|page|top|ca|ng|gh|ke|za"
_URL = re.compile(r"(?:\bhttps?://|\bwww\.)[^\s<>\"']+|\b(?:[a-z0-9\-]+\.)+(?:" + _TLDS + r")\b(?:/[^\s<>\"']*)?", re.I)
_URL_SPOKEN = re.compile(r"\b[a-z0-9\-]{2,}(?:\s*\(\s*dot\s*\)\s*|\s*\[\s*dot\s*\]\s*|\s+dot\s+)(?:" + _TLDS + r")\b", re.I)
_PHONE_RUN = re.compile(r"(?<![A-Za-z0-9])\+?\d[\d\s().\-]{7,}\d(?![A-Za-z])")
_TRACKING_CTX = re.compile(r"(track|tracking|ups|usps|fedex|dhl|parcel)\W*(number|no\.?|#|id)?\W*$", re.I)
_WORD_DIGITS = re.compile(r"\b(?:(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)[\s\-,]*){7,}\b", re.I)
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
CONTACT_MASK, LINK_MASK, PAY_MASK = "[contact details hidden]", "[link hidden]", "[payment details hidden]"


def sanitize(text: str, limit: int = 5000) -> str:
    """Plain text only: strips tags and control characters (React escapes output; emails escape too)."""
    t = unicodedata.normalize("NFKC", text or "")
    t = _TAG.sub("", _CTRL.sub("", t))
    return re.sub(r"[ \t]{3,}", "  ", t).strip()[:limit]


async def rules() -> dict:
    doc = await db.platform_settings.find_one({"key": RULES_KEY})
    return {**DEFAULT_RULES, **((doc or {}).get("value") or {})}


async def save_rules(value: dict, actor_id) -> dict:
    merged = {**DEFAULT_RULES, **value}
    await db.platform_settings.update_one({"key": RULES_KEY}, {"$set": {"value": merged, "updated_at": utcnow(), "updated_by": actor_id},
                                                                "$setOnInsert": {"key": RULES_KEY, "created_at": utcnow()}}, upsert=True)
    return merged


def _host(url: str) -> str:
    h = re.sub(r"^(?:https?://)", "", url.strip().lower()).split("/")[0].split("?")[0].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def _approved(host: str, domains: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).lower().translate(_LEET))


def _terms(text: str, terms: list[str]) -> list[str]:
    n = _norm(text)
    joined = re.sub(r"(?<![a-z])([a-z])[\s.\-_*]+(?=[a-z](?![a-z]))", r"\1", n)
    joined = re.sub(r"(?<![a-z])([a-z])[\s.\-_*]+(?=[a-z](?![a-z]))", r"\1", joined)
    return [t for t in terms if any(re.search(r"(?<![a-z])" + re.escape(t.lower()) + r"(?![a-z])", s) for s in (n, joined))]


def scan(text: str, r: dict) -> dict:
    """Returns masked text plus flags. 'high' = payment redirection or threats (stronger handling)."""
    flags: set[str] = set()
    out = _ORDER_REF.sub(lambda m: m.group(0).replace("-", "\u2011"), text)

    def email(m):
        raw = re.sub(r"\s+|\(\s*at\s*\)|\[\s*at\s*\]", lambda x: "@" if "at" in x.group(0) else "", m.group(0))
        dom = re.sub(_DOT, ".", raw.split("@")[-1], flags=re.I)
        if _approved(dom.lower(), r["approved_domains"]):
            return m.group(0)
        flags.add("email")
        return CONTACT_MASK

    out = _EMAIL.sub(email, out)
    out = _EMAIL_SPOKEN.sub(lambda m: (flags.add("email"), CONTACT_MASK)[1], out)

    def url(m):
        host = _host(m.group(0))
        if _approved(host, r["approved_domains"]):
            return m.group(0)
        if _approved(host, r["payment_domains"]):
            flags.add("payment_link")
            return PAY_MASK
        flags.add("link")
        return LINK_MASK

    out = _URL.sub(url, out)
    out = _URL_SPOKEN.sub(lambda m: (flags.add("link"), LINK_MASK)[1], out)

    def phone(m):
        if _TRACKING_CTX.search(m.string[max(0, m.start() - 30):m.start()]):
            return m.group(0)
        if 10 <= len(re.sub(r"\D", "", m.group(0))) <= 15:
            flags.add("phone")
            return CONTACT_MASK
        return m.group(0)

    out = _PHONE_RUN.sub(phone, out)
    out = _WORD_DIGITS.sub(lambda m: (flags.add("phone"), CONTACT_MASK + " ")[1], out)
    pay = _terms(out, r["payment_terms"])
    if pay:
        flags.add("payment_solicitation")
        for t in pay:
            loose = r"[\s.\-_*]*".join(re.escape(ch) for ch in t if not ch.isspace()) if " " not in t else re.escape(t)
            out = re.sub(loose, PAY_MASK, out, flags=re.I)
    if _terms(text, r["threat_terms"]):
        flags.add("threat")
    if _terms(text, r["abuse_terms"]):
        flags.add("abuse")
    if _terms(text, r["spam_terms"]):
        flags.add("spam")
    out = out.replace("\u2011", "-")
    return {"masked": out, "flags": sorted(flags), "high": bool(flags & {"payment_link", "payment_solicitation", "threat"})}
