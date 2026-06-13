import { listTests } from "@/lib/queries";
import Dashboard from "@/components/Dashboard";

export const dynamic = "force-dynamic";

export default async function Home() {
  const tests = await listTests();
  return <Dashboard tests={tests} />;
}
