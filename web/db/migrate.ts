/**
 * Apply db/schema.sql to the configured Postgres database.
 *
 * Usage:
 *   npx tsx db/migrate.ts
 */
import "dotenv/config";
import { readFileSync } from "fs";
import path from "path";
import { Pool } from "pg";

async function main(): Promise<void> {
  const schemaPath = path.resolve(__dirname, "schema.sql");
  const schema = readFileSync(schemaPath, "utf-8");

  const pool = new Pool({
    connectionString: process.env.POSTGRES_URL ?? process.env.DATABASE_URL,
  });

  try {
    await pool.query(schema);
    console.log("Schema applied.");
  } finally {
    await pool.end();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
