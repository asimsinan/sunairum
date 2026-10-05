import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { cookies, headers } from "next/headers";
import "./globals.css";
import AppShell from "@/components/AppShell";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Sunairum",
  description: "AI presentation studio — generate PPTX decks from templates",
  icons: {
    icon: [{ url: "/logo.png", type: "image/png" }],
    apple: [{ url: "/logo.png", type: "image/png" }],
  },
};

function resolveInitialLang(): "tr" | "en" {
  const cookieLang = cookies().get("ui_lang")?.value;
  if (cookieLang === "en" || cookieLang === "tr") return cookieLang;
  const acceptLang = headers().get("accept-language") || "";
  return acceptLang.toLowerCase().startsWith("en") ? "en" : "tr";
}

function resolveInitialTheme(): "light" | "dark" {
  return cookies().get("theme")?.value === "dark" ? "dark" : "light";
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const theme = resolveInitialTheme();
  return (
    <html lang="en" className={`${inter.className} ${theme === "dark" ? "dark" : ""}`}>
      <body className="bg-page text-fg min-h-screen">
        <AppShell initialLang={resolveInitialLang()}>{children}</AppShell>
      </body>
    </html>
  );
}
