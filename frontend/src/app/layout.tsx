import type { Metadata } from "next";
import "@/styles/globals.css";
export const metadata: Metadata = { title: "Swing Screener", description: "KOSPI swing trading decision support" };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="ko"><body>{children}</body></html>; }
