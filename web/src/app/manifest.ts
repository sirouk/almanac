import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ArcLink",
    short_name: "ArcLink",
    description: "Raven deploys autonomous ArcLink agents that run recurring operations.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#080808",
    theme_color: "#080808",
    icons: [
      {
        src: "/marketing/Favicon.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/marketing/Arclink-share.png",
        sizes: "1200x630",
        type: "image/png",
      },
    ],
  };
}
