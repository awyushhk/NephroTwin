import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/layout/AppShell";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Renal Risk Prediction System | KidneyCare AI",
  description:
    "Clinical decision-support research platform for Chronic Kidney Disease (CKD) risk screening and CT scan analysis.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full font-sans bg-slate-50 text-slate-900 flex flex-col">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
