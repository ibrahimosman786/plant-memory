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

const clerkAppearance = {
  variables: {
    colorBackground: "#ffffff",
    colorForeground: "#183047",
    colorPrimary: "#005587",
    colorInput: "#f4f7fb",
    colorInputForeground: "#183047",
    colorMutedForeground: "#5b6d80",
    borderRadius: "0.5rem",
  },
} as const;

export default function RootLayout({ children }: LayoutProps<"/">) {
  const tree = <Providers>{children}</Providers>;
  return (
    <html lang="en" className={`${inter.variable} h-full bg-canvas antialiased`}>
      <body className="min-h-full bg-canvas font-sans font-normal text-ink">
        {process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ? (
          <ClerkProvider appearance={clerkAppearance}>{tree}</ClerkProvider>
        ) : (
          tree
        )}
      </body>
    </html>
  );
}