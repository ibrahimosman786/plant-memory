import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["600", "800"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Plant Memory",
  description: "Evidence-linked engineering upgrade assessments for Spartan Controls.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full bg-canvas antialiased`}>
      <body className="min-h-full bg-canvas font-sans font-semibold text-ink">
        <ClerkProvider
          appearance={{
            variables: {
              colorBackground: "#2e3035",
              colorForeground: "#f0f2f5",
              colorPrimary: "#00b24b",
              colorInput: "#141415",
              colorInputForeground: "#f0f2f5",
              colorMutedForeground: "#9aa1b1",
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