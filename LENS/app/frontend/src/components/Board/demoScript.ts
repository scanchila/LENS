import type {
  Candidate,
  DiffEvent,
  DossierTicket,
  YcRfsItem,
  YcScore,
} from "./types"

let _idCounter = 0
const nextId = (prefix: string) => `${prefix}-${++_idCounter}`

export interface DemoStage {
  key: string
  label: string
  narration: string
  apply: (state: DemoState) => DemoState
}

export interface DemoState {
  candidates: Candidate[]
  events: DiffEvent[]
  dossierTickets: DossierTicket[]
  ycScore: YcScore
  ycRevealed: boolean
  fullReeval: boolean
  briefCandidateId: string | null
}

const YC_RFS_ITEMS: YcRfsItem[] = [
  {
    id: "rfs-001",
    title: "AI co-scientist tools",
    description: "Tools that act as research collaborators, not just retrievers",
    tags: ["ai", "research"],
  },
  {
    id: "rfs-002",
    title: "Compliance copilots for SMBs",
    description: "Vertical compliance tooling for sub-$50M SMBs",
    tags: ["fintech", "vertical-saas"],
  },
  {
    id: "rfs-003",
    title: "Real-time data quality for AI training",
    description: "Pipelines that surface and fix bad training data live",
    tags: ["ai-infra", "devtools"],
  },
  {
    id: "rfs-004",
    title: "Voice-first ops for field workers",
    description: "Voice-only field workflows for trades and logistics",
    tags: ["ai", "vertical"],
  },
  {
    id: "rfs-005",
    title: "Browser-native LLM agents",
    description: "Agents running locally in the browser with tab-level context",
    tags: ["ai", "browser"],
  },
  {
    id: "rfs-006",
    title: "Synthetic-data marketplaces",
    description: "Marketplaces for high-quality, licensed synthetic data",
    tags: ["ai-infra", "data"],
  },
  {
    id: "rfs-007",
    title: "Personal RAG for knowledge workers",
    description: "Private retrieval over a person's full document trail",
    tags: ["ai", "productivity"],
  },
  {
    id: "rfs-008",
    title: "Provenance-first content pipelines",
    description: "Citations, confidence, and challenge by default",
    tags: ["ai", "media"],
  },
  {
    id: "rfs-009",
    title: "AI-native CRMs for studios",
    description: "Pipeline tools tuned to startup-studio workflows",
    tags: ["saas", "vertical"],
  },
  {
    id: "rfs-010",
    title: "Open-source agent observability",
    description: "Tracing, eval, and cost dashboards for agent runs",
    tags: ["ai-infra", "open-source"],
  },
]

export const initialDemoState = (): DemoState => {
  _idCounter = 0
  return {
    candidates: [],
    events: [],
    dossierTickets: [],
    ycScore: {
      precision: 0,
      recall: 0,
      direct_matches: 0,
      adjacent: 0,
      missed: YC_RFS_ITEMS.length,
      excess: 0,
      history: [],
      matches: [],
      revealed: false,
    },
    ycRevealed: false,
    fullReeval: false,
    briefCandidateId: null,
  }
}

const recomputeScore = (state: DemoState): YcScore => {
  const live = state.candidates.filter(
    (c) => c.status !== "killed" && c.status !== "merged_into",
  )
  const top10 = [...live]
    .sort((a, b) => b.v_hat * b.c_hat - a.v_hat * a.c_hat)
    .slice(0, 10)
  const direct = top10.filter((c) =>
    state.ycScore.matches.find(
      (m) => m.prediction_id === c.id && m.match_kind === "direct",
    ),
  ).length
  const adjacent = top10.filter((c) =>
    state.ycScore.matches.find(
      (m) => m.prediction_id === c.id && m.match_kind === "adjacent",
    ),
  ).length
  const excess = top10.filter((c) => c.ahead_of_yc).length
  const precision = top10.length === 0 ? 0 : direct / top10.length
  const recall = direct / YC_RFS_ITEMS.length
  return {
    ...state.ycScore,
    precision,
    recall,
    direct_matches: direct,
    adjacent,
    excess,
    missed: YC_RFS_ITEMS.length - direct,
    history: [
      ...state.ycScore.history,
      { ts: Date.now(), precision, recall },
    ].slice(-200),
  }
}

