import { useCallback, useMemo, useState } from "react"

import {
  applyStage,
  DEMO_STAGES,
  initialDemoState,
  type DemoState,
} from "@/components/Board/demoScript"

export interface UseBoardSimulation {
  state: DemoState
  stageIndex: number
  stages: typeof DEMO_STAGES
  currentStage: (typeof DEMO_STAGES)[number] | null
  next: () => void
  prev: () => void
  reset: () => void
  jumpTo: (index: number) => void
  setBriefCandidate: (id: string | null) => void
  setFullReeval: (v: boolean) => void
}

export function useBoardSimulation(): UseBoardSimulation {
  const [state, setState] = useState<DemoState>(initialDemoState())
  const [stageIndex, setStageIndex] = useState(0)

  const next = useCallback(() => {
    setStageIndex((idx) => {
      if (idx >= DEMO_STAGES.length) return idx
      const stage = DEMO_STAGES[idx]
      setState((current) => applyStage(current, stage))
      return idx + 1
    })
  }, [])

  const prev = useCallback(() => {
    setStageIndex((idx) => {
      const target = Math.max(0, idx - 1)
      let s = initialDemoState()
      for (let i = 0; i < target; i++) {
        s = applyStage(s, DEMO_STAGES[i])
      }
      setState(s)
      return target
    })
  }, [])

  const reset = useCallback(() => {
    setStageIndex(0)
    setState(initialDemoState())
  }, [])

  const jumpTo = useCallback((index: number) => {
    const target = Math.max(0, Math.min(DEMO_STAGES.length, index))
    let s = initialDemoState()
    for (let i = 0; i < target; i++) {
      s = applyStage(s, DEMO_STAGES[i])
    }
    setState(s)
    setStageIndex(target)
  }, [])

  const setBriefCandidate = useCallback((id: string | null) => {
    setState((s) => ({ ...s, briefCandidateId: id }))
  }, [])

  const setFullReeval = useCallback((v: boolean) => {
    setState((s) => ({ ...s, fullReeval: v }))
  }, [])

  const currentStage = useMemo(
    () =>
      stageIndex === 0 ? null : DEMO_STAGES[Math.min(stageIndex - 1, DEMO_STAGES.length - 1)],
    [stageIndex],
  )

  return {
    state,
    stageIndex,
    stages: DEMO_STAGES,
    currentStage,
    next,
    prev,
    reset,
    jumpTo,
    setBriefCandidate,
    setFullReeval,
  }
}
