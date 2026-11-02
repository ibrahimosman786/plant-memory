import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Plant Memory · Spartan Controls",
  description: "Agentic upgrade-assessment workspace for Spartan Controls. Reads plant records, drafts findings, scope, estimate, and tests. An engineer still reviews the draft.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full bg-canvas antialiased`}>
      <body className="min-h-full bg-canvas font-sans font-normal text-ink">
        <ClerkProvider
          appearance={{
            variables: {
              colorBackground: "#ffffff",
              colorForeground: "#183047",
              colorPrimary: "#005587",
              colorInput: "#f4f7fb",
              colorInputForeground: "#183047",
              colorMutedForeground: "#5b6d80",
              borderRadius: "0.5rem",
            },
          }}
        >
          <Providers>{children}</Providers>
        </ClerkProvider>
      </body>
    </html>
  );
}