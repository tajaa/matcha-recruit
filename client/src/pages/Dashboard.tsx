import { Card } from '../components/Card';

export function Dashboard() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Dashboard</h1>
          <p className="text-sm text-zinc-500 mt-1">Welcome to your client dashboard</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Card className="p-6">
          <h3 className="text-lg font-medium text-white mb-2">Overview</h3>
          <p className="text-sm text-zinc-400">
            Welcome to the Matcha Recruit client dashboard. Select an option from the sidebar to get started.
          </p>
        </Card>
      </div>
    </div>
  );
}

export default Dashboard;
