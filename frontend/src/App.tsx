import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, type RouteObject, RouterProvider } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Placeholder, Portal } from "@/features/auth/Portal";
import { Login, RequireRole, SessionProvider } from "@/features/auth/session";
import { Home } from "@/routes/Home";
import { NotFound } from "@/routes/NotFound";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: (
      <SessionProvider>
        <Layout />
      </SessionProvider>
    ),
    children: [
      { index: true, element: <Home /> },
      { path: "login", element: <Login /> },
      {
        element: <RequireRole allowedRole="user" />,
        children: [
          {
            path: "user",
            element: <Portal allowedRole="user" />,
            children: [
              { index: true, element: <Placeholder /> },
              ...["dialog", "card", "paths", "claim", "offers"].map((path) => ({
                path,
                element: <Placeholder />,
              })),
            ],
          },
        ],
      },
      {
        element: <RequireRole allowedRole="lawyer" />,
        children: [
          {
            path: "lawyer",
            element: <Portal allowedRole="lawyer" />,
            children: [
              { index: true, element: <Placeholder /> },
              ...["queue", "pool", "cases"].map((path) => ({ path, element: <Placeholder /> })),
            ],
          },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
];
const router = createBrowserRouter(routes);
export function App({ queryClient = new QueryClient() }: { queryClient?: QueryClient }) {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
