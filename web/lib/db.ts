import { Pool } from "pg";

// A single shared pool, reused across requests in the same server runtime.
// In dev with Next.js hot-reload, stash the pool on `global` to avoid
// exhausting connections on every reload.

declare global {
  var __quizcatPool: Pool | undefined;
}

function createPool(): Pool {
  const connectionString =
    process.env.POSTGRES_URL ?? process.env.DATABASE_URL;

  if (!connectionString) {
    throw new Error(
      "Missing POSTGRES_URL (or DATABASE_URL) environment variable. " +
        "Set it to your Vercel Postgres / Neon connection string."
    );
  }

  return new Pool({
    connectionString,
    ssl:
      connectionString.includes("sslmode=") || connectionString.includes("localhost")
        ? undefined
        : { rejectUnauthorized: false },
  });
}

export function getPool(): Pool {
  if (!global.__quizcatPool) {
    global.__quizcatPool = createPool();
  }
  return global.__quizcatPool;
}
