import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface TrendChartProps {
  data: Array<{ date: string; value: number; label?: string }>;
  type?: 'line' | 'bar';
  color?: string;
  dataKey?: string;
  xAxisKey?: string;
}

export function TrendChart({
  data,
  type = 'line',
  color = '#34d399',
  dataKey = 'value',
  xAxisKey = 'date'
}: TrendChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-zinc-500 text-sm">
        No data available
      </div>
    );
  }

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-zinc-900 border border-white/20 px-3 py-2 rounded">
          <p className="text-xs text-zinc-400 mb-1">{payload[0].payload[xAxisKey]}</p>
          <p className="text-sm text-white font-medium">
            {payload[0].payload.label || payload[0].value}
          </p>
        </div>
      );
    }
    return null;
  };

  const ChartComponent = type === 'line' ? LineChart : BarChart;
  const DataComponent = type === 'line' ? Line : Bar;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ChartComponent data={data} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey={xAxisKey}
          stroke="#71717a"
          style={{ fontSize: '11px', fill: '#71717a' }}
          tickLine={false}
        />
        <YAxis
          stroke="#71717a"
          style={{ fontSize: '11px', fill: '#71717a' }}
          tickLine={false}
        />
        <Tooltip content={<CustomTooltip />} />
        <DataComponent
          type={type === 'line' ? 'monotone' : undefined}
          dataKey={dataKey}
          stroke={color}
          fill={color}
          strokeWidth={2}
          dot={type === 'line' ? { fill: color, r: 3 } : undefined}
          activeDot={type === 'line' ? { r: 5 } : undefined}
        />
      </ChartComponent>
    </ResponsiveContainer>
  );
}
