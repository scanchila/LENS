import { cn } from "@/lib/utils"

interface SparklineProps {
  values: number[]
  width?: number
  height?: number
  stroke?: string
  fill?: string
  label?: string
  className?: string
}

export function Sparkline({
  values,
  width = 120,
  height = 28,
  stroke = "currentColor",
  fill = "none",
  className,
}: SparklineProps) {
  if (values.length === 0) {
    return (
      <svg
        width={width}
        height={height}
        className={cn("text-muted-foreground/40", className)}
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="currentColor"
          strokeWidth={1}
          strokeDasharray="2 3"
        />
      </svg>
    )
  }
  const max = Math.max(...values, 0.01)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const step = values.length === 1 ? width : width / (values.length - 1)
  const points = values
    .map((v, i) => {
      const x = i * step
      const y = height - ((v - min) / range) * (height - 2) - 1
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
  const last = values[values.length - 1]
  const lastX = (values.length - 1) * step
  const lastY = height - ((last - min) / range) * (height - 2) - 1
  return (
    <svg width={width} height={height} className={className}>
      <polyline
        fill={fill}
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
      <circle cx={lastX} cy={lastY} r={2} fill={stroke} />
    </svg>
  )
}
