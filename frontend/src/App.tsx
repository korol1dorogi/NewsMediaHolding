import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, type RouteObject, RouterProvider } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Portal } from "@/features/auth/Portal";
import { Login, RequireRole, SessionProvider } from "@/features/auth/session";
import { CardScreen } from "@/features/cases/CardScreen";
import { CaseLayout, CasesList, NewCase } from "@/features/cases/CaseLayout";
import { ClaimScreen } from "@/features/cases/ClaimScreen";
import { DialogScreen } from "@/features/cases/DialogScreen";
import { PathsScreen } from "@/features/cases/PathsScreen";
import { SpecialistScreen } from "@/features/cases/SpecialistScreen";
import {
  LawyerCaseScreen,
  LawyerCasesScreen,
  PoolCardScreen,
  PoolScreen,
} from "@/features/lawyer/PoolScreens";
import { QueueScreen, ReviewScreen } from "@/features/lawyer/ReviewScreens";
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
              { index: true, element: <CasesList /> },
              { path: "new", element: <NewCase /> },
              {
                path: "cases/:caseId",
                element: <CaseLayout />,
                children: [
                  { index: true, element: <DialogScreen /> },
                  { path: "card", element: <CardScreen /> },
                  { path: "paths", element: <PathsScreen /> },
                  { path: "claim", element: <ClaimScreen /> },
                  { path: "specialist", element: <SpecialistScreen /> },
                ],
              },
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
              { index: true, element: <QueueScreen /> },
              { path: "queue", element: <QueueScreen /> },
              { path: "queue/:claimId", element: <ReviewScreen /> },
              { path: "pool", element: <PoolScreen /> },
              { path: "pool/:cardId", element: <PoolCardScreen /> },
              { path: "cases", element: <LawyerCasesScreen /> },
              { path: "cases/:caseId", element: <LawyerCaseScreen /> },
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
