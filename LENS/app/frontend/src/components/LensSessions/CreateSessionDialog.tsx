import { useState } from "react"
import { Loader2, Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface CreateSessionDialogProps {
  onCreate: (input: {
    title: string
    goal_query?: string
    description?: string
  }) => Promise<{ id: string }>
  loading?: boolean
}

export function CreateSessionDialog({ onCreate, loading }: CreateSessionDialogProps) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [goalQuery, setGoalQuery] = useState("")
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const reset = () => {
    setTitle("")
    setGoalQuery("")
    setDescription("")
    setErr(null)
  }

  const submit = async () => {
    if (!title.trim()) {
      setErr("title is required")
      return
    }
    setSubmitting(true)
    setErr(null)
    try {
      await onCreate({
        title: title.trim(),
        goal_query: goalQuery.trim() || undefined,
        description: description.trim() || undefined,
      })
      reset()
      setOpen(false)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v)
        if (!v) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" className="gap-1.5">
          <Plus className="size-4" />
          New session
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create session</DialogTitle>
          <DialogDescription>
            A session is the unit of investigation. You'll trigger discrete
            runs against it (seed, document upload, HN search, contradiction
            lens) and watch ideas evolve.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="session-title">Title</Label>
            <Input
              id="session-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. AI dev tooling — Q3 scan"
              disabled={submitting}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="session-goal">Goal query (optional)</Label>
            <Input
              id="session-goal"
              value={goalQuery}
              onChange={(e) => setGoalQuery(e.target.value)}
              placeholder="What signal area is this session investigating?"
              disabled={submitting}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="session-desc">Notes (optional)</Label>
            <Input
              id="session-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Free-form context for collaborators."
              disabled={submitting}
            />
          </div>
          {err && <p className="text-xs text-destructive">{err}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={submitting || loading}>
            {submitting ? <Loader2 className="size-4 animate-spin" /> : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
