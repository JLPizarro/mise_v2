import { RouterProvider } from "react-router-dom"
import VersionNueva from "@/pwa/VersionNueva"
import { router } from "@/router"

export default function App() {
  return (
    <>
      <VersionNueva />
      <RouterProvider router={router} />
    </>
  )
}
