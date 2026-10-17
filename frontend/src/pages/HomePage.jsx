import { HeroSection } from "@/components/home/HeroSection";
import { CategoryTeaser } from "@/components/home/CategoryTeaser";
import { HowItWorks } from "@/components/home/HowItWorks";
import { VendorCta } from "@/components/home/VendorCta";
import { HOME } from "@/constants/testIds";

export default function HomePage() {
  return (
    <div data-testid={HOME.page}>
      <HeroSection />
      <CategoryTeaser />
      <HowItWorks />
      <VendorCta />
    </div>
  );
}
