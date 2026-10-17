// DEVELOPMENT DATA ONLY — fictional sample vendors/products/prices for layout. Not real listings.
// Shapes mirror the Phase 04 entity contracts (categories, vendors, products, product_variants).
const img = (n) => `/images/dev/${n}.jpg`;

export const CATEGORIES = [
  { slug: "fashion", name: "Fashion", image: img("cat-fashion"), blurb: "Ankara, kente, adire and contemporary diaspora design.", subcategories: ["Dresses", "Shirts", "Headwraps", "Accessories"] },
  { slug: "beauty", name: "Beauty", image: img("cat-beauty"), blurb: "Shea, black soap, botanical oils and natural care.", subcategories: ["Skin care", "Hair care", "Body", "Fragrance"] },
  { slug: "food-groceries", name: "Food & Groceries", image: img("cat-food"), blurb: "Spices, grains, teas and pantry staples from home.", subcategories: ["Spices", "Grains & flours", "Teas", "Snacks"] },
  { slug: "home-living", name: "Home & Living", image: img("cat-home"), blurb: "Baskets, textiles and ceramics for warm, storied homes.", subcategories: ["Baskets", "Textiles", "Ceramics", "Wall decor"] },
  { slug: "arts-crafts", name: "Arts & Crafts", image: img("cat-arts"), blurb: "Carvings, paintings and handmade pieces by working artists.", subcategories: ["Carvings", "Masks", "Paintings", "Prints"] },
  { slug: "jewelry", name: "Jewelry", image: img("cat-jewelry"), blurb: "Beadwork, brass and statement pieces.", subcategories: ["Necklaces", "Bracelets", "Earrings", "Rings"] },
  { slug: "electronics", name: "Electronics", image: img("cat-electronics"), blurb: "Gadgets and accessories from diaspora-owned brands.", subcategories: ["Audio", "Phone accessories", "Chargers"] },
  { slug: "books", name: "Books", image: img("cat-books"), blurb: "African and Caribbean authors, history and children's titles.", subcategories: ["Fiction", "History", "Children", "Cookbooks"] },
  { slug: "cultural-products", name: "Cultural Products", image: img("cat-cultural"), blurb: "Instruments, heritage and ceremonial items.", subcategories: ["Instruments", "Ceremonial", "Heritage gifts"] },
];

export const VENDORS = [
  { slug: "adwoa-threads", name: "Adwoa Threads", location: "Accra, Ghana", logo: img("v-2"), banner: img("cat-fashion"), categories: ["fashion", "jewelry", "home-living"], tagline: "Hand-finished textiles and wearable heritage.", story: "Sample vendor story. A small studio pairing traditional weaving with modern tailoring. Replace with the vendor's own words when real storefronts launch.", verified: true },
  { slug: "oyin-pantry", name: "Oyin Pantry", location: "Lagos, Nigeria", logo: img("v-1"), banner: img("cat-food"), categories: ["food-groceries"], tagline: "Spice blends and pantry staples, packed with care.", story: "Sample vendor story. A family pantry business sourcing spices and grains from local markets.", verified: true },
  { slug: "island-roots-botanicals", name: "Island Roots Botanicals", location: "Kingston, Jamaica", logo: img("v-4"), banner: img("cat-beauty"), categories: ["beauty"], tagline: "Small-batch body care from Caribbean botanicals.", story: "Sample vendor story. Body butters and creams made in small batches.", verified: true },
  { slug: "sankofa-crafts-house", name: "Sankofa Crafts House", location: "Houston, USA", logo: img("v-3"), banner: img("cat-arts"), categories: ["arts-crafts", "home-living", "books", "cultural-products"], tagline: "A diaspora gallery of carvings, instruments and books.", story: "Sample vendor story. A diaspora-run shop connecting buyers with continental artisans.", verified: false },
  { slug: "kola-tech", name: "Kola Tech", location: "Atlanta, USA", logo: img("p-elec-1"), banner: img("cat-electronics"), categories: ["electronics"], tagline: "Everyday tech from a diaspora-owned brand.", story: "Sample vendor story. Audio and accessories designed for daily use.", verified: true },
];

