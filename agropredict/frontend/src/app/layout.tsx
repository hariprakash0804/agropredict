import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#09090b",
};

export const metadata: Metadata = {
  title: "AgroPredict — Commodity Price Forecasting",
  description:
    "Production-grade agricultural commodity price forecasting for Indian markets. Powered by Chronos-2 foundation model with real-time AGMARKNET data.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased dark`}>
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-50 font-[family-name:var(--font-inter)] overflow-x-hidden w-full">
        {children}
      </body>
    </html>
  );
}
