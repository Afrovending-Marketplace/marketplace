import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const ProductInfoTabs = ({ product }) => (
  <Tabs defaultValue="details" className="w-full">
    <TabsList className="h-auto flex-wrap justify-start gap-1 rounded-full bg-av-sand p-1">
      {[["details", "Details"], ["shipping", "Shipping & returns"], ["reviews", "Reviews"]].map(([v, l]) => (
        <TabsTrigger key={v} value={v} data-testid={`pdp-tab-${v}`} className="rounded-full px-4 py-2 data-[state=active]:bg-white">{l}</TabsTrigger>
      ))}
    </TabsList>
    <TabsContent value="details" className="mt-6 space-y-4 text-av-ink/80">
      <p>{product.description}</p>
      <ul className="list-disc space-y-1 pl-5 text-sm">{product.details.map((d) => <li key={d}>{d}</li>)}</ul>
    </TabsContent>
    <TabsContent value="shipping" className="mt-6 text-sm text-av-ink/80">
      Shipping methods, delivery estimates, tracking and returns are part of Phase 08. Vendor-specific policies will appear here.
    </TabsContent>
    <TabsContent value="reviews" data-testid="pdp-reviews-empty" className="mt-6 text-sm text-av-ink/80">
      No reviews yet. Verified-purchase reviews arrive in Phase 11.
    </TabsContent>
  </Tabs>
);
