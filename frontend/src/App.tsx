import { useQuery } from "@tanstack/react-query";
import Map from "react-map-gl/maplibre";

const BASEMAP = "https://tiles.openfreemap.org/styles/positron";
const US_VIEW = { longitude: -98.5, latitude: 39.5, zoom: 3.6 };

export default function App() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await fetch("/api/health")).json() as Promise<{ status: string }>,
  });

  return (
    <div className="relative h-full w-full">
      <Map initialViewState={US_VIEW} mapStyle={BASEMAP} style={{ width: "100%", height: "100%" }} />
      <div className="absolute left-4 top-4 rounded-lg bg-white/90 px-3 py-2 text-sm shadow">
        API: {health.isPending ? "…" : health.data?.status ?? "offline"}
      </div>
    </div>
  );
}