const SIZES = ["S", "M", "L", "XL"];
const p = (slug, title, category_slug, vendor_slug, price_minor, images, created_at, extra = {}) => ({
  id: `dev-${slug}`, slug, title, category_slug, vendor_slug, price_minor, currency: "USD", images, created_at,
  is_featured: false, variants: [], is_dev_data: true,
  description: "Sample description for layout purposes. Real product details, materials and care instructions will be written by the vendor.",
  details: ["Sample detail — material", "Sample detail — dimensions", "Sample detail — origin"],
  ...extra,
});

export const PRODUCTS = [
  p("kente-wrap-dress", "Kente Wrap Dress", "fashion", "adwoa-threads", 8900, [img("p-fashion-1"), img("cat-fashion")], "2026-09-02", { is_featured: true, variants: SIZES }),
  p("ankara-print-shirt", "Ankara Print Shirt", "fashion", "adwoa-threads", 6500, [img("p-fashion-2")], "2026-10-10", { variants: SIZES }),
  p("raw-shea-butter", "Raw Whipped Shea Butter", "beauty", "island-roots-botanicals", 1800, [img("p-beauty-1"), img("cat-beauty")], "2026-08-20", { is_featured: true, variants: ["4 oz", "8 oz"] }),
  p("coconut-body-cream", "Coconut Body Cream", "beauty", "island-roots-botanicals", 2200, [img("p-beauty-2")], "2026-10-12", { variants: ["8 oz"] }),
  p("suya-spice-blend", "Suya Spice Blend", "food-groceries", "oyin-pantry", 1200, [img("p-food-1")], "2026-09-15", { is_featured: true, variants: ["100 g", "250 g"] }),
  p("market-spice-sampler", "Market Spice Sampler", "food-groceries", "oyin-pantry", 3400, [img("p-food-2"), img("cat-food")], "2026-10-14"),
  p("woven-wall-basket-set", "Woven Wall Basket Set", "home-living", "sankofa-crafts-house", 7500, [img("p-home-1"), img("cat-home")], "2026-09-01", { is_featured: true, variants: ["Set of 3", "Set of 5"] }),
  p("bolga-market-basket", "Bolga Market Basket", "home-living", "sankofa-crafts-house", 4800, [img("p-home-2")], "2026-08-11"),
  p("heritage-adire-throw", "Heritage Adire Throw", "home-living", "adwoa-threads", 6800, ["/images/weaving.jpg"], "2026-10-08"),
  p("carved-wood-figurines", "Carved Wood Figurines", "arts-crafts", "sankofa-crafts-house", 12000, [img("p-arts-1")], "2026-07-30", { is_featured: true }),
  p("hand-carved-mask", "Hand-Carved Wooden Mask", "arts-crafts", "sankofa-crafts-house", 9500, [img("cat-arts")], "2026-10-05"),
  p("beaded-statement-necklace", "Beaded Statement Necklace", "jewelry", "adwoa-threads", 4200, [img("cat-jewelry")], "2026-09-20", { is_featured: true }),
  p("beaded-cuff-set", "Beaded Cuff & Ring Set", "jewelry", "adwoa-threads", 2400, [img("p-jewelry-2"), img("p-jewelry-1")], "2026-10-15"),
  p("studio-wireless-headphones", "Studio Wireless Headphones", "electronics", "kola-tech", 14900, [img("p-elec-1"), img("cat-electronics")], "2026-10-01", { variants: ["Black", "Gold"] }),
  p("diaspora-reading-bundle", "Diaspora Reading Bundle", "books", "sankofa-crafts-house", 5600, [img("p-books-1"), img("cat-books")], "2026-09-25"),
  p("djembe-hand-drum", "Djembe Hand Drum", "cultural-products", "sankofa-crafts-house", 15000, [img("cat-cultural"), img("p-cultural-1")], "2026-10-11", { is_featured: true, variants: ["Small", "Medium"] }),
];
