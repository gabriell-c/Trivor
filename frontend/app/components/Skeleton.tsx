'use client'
import { motion } from 'framer-motion'

interface SkeletonProps {
  className?: string
  variant?: 'rectangle' | 'circle' | 'text'
  count?: number
}

export function Skeleton({ className = '', variant = 'rectangle' }: SkeletonProps) {
  const baseClasses = 'animate-pulse bg-slate-700/50 rounded'

  const variantClasses = {
    rectangle: 'h-4 w-full',
    circle: 'rounded-full',
    text: 'h-4 w-3/4',
  }

  return (
    <motion.div
      initial={{ opacity: 0.5 }}
      animate={{ opacity: [0.4, 0.6, 0.4] }}
      transition={{ duration: 1.5, repeat: Infinity }}
      className={`${baseClasses} ${variantClasses[variant]} ${className}`}
    />
  )
}

export function CardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 ${className}`}>
      <Skeleton className="h-6 w-1/3 mb-4" />
      <Skeleton className="h-4 w-1/2 mb-2" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  )
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4">
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-4 w-1/4" />
        </div>
      ))}
    </div>
  )
}
