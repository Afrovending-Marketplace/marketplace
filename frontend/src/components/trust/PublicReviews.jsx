import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { RatingSummary, ReviewItem } from "@/components/trust/Reviews";

const useReviews = (url) => {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get(url).then((r) => setD(r.data)).catch(() => setD({ summary: { total: 0 }, reviews: [] }));
  }, [url]);
  return d;
};

export const ProductReviews = ({ slug }) => {
  const d = useReviews(`/products/${slug}/reviews`);
  if (!d) return null;
  return (
    <section className="space-y-4 border-t border-av-line pt-8" data-testid="product-reviews">
      <h2 className="text-2xl font-semibold text-av-ink">Customer reviews</h2>
      <RatingSummary s={d.summary} empty="No reviews yet. Reviews come only from customers who bought and received this item." testId="product-rating" />
      {d.reviews.length > 0 && <ul className="divide-y divide-av-line">{d.reviews.map((r) => <ReviewItem key={r.id} r={r} />)}</ul>}
    </section>
  );
};

export const SellerRatings = ({ slug, compact }) => {
  const d = useReviews(`/stores/${slug}/seller-ratings`);
  if (!d) return null;
  return (
    <section className="space-y-3" data-testid="seller-ratings">
      <p className="av-eyebrow">Seller service rating</p>
      <RatingSummary s={d.summary} empty="No seller ratings yet." testId="seller-rating" />
      {!compact && d.reviews.length > 0 && <ul className="divide-y divide-av-line">{d.reviews.slice(0, 10).map((r) => <ReviewItem key={r.id} r={r} />)}</ul>}
    </section>
  );
};
