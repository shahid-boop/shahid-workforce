/** @type {import('next').NextConfig} */

// `NEXT_OUTPUT=export` switches the dashboard into fully static mode for
// the packaged Windows build (served by FastAPI). Dev/CI builds keep the
// default server mode with the `/api/*` proxy route handlers.
const isStatic = process.env.NEXT_OUTPUT === "export";

const nextConfig = {
  reactStrictMode: true,
  ...(isStatic
    ? {
        output: "export",
        // Emit `<route>/index.html` so FastAPI can serve `/tasks` etc.
        trailingSlash: true,
      }
    : {}),
};

export default nextConfig;
