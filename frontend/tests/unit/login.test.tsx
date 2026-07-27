import { render, screen } from "@testing-library/react";
import { vi, test, expect } from "vitest";
import LoginPage from "@/app/login/page";
vi.mock("next/navigation", () => ({useRouter: () => ({replace: vi.fn()})}));
test("renders administrator login", () => { render(<LoginPage />); expect(screen.getByRole("heading", {name:"관리자 로그인"})).toBeInTheDocument(); });
