/**
 * Build the dashboard as a fully static export (`out/`) for the packaged
 * Windows build.
 *
 * The `app/api/*` proxy route handlers only make sense behind the Next.js
 * server (dev / normal CI build). In static mode the FastAPI app serves
 * `/api/*` itself, so those files are temporarily moved out of `app/`
 * during the export build and restored afterwards - `output: export`
 * fails the build on dynamic route handlers.
 *
 * Run: `npm run build:static`
 */
import { existsSync, mkdirSync, renameSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url))); // apps/dashboard
const apiDir = join(root, "app", "api");
const stashRoot = join(root, ".static-stash");
const stashApi = join(stashRoot, "api");
const nextBin = join(root, "node_modules", "next", "dist", "bin", "next");

let stashed = false;
let status = 1;

function stashApiDir() {
  // Windows gives EPERM while another process (typically `next dev`)
  // still holds handles on files under app/api - retry briefly, then
  // tell the operator to stop the dev server.
  rmSync(stashRoot, { recursive: true, force: true });
  mkdirSync(stashRoot, { recursive: true });
  const deadline = Date.now() + 5000;
  for (;;) {
    try {
      renameSync(apiDir, stashApi);
      return true;
    } catch (error) {
      if (error && error.code === "EPERM" && Date.now() < deadline) {
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
        continue;
      }
      console.error(
        "\n[static] Could not move app/api out of the way " +
          `(${error && error.code ? error.code : error}).`,
      );
      console.error(
        "[static] Stop the dashboard dev server (`npm run dev`) and retry.",
      );
      rmSync(stashRoot, { recursive: true, force: true });
      return false;
    }
  }
}

try {
  if (existsSync(apiDir)) {
    if (!stashApiDir()) process.exit(1);
    stashed = true;
  }

  const result = spawnSync(
    process.execPath,
    [nextBin, "build"],
    {
      cwd: root,
      stdio: "inherit",
      env: { ...process.env, NEXT_OUTPUT: "export" },
    },
  );
  status = result.status ?? 1;
} finally {
  if (stashed && existsSync(stashApi)) {
    renameSync(stashApi, apiDir);
    rmSync(stashRoot, { recursive: true, force: true });
  }
}

if (status === 0) {
  const outDir = join(root, "out");
  if (existsSync(outDir)) {
    console.log(`\n[static] dashboard exported to ${outDir}`);
  }
}
process.exit(status);
