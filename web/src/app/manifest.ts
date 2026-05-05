import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ArcLink",
    short_name: "ArcLink",
    description: "Private AI infrastructure with Raven as the launch guide.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#080808",
    theme_color: "#080808",
    icons: [
      {
        src: "/brand/raven/raven_pfp.webp",
        sizes: "512x512",
        type: "image/webp",
        purpose: "maskable",
      },
      {
        src: "/brand/raven/raven_card.webp",
        sizes: "512x512",
        type: "image/webp",
      },
    ],
  };
}