const addEvent = (
  state: DemoState,
  event: Omit<DiffEvent, "id" | "ts">,
): DemoState => ({
  ...state,
  events: [
    {
      id: nextId("evt"),
      ts: Date.now(),
      ...event,
    },
    ...state.events,
  ],
})

const addCandidate = (state: DemoState, candidate: Candidate): DemoState => {
  const next = {
    ...state,
    candidates: [...state.candidates, candidate],
  }
  return addEvent(next, {
    kind: "candidate_added",
    candidate_id: candidate.id,
    message: `+ ${candidate.statement.slice(0, 90)}…`,
  })
}

const updateCandidate = (
  state: DemoState,
  id: string,
  patch: Partial<Candidate>,
  event?: Omit<DiffEvent, "id" | "ts">,
): DemoState => {
  const next: DemoState = {
    ...state,
    candidates: state.candidates.map((c) =>
      c.id === id ? { ...c, ...patch } : c,
    ),
  }
  if (event) return addEvent(next, event)
  return next
}

export const DEMO_STAGES: DemoStage[] = [
  {
    key: "00-cold-start",
    label: "0:00 Cold start (YC history + CS/AI catalog)",
    narration:
      "Generic predictions, low confidence, no dossier badges. The system starts uncertain.",
    apply: (state) => {
      let s = state
      const seeds: Candidate[] = [
        {
          id: nextId("c"),
          statement:
            "Founders need a structured way to compare opportunity briefs across studios",
          lens: "cross_domain_transfer",
          status: "speculative",
          v_hat: 0.46,
          c_hat: 0.32,
          evidence_chunk_ids: ["chk-y1", "chk-y2"],
          source_count: 2,
          dossier_grounded: false,
          provenance_audited: false,
          pipeline_steps: ["Survey 5 studio partners", "Prototype brief schema"],
        },
        {
          id: nextId("c"),
          statement:
            "Vertical compliance copilots for sub-$50M SMBs are underbuilt",
          lens: "contradiction_surfacing",
          status: "speculative",
          v_hat: 0.51,
          c_hat: 0.28,
          evidence_chunk_ids: ["chk-y3"],
          source_count: 1,
          dossier_grounded: false,
          provenance_audited: false,
          pipeline_steps: ["Interview 10 SMB CFOs", "Compare 3 incumbent tools"],
        },
        {
          id: nextId("c"),
          statement:
            "Open-source agent observability is a missing dev-tools wedge",
          lens: "distance_from_focus",
          status: "speculative",
          v_hat: 0.49,
          c_hat: 0.34,
          evidence_chunk_ids: ["chk-y4"],
          source_count: 1,
          dossier_grounded: false,
          provenance_audited: false,
          pipeline_steps: ["Audit existing OSS observability", "Spec MVP"],
        },
        {
          id: nextId("c"),
          statement:
            "AI-native CRM tuned to startup-studio pipeline mechanics",
          lens: "cross_domain_transfer",
          status: "speculative",
          v_hat: 0.41,
          c_hat: 0.3,
          evidence_chunk_ids: ["chk-y5"],
          source_count: 1,
          dossier_grounded: false,
          provenance_audited: false,
          pipeline_steps: ["Map studio CRM workflow", "Build pipeline schema"],
        },
        {
          id: nextId("c"),
          statement:
            "Studios should run adversarial review on every opportunity brief",
          lens: "contradiction_surfacing",
          status: "speculative",
          v_hat: 0.39,
          c_hat: 0.27,
          evidence_chunk_ids: [],
          source_count: 0,
          dossier_grounded: false,
          provenance_audited: false,
          pipeline_steps: [
            "Build challenger persona library",
            "Run on 5 historical briefs",
          ],
        },
      ]
      for (const c of seeds) s = addCandidate(s, c)
      s = { ...s, ycScore: recomputeScore(s) }
      return s
    },
  },
  {
    key: "01-hn-drop",
    label: "0:30 HN top posts (last 90 days)",
    narration:
      "Board churns. Complaint-shaped opportunities appear: contradictions surface from messy user pain.",
    apply: (state) => {
      let s = state
      // Boost contradiction candidate, surface 3 new ones
      const cs1 = s.candidates.find((c) => c.lens === "contradiction_surfacing")
      if (cs1) {
        s = updateCandidate(
          s,
          cs1.id,
          {
            v_hat: 0.62,
            c_hat: 0.41,
            source_count: 5,
            evidence_chunk_ids: [...cs1.evidence_chunk_ids, "chk-hn1", "chk-hn2"],
          },
          {
            kind: "candidate_v_hat_updated",
            candidate_id: cs1.id,
            message: `↑ V̂ ${cs1.v_hat.toFixed(2)} → 0.62 (HN evidence)`,
            delta: { from: cs1.v_hat, to: 0.62 },
          },
        )
      }
      const newCandidates: Candidate[] = [
        {
          id: nextId("c"),
          statement:
            "Why does Stripe say 'AI is plug-and-play' while founders ship 6-month integrations?",
          lens: "contradiction_surfacing",
          status: "supported",
          v_hat: 0.71,
          c_hat: 0.47,
          evidence_chunk_ids: ["chk-hn3", "chk-hn4", "chk-hn5"],
          source_count: 4,
          dossier_grounded: false,
          provenance_audited: false,
          pipeline_steps: [
            "Talk to 10 founders shipping AI features",
            "Map integration time-to-value",
            "Compare to vendor claims",
          ],
        },
        {
          id: nextId("c"),
          statement:
            "Personal RAG over a knowledge worker's full document trail (private, not enterprise)",
          lens: "contradiction_surfacing",
          status: "supported",
          v_hat: 0.69,
          c_hat: 0.43,
          evidence_chunk_ids: ["chk-hn6", "chk-hn7"],
          source_count: 3,
          dossier_grounded: false,
          provenance_audited: false,
          pipeline_steps: [
            "Survey 20 knowledge workers",
            "Compare 3 personal-RAG attempts",
          ],
        },
        {
          id: nextId("c"),
          statement:
            "Voice-first ops for field workers — trades, logistics, last-mile",
          lens: "contradiction_surfacing",
          status: "supported",
          v_hat: 0.66,
          c_hat: 0.4,
          evidence_chunk_ids: ["chk-hn8", "chk-hn9"],
          source_count: 3,
          dossier_grounded: false,
          provenance_audited: false,
          pipeline_steps: [
            "Shadow 3 field crews",
            "Test voice-only journey for 2 trades",
          ],
        },
      ]
      for (const c of newCandidates) s = addCandidate(s, c)

      // Knock down a weak speculative candidate
      const weakOne = s.candidates.find(
        (c) => c.statement.startsWith("Studios should run adversarial"),
      )
      if (weakOne) {
        s = updateCandidate(s, weakOne.id, {
          v_hat: 0.31,
          c_hat: 0.21,
        })
      }
      s = { ...s, ycScore: recomputeScore(s) }
      return s
    },
  },
  {
    key: "02-arxiv-drop",
    label: "1:15 arXiv + Stratechery archives",
    narration:
      "Cross-domain transfer surfaces a structurally analogous candidate: 💡 chip pulses.",
    apply: (state) => {
      let s = state
      const cd: Candidate = {
        id: nextId("c"),
        statement:
          "Browser-native LLM agents with tab-level context — apply OS-level scheduler primitives to attention budgets",
        lens: "cross_domain_transfer",
        status: "supported",
        v_hat: 0.78,
        c_hat: 0.55,
        evidence_chunk_ids: [
          "chk-arx1",
          "chk-arx2",
          "chk-strat1",
          "chk-hn4",
        ],
        source_count: 6,
        dossier_grounded: false,
        provenance_audited: false,
        ahead_of_yc: false,
        pipeline_steps: [
          "Map current browser-agent architectures",
          "Spec a tab-context protocol",
          "Test on 3 vertical workflows",
        ],
      }
      s = addCandidate(s, cd)

      const cd2: Candidate = {
        id: nextId("c"),
        statement:
          "Real-time data quality for AI training — borrow stream-processing fault-tolerance from finance ETL",
        lens: "cross_domain_transfer",
        status: "supported",
        v_hat: 0.74,
        c_hat: 0.5,
        evidence_chunk_ids: ["chk-arx3", "chk-strat2"],
        source_count: 4,
        dossier_grounded: false,
        provenance_audited: false,
        pipeline_steps: [
          "Audit 5 training pipelines for silent corruption",
          "Adapt finance ETL guarantees",
        ],
      }
      s = addCandidate(s, cd2)
      s = { ...s, ycScore: recomputeScore(s) }
      return s
    },
  },
  {
    key: "03-dossier-queue",
    label: "1:20 Queue evidence dossier (Browser-native LLM agents)",
    narration:
      "High-V̂ candidate triggers an evidence_dossier CAR ticket. Side panel shows it pending.",
    apply: (state) => {
      const target = state.candidates.find((c) =>
        c.statement.includes("Browser-native LLM agents"),
      )
      if (!target) return state
      const ticket: DossierTicket = {
        ticket_id: `tkt_${target.id.replace(/-/g, "")}`,
        ticket_number: "TICKET-D-014",
        candidate_id: target.id,
        claim_summary: target.statement,
        status: "queued",
        queued_at: Date.now(),
      }
      const next = {
        ...state,
        dossierTickets: [...state.dossierTickets, ticket],
      }
      return addEvent(next, {
        kind: "dossier_queued",
        candidate_id: target.id,
        message: `📚 dossier queued — ${target.statement.slice(0, 60)}…`,
      })
    },
  },
  {
    key: "04-founder-transcripts",
    label: "1:45 Founder interview transcripts",
    narration:
      "Reinforced candidate emerges across multiple sources. Private corpus makes output more proprietary.",
    apply: (state) => {
      let s = state
      const target = s.candidates.find((c) =>
        c.statement.includes("Personal RAG"),
      )
      if (target) {
        s = updateCandidate(
          s,
          target.id,
          {
            v_hat: 0.81,
            c_hat: 0.58,
            source_count: 8,
            evidence_chunk_ids: [
              ...target.evidence_chunk_ids,
              "chk-tx1",
              "chk-tx2",
              "chk-tx3",
            ],
            reinforces: ["contradiction_surfacing", "distance_from_focus"],
          },
          {
            kind: "candidate_v_hat_updated",
            candidate_id: target.id,
            message: `↑ V̂ ${target.v_hat.toFixed(2)} → 0.81 (founder transcripts reinforce)`,
            delta: { from: target.v_hat, to: 0.81 },
          },
        )
      }

      const ticketTarget = s.dossierTickets[0]
      if (ticketTarget && ticketTarget.status === "queued") {
        s = {
          ...s,
          dossierTickets: s.dossierTickets.map((t) =>
            t.ticket_id === ticketTarget.ticket_id
              ? { ...t, status: "running", started_at: Date.now() }
              : t,
          ),
        }
        s = addEvent(s, {
          kind: "dossier_running",
          candidate_id: ticketTarget.candidate_id,
          message: "📚 dossier running — Hermes searching web/papers/forums",
        })
      }
      s = { ...s, ycScore: recomputeScore(s) }
      return s
    },
  },
  {
    key: "05-dossier-complete",
    label: "2:00 First dossier completes",
    narration:
      "Source badge appears; confidence jumps; graph evidence available. Deep research affects ranking.",
    apply: (state) => {
      let s = state
      const ticket = s.dossierTickets.find((t) => t.status === "running")
      if (!ticket) return s
      s = {
        ...s,
        dossierTickets: s.dossierTickets.map((t) =>
          t.ticket_id === ticket.ticket_id
            ? { ...t, status: "complete", completed_at: Date.now() }
            : t,
        ),
      }
      const target = s.candidates.find((c) => c.id === ticket.candidate_id)
      if (target) {
        s = updateCandidate(
          s,
          target.id,
          {
            v_hat: 0.91,
            c_hat: 0.78,
            source_count: target.source_count + 7,
            dossier_grounded: true,
            evidence_sources: [
              {
                title: "Browser agent runtime — design notes",
                kind: "paper",
                url: "https://arxiv.org/abs/2026.01234",
              },
              {
                title: "Why tab-context matters for agent attention budgets",
                kind: "blog",
                url: "https://stratechery.com/2026/tab-context",
              },
              {
                title: "Practitioner: shipped a browser agent in 6 weeks",
                kind: "forum",
                url: "https://news.ycombinator.com/item?id=987654",
              },
              {
                title: "Survey: knowledge-worker browser-tab habits",
                kind: "paper",
                url: "https://arxiv.org/abs/2026.05678",
              },
            ],
          },
          {
            kind: "dossier_complete",
            candidate_id: target.id,
            message: `📚 dossier complete · V̂ ${target.v_hat.toFixed(2)} → 0.91`,
            delta: { from: target.v_hat, to: 0.91 },
          },
        )
      }
      s = { ...s, ycScore: recomputeScore(s) }
      return s
    },
  },
  {
    key: "06-synthesizer-merge",
    label: "2:30 Synthesizer re-runs",
    narration:
      "Two candidates share evidence sources — they merge into one stronger prediction.",
    apply: (state) => {
      let s = state
      const personal = s.candidates.find((c) =>
        c.statement.includes("Personal RAG"),
      )
      const stripe = s.candidates.find((c) =>
        c.statement.includes("Stripe says 'AI is plug-and-play'"),
      )
      if (personal && stripe) {
        // Merge stripe contradiction into personal RAG (the stronger one)
        s = updateCandidate(
          s,
          personal.id,
          {
            statement:
              "Personal RAG over a knowledge worker's full document trail (private; addresses the 'AI is plug-and-play' contradiction founders ship around)",
            merged_from: [...(personal.merged_from ?? []), stripe.id],
            v_hat: 0.84,
            c_hat: 0.62,
            source_count: personal.source_count + stripe.source_count,
            evidence_chunk_ids: [
              ...personal.evidence_chunk_ids,
              ...stripe.evidence_chunk_ids,
            ],
          },
          {
            kind: "candidate_merged",
            candidate_id: personal.id,
            message: `⤲ merged 2 candidates (4 shared sources) → V̂ 0.84`,
          },
        )
        s = updateCandidate(s, stripe.id, { status: "merged_into" })
      }
      s = { ...s, ycScore: recomputeScore(s) }
      return s
    },
  },
  {
    key: "07-challenger-pass",
    label: "2:45 Challenger pass",
    narration:
      "Weak candidates are red-struck; one dossier-grounded candidate survives — challenged & held.",
    apply: (state) => {
      let s = state
      // Kill the weakest candidates
      const toKill = s.candidates.filter(
        (c) =>
          c.status !== "killed" &&
          c.status !== "merged_into" &&
          c.v_hat < 0.5 &&
          !c.dossier_grounded,
      )
      for (const k of toKill) {
        s = updateCandidate(
          s,
          k.id,
          { status: "killed", challenger_verdict: "red_struck" },
          {
            kind: "candidate_killed",
            candidate_id: k.id,
            message: `✗ killed — ${k.statement.slice(0, 60)}…`,
          },
        )
      }
      // Provenance failed for one (no evidence chunks)
      const provFail = s.candidates.find(
        (c) =>
          c.evidence_chunk_ids.length === 0 &&
          c.status !== "killed" &&
          c.status !== "merged_into",
      )
      if (provFail) {
        s = updateCandidate(
          s,
          provFail.id,
          {
            status: "killed",
            challenger_verdict: "provenance_failed",
          },
          {
            kind: "candidate_red_struck",
            candidate_id: provFail.id,
            message: `✗ provenance failed — claim has no source`,
          },
        )
      }
      // The dossier-grounded candidate is held
      const held = s.candidates.find(
        (c) => c.dossier_grounded && c.status !== "killed",
      )
      if (held) {
        s = updateCandidate(
          s,
          held.id,
          {
            challenger_verdict: "held",
            provenance_audited: true,
            status: "ready_to_validate",
          },
          {
            kind: "candidate_challenged_held",
            candidate_id: held.id,
            message: `✓ challenged & held — ${held.statement.slice(0, 50)}…`,
          },
        )
      }
      s = { ...s, ycScore: recomputeScore(s) }
      return s
    },
  },
  {
    key: "08-yc-reveal",
    label: "3:15 Reveal YC Summer 2026 RFS",
    narration:
      "Precision/recall curve improves across stages. The system can be evaluated.",
    apply: (state) => {
      let s = state
      // Build YC matches based on candidate statements (simulated)
      const live = s.candidates.filter(
        (c) => c.status !== "killed" && c.status !== "merged_into",
      )
      const matches = [
        // Direct matches
        ...live
          .filter((c) => c.statement.includes("Browser-native LLM agents"))
          .map((c) => ({
            prediction_id: c.id,
            rfs_item_id: "rfs-005",
            match_kind: "direct" as const,
            rationale: "Both target browser-native agents with local context",
          })),
        ...live
          .filter((c) => c.statement.includes("Personal RAG"))
          .map((c) => ({
            prediction_id: c.id,
            rfs_item_id: "rfs-007",
            match_kind: "direct" as const,
            rationale: "Both target private retrieval over personal docs",
          })),
        ...live
          .filter((c) => c.statement.includes("Real-time data quality"))
          .map((c) => ({
            prediction_id: c.id,
            rfs_item_id: "rfs-003",
            match_kind: "direct" as const,
            rationale: "Both target training-data quality at runtime",
          })),
        ...live
          .filter((c) =>
            c.statement.includes("Vertical compliance copilots"),
          )
          .map((c) => ({
            prediction_id: c.id,
            rfs_item_id: "rfs-002",
            match_kind: "direct" as const,
            rationale: "Both target SMB compliance",
          })),
        // Adjacent matches
        ...live
          .filter((c) => c.statement.includes("Voice-first ops"))
          .map((c) => ({
            prediction_id: c.id,
            rfs_item_id: "rfs-004",
            match_kind: "direct" as const,
            rationale: "Both target voice-first field-worker workflows",
          })),
        ...live
          .filter((c) =>
            c.statement.includes("Open-source agent observability"),
          )
          .map((c) => ({
            prediction_id: c.id,
            rfs_item_id: "rfs-010",
            match_kind: "direct" as const,
            rationale: "Both target agent observability tooling",
          })),
        ...live
          .filter((c) => c.statement.includes("AI-native CRM"))
          .map((c) => ({
            prediction_id: c.id,
            rfs_item_id: "rfs-009",
            match_kind: "adjacent" as const,
            rationale: "Adjacent to AI-native CRM for studios",
          })),
      ]
      s = {
        ...s,
        ycRevealed: true,
        ycScore: { ...s.ycScore, matches, revealed: true },
      }
      s = { ...s, ycScore: recomputeScore(s) }
      s = addEvent(s, {
        kind: "yc_revealed",
        message: `▣ YC Summer 2026 revealed · 6/10 direct, 1 adjacent`,
      })
      return s
    },
  },
  {
    key: "09-ahead-of-yc",
    label: "3:45 Highlight ahead-of-YC excess",
    narration:
      "Defensible non-overlap examples — excess can be leading indicator, not noise.",
    apply: (state) => {
      let s = state
      // Mark the founder-validated candidates ahead of YC
      const surviving = s.candidates.filter(
        (c) =>
          c.status !== "killed" &&
          c.status !== "merged_into" &&
          !s.ycScore.matches.find((m) => m.prediction_id === c.id),
      )
      for (const cand of surviving.slice(0, 2)) {
        s = updateCandidate(
          s,
          cand.id,
          { ahead_of_yc: true },
          {
            kind: "ahead_of_yc",
            candidate_id: cand.id,
            message: `🚀 ahead of YC — ${cand.statement.slice(0, 50)}…`,
          },
        )
      }
      s = { ...s, ycScore: recomputeScore(s) }
      return s
    },
  },
  {
    key: "10-open-brief",
    label: "4:00 Open opportunity brief",
    narration:
      "Problem, pain owner, evidence, contradictions, assumptions, validation steps. The paid artifact.",
    apply: (state) => {
      const target = state.candidates.find(
        (c) => c.dossier_grounded && c.status === "ready_to_validate",
      )
      if (!target) return state
      const enriched = {
        pain_owner:
          "Knowledge workers at studios + analyst-heavy firms (5–50 users), and the EIRs / venture analysts whose document trails are private and growing",
        why_now:
          "Browser agent runtimes shipped late 2025; on-device inference closed the latency gap; user habits have moved to tab-as-context (Stratechery 2026 archive).",
        contradictions: [
          "Vendors claim 'turn-key knowledge agents' while founders ship 6-month integrations",
          "Enterprise tools assume centralized doc stores — knowledge workers' docs span 10+ apps",
          "A 2026 arXiv survey shows 40% of knowledge workers explicitly distrust cloud-LLM products",
        ],
        open_assumptions: [
          "On-device retrieval can match cloud RAG quality within 18 months",
          "Users will share document trails with a private agent if local-only",
          "Tab-level context can be captured without breaking site privacy expectations",
        ],
        validation_path: [
          "Interview 10 analysts at studios about their personal doc trails",
          "Prototype a tab-context capture extension and ship to 20 alpha users",
          "Measure retrieval quality vs. centralized RAG on a fixed 100-doc corpus",
          "Kill if alpha users disable tab-capture > 50% of sessions",
        ],
      }
      const next = {
        ...state,
        candidates: state.candidates.map((c) =>
          c.id === target.id ? { ...c, ...enriched } : c,
        ),
        briefCandidateId: target.id,
      }
      return next
    },
  },
]

export const getYcRfsItems = () => YC_RFS_ITEMS

export function applyStage(state: DemoState, stage: DemoStage): DemoState {
  return stage.apply(state)
}
