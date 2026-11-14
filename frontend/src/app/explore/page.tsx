import type { Metadata } from "next";
import ExploreView from "@/features/explore/ExploreView";

export const metadata: Metadata = {
  title: "Explore · Earth Trend Detective",
  description: "Click any place on Earth to see what is changing, whether it is real, and whether it is the climate.",
};

export default function ExplorePage() {
  return <ExploreView />;
}
