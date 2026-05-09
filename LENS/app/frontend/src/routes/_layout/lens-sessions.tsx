import { createFileRoute, Outlet } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/lens-sessions")({
  component: LensSessionsLayout,
})

function LensSessionsLayout() {
  return <Outlet />
}
