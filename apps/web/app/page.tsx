import { SplashAgentLoop } from "@/components/splash/agent-loop";
import { SplashApproach } from "@/components/splash/approach";
import { SplashArchitecture } from "@/components/splash/architecture";
import { SplashCta } from "@/components/splash/cta";
import { SplashDemoStatus } from "@/components/splash/demo-status";
import { SplashFrame } from "@/components/splash/frame";
import { SplashGuardrails } from "@/components/splash/guardrails";
import { SplashHero } from "@/components/splash/hero";
import { SplashProblem } from "@/components/splash/problem";
import { SplashReveal } from "@/components/splash/reveal";
import { SplashHeader } from "@/components/splash/splash-header";
import { SplashWorkedExample } from "@/components/splash/worked-example";

export default function Home() {
  return (
    <div className="min-h-dvh bg-canvas text-ink">
      <SplashHeader />
      <SplashFrame>
        <SplashHero />
      </SplashFrame>
      <main className="relative z-10 mx-auto flex max-w-6xl flex-col gap-20 px-4 py-16 pb-28">
        <SplashReveal>
          <SplashProblem />
        </SplashReveal>
        <SplashReveal>
          <SplashApproach />
        </SplashReveal>
        <SplashReveal>
          <SplashAgentLoop />
        </SplashReveal>
        <SplashReveal>
          <SplashArchitecture />
        </SplashReveal>
        <SplashReveal>
          <SplashWorkedExample />
        </SplashReveal>
        <SplashReveal>
          <SplashGuardrails />
        </SplashReveal>
        <SplashReveal>
          <SplashDemoStatus />
        </SplashReveal>
        <SplashReveal>
          <section className="space-y-4 border-t border-hairline/80 pt-12">
            <h2 className="text-heading font-extrabold">Open the workspace and run the same investigation.</h2>
            <p className="max-w-2xl text-body text-muted">
              Sign in, load a project snapshot, and ask to replace the station panel. The agent will cite the records.
              You still accept or reject the draft.
            </p>
            <SplashCta />
          </section>
        </SplashReveal>
      </main>
    </div>
  );
}
